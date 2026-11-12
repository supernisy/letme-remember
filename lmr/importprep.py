"""存量记忆的只读预处理（import-preprocessing/spec.md 的落地）。

把异构源文件逐条判定为三类，产出候选卡片（落在暂存区 staging）与
脱敏报告。这是「存量记忆安全进仓库」的前置闸门：

  - 格式合规可转  形状红线通过 + 字段完整 + 日期合法 + 类型可猜
  - 待裁决         形状合规但存在需人判断的信号（类型不定 / 疑似取代 / 合规边界）
  - 明确排除       日志流水、过程推演、重复备份、会话原文

判定 SHALL 只依据机器能确定性判断的形状/格式层信号，SHALL NOT 判定
「该结论现在是否成立」——那是人的事。因此本模块零 LLM、零网络。

卡片 ≠ 记忆：卡片只写 paths.staging/，SHALL NOT 进入 store/archive、
索引文件与检索结果。人确认后的卡片才走与常规写入相同的三审。

报告脱敏：只记数量、来源类别、命中规则编号、缺失字段，SHALL NOT 记
正文、命中处原值或凭据形状原值。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import frontmatter, redaction, schema, validate

# 三类判定结果。
VERDICT_OK = "ok"            # 格式合规可转
VERDICT_REVIEW = "review"    # 待裁决
VERDICT_EXCLUDE = "exclude"  # 明确排除

# 明确排除的启发式来源类别。预处理只做机器能确定性判断的事，
# 日志/过程/备份/会话原文这些「流水」按来源类别优先识别为排除。
EXCLUDE_SOURCE_CATEGORIES = frozenset({
    "log", "logs", "session", "sessions", "daily-log", "changelog",
    "backup", "backups", "transcript", "chat", "chat-log",
})

# 正文里出现的「过程流水」标记：命中即视为过程推演 / 会话原文。
# 这些是形状层信号，不是语义判断。
_PROCESS_MARKERS = (
    "今天下午", "本次会话", "接下来", "TODO", "FIXME", "待办",
    "推演", "过程记录", "会话记录", "日志流水",
)

# 明确排除：正文无「结论」「理由」两节的碎片（流水）。
# 疑似取代 / 待裁决：正文出现「取代」「作废」「已过时」等信号，
# 或类型无法确定。
_SUPERSEDE_MARKERS = ("取代", "作废", "过时", "推翻", "superseded", "invalid")

# 来源类别 → 默认类型猜测，命中合规边界时归「待裁决」。
_CATEGORY_TYPE_HINT = {
    "profile": "profile",
    "preference": "preference",
    "entity": "entity",
    "event": "event",
    "decision": "decision",
    "procedure": "procedure",
    "fact": "fact",
    "experience": "experience",
    "reference": "reference",
    "rule": "procedure",
    "rule-file": "procedure",
    "identity": "profile",
    "process-doc": "procedure",
    "job": "experience",
    "job-review": "reference",
}


def content_hash(text: str) -> str:
    """内容哈希（sha256）作幂等键：同源重复预处理据此跳过。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_frontmatter_open(lines: list[str], idx: int) -> bool:
    """判断第 idx 行是否为 frontmatter 起始分隔线（而非 Markdown 水平线）。

    frontmatter 起始 `---` 之后的下一个非空行必须是合法字段行（key: value，
    key 属 frontmatter.FIELDS 白名单）；否则视为 Markdown 水平线。
    """
    for j in range(idx + 1, len(lines)):
        ln = lines[j].strip()
        if not ln:
            continue
        # 下一非空行必须形如「key: value」，且 key 是已知字段。
        if ":" not in ln:
            return False
        key = ln.split(":", 1)[0].strip()
        return key in frontmatter.FIELDS
    return False


def _split_entries(text: str) -> list[str]:
    """把源文本按条目切分。

    一个源文件通常是「一条记忆」（含 frontmatter + 结论/理由正文）。
    当文件里连续出现多个完整 frontmatter 块时，按「--- ... ---」边界
    切分成多条。无 frontmatter（或只有 Markdown 水平线）时整段作为一条
    （交给判定层处理）。水平线 `---` 后跟正文/标题而非字段行，不参与切分。
    """
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")

    # 找出所有「合法 frontmatter 起始」的行号。
    open_idx = [i for i, ln in enumerate(lines)
                if ln.strip() == "---" and _is_frontmatter_open(lines, i)]
    if not open_idx:
        return [normalized]

    # 找每个起始对应的闭头（块内第二个 ---）。
    chunks: list[str] = []
    for i, block_start in enumerate(open_idx):
        # 闭头：block_start 之后的第一个独立成行 ---。
        block_end = None
        for j in range(block_start + 1, len(lines)):
            if lines[j].strip() == "---":
                block_end = j
                break
        if block_end is None:
            # 无闭头，不算合法块，整段留到文件尾由判定层处理。
            continue
        # 正文吞到下一个合法 frontmatter 起始（若存在），否则到文件尾。
        next_start = open_idx[i + 1] if i + 1 < len(open_idx) else len(lines)
        chunks.append("\n".join(lines[block_start:next_start]))

    if not chunks:
        return [normalized]
    return [c for c in chunks if c.strip()]


