"""第二审的可插拔提炼器接口（design D4）。

仓库不内置任何模型调用。宿主可以注入一个提炼器（把长内容浓缩成候选
结论），但模型产出永远是「候选」，绝不直接落库：
  - 全部候选先做一次批量原子预校验，任一非法则整批拒绝、零文件写出；
  - 每个候选仍走与常规写入完全相同的第一审与 git 审计路径。

v1.1 新增 :class:`LLMDistiller`：接真实 LLM 把长文本蒸馏成候选记忆，
用于存量旧记忆的批量导入。
"""

from __future__ import annotations

import json
import re
from typing import Iterable, Protocol

from . import store


class Distiller(Protocol):
    """提炼器契约：输入一段文本，产出候选字典的可迭代对象。"""

    def distill(self, text: str) -> Iterable[dict]:
        ...


DISTILL_PROMPT = """你是记忆蒸馏器。把下面这段「旧记忆/日志文本」提炼成若干条「结论级记忆」，每条只保留跨会话可复用的结论，丢掉过程流水、一次性环境细节、重复内容。

旧文本：
{text}

要求：
1. 每条记忆固定字段：name（唯一英文标识）、abstract（一句话摘要）、type（9 类之一：profile/preference/entity/event/decision/procedure/fact/experience/reference）、conclusion（结论原文）、reason（为什么这么记）。
2. 认知/偏好类的结论，reason 里要标注「以用户最新表态为准」。
3. 不要输出流水账、当天干了什么、临时状态、指针路径。
4. 只输出 JSON 数组，不要任何多余文字、不要 markdown 代码块。

只输出 JSON 数组："""


def _extract_json_array(raw: str) -> list:
    """从 LLM 返回文本稳健提取 JSON 数组。"""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 未返回 JSON 数组")
    return json.loads(text[start : end + 1])


class LLMDistiller:
    """接真实 LLM 的蒸馏器：长文本 → 候选记忆列表。"""

    def __init__(self, client):
        self.client = client

    def distill(self, text: str) -> list[dict]:
        raw = self.client.chat(
            [{"role": "system", "content": "你是一个严谨的记忆蒸馏器，只输出 JSON 数组。"},
             {"role": "user", "content": DISTILL_PROMPT.format(text=text)}],
            temperature=0.0,
            max_tokens=4096,
        )
        return _extract_json_array(raw)


def run_candidates(candidates, paths, settings):
    """批量写入候选。原子预校验在前，任何一个不合法就整批不动磁盘。"""
    items = list(candidates)
    store.prevalidate(items, settings)
    results = []
    for raw in items:
        outcome = store.record(paths, settings, raw)
        results.append({"id": outcome["id"], "commit": outcome["commit"]})
    return {"count": len(results), "items": results}


def run_distiller(distiller, text, paths, settings):
    """宿主注入提炼器时的入口；模型只负责产候选，落库仍由代码把关。"""
    return run_candidates(distiller.distill(text), paths, settings)
