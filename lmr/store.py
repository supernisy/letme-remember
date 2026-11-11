"""写入链（design D4 / D5 / D11）与真相源读写。

一条候选记忆：redact（第一审红线）-> validate（第一审校验）-> 落盘
-> 私有 git 提交 -> 增量索引。校验失败时一个字节都不写。
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from . import config, frontmatter, gitutil, index, redaction, schema, validate
from .errors import NotFoundError, ValidationError

SAMPLE_MEMORY = """---
name: preference-示例-文本笔记
abstract: 虚构示例：偏好用纯文本记录笔记
type: preference
created: 2026-01-01T00:00:00+00:00
updated: 2026-01-01T00:00:00+00:00
valid_from: 2026-01-01
invalid_at:
superseded_by:
weight: 1.0
author: sample
links:
provenance:
---

## 结论

（虚构示例）整理笔记时偏好使用纯文本文件。

## 理由

（虚构示例）纯文本便于检索与版本管理；本条只用于演示文件格式，不代表任何真实偏好。
"""


def init_data_dir(data_dir, sample=True):
    """初始化数据目录、私有 git 与用户级配置模板。"""
    import json

    paths = config.Paths(data_dir)
    for directory in paths.all_dirs():
        directory.mkdir(parents=True, exist_ok=True)
    if not paths.config.is_file():
        config_payload = {
            "data_dir": str(paths.root),
            "redact_b_class": False,
            "injection_budget_bytes": 8192,
        }
        paths.config.write_text(
            json.dumps(config_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    # 只让「真相源文件」进私有 git。派生产物不入库有两个理由：
    # 1) 索引与目录可随时从真相源重建，不是知识；
    # 2) 若每条写入都改同一份共享文件，revert 早期批次提交会反复冲突，
    #    整批撤销就不可靠。审计信息由 git log 与提交信息承载。
    gitignore = paths.root / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text(
            ".index/\nstaging/\nMEMORY.md\naudit.log\n", encoding="utf-8"
        )
    gitutil.ensure_repo(paths.root)
    if sample and not any(paths.store.glob("*.md")):
        (paths.store / schema.filename_for("preference", "preference-示例-文本笔记")).write_text(
            SAMPLE_MEMORY, encoding="utf-8"
        )
    idx = index.Index(paths, config.settings_for(paths.root))
    idx.sync(force=True)
    idx.build_memory_md()
    gitutil.commit(paths.root, "init: 初始化私有记忆数据目录（含虚构示例）")
    # 环境变量常用于临时数据目录（测试），不要把临时路径固化进用户级配置。
    if not config.USER_CONFIG_PATH.is_file() and not os.environ.get(config.ENV_DATA_DIR):
        config.write_user_config(paths.root)
    return paths


def _now():
    return datetime.now().astimezone().replace(microsecond=0)


def build_candidate(raw):
    """把宿主提交的候选字典组装成 (meta, body)，不改变任何磁盘状态。"""
    now = _now()
    today = now.date().isoformat()
    meta = frontmatter.empty_meta()
    source_category = str(raw.get("source_category") or "").strip()
    original_date = str(raw.get("original_date") or "").strip()
    batch = str(raw.get("batch") or "").strip()
    importing = bool(source_category or original_date or batch)

    if importing:
        if not (source_category and original_date and batch):
            raise ValidationError("导入条目必须同时提供 source_category、original_date、batch")
        meta["author"] = "import:%s" % source_category
        meta["valid_from"] = original_date
        meta["provenance"] = [source_category, original_date, batch]
    else:
        meta["author"] = str(raw.get("author") or "human").strip()
        meta["valid_from"] = str(raw.get("valid_from") or today).strip()
        provenance = raw.get("provenance") or []
        meta["provenance"] = [str(item) for item in provenance]

    name = str(raw.get("name") or "").strip()
    if not name and raw.get("key"):
        name = schema.derive_name(str(raw.get("type") or ""), [raw.get("key")])
    meta["name"] = name
    meta["abstract"] = str(raw.get("abstract") or "").strip()
    meta["type"] = str(raw.get("type") or "").strip()
    meta["created"] = str(raw.get("created") or now.isoformat()).strip()
    meta["updated"] = now.isoformat()
    meta["weight"] = str(raw.get("weight") if raw.get("weight") is not None else "1.0").strip()
    meta["links"] = [str(item) for item in (raw.get("links") or [])]
    meta["invalid_at"] = str(raw.get("invalid_at") or "").strip()
    meta["superseded_by"] = str(raw.get("superseded_by") or "").strip()
    body = frontmatter.make_body(raw.get("conclusion") or "", raw.get("reason") or "")
    return meta, body


def prepare(raw, settings=None, rules=None, extra_allowlist=()):
    """纯函数：打码 + 校验。用于批量预校验，绝不写文件。"""
    settings = settings or {}
    cleaned = {}
    all_findings = []
    for key in ("name", "abstract", "conclusion", "reason"):
        value = str(raw.get(key) or "")
        masked, findings = redaction.redact(value, settings, rules, extra_allowlist)
        cleaned[key] = masked
        all_findings.extend(findings)
    merged = dict(raw)
    merged.update(cleaned)
    for key in ("links", "provenance"):
        items = []
        for item in (raw.get(key) or []):
            masked, findings = redaction.redact(str(item), settings, rules, extra_allowlist)
            items.append(masked)
            all_findings.extend(findings)
        merged[key] = items
    meta, body = build_candidate(merged)
    errors = validate.validate_meta(meta, body)
    return {"meta": meta, "body": body, "errors": errors, "findings": all_findings, "raw": merged}


def prevalidate(candidates, settings=None):
    """批量原子预校验：任一候选非法则整批拒绝，零文件写出。"""
    prepared = [prepare(item, settings) for item in candidates]
    errors = []
    for number, item in enumerate(prepared, 1):
        for message in item["errors"]:
            errors.append("候选 %d: %s" % (number, message))
    if errors:
        raise ValidationError("；".join(errors))
    return prepared


def _find_file(paths, entry_id):
    for directory in (paths.store, paths.archive):
        candidate = directory / (entry_id + ".md")
        if candidate.is_file():
            return candidate
    raise NotFoundError("未找到记忆条目: %s" % entry_id)


def _sync_only(paths, settings):
    """只重建派生产物，不提交。调用方负责把真相源与派生产物放进同一条提交。"""
    idx = index.Index(paths, settings)
    stats = idx.sync()
    index_info = idx.build_memory_md()
    return {"index": stats, "memory_index": index_info}


def record(paths, settings, raw):
    """写入一条候选；返回定位标识、审计命中与提交号。

    导入语义只由候选自身的 source_category / original_date / batch 三字段决定，
    不另设旁路参数，避免「批次写入」绕过常规校验。
    """
    prepared = prevalidate([raw], settings)[0]
    meta, body = prepared["meta"], prepared["body"]
    filename = schema.filename_for(meta["type"], meta["name"])
    path = paths.store / filename
    if path.is_file():
        old, _ = frontmatter.read_file(path)
        meta["created"] = old["created"]
    frontmatter.write_file(path, meta, body)
    _append_audit(paths, "record", schema.entry_id(filename), prepared["findings"])
    extra = _sync_only(paths, settings)
    batch_tag = ""
    if meta["author"].startswith("import:") and len(meta["provenance"]) == 3:
        batch_tag = " batch:%s" % meta["provenance"][2]
    # 真相源 + 审计 + 索引目录进同一条提交，HEAD 就是这次写入，撤销才撤得准。
    commit = gitutil.commit(paths.root, "record %s%s" % (schema.entry_id(filename), batch_tag))
    return {
        "id": schema.entry_id(filename),
        "path": str(path),
        "commit": commit,
        "findings": prepared["findings"],
        "details": extra,
    }


def _append_audit(paths, action, entry_id, findings):
    """审计只记操作、时间、条目与规则编号，绝不记录命中处的原值。"""
    lines = redaction.audit_lines(findings)
    stamp = gitutil.now_iso()
    with paths.audit.open("a", encoding="utf-8") as handle:
        handle.write("%s\t%s\t%s\t%s\n" % (stamp, action, entry_id, ",".join(lines)))


def show(paths, entry_id):
    path = _find_file(paths, entry_id)
    return path.read_text(encoding="utf-8")


def list_entries(paths):
    if not paths.memory_md.is_file():
        return ""
    return paths.memory_md.read_text(encoding="utf-8")


def invalidate(paths, settings, entry_id, superseded_by=None, invalid_at=None):
    path = _find_file(paths, entry_id)
    meta, body = frontmatter.read_file(path)
    meta["invalid_at"] = invalid_at or _now().date().isoformat()
    meta["updated"] = _now().isoformat()
    if superseded_by:
        meta["superseded_by"] = superseded_by
    validate.assert_valid(meta, body)
    frontmatter.write_file(path, meta, body)
    _append_audit(paths, "invalidate", entry_id, [])
    _sync_only(paths, settings)
    commit = gitutil.commit(paths.root, "invalidate %s" % entry_id)
    return {"id": entry_id, "invalid_at": meta["invalid_at"], "path": str(path), "commit": commit}


def archive(paths, settings, entry_id):
    path = _find_file(paths, entry_id)
    if path.parent == paths.archive:
        return {"id": entry_id, "archived": True}
    target = paths.archive / path.name
    shutil.move(str(path), str(target))
    _sync_only(paths, settings)
    gitutil.commit(paths.root, "archive %s" % entry_id)
    return {"id": entry_id, "archived": True, "path": str(target)}


def purge(paths, settings, entry_id, reason=""):
    """真正删除一条错误/无效记忆（与 invalidate 的软失效相对）。

    用于「明显错误、纯属虚构、测试残留」的记忆，而非「曾正确后过时」的结论。
    不可逆：物理移除文件 + 审计留痕 + 提交。调用方 MUST 先走审批（L2）。
    """
    path = _find_file(paths, entry_id)
    if path.parent == paths.archive:
        # 若已在归档目录，直接删除归档里的文件。
        pass
    os.remove(str(path))
    _append_audit(paths, "purge", entry_id, [])
    if reason:
        with paths.audit.open("a", encoding="utf-8") as handle:
            handle.write("%s\tpurge-reason\t%s\t%s\n" % (gitutil.now_iso(), entry_id, reason))
    _sync_only(paths, settings)
    gitutil.commit(paths.root, "purge %s" % entry_id)
    return {"id": entry_id, "purged": True, "reason": reason}


def undo(paths, settings):
    count = gitutil.undo_last(paths.root)
    _sync_only(paths, settings)
    gitutil.commit(paths.root, "index: 撤销后同步索引与目录")
    return {"reverted": count}


def undo_batch(paths, settings, batch):
    count = gitutil.undo_batch(paths.root, batch)
    _sync_only(paths, settings)
    gitutil.commit(paths.root, "index: 批次撤销后同步索引与目录")
    return {"batch": batch, "reverted": count}


def entry_count(paths):
    return len(list(paths.store.glob("*.md")))
