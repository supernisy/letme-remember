"""第一审的形状规则引擎（design D9）。

三层边界：
  A 类 凭据与密钥      -> 强制打码，无例外
  B 类 机器可读标识符  -> 默认只告警，打码可配置
  C 类 叙述性私人事实  -> 不进脚本，照常入库（输出口径由后续的输出策略层负责）

处置顺序：形状匹配 -> 校验和 / 熵复核 -> 误报白名单 -> 打码或告警
          -> 审计只记规则编号，绝不记录命中的原值。
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

RULES_PATH = Path(__file__).with_name("rules.json")
# 不能用方括号：封闭文件头把 [ ] { } 视为富格式并直接拒绝解析。
REDACTED = "_REDACTED_"

# 明确排除在脚本之外的类别：只能靠语义判断，不是形状规则能拦的。
NON_SHAPE_CLASSES = ("C",)


def load_rules():
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _shannon(text):
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def _luhn_ok(text):
    digits = [int(ch) for ch in text if ch.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _iban_ok(text):
    compact = text.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(
        str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged
    )
    remainder = 0
    for ch in numeric:
        remainder = (remainder * 10 + int(ch)) % 97
    return remainder == 1


def _passes_check(rule, matched):
    check = rule.get("check", "regex")
    if check == "luhn":
        return _luhn_ok(matched)
    if check == "iban":
        return _iban_ok(matched)
    if check == "entropy":
        return _shannon(matched) >= float(rule.get("threshold", 3.5))
    return True


def _span_for(rule, match):
    group = rule.get("redact_group")
    if group:
        try:
            return match.span(int(group))
        except (IndexError, ValueError):
            pass
    return match.span(0)


def scan(text, rules=None, extra_allowlist=()):
    """返回内部命中记录（含区间）；该结构只在进程内使用，不写日志。"""
    data = rules or load_rules()
    allowlist = [str(x).upper() for x in list(data.get("allowlist", [])) + list(extra_allowlist) if x]
    hits = []
    for rule in data["rules"]:
        try:
            pattern = re.compile(rule["pattern"])
        except re.error as exc:
            raise RuntimeError("规则 %s 正则非法: %s" % (rule["id"], exc)) from exc
        for match in pattern.finditer(text):
            span = _span_for(rule, match)
            matched = text[span[0]:span[1]]
            if any(token in matched.upper() for token in allowlist):
                continue
            if not _passes_check(rule, matched):
                continue
            hits.append({
                "rule": rule["id"],
                "class": rule["class"],
                "start": span[0],
                "end": span[1],
            })
    return hits


def rule_hits(text, rule_id, rules=None, extra_allowlist=()):
    """测试辅助：判断某条规则是否命中，不返回原值。"""
    return any(h["rule"] == rule_id for h in scan(text, rules, extra_allowlist))


def _merge_spans(spans):
    """A 类优先，合并重叠区间，避免多次替换造成偏移。"""
    ordered = sorted(spans, key=lambda s: (0 if s["class"] == "A" else 1, s["start"], -s["end"]))
    chosen = []
    occupied_end = -1
    for item in ordered:
        if item["start"] < occupied_end:
            continue
        chosen.append(item)
        occupied_end = item["end"]
    return sorted(chosen, key=lambda s: s["start"])


def redact(text, settings=None, rules=None, extra_allowlist=()):
    """返回 (打码后的文本, 审计记录)。审计记录只含规则编号与数量。"""
    settings = settings or {}
    hits = scan(text, rules, extra_allowlist)
    redact_b = bool(settings.get("redact_b_class", False))
    to_mask = _merge_spans([h for h in hits if h["class"] == "A" or redact_b])

    result = text
    for item in reversed(to_mask):
        result = result[:item["start"]] + REDACTED + result[item["end"]:]

    counts = {}
    for hit in hits:
        key = (hit["rule"], hit["class"])
        counts[key] = counts.get(key, 0) + 1
    findings = [
        {"rule": rule_id, "class": cls, "count": count,
         "action": "masked" if cls == "A" or redact_b else "warned"}
        for (rule_id, cls), count in sorted(counts.items())
    ]
    return result, findings


def audit_lines(findings):
    """给审计日志用的文本：只有规则编号与计数，没有原值。"""
    return ["%s:%s:%s:%s" % (f["rule"], f["class"], f["action"], f["count"]) for f in findings]
