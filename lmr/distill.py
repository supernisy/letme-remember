"""第二审的可插拔提炼器接口（design D4）。

仓库不内置任何模型调用。宿主可以注入一个提炼器（把长内容浓缩成候选
结论），但模型产出永远是「候选」，绝不直接落库：
  - 全部候选先做一次批量原子预校验，任一非法则整批拒绝、零文件写出；
  - 每个候选仍走与常规写入完全相同的第一审与 git 审计路径。
"""

from __future__ import annotations

from typing import Iterable, Protocol

from . import store


class Distiller(Protocol):
    """提炼器契约：输入一段文本，产出候选字典的可迭代对象。"""

    def distill(self, text: str) -> Iterable[dict]:
        ...


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
