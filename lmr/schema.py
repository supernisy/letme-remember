"""typed 记忆（CoALA 三类）与文件名规则。

类型对齐 CoALA 认知架构（Princeton, 2023）的长期记忆分类，三类：
  semantic    语义 —— 稳定事实、偏好、决策结论、教训（可复用，不随时间衰减）
  episodic    情景 —— 过去发生的事件/复盘索引（指向原文，随时间衰减）
  procedural  程序 —— 怎么做的流程、规则、做法

落盘粒度：每条记忆以文件头 name 字段独立成文件（放弃按类型分组的
key_fields 机制），同 name 永远落到同一个文件，便于单条检索与审计。
"""

from __future__ import annotations

import hashlib
import re

TYPES = {
    "semantic",
    "episodic",
    "procedural",
}

# 旧九类 → CoALA 三类的迁移映射（只作存量迁移与导入猜测的初值，非铁律）。
# 语义判断仍以蒸馏 prompt 为准；此处仅提供保守默认。
LEGACY_TYPE_MAP = {
    "profile": "semantic",
    "preference": "semantic",
    "entity": "semantic",
    "decision": "semantic",
    "fact": "semantic",
    "experience": "semantic",
    "event": "episodic",
    "reference": "episodic",
    "procedure": "procedural",
}

_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def canonical_type(value):
    """把旧类型名规范化到三类；已是三类则原样返回，未知返回 None。"""
    if value in TYPES:
        return value
    return LEGACY_TYPE_MAP.get(value)


def safe_slug(name):
    """保留中文、字母数字与 ._-；其余字符替换，过长时追加内容哈希。"""
    text = str(name).strip()
    if _FORBIDDEN.search(text):
        raise ValueError("身份名含非法字符")
    cleaned = re.sub(r"[^\w.\-]+", "-", text, flags=re.UNICODE)
    cleaned = cleaned.strip("-") or "entry"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    if len(cleaned) > 60:
        cleaned = cleaned[:60].rstrip("-") + "-" + digest
    return cleaned


def filename_for(memory_type, name):
    if memory_type not in TYPES:
        raise ValueError("未知类型: %s" % memory_type)
    return "%s--%s.md" % (memory_type, safe_slug(name))


def entry_id(filename):
    """定位标识 = 文件名去掉扩展名，宿主无需知道路径。"""
    return filename[:-3] if filename.endswith(".md") else filename