def _guess_type(meta: dict, body: str, source_category: str) -> str | None:
    """猜测类型：优先 frontmatter type，其次来源类别映射，最后正文启发。"""
    declared = (meta.get("type") or "").strip()
    if declared and declared in schema.TYPES:
        return declared
    if source_category in _CATEGORY_TYPE_HINT:
        return _CATEGORY_TYPE_HINT[source_category]
    # 正文出现「教训/症状/原因/修复」→ experience；「选择/决定」→ decision。
    lowered = body
    if any(k in lowered for k in ("症状", "原因", "修复", "教训")):
        return "experience"
    if any(k in lowered for k in ("选择", "决定", "拍板")):
        return "decision"
    return None


def _verdict_for(text: str, source_category: str) -> tuple[str, dict]:
    """对单条源内容做三类判定，返回 (判定, 详情)。详情只含元信息，不含原值。"""
    detail = {"missing_fields": [], "rule": None, "needs_human": []}

    # 1) 明确排除：来源类别是流水类，或正文命中过程标记。
    if source_category in EXCLUDE_SOURCE_CATEGORIES:
        detail["rule"] = "exclude:source-category"
        return VERDICT_EXCLUDE, detail
    if any(marker in text for marker in _PROCESS_MARKERS):
        detail["rule"] = "exclude:process-marker"
        return VERDICT_EXCLUDE, detail

    # 2) 尝试解析文件头；解析失败即无 frontmatter。
    #    此时查正文是否含「结论+理由」两节：
    #    有 → 待裁决（有价值但缺形状，提示补 frontmatter）；
    #    无 → 明确排除（碎片）。
    try:
        meta, body = frontmatter.parse(text)
    except Exception:
        sections = frontmatter.body_sections(text)
        if sections["结论"] and sections["理由"]:
            detail["rule"] = "review:missing-frontmatter"
            detail["needs_human"].append("missing-frontmatter")
            return VERDICT_REVIEW, detail
        detail["rule"] = "exclude:no-frontmatter"
        return VERDICT_EXCLUDE, detail

    # 3) 形状红线：正文必须有「结论」「理由」两节，否则是流水碎片。
    sections = frontmatter.body_sections(body)
    if not sections["结论"] or not sections["理由"]:
        detail["rule"] = "exclude:no-conclusion-reason"
        detail["missing_fields"].append("conclusion/reason")
        return VERDICT_EXCLUDE, detail

    # 4) 字段完整性 + 日期合法性：缺失必填字段或日期非法 → 待裁决。
    errors = validate.validate_meta(meta, body)
    if errors:
        detail["rule"] = "review:validation"
        for message in errors:
            detail["missing_fields"].append(message)
        return VERDICT_REVIEW, detail

    # 5) 类型可猜 + 疑似取代信号。
    guessed = _guess_type(meta, body, source_category)
    if guessed is None:
        detail["needs_human"].append("type-unknown")
    if guessed and guessed not in schema.TYPES:
        guessed = None
        detail["needs_human"].append("type-unknown")

    superseded = meta.get("superseded_by") or any(
        marker in body for marker in _SUPERSEDE_MARKERS)
    if superseded:
        detail["needs_human"].append("possible-supersede")

    # 命中合规边界（A/B 类凭据形状）→ 待裁决，需人确认是否放行。
    findings = redaction.scan(text)
    a_b = [h for h in findings if h["class"] in ("A", "B")]
    if a_b:
        detail["needs_human"].append("credential-shape")
        detail["rule"] = "review:credential-shape"
        return VERDICT_REVIEW, detail

    # 6) 需人判断的信号 → 待裁决；否则格式合规可转。
    if detail["needs_human"]:
        detail["rule"] = "review:needs-human"
        return VERDICT_REVIEW, detail

    detail["rule"] = "ok"
    return VERDICT_OK, detail


