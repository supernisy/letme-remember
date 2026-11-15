"""分块蒸馏的 Map-Reduce 编排 + 结论级增量 diff（v2 方向④）。

设计（design.md D1/D3）：
- Map 阶段：长文本分块后，每块用现有 LLMDistiller.distill 提炼候选；
- Reduce 阶段：合并去重（name 级确定性去重，分块内重复保留后者）；
  更深的语义去重（ADD/UPDATE/SUPERSEDE/NOOP）留给 consolidate 落库时做，
  这里不新造一套去重。
- diff 阶段：同一项目多次面试，把「上一版结论集」与「这一版候选」
  交 LLM 对比，产出「本次新增/深化」清单（结论级，不做句子级溯源）。

本模块只做编排与确定性合并；LLM 调用复用 llm.LLMClient 与 distill.LLMDistiller。
"""

from __future__ import annotations

import json
import re

from . import chunk as chunk_module
from . import distill as distill_module


# ---------------------------------------------------------------------------
# Map-Reduce 分块蒸馏
# ---------------------------------------------------------------------------

def _merge_by_name(candidates: list[dict]) -> list[dict]:
    """按 name 确定性去重：同 name 保留最后一条（分块蒸馏的重复合并第一步）。

    不跨 name 做语义去重——那是 consolidate（ADD/UPDATE/SUPERSEDE/NOOP）的职责。
    """
    seen: dict[str, dict] = {}
    order: list[str] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        if name not in seen:
            order.append(name)
        seen[name] = c
    return [seen[n] for n in order]


def distill_chunked(client, text: str, max_chars: int | None = None) -> dict:
    """Map-Reduce 分块蒸馏：分块 → 每块提炼 → 合并去重。

    返回 {chunks, candidates, merged}：
    - chunks: 分块数
    - candidates: 各块候选的扁平列表（合并前）
    - merged: name 去重后的候选列表
    """
    if max_chars is None:
        max_chars = chunk_module.DEFAULT_MAX_CHARS
    chunks = chunk_module.chunk_transcript(text, max_chars=max_chars)
    distiller = distill_module.LLMDistiller(client)
    all_candidates: list[dict] = []
    for ch in chunks:
        try:
            cands = distiller.distill(ch["text"])
        except Exception:
            # 单块蒸馏失败不阻断整批，记录后继续（块级容错）。
            continue
        all_candidates.extend(cands)
    merged = _merge_by_name(all_candidates)
    return {"chunks": len(chunks), "candidates": all_candidates, "merged": merged}


# ---------------------------------------------------------------------------
# 结论级增量 diff
# ---------------------------------------------------------------------------

DIFF_PROMPT = """你是记忆增量分析器。下面是「同一主题」的两批结论，请判断这批新结论相对旧结论，哪些是「新增」、哪些是「深化/更新」。

旧结论集（上一版，每条含 name 与摘要）：
{prev}

新候选集（这一版，每条含 name/abstract/conclusion）：
{new}

请输出一个 JSON 对象，字段：
- added: 字符串数组。新候选里「旧结论完全没有、本次全新出现」的结论（写 name 或一句话摘要）。
- deepened: 字符串数组。新候选里「旧结论已有、但本次补充了新细节/新维度」的结论（写 name + 一句话说明深在哪）。
- unchanged: 字符串数组。新旧基本一致的结论（写 name）。
- note: 字符串。一句话总结本次相对上次的整体变化（如「本次新增了 X 主题，深化了 Y 主题」）。

判定口诀：旧结论里没有 = added；旧结论里有但新说法更细/更多 = deepened；基本一样 = unchanged。

只输出 JSON："""


def _extract_json_object(raw: str) -> dict:
    """稳健提取 JSON 对象（复用 distill 的清洗思路）。"""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 未返回 JSON 对象")
    return json.loads(text[start : end + 1])


def diff_conclusions(client, prev: list[str], new: list[dict]) -> dict:
    """结论级增量 diff：新旧结论集交 LLM，产出 added/deepened/unchanged 清单。

    prev: 上一版结论的文本列表（如 [name + abstract 拼接]）。
    new: 这一版候选列表（含 name/abstract/conclusion）。
    """
    prev_text = "\n".join("- " + p for p in prev) if prev else "（无，首次）"
    new_lines = []
    for c in new:
        name = str(c.get("name") or "").strip()
        abstract = str(c.get("abstract") or "").strip()
        conclusion = str(c.get("conclusion") or "").strip()
        new_lines.append("- %s | %s | %s" % (name, abstract, conclusion))
    new_text = "\n".join(new_lines) if new_lines else "（无）"

    raw = client.chat(
        [{"role": "system", "content": "你是一个严谨的记忆增量分析器，只输出 JSON。"},
         {"role": "user", "content": DIFF_PROMPT.format(prev=prev_text, new=new_text)}],
        temperature=0.0,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    data = _extract_json_object(raw)
    return {
        "added": data.get("added") or [],
        "deepened": data.get("deepened") or [],
        "unchanged": data.get("unchanged") or [],
        "note": data.get("note") or "",
    }
