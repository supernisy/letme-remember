"""第三审：内容变更类操作的审批提案（design D4）。

「哪些操作必须审批」写死在代码的分类表里，不由模型临时决定；
每类操作有单次数量上限。未确认的提案不改变真相源。
删除永远落实为「标记失效」，不物理删除文件。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from . import frontmatter, gitutil, index, store, validate
from .errors import NotFoundError, ValidationError

# 分类表：确定性操作脚本自动做；需要判断的操作必须出提案等人确认。
DETERMINISTIC = frozenset({
    "normalize_date", "adjust_weight", "add_link", "dedupe_exact", "categorize",
})
APPROVAL_REQUIRED = frozenset({
    "merge", "split", "supersede", "delete", "update_abstract",
})
MAX_PER_BATCH = {
    "merge": 5, "split": 3, "supersede": 5, "delete": 3, "update_abstract": 5,
}


def classify(operation):
    if operation in DETERMINISTIC:
        return "deterministic"
    if operation in APPROVAL_REQUIRED:
        return "approval"
    return "unknown"


def create(paths, operation, target, payload=None):
    if classify(operation) != "approval":
        raise ValidationError("该操作不是审批类操作，或未被分类表收录: %s" % operation)
    identifier = uuid.uuid4().hex[:12]
    data = {
        "id": identifier,
        "op": operation,
        "target": target,
        "payload": payload or {},
        "status": "pending",
        "created": datetime.now().astimezone().replace(microsecond=0).isoformat(),
    }
    paths.proposals.mkdir(parents=True, exist_ok=True)
    (paths.proposals / ("%s.json" % identifier)).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    gitutil.commit(paths.root, "proposal create %s (%s)" % (identifier, operation))
    return data


def create_batch(paths, items):
    """按操作类型截断到单次上限，超量部分不生成提案并如实报告。"""
    kept, truncated = [], []
    counters = {}
    for item in items:
        operation = item.get("op", "")
        if classify(operation) != "approval":
            raise ValidationError("未知操作类型: %s" % operation)
        limit = MAX_PER_BATCH[operation]
        counters[operation] = counters.get(operation, 0) + 1
        if counters[operation] > limit:
            truncated.append(item)
        else:
            kept.append(item)
    created = [create(paths, item["op"], item.get("target", ""), item.get("payload")) for item in kept]
    return {"created": len(created), "truncated": len(truncated), "items": created}


def list_proposals(paths):
    if not paths.proposals.is_dir():
        return []
    result = []
    for path in sorted(paths.proposals.glob("*.json")):
        try:
            result.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return result


def _find(paths, entry_id):
    for directory in (paths.store, paths.archive):
        candidate = directory / (entry_id + ".md")
        if candidate.is_file():
            return candidate
    raise NotFoundError("未找到记忆条目: %s" % entry_id)


def _raw_from_file(paths, entry_id):
    path = _find(paths, entry_id)
    meta, body = frontmatter.read_file(path)
    sections = frontmatter.body_sections(body)
    return {
        "name": meta["name"], "abstract": meta["abstract"], "type": meta["type"],
        "conclusion": sections["结论"], "reason": sections["理由"],
        "author": meta["author"], "weight": meta["weight"],
        "valid_from": meta["valid_from"], "created": meta["created"],
        "links": meta["links"], "provenance": meta["provenance"],
    }


def _apply_one(paths, settings, data):
    operation = data["op"]
    target = data["target"]
    payload = data["payload"]
    if operation == "delete":
        return store.invalidate(paths, settings, target)
    if operation == "supersede":
        return store.invalidate(paths, settings, target, superseded_by=payload.get("by"))
    if operation == "update_abstract":
        raw = _raw_from_file(paths, target)
        raw["abstract"] = payload.get("abstract", raw["abstract"])
        return store.record(paths, settings, raw)
    if operation == "merge":
        raw = _raw_from_file(paths, target)
        raw["abstract"] = payload.get("abstract", raw["abstract"])
        raw["conclusion"] = payload.get("conclusion", raw["conclusion"])
        raw["reason"] = payload.get("reason", raw["reason"])
        merged = store.record(paths, settings, raw)
        merged_id = merged["id"]
        for source in payload.get("from", []):
            store.invalidate(paths, settings, source, superseded_by=merged_id)
        return {"id": merged_id, "merged_from": payload.get("from", [])}
    if operation == "split":
        created = []
        for raw in payload.get("new", []):
            created.append(store.record(paths, settings, raw)["id"])
        if created:
            store.invalidate(paths, settings, target, superseded_by=created[0])
        return {"id": target, "split_into": created}
    raise ValidationError("未实现的操作: %s" % operation)


def apply(paths, settings, proposal_id):
    path = paths.proposals / ("%s.json" % proposal_id)
    if not path.is_file():
        raise NotFoundError("未找到提案: %s" % proposal_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "pending":
        raise ValidationError("提案不是待确认状态，不能重复应用")
    outcome = _apply_one(paths, settings, data)
    data["status"] = "applied"
    data["applied_at"] = datetime.now().astimezone().replace(microsecond=0).isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    idx = index.Index(paths, settings)
    idx.sync()
    idx.build_memory_md()
    gitutil.commit(paths.root, "proposal apply %s (%s)" % (proposal_id, data["op"]))
    return {"proposal": proposal_id, "op": data["op"], "result": outcome}
