"""一次性存量迁移：为历史记忆补 host（宿主）字段，从 author 前缀推导。

host 与 author 解耦（方向②「库内多宿主冲突仲裁」）：author 存「谁写的」，
host 存「哪来的」（归一化宿主标识）。存量数据的 author 是导入来源标识，
据此推导：import:workbuddy-* -> workbuddy；user-direct -> manual。

只补 host，不改 author / provenance，不破坏历史审计。数据目录在 git 管理下，
迁移后单独提交；回退 = git reset 到迁移前。

用法：py -3.14 scripts/migrate_host.py [--data-dir PATH] [--dry-run]
"""
import argparse
import sys
from pathlib import Path

# 不依赖 lmr 包（独立可跑），直接内联归一化逻辑，与 lmr/schema.py 保持一致。
def infer_host(author: str) -> str:
    if not author:
        return ""
    text = author.strip()
    if text.startswith("import:workbuddy") or text.startswith("workbuddy"):
        return "workbuddy"
    if "user-direct" in text:
        return "manual"
    return ""


def migrate_one(f: Path, dry_run: bool = False) -> tuple[str, str, bool]:
    """迁移单个文件，返回 (原 host 值, 新 host 值, 是否改动)。dry_run 时不写盘。"""
    text = f.read_text(encoding="utf-8")
    lines = text.splitlines()

    author = ""
    host_idx = None
    for i, line in enumerate(lines):
        if line.startswith("author:"):
            author = line.split(":", 1)[1].strip()
        elif line.startswith("host:"):
            host_idx = i

    new_host = infer_host(author)
    if host_idx is not None:
        old = lines[host_idx].split(":", 1)[1].strip()
        if old == new_host:
            return old, new_host, False
        lines[host_idx] = "host: %s" % new_host
    else:
        # 旧文件没有 host 字段，在 author 行之后插入一行（保持字段顺序接近）。
        # 找不到 author 行则在 provenance 行之后或文件头末尾插入。
        insert_at = None
        for i, line in enumerate(lines):
            if line.startswith("author:"):
                insert_at = i + 1
                break
        if insert_at is None:
            for i, line in enumerate(lines):
                if line.startswith("provenance:"):
                    insert_at = i + 1
                    break
        if insert_at is None:
            return "", new_host, False
        lines.insert(insert_at, "host: %s" % new_host)
        old = ""

    if not dry_run:
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return old, new_host, True


def main():
    parser = argparse.ArgumentParser(description="存量 host 回填")
    parser.add_argument("--data-dir", default=str(Path.home() / ".letme-remember" / "data"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    store_dir = Path(args.data_dir) / "store"
    if not store_dir.is_dir():
        print("数据目录不存在: %s" % store_dir, file=sys.stderr)
        return 1

    files = sorted(store_dir.glob("*.md"))
    changed = []
    unchanged = 0
    empty = 0
    for f in files:
        old, new, did = migrate_one(f, dry_run=args.dry_run)
        if did:
            changed.append((f.name, old, new))
        elif not new:
            empty += 1
        else:
            unchanged += 1

    print("共 %d 条，改动 %d 条，已一致 %d 条，无法推导 %d 条"
          % (len(files), len(changed), unchanged, empty))
    if changed:
        print("改动样例：")
        for name, old, new in changed[:10]:
            print("  %s: '%s' -> '%s'" % (name, old or "(无)", new))
        if len(changed) > 10:
            print("  ... 共 %d 条" % len(changed))
    if empty:
        print("注意：%d 条无法从 author 推导 host，需人工补。" % empty)

    if args.dry_run:
        print("（dry-run：未写盘）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
