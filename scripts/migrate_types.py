"""一次性存量迁移：type 从旧九类 -> CoALA 三类，并重命名文件前缀。

可回退：数据目录在 git 管理下，迁移后单独提交；回退 = git reset 到迁移前。
用法：py -3.14 scripts/migrate_types.py [--data-dir PATH] [--dry-run]
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# 不依赖 lmr 包（独立可跑），直接内联映射与类型集合。
LEGACY_MAP = {
    "profile": "semantic", "preference": "semantic", "entity": "semantic",
    "decision": "semantic", "fact": "semantic", "experience": "semantic",
    "event": "episodic", "reference": "episodic",
    "procedure": "procedural",
}
THREE_TYPES = {"semantic", "episodic", "procedural"}


def migrate_one(f: Path) -> tuple[str, str, bool]:
    """迁移单个文件，返回 (原前缀, 新前缀, 是否改动)。"""
    stem = f.stem
    if "--" not in stem:
        return "", "", False
    old_prefix, rest = stem.split("--", 1)
    if old_prefix not in LEGACY_MAP:
        return old_prefix, old_prefix, False
    new_prefix = LEGACY_MAP[old_prefix]
    if old_prefix == new_prefix:
        return old_prefix, new_prefix, False

    text = f.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r"(?m)^type:[ \t]*" + re.escape(old_prefix) + r"$",
        "type: " + new_prefix,
        text,
    )
    if n != 1:
        raise RuntimeError("type 行替换次数 %d（文件 %s）" % (n, f.name))

    f.write_text(new_text, encoding="utf-8")
    f.rename(f.parent / ("%s--%s.md" % (new_prefix, rest)))
    return old_prefix, new_prefix, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(Path.home() / ".letme-remember" / "data"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    store = Path(args.data_dir) / "store"
    if not store.is_dir():
        print("数据目录不存在:", store)
        sys.exit(1)

    files = sorted(store.glob("*.md"))
    plan = Counter()
    changed = 0
    for f in files:
        old, new, _ = migrate_one(f) if not args.dry_run else (f.stem.split("--", 1)[0], "", False)
        if args.dry_run:
            old = f.stem.split("--", 1)[0] if "--" in f.stem else ""
            new = LEGACY_MAP.get(old, old)
        if old != new:
            changed += 1
        plan[old + " -> " + new] += 1

    print("文件总数:", len(files))
    print("迁移（或待迁移）条数:", changed)
    print("分布:")
    for k, v in sorted(plan.items(), key=lambda kv: -kv[1]):
        print("  %4d  %s" % (v, k))


if __name__ == "__main__":
    main()
