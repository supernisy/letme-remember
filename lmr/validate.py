"""写入前第一审：字段与正文的确定性校验。

校验只做显式判断：日期是否合法、区间是否自洽、取代链是否完整、
权重是否在范围内、结论是否带理由。不做任何隐式类型转换。
"""

from __future__ import annotations

import re
from datetime import datetime

from . import frontmatter, schema

REQUIRED = ("name", "abstract", "type", "created", "updated", "valid_from", "author")
DATE_FIELDS = ("created", "updated", "valid_from", "invalid_at")
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)


def iso_date(value):
    """返回可比较的 date；非法输入返回 None。"""
    if not isinstance(value, str) or not _ISO_RE.match(value.strip()):
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
    except ValueError:
        return None


def validate_meta(meta, body):
    """返回错误列表；空列表表示通过。"""
    errors = []
    for key in frontmatter.FIELDS:
        if key not in meta:
            errors.append("缺少字段: %s" % key)
    if errors:
        return errors

    for key in REQUIRED:
        value = meta[key]
        if not isinstance(value, str) or not value.strip():
            errors.append("必填字段为空: %s" % key)

    if meta["type"] and meta["type"] not in schema.TYPES:
        errors.append("未知类型: %s" % meta["type"])

    name = meta["name"]
    if name and ("\n" in name or "/" in name or "\\" in name):
        errors.append("身份名含路径分隔符或换行")

    parsed = {}
    for key in DATE_FIELDS:
        raw = meta[key]
        if not raw:
            continue
        value = iso_date(raw)
        if value is None:
            errors.append("日期不是 ISO 8601: %s" % key)
        else:
            parsed[key] = value

    if "valid_from" in parsed and "invalid_at" in parsed:
        if parsed["invalid_at"] < parsed["valid_from"]:
            errors.append("invalid_at 早于 valid_from")

    if meta["superseded_by"] and not meta["invalid_at"]:
        errors.append("声明了 superseded_by 却缺少 invalid_at 失效区间")

    try:
        weight = float(meta["weight"])
    except (TypeError, ValueError):
        errors.append("weight 不是数值")
    else:
        if not (0.0 <= weight <= 10.0):
            errors.append("weight 超出范围 [0, 10]")

    sections = frontmatter.body_sections(body)
    if not sections["结论"]:
        errors.append("正文缺少「## 结论」或结论为空")
    if not sections["理由"]:
        errors.append("结论必须带理由：正文缺少「## 理由」或理由为空")

    # 导入条目：provenance 必须记来源类别、原始日期、批次；时间语义三者分离。
    author = meta["author"]
    if author.startswith("import:"):
        provenance = meta["provenance"]
        if len(provenance) != 3:
            errors.append("导入条目的 provenance 必须为三段：来源类别|原始日期|批次标识")
        else:
            if iso_date(provenance[1]) is None:
                errors.append("provenance 的原始日期不是 ISO 8601")
            if not provenance[2]:
                errors.append("provenance 缺少导入批次标识")
            if meta["valid_from"] and provenance[1]:
                if iso_date(meta["valid_from"]) != iso_date(provenance[1]):
                    errors.append("valid_from 必须与 provenance 的原始日期一致")

    for field in frontmatter.LIST_FIELDS:
        value = meta[field]
        if not isinstance(value, list):
            errors.append("列表字段类型错误: %s" % field)
    return errors


def assert_valid(meta, body):
    from .errors import ValidationError

    errors = validate_meta(meta, body)
    if errors:
        raise ValidationError("；".join(errors))
