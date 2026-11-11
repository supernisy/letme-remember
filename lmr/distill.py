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


DISTILL_PROMPT = """你是记忆蒸馏器。把下面这段「旧记忆/日志文本」提炼成若干条记忆，每条是「结论」或「案例索引」二者之一。丢掉过程流水、一次性环境细节、重复内容。

旧文本：
{text}

要求：
1. 每条固定字段：name（唯一英文标识）、abstract（一句话摘要）、type（9 类之一）、conclusion（结论或索引说明）、reason（为什么这么记）。
2. 认知/偏好类的结论，reason 里要标注「以用户最新表态为准」。

**产出分两类（双轨，都很重要）**：

【结论类】跨会话可复用的纪律、规则、方法、稳定事实。type 用 profile/preference/entity/event/decision/procedure/fact/experience。

【案例索引类】某次具体面试、某次事件、某份报告的完整复盘——这类「具体问答/具体过程」的细节不值得蒸成结论，但 MUST 用 type="reference" 产出一条**索引**：
- abstract 写清「这是什么案例、发生在何时、核心议题是什么」
- conclusion 写「完整细节见原文：<文件名>」，文件名照抄文本里出现过的名字，只存指针，不抄正文
- reason 写「作为复盘案例存档，需查具体问答/分析时按此索引找原文」
- 注意：你**不负责给路径**，只写你从文本里看到的文件名；磁盘绝对路径会由代码回填。若文本里没有明确文件名，conclusion 写「原文未指明文件名」，并额外给一个 ref_subject 字段写清案例主题（公司+岗位+日期），供代码按主题回填。

**克制原则（宁缺毋滥）**：
- 只产出「未来跨会话还会用得上」的内容。每写一条前自问：删掉这条会不会后悔？不会后悔的就不写。
- 同一主题的多条碎片 MUST 合并成一条，禁止把一件事拆成好几条。
- 以下内容不单独产结论，只在上一条「案例索引」里被覆盖：某次面试/会议的问答逐字稿、当天做了什么、岗位的具体判断、碎片化技术名词解释、空洞的「XX 的核心在于 XX」套话。
- 一段文本通常只值得产出 1~6 条。宁可只产出 0 条，也不要凑数。

3. 只输出 JSON 数组，不要任何多余文字、不要 markdown 代码块。

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
