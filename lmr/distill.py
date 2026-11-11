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
from .errors import ValidationError


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
- **每条 MUST 额外带一个 importance 字段**（整数 1~5，5=跨会话长期关键，1=边缘可弃）。代码会按 importance 截断，所以请如实给分：只有真正关键的才给 4~5，一般的给 3，边缘的给 1~2。

**正例（该产出）**：
- 「求职薪资三个数（期望/底线/可接受）不能混写」→ 一条 experience，importance=5
- 「长鑫二面离职原因被追问的完整过程」→ 一条 reference 索引指向原文，importance=4

**反例（不该产出）**：
- 「今天下午修了 X 的 bug，改了几行代码」→ 不产，这是一次性流水
- 「A2UI 的核心难点在于多通道仲裁」「A2UI 的核心判据是……」→ 不产，这是空洞套话

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
    """接真实 LLM 的蒸馏器：长文本 → 候选记忆列表。

    改进点（v1.1 后期）：
    - response_format=json_object 强制 JSON，减少畸形输出；
    - 每条候选带 importance（1~5），代码按阈值截断，把「挑哪些」的
      裁决权从模型直觉收回到代码确定性。
    """

    # 代码层截断阈值：importance 低于此值的候选直接丢弃（不落库、不产出）。
    IMPORTANCE_MIN = 3

    def __init__(self, client, importance_min: int | None = None):
        self.client = client
        if importance_min is not None:
            self.IMPORTANCE_MIN = importance_min

    def distill(self, text: str) -> list[dict]:
        raw = self.client.chat(
            [{"role": "system", "content": "你是一个严谨的记忆蒸馏器，只输出 JSON 数组。"},
             {"role": "user", "content": DISTILL_PROMPT.format(text=text)}],
            temperature=0.0,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        candidates = _extract_json_array(raw)
        return self._filter_by_importance(candidates)

    def _filter_by_importance(self, candidates: list[dict]) -> list[dict]:
        """按 importance 截断：低于阈值的丢弃；importance 字段从落库候选里剥掉。"""
        kept = []
        for c in candidates:
            if not isinstance(c, dict):
                continue
            imp = c.get("importance", self.IMPORTANCE_MIN)
            try:
                imp = int(imp)
            except (TypeError, ValueError):
                imp = self.IMPORTANCE_MIN
            if imp < self.IMPORTANCE_MIN:
                continue
            c.pop("importance", None)  # 内部字段，不落库
            kept.append(c)
        return kept


IMPORT_FIELDS = ("source_category", "original_date", "batch")


def enforce_import_fields(candidates):
    """蒸馏链路的必填字段完整性校验（入口拦截）。

    蒸馏/批量导入产出的候选只要带任一导入字段（source_category /
    original_date / batch），就必须三字段齐全；否则在写库前就抛错，
    避免像历史那样缺 original_date 的候选一直漏到落库阶段才中断整批。

    与 store.build_candidate 里「半导入」隐式判断不同，这里显式要求：
    带任一导入字段 = 必须三字段齐全；三字段全空 = 视为人类手写，放行。
    """
    items = list(candidates)
    for number, raw in enumerate(items, 1):
        if not isinstance(raw, dict):
            raise ValidationError("候选 %d 不是字典" % number)
        present = [k for k in IMPORT_FIELDS if str(raw.get(k) or "").strip()]
        if present and len(present) != len(IMPORT_FIELDS):
            missing = [k for k in IMPORT_FIELDS if not str(raw.get(k) or "").strip()]
            name = raw.get("name") or "(未命名)"
            raise ValidationError(
                "候选 %d（%s）导入字段不完整：缺失 %s，请回填后重试" % (
                    number, name, "、".join(missing))
            )
    return items


def run_candidates(candidates, paths, settings):
    """批量写入候选。原子预校验在前，任何一个不合法就整批不动磁盘。"""
    items = enforce_import_fields(candidates)
    store.prevalidate(items, settings)
    results = []
    for raw in items:
        outcome = store.record(paths, settings, raw)
        results.append({"id": outcome["id"], "commit": outcome["commit"]})
    return {"count": len(results), "items": results}


def run_distiller(distiller, text, paths, settings):
    """宿主注入提炼器时的入口；模型只负责产候选，落库仍由代码把关。"""
    return run_candidates(distiller.distill(text), paths, settings)
