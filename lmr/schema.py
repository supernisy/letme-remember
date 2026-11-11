"""9 类 typed 记忆、身份键与文件名规则。

粒度按类型定义（借鉴 agent-memory 的 schema 机制）：每类声明自己的
分组键与粒度说明。落盘身份统一用文件头的 name 字段；同类型同 name
永远落到同一个文件。
"""

from __future__ import annotations

import hashlib
import re

TYPES = {
    "profile": {"key_fields": ("user",), "granularity": "一人一文件", "add_only": False},
    "preference": {"key_fields": ("topic", "subject"), "granularity": "一个稳定偏好一文件", "add_only": False},
    "entity": {"key_fields": ("category", "subject"), "granularity": "一个实体一文件", "add_only": False},
    "event": {"key_fields": ("date", "subject"), "granularity": "一事一文件", "add_only": True},
    "decision": {"key_fields": ("project", "subject"), "granularity": "一个选择及其原因一文件", "add_only": False},
    "procedure": {"key_fields": ("project", "subject"), "granularity": "一个重复任务的做法一文件", "add_only": False},
    "fact": {"key_fields": ("project", "subject"), "granularity": "一条稳定事实一文件", "add_only": False},
    "experience": {"key_fields": ("topic", "subject"), "granularity": "一条教训（症状/原因/修复）一文件", "add_only": False},
    "reference": {"key_fields": ("source", "subject"), "granularity": "一份外部材料一文件", "add_only": False},
}

_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def derive_name(memory_type, key_parts):
    """按类型声明的分组键拼出身份名，供宿主不必自己造 slug。"""
    if memory_type not in TYPES:
        raise ValueError("未知类型: %s" % memory_type)
    parts = [str(part).strip() for part in key_parts if str(part).strip()]
    if not parts:
        raise ValueError("身份键不能为空")
    return "%s-%s" % (memory_type, "-".join(parts))


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