def preprocess(source, source_category: str, batch: str = "") -> dict:
    """扫描单个源文件，产出候选卡片（写 staging）与脱敏报告。

    source 可为 str 路径或 Path。源文件始终只读；卡片按内容哈希幂等，
    已存在的卡片（同哈希）不重复生成。
    """
    source = Path(source)
    text = source.read_text(encoding="utf-8", errors="ignore")
    digest = content_hash(text)

    entries = _split_entries(text)
    cards = []
    report_rows = []
    for entry in entries:
        entry_text = entry.strip()
        if not entry_text:
            continue
        verdict, detail = _verdict_for(entry_text, source_category)
        row = {
            "source": source.name,
            "source_category": source_category,
            "content_hash": content_hash(entry_text),
            "verdict": verdict,
            "rule": detail["rule"],
            "missing_fields": detail["missing_fields"],
            "needs_human": detail["needs_human"],
        }
        report_rows.append(row)
        # 只有「格式合规可转」才产出卡片；待裁决/排除只进报告。
        if verdict == VERDICT_OK:
            cards.append({
                "content_hash": content_hash(entry_text),
                "source": source.name,
                "source_category": source_category,
                "batch": batch,
                "verdict": verdict,
                "text": entry_text,  # 卡片内容只在私有 staging 内，不进公开仓库
            })

    return {
        "source": source.name,
        "source_content_hash": digest,
        "total_entries": len(report_rows),
        "cards": cards,
        "report": report_rows,
    }


def write_cards(paths, cards: list[dict]) -> list[dict]:
    """把候选卡片写进暂存区，按内容哈希幂等去重。

    返回实际写入的卡片元信息（不含正文）；已存在的同哈希卡片跳过。
    """
    staging = paths.staging
    staging.mkdir(parents=True, exist_ok=True)
    written = []
    for card in cards:
        digest = card["content_hash"]
        target = staging / ("card-%s.json" % digest)
        if target.is_file():
            continue  # 幂等：已存在则跳过
        payload = {
            "content_hash": digest,
            "source": card["source"],
            "source_category": card["source_category"],
            "batch": card["batch"],
            "verdict": card["verdict"],
            "text": card["text"],
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append({
            "content_hash": digest,
            "source": card["source"],
            "card_file": target.name,
        })
    return written


def build_report(preprocess_result: dict) -> dict:
    """从预处理结果生成脱敏报告：只记数量、来源类别、命中规则编号、缺失字段。"""
    rows = preprocess_result["report"]
    counts = {
        "ok": 0,
        "review": 0,
        "exclude": 0,
    }
    rule_hits: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
        rule = row["rule"]
        if rule:
            rule_hits[rule] = rule_hits.get(rule, 0) + 1
    return {
        "source": preprocess_result["source"],
        "source_category": None,  # 由调用方回填，避免重复
        "total": preprocess_result["total_entries"],
        "verdict_counts": counts,
        "rule_hits": rule_hits,
        # 缺失字段只记字段名/错误描述，不记正文或原值。
        "missing_fields_summary": _summarize_missing(rows),
    }


def _summarize_missing(rows: list[dict]) -> list[str]:
    """汇总缺失字段名（去重），绝不携带原值。"""
    seen: list[str] = []
    for row in rows:
        for field in row.get("missing_fields", []):
            if field not in seen:
                seen.append(field)
    return seen


def run(paths, sources, source_category: str = "", batch: str = "") -> dict:
    """预处理入口：扫描多个源，产出卡片（写 staging）+ 脱敏报告。

    返回结构只含数量、来源类别、规则编号与缺失字段，SHALL NOT 含正文。
    """
    all_cards = []
    all_reports = []
    for src in sources:
        result = preprocess(src, source_category, batch)
        all_cards.extend(result["cards"])
        all_reports.append(build_report(result))

    written = write_cards(paths, all_cards)

    # 汇总报告：只记数量与元信息。
    verdict_counts = {"ok": 0, "review": 0, "exclude": 0}
    rule_hits: dict[str, int] = {}
    missing: list[str] = []
    for rep in all_reports:
        for k, v in rep["verdict_counts"].items():
            verdict_counts[k] = verdict_counts.get(k, 0) + v
        for rule, n in rep["rule_hits"].items():
            rule_hits[rule] = rule_hits.get(rule, 0) + n
        for field in rep["missing_fields_summary"]:
            if field not in missing:
                missing.append(field)

    return {
        "source_category": source_category,
        "batch": batch,
        "sources_scanned": len(sources),
        "total_entries": sum(r["total"] for r in all_reports),
        "verdict_counts": verdict_counts,
        "rule_hits": rule_hits,
        "missing_fields": missing,
        "cards_written": len(written),
        "cards_skipped_duplicate": len(all_cards) - len(written),
        "card_files": [w["card_file"] for w in written],
    }
