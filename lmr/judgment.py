"""大模型软判断（第二审）与分级裁决（v1.1）。

职责边界（write-approval spec）：
- LLM 只产出「结构化体检报告」，不落库、不裁决；
- 代码按固定阈值把报告映射为 L0 / L1 / L2，绝不因接 LLM 而让模型自行拍板；
- LLM 不可用时由上层走降级路径（规则报告）。

体检报告字段（六触发器 + 补充维度）：
  conflict / high_impact / ambiguous / novel_type / compliance / uncertain
  + importance / confidence / missing

v1.1 冲突检测增强（#10）：
  conflict 字段升级为「冲突对象 + 建议操作」，显式判定
  ADD / UPDATE / SUPERSEDE / NOOP，与时间轴（invalid_at / superseded_by）联动。
"""

from __future__ import annotations

import json
import re

from . import llm

# 六触发器 + 三补充维度，构成完整体检报告。
REPORT_KEYS = (
    "conflict", "high_impact", "ambiguous", "novel_type",
    "compliance", "uncertain", "importance", "confidence", "missing",
)

# 重要性三档、置信度三档（与 spec 对齐）。
IMPORTANCE_LEVELS = ("low", "medium", "high")
CONFIDENCE_LEVELS = ("low", "medium", "high")

# 冲突检测增强（#10）：建议操作四值。
ACTIONS = ("ADD", "UPDATE", "SUPERSEDE", "NOOP")

JUDGMENT_PROMPT = """你是记忆仓库的第二审质检员。对下面这条「候选记忆」做软判断，只输出一个 JSON 对象（不要任何多余文字、不要 markdown 代码块）。

候选记忆：
{payload}

已有相似结论（可能为空，每条带 id 定位）：
{existing}

请严格按以下 schema 输出，字段含义：
- conflict: 对象或 null。候选与已有相似结论的关系判断。若无任何相似结论，输出 null；否则输出 {{"ids": ["冲突或重叠的已有条目 id"], "action": "ADD/UPDATE/SUPERSEDE/NOOP 之一"}}。action 判定标准（务必区分 UPDATE 与 SUPERSEDE）：
  * NOOP：候选与已有结论语义等价（换个说法说同一件事），无需新增。
  * UPDATE：候选是已有结论的**补充、细化或延伸**，二者不矛盾，可并存。例如已有「杭州优先」，候选「补充：薪资分城市」。
  * SUPERSEDE：候选**推翻/取代**已有结论，二者在语义上互相矛盾、不能并存。例如已有「只看杭州」，候选「改为上海优先」。凡新结论使旧结论不再成立，一律用 SUPERSEDE 而非 UPDATE。
  * ADD：候选是库里没有的全新结论（此时应输出 null 而非带 ADD 的对象；只有确需显式声明时才用）。
  判定口诀：新结论与旧结论「能并存=UPDATE，不能并存=SUPERSEDE」。
- high_impact: 布尔。是否为高影响/不可逆操作（删除、作废被多处引用的核心结论）。
- ambiguous: 布尔。候选本身是否歧义或自相矛盾。
- novel_type: 布尔。类型是否未定义过（type 不在 profile/preference/entity/event/decision/procedure/fact/experience/reference 之内）。
- compliance: 布尔。是否疑似触碰合规/隐私边界（脚本未拦但可疑）。
- uncertain: 布尔。候选理由中是否含「可能/也许/例外」等不确定表述。
- importance: 字符串，low/medium/high 之一。这条结论对用户的重要程度。
- confidence: 字符串，low/medium/high 之一。你对上面判断的置信度。
- missing: 字符串。缺失的关键信息（如缺来源、缺理由、缺有效期），没有则空字符串。

只输出 JSON："""


def build_prompt(candidate: dict, existing: list[str]) -> str:
    payload = json.dumps(candidate, ensure_ascii=False, indent=2)
    existing_text = "\n".join("- " + e for e in existing) if existing else "（无）"
    return JUDGMENT_PROMPT.format(payload=payload, existing=existing_text)


def parse_report(raw: str) -> dict:
    """从 LLM 返回文本里稳健提取 JSON 体检报告。

    LLM 可能输出多余文字或 markdown 代码块，这里做清洗后解析。
    解析失败抛 ValueError，由上层走降级路径。
    """
    text = raw.strip()
    # 去掉可能的 markdown 代码块包裹。
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 截取第一个 { 到最后一个 } 之间的内容。
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 未返回 JSON 对象")
    data = json.loads(text[start : end + 1])
    return data


def _normalize_conflict(val) -> dict:
    """归一化 conflict 字段为统一结构 {"ids": [...], "action": "..."}。

    兼容两种输入形态：
    - 布尔（旧格式 / 降级路径）：True → {"ids": [], "action": ""}，False → None；
    - 对象（新格式 / LLM 增强）：{"ids": [...], "action": "ADD/UPDATE/SUPERSEDE/NOOP"}。
    非法 action 或 ids 取安全默认（action 空串，ids 空列表）。
    """
    if val is None or val is False:
        return None
    if val is True:
        return {"ids": [], "action": ""}
    if isinstance(val, dict):
        ids = val.get("ids") or []
        if not isinstance(ids, list):
            ids = []
        ids = [str(i) for i in ids if i]
        action = val.get("action") or ""
        action = action if action in ACTIONS else ""
        return {"ids": ids, "action": action}
    # 其它非空值（如非空字符串）视为存在冲突但缺细节。
    return {"ids": [], "action": ""}


