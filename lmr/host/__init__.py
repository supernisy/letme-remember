"""宿主适配器注册表：按名字查找适配器。"""

from __future__ import annotations

from .base import HostAdapter
from .workbuddy import WorkBuddyAdapter

_REGISTRY = {
    WorkBuddyAdapter.name: WorkBuddyAdapter,
}


def get_host(name: str) -> HostAdapter:
    """按宿主名返回适配器实例；未知宿主报错。"""
    if name not in _REGISTRY:
        from ..errors import ValidationError
        raise ValidationError("未知宿主: %s（可用: %s）" % (name, ", ".join(sorted(_REGISTRY))))
    return _REGISTRY[name]()


def available_hosts():
    return sorted(_REGISTRY.keys())
