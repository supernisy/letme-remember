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
CHUNK_BYTES = 12000  # 单块上限，超过按段落切（改小以避免大文件单块输出失控）
# 原始档案（求职复盘/岗位分析）的已知根目录，用于 reference 路径回填。
ARCHIVE_ROOTS = [
    Path(r"C:\Users\super\WorkBuddy\2026-09-23-15-46-13\job-search"),
]


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


def _extract_fname(conclusion: str) -> str:
    """从 reference 的 conclusion 里提取文件名（形如 `xx.md` 或 `xx-YYYYMMDD.md`）。"""
    m = re.search(r"([\w\u4e00-\u9fff｜\-]+\.md)", conclusion)
    return m.group(1) if m else ""


def resolve_reference_path(candidate: dict) -> dict:
    """给 reference 条目回填真实绝对路径（source 字段）。

    策略：优先用 conclusion 里 LLM 抄的文件名精确匹配；匹配不到再用
    ref_subject / abstract 里的关键词做文件名模糊匹配。都失败则 source 留空，
    由人审阶段兜底。保证不产出「LLM 瞎猜的死指针」。
    """
    if candidate.get("type") != "reference":
        return candidate

    conclusion = candidate.get("conclusion", "")
    fname = _extract_fname(conclusion)
    resolved = None

    # 1) 精确文件名匹配（跨所有档案根目录）
    if fname:
        for root in ARCHIVE_ROOTS:
            if not root.is_dir():
                continue
            hit = root / fname
            if hit.is_file():
                resolved = str(hit)
                break
            # 也允许子目录里的同名文件
            if not resolved:
                for p in root.rglob(fname):
                    if p.is_file():
                        resolved = str(p)
                        break
                if resolved:
                    break

    # 2) 关键词模糊匹配：用 subject/abstract 的汉字串去文件名里找
    if not resolved:
        subject = candidate.get("ref_subject") or candidate.get("abstract") or ""
        # 提取连续汉字片段作为关键词
        keys = re.findall(r"[\u4e00-\u9fff]{2,}", subject)
        if keys:
            for root in ARCHIVE_ROOTS:
                if not root.is_dir():
                    continue
                for p in root.rglob("*.md"):
                    name = p.name
                    if any(k in name for k in keys if len(k) >= 2):
                        resolved = str(p)
                        break
                if resolved:
                    break

    if resolved:
        # reference 的身份键是 (source, subject)，source 存真实路径。
        candidate["source"] = resolved
        candidate["_path_resolved"] = True
    else:
        candidate["_path_resolved"] = False
    return candidate


def main():
    parser = argparse.ArgumentParser(description="批量蒸馏旧记忆文件（dry-run）")
    parser.add_argument("--inventory", default=str(Path(r"C:\Users\super\WorkBuddy\2026-11-10-20-12-59\盘点清单.json")))
    parser.add_argument("--out", default=str(Path(r"C:\Users\super\WorkBuddy\2026-11-10-20-12-59\distill-candidates.json")))
    parser.add_argument("--data-dir", default=None, help="记忆数据目录（默认 ~/.letme-remember/data）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个文件（0=全部），用于小样本试蒸")
    parser.add_argument("--only", default="", help="只处理文件名包含该子串的文件（重蒸用）")
    parser.add_argument("--model", default="", help="覆盖配置里的 llm_model（换强模型试蒸用）")
    parser.add_argument("--batch", default="import-legacy-batch-01", help="导入批次标识")
    args = parser.parse_args()

    paths = config.Paths(config.resolve_data_dir(args.data_dir))
    settings = config.settings_for(paths.root)
    data_config = config._data_config(paths.root)
    if args.model:
        settings["llm_model"] = args.model
    client = llm.make_client(settings, data_config)

    items = load_a_items(Path(args.inventory))
    if args.only:
        items = [it for it in items if args.only in it["file"]]
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
            # reference 条目：回填真实磁盘路径（不靠 LLM 猜）
            c = resolve_reference_path(c)
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