def validate_report(report: dict) -> dict:
    """校验并归一化体检报告，非法字段取安全默认值。"""
    clean = {}
    for key in REPORT_KEYS:
        val = report.get(key)
        if key == "conflict":
            clean[key] = _normalize_conflict(val)
        elif key in ("high_impact", "ambiguous", "novel_type", "compliance", "uncertain"):
            clean[key] = bool(val)
        elif key == "importance":
            clean[key] = val if val in IMPORTANCE_LEVELS else "low"
        elif key == "confidence":
            clean[key] = val if val in CONFIDENCE_LEVELS else "low"
        elif key == "missing":
            clean[key] = str(val) if val else ""
    return clean


def judge(client: llm.LLMClient, candidate: dict, existing: list[str]) -> dict:
    """用 LLM 对候选做软判断，返回归一化后的体检报告。"""
    prompt = build_prompt(candidate, existing)
    raw = client.chat(
        [{"role": "system", "content": "你是一个严谨的记忆质检员，只输出 JSON。"},
         {"role": "user", "content": prompt}],
        temperature=0.0,
    )
    report = parse_report(raw)
    return validate_report(report)


def classify(report: dict) -> str:
    """代码按固定阈值把体检报告映射为 L0 / L1 / L2。

    这是「裁决权归代码」的关键：LLM 只出报告，这里才定级。
    """
    # L2：高影响 / 合规边界 / 低置信 —— 强制人工，不批不动。
    if report["high_impact"] or report["compliance"] or report["confidence"] == "low":
        return "L2"
    # L1：任一触发器命中，或中等重要，或中置信，或缺失关键信息 —— 进待审批队列。
    if (report["conflict"] or report["ambiguous"] or report["novel_type"]
            or report["uncertain"] or report["missing"]
            or report["importance"] != "low" or report["confidence"] == "medium"):
        return "L1"
    # L0：无冲突、无缺失、低重要、高置信 —— 自动入库。
    return "L0"


# ---- 降级路径：LLM 不可用时用纯规则产出体检报告（v1 行为） ----

UNCERTAIN_WORDS = re.compile(r"可能|也许|或许|大概|例外|不一定|视情况|待定|暂不")


def rule_report(candidate: dict, existing: list[str]) -> dict:
    """纯规则产出体检报告（降级路径）。

    判断力弱于 LLM，但保证流程照常：
    - conflict：只能靠显式关联字段近似，默认 False；
    - high_impact：仅当操作类型为删除/作废时判 True；
    - novel_type：靠类型是否在九类之内判断；
    - uncertain：靠理由里是否含不确定词判断；
    - 其余维度取保守默认（importance 依 weight 推断，confidence 一律 low）。
    """
    from . import schema as _schema  # 延迟导入，避免循环依赖

    valid_types = set(_schema.TYPES)
    ctype = candidate.get("type", "")
    weight = candidate.get("weight", 0)
    reason = candidate.get("reason", "") or ""

    report = {
        "conflict": None,
        "high_impact": ctype in ("delete", "purge", "supersede", "invalidate"),
        "ambiguous": False,
        "novel_type": bool(ctype) and ctype not in valid_types,
        "compliance": False,
        "uncertain": bool(UNCERTAIN_WORDS.search(reason)),
        "importance": "high" if weight >= 8 else ("medium" if weight >= 5 else "low"),
        "confidence": "low",
        "missing": "",
    }
    # 缺失检测：结论或理由为空即判缺失。
    if not candidate.get("conclusion"):
        report["missing"] = "缺结论"
    elif not reason:
        report["missing"] = "缺理由"
    return report


def decide_action(report: dict) -> str:
    """从体检报告里取出「建议操作」，缺省返回 ADD。

    这是自动去重分流的裁决依据：LLM 产出的 conflict.action 决定
    候选该 ADD / UPDATE / SUPERSEDE / NOOP。报告里没有 conflict
    （即无相似结论）时视为全新，返回 ADD。
    """
    conflict = report.get("conflict")
    if not conflict:
        return "ADD"
    action = conflict.get("action") or ""
    return action if action in ACTIONS else "ADD"


def find_related(index, candidate: dict, limit: int = 8) -> list[str]:
    """检索库中与候选相似的已有结论，返回「id + 摘要」文本列表喂给 LLM 比对。

    读路径零网络约束：只走本地 SQLite 索引（Index.recall），不调模型、不联网。
    查询词取候选的 abstract + conclusion + name，命中后转成可读文本。
    检索失败（如索引未建）时返回空列表，不阻断软判断流程。
    """
    abstract = (candidate.get("abstract") or "").strip()
    conclusion = (candidate.get("conclusion") or "").strip()
    name = (candidate.get("name") or "").strip()
    # 查询词优先用摘要 + 名（精准），摘要为空才退回结论全文。
    query = " ".join(x for x in (abstract, name) if x) or conclusion
    if not query:
        return []
    try:
        hits = index.recall(query, limit=limit)
    except Exception:
        return []
    lines = []
    for hit in hits:
        ident = hit.get("id", "")
        abstract_text = hit.get("abstract", "") or ""
        type_text = hit.get("type", "") or ""
        parts = [ident]
        if type_text:
            parts.append("[%s]" % type_text)
        if abstract_text:
            parts.append(abstract_text)
        lines.append(" ".join(parts))
    return lines
