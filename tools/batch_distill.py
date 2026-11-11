"""批量蒸馏旧记忆文件（v1.1 #12）。

遍历盘点清单里的 A 类（可蒸馏）文件，逐个调 LLM 蒸馏成候选记忆。
dry-run 模式只产出候选 JSON，不落库；产出带溯源字段（source_category /
original_date / batch），供人审后走 distill 命令正式入库。

工程约束：
- 大文件（>20KB）按段落（空行/标题）分块，逐块蒸馏后合并，避免超上下文。
- 单文件失败不中断整体，记入 failures，最后汇总报告。
- key 走私有数据目录配置，公开仓库不发布 key。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 让 tools/ 下的脚本能导入仓库根的 lmr 包。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lmr import config, distill, llm

WORKBUDDY = Path(r"C:\Users\super\WorkBuddy")
CHUNK_BYTES = 20000  # 单块上限，超过按段落切


def load_a_items(inventory_path: Path) -> list[dict]:
    data = json.loads(inventory_path.read_text(encoding="utf-8"))
    return [it for it in data["items"] if it["category"] == "A"]


def _split_chunks(text: str, limit: int = CHUNK_BYTES) -> list[str]:
    """按字节上限切块，优先在段落边界（空行）切开，避免切断一行。"""
    if len(text.encode("utf-8")) <= limit:
        return [text]
    chunks = []
    buf = ""
    for line in text.splitlines(keepends=True):
        if len((buf + line).encode("utf-8")) > limit and buf:
            chunks.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        chunks.append(buf)
    return chunks


def original_date(rel_path: str) -> str:
    """从文件名推断原始日期（形如 2026-10-29.md），失败返回空。"""
    name = Path(rel_path).name
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else ""


def run(client, text: str) -> list[dict]:
    distiller = distill.LLMDistiller(client)
    candidates = []
    for chunk in _split_chunks(text):
        try:
            candidates.extend(distiller.distill(chunk))
        except Exception as exc:  # 单块失败记录后继续
            candidates.append({"__chunk_error__": type(exc).__name__})
    return candidates


def main():
    parser = argparse.ArgumentParser(description="批量蒸馏旧记忆文件（dry-run）")
    parser.add_argument("--inventory", default=str(Path(r"C:\Users\super\WorkBuddy\2026-11-10-20-12-59\盘点清单.json")))
    parser.add_argument("--out", default=str(Path(r"C:\Users\super\WorkBuddy\2026-11-10-20-12-59\distill-candidates.json")))
    parser.add_argument("--data-dir", default=None, help="记忆数据目录（默认 ~/.letme-remember/data）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个文件（0=全部），用于小样本试蒸")
    parser.add_argument("--batch", default="import-legacy-batch-01", help="导入批次标识")
    args = parser.parse_args()

    paths = config.Paths(config.resolve_data_dir(args.data_dir))
    settings = config.settings_for(paths.root)
    data_config = config._data_config(paths.root)
    client = llm.make_client(settings, data_config)

    items = load_a_items(Path(args.inventory))
    if args.limit > 0:
        items = items[: args.limit]

    results = []
    failures = []
    for it in items:
        rel = it["file"].replace("\\", "/")
        abs_path = WORKBUDDY / rel
        date = original_date(rel)
        try:
            text = abs_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            failures.append({"file": rel, "error": type(exc).__name__})
            continue
        try:
            candidates = run(client, text)
        except Exception as exc:
            failures.append({"file": rel, "error": type(exc).__name__})
            continue
        # 剔除块错误占位，给每条候选打溯源字段
        clean = []
        for c in candidates:
            if "__chunk_error__" in c:
                failures.append({"file": rel, "error": "chunk:" + c["__chunk_error__"]})
                continue
            c.setdefault("source_category", "workbuddy-project-memory")
            if date:
                c.setdefault("original_date", date)
            c.setdefault("batch", args.batch)
            clean.append(c)
        results.append({"file": rel, "date": date, "count": len(clean), "candidates": clean})
        print("OK  %-60s  %d 条" % (rel, len(clean)), flush=True)

    total = sum(r["count"] for r in results)
    out = {
        "total_files": len(results),
        "total_candidates": total,
        "failures": failures,
        "items": results,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 汇总 ===")
    print("成功文件: %d，产出候选: %d，失败: %d" % (len(results), total, len(failures)))
    print("输出: %s" % args.out)


if __name__ == "__main__":
    main()
