"""封闭文件头（frontmatter）读写器。

设计 D8：不引入 YAML / JSON 解析器，只认固定字段集合与固定写法。
任何未知字段、嵌套结构、富格式写法一律直接拒绝，而不是悄悄重解释。
所有值都按原始字符串读回，不做 yes/no、日期、数字的隐式类型转换。
"""

from __future__ import annotations

from .errors import FrontmatterError

FIELDS = (
    "name",
    "abstract",
    "type",
    "created",
    "updated",
    "valid_from",
    "invalid_at",
    "superseded_by",
    "weight",
    "author",
    "links",
    "provenance",
)
LIST_FIELDS = frozenset({"links", "provenance"})
_RICH_CHARS = frozenset("[]{}")

DELIM = "---"
LIST_SEP = "|"


def empty_meta():
    return {f: ([] if f in LIST_FIELDS else "") for f in FIELDS}


def _check_scalar(key, value):
    if any(ch in value for ch in _RICH_CHARS):
        raise FrontmatterError("字段 %s 含富格式字符，拒绝解析" % key)
    if "\n" in value or "\r" in value:
        raise FrontmatterError("字段 %s 含换行，拒绝解析" % key)
    if key not in LIST_FIELDS and LIST_SEP in value:
        raise FrontmatterError("字段 %s 不是列表字段，不能含分隔符" % key)


def parse(text):
    """返回 (meta, body)。meta 恒含全部 12 个字段。"""
    if not isinstance(text, str):
        raise FrontmatterError("文件头必须是文本")
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != DELIM:
        raise FrontmatterError("缺少文件头起始分隔线")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == DELIM:
            end = i
            break
    if end is None:
        raise FrontmatterError("缺少文件头结束分隔线")

    meta = empty_meta()
    seen = set()
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        if raw != raw.lstrip():
            raise FrontmatterError("出现缩进（嵌套结构），拒绝解析")
        if ":" not in raw:
            raise FrontmatterError("文件头每行必须为 key: value")
        key, value = raw.split(":", 1)
        if key != key.strip() or key not in FIELDS:
            raise FrontmatterError("未知字段，拒绝解析: %s" % key.strip())
        if key in seen:
            raise FrontmatterError("字段重复: %s" % key)
        seen.add(key)
        value = value.lstrip(" ").rstrip()
        _check_scalar(key, value)
        if key in LIST_FIELDS:
            meta[key] = [part.strip() for part in value.split(LIST_SEP) if part.strip()]
        else:
            meta[key] = value
    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return meta, body


def render(meta, body=""):
    """把 meta 与正文拼成规范文本；渲染前同样做封闭性检查。"""
    lines = [DELIM]
    for key in FIELDS:
        value = meta.get(key, [] if key in LIST_FIELDS else "")
        if key in LIST_FIELDS:
            if isinstance(value, str):
                value = [value] if value else []
            parts = [str(part).strip() for part in value]
            if any(not part for part in parts):
                raise FrontmatterError("列表字段 %s 含空项" % key)
            if any(LIST_SEP in part or any(ch in part for ch in _RICH_CHARS) for part in parts):
                raise FrontmatterError("列表字段 %s 的项含分隔符或富格式字符" % key)
            value = LIST_SEP.join(parts)
        else:
            value = str(value)
        _check_scalar(key, value)
        lines.append("%s: %s" % (key, value))
    lines.append(DELIM)
    lines.append("")
    lines.append(body.rstrip("\n"))
    return "\n".join(lines) + "\n"


def read_file(path):
    from pathlib import Path

    return parse(Path(path).read_text(encoding="utf-8"))


def write_file(path, meta, body):
    from pathlib import Path

    Path(path).write_text(render(meta, body), encoding="utf-8")


BODY_SECTIONS = ("结论", "理由")


def body_sections(body):
    """正文必须含「结论」与「理由」两节，返回各节文本。"""
    found = {}
    current = None
    buffer = []
    for line in body.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            if current is not None:
                found[current] = "\n".join(buffer).strip()
            title = stripped[3:].strip()
            current = title if title in BODY_SECTIONS else None
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        found[current] = "\n".join(buffer).strip()
    return {name: found.get(name, "") for name in BODY_SECTIONS}


def make_body(conclusion, reason):
    return "## 结论\n\n%s\n\n## 理由\n\n%s\n" % (
        str(conclusion).strip(),
        str(reason).strip(),
    )
