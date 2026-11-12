"""待审队列：蒸馏候选（L1/L2）的异步入库审批（approval-queue/spec.md 落地）。

与 proposal.py 的区别：proposal.py 审批的是「对已有记忆的内容变更操作」
（merge/split/supersede/delete/purge），本模块审批的是「蒸馏产出的新候选
是否入库」——两者都走 proposals/ 目录，但用 queue- 前缀区分。

不变式（硬约束）：
- 待审候选绝不自动执行；只有 approve 才走 store.record 完整写入链。
- 批准入库不绕过安全闸门：仍经过第一审脚本校验 + 密钥形状红线。
- 用户不表态不丢弃；超时降级到 archive 冷存储，保留完整内容可恢复。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from . import gitutil, index, store
from .errors import NotFoundError, ValidationError

# 候选入库需要保留的字段（其余元数据不进真相源）。
CANDIDATE_FIELDS = (
    "name", "abstract", "type", "conclusion", "reason", "author",
    "weight", "valid_from", "created", "invalid_at", "superseded_by",
    "source_category", "original_date", "batch",
)

# 超时降级默认时限（天）。
DEFAULT_TIMEOUT_DAYS = 7


def _now():
    return datetime.now().astimezone().replace(microsecond=0)


def _queue_path(paths, entry_id):
    return paths.proposals / ("queue-%s.json" % entry_id)


def _archive_path(paths, entry_id):
    return paths.archive / ("queue-%s.json" % entry_id)


def _audit(paths, action, entry_id, level=""):
    stamp = gitutil.now_iso()
    with paths.audit.open("a", encoding="utf-8") as handle:
        handle.write("%s\tqueue-%s\t%s\t%s\n" % (stamp, action, entry_id, level))


def enqueue(paths, settings, candidate, level):
    """把一条 L1/L2 候选写入待审队列（状态 pending），不碰真相源。

    level 必须是 "L1" 或 "L2"；L0 不该进队列（应直接 store.record）。
    """
    if level not in ("L1", "L2"):
        raise ValidationError("待审队列只接受 L1/L2 候选，收到: %s" % level)
    cleaned = {k: candidate.get(k) for k in CANDIDATE_FIELDS if candidate.get(k) is not None}
    if not cleaned.get("conclusion"):
        raise ValidationError("候选缺少 conclusion，无法入库: %s" % (candidate.get("name", "")))
    entry_id = uuid.uuid4().hex[:12]
    data = {
        "id": entry_id,
        "level": level,
        "candidate": cleaned,
        "status": "pending",
        "created": _now().isoformat(),
    }
    paths.proposals.mkdir(parents=True, exist_ok=True)
    _queue_path(paths, entry_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _audit(paths, "enqueue", entry_id, level)
    gitutil.commit(paths.root, "queue enqueue %s (%s)" % (entry_id, level))
    return data


def list_pending(paths):
    """列出所有 pending 待审候选（不含已处理/已过期）。"""
    if not paths.proposals.is_dir():
        return []
    result = []
    for path in sorted(paths.proposals.glob("queue-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("status") == "pending":
            result.append(data)
    return result


def _load(paths, entry_id, expect_pending=True):
    path = _queue_path(paths, entry_id)
    if not path.is_file():
        raise NotFoundError("未找到待审候选: %s" % entry_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if expect_pending and data.get("status") != "pending":
        raise ValidationError("候选不是待审状态，不能重复处理: %s" % entry_id)
    return data, path


def approve(paths, settings, entry_id):
    """批准一条待审候选，走完整写入链入库（含脚本红线 + 分级裁决）。"""
    data, path = _load(paths, entry_id)
    outcome = store.record(paths, settings, data["candidate"])
    data["status"] = "approved"
    data["approved_at"] = _now().isoformat()
    data["result"] = outcome
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _audit(paths, "approve", entry_id, data.get("level", ""))
    gitutil.commit(paths.root, "queue approve %s" % entry_id)
    return {"id": entry_id, "result": outcome}


def reject(paths, entry_id):
    """驳回一条待审候选：从队列移除，不写入真相源。"""
    data, path = _load(paths, entry_id)
    data["status"] = "rejected"
    data["rejected_at"] = _now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _audit(paths, "reject", entry_id, data.get("level", ""))
    gitutil.commit(paths.root, "queue reject %s" % entry_id)
    return {"id": entry_id, "status": "rejected"}


def expire(paths, timeout_days=DEFAULT_TIMEOUT_DAYS):
    """超时降级：pending 超过时限的候选移至 archive 冷存储，保留完整内容。

    不静默丢弃：数据完整保留在 archive，用户随时可恢复（改回 pending 重新 approve）。
    """
    deadline = _now() - timedelta(days=timeout_days)
    expired = []
    for data in list_pending(paths):
        created = data.get("created", "")
        try:
            dt = datetime.fromisoformat(created)
        except ValueError:
            continue
        if dt <= deadline:
            entry_id = data["id"]
            data["status"] = "expired"
            data["expired_at"] = _now().isoformat()
            paths.archive.mkdir(parents=True, exist_ok=True)
            _archive_path(paths, entry_id).write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            _queue_path(paths, entry_id).unlink()
            _audit(paths, "expire", entry_id, data.get("level", ""))
            expired.append(entry_id)
    if expired:
        gitutil.commit(paths.root, "queue expire %d items" % len(expired))
    return {"expired": expired}
