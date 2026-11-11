"""只读盘点：扫描 WorkBuddy 项目级记忆文件，分类并抽取候选结论预览。

分类遵循业界标准（secret value vs reference 分离）：
- 真实密钥值（sk-/ghp_ 等）→ 高敏感，禁止入库
- 密钥文件路径/引用 → 可入库（是引用不是值），标注"引用"
- 用户名绝对路径段 → 泛化处理，标注"含用户名路径"
- 叙述性提及（Token Plan 套餐名等）→ 不敏感，误报

不修改任何源文件，只输出一份盘点清单（JSON）。
"""
import json
import re
from pathlib import Path

WORKBUDDY = Path(r"C:\Users\super\WorkBuddy")

# 真实凭据值（业界公认前缀 + 长随机串）
REAL_SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)

# 指向凭据文件的路径（可入库的「引用」）
SECRET_FILE_RE = re.compile(
    r"[\w./\\-]*(bailian_config|config)\.json|credentials\.json|\.env|"
    r"settings\.local\.json|keyring|gh\.exe|PAT\s*(?:存|在|位于)",
    re.IGNORECASE,
)

# 含用户名段的本机绝对路径（需泛化）
USER_PATH_RE = re.compile(r"C:\\Users\\[A-Za-z0-9_.-]+")

# 结论句特征
CONCLUSION_HINT = re.compile(
    r"^(#+|\s*[-*]|\d+\.)\s*.*(约定|结论|决定|规则|经验|注意|踩坑|教训|修复|"
    r"配置|必须|应当|不要|禁止|避免|已|改为|不再|需要|建议|卡点|踩过|坑)",
)


def classify(text: str) -> tuple[str, str, list]:
    """返回 (类别, 备注, 命中片段)。类别：secret值 / 引用 / 泛化 / A可蒸馏 / B流水账。"""
    flags = []
    real = REAL_SECRET_RE.findall(text)
    if real:
        return "SECRET", "含真实密钥值，禁止入库", real[:3]
    secret_file = SECRET_FILE_RE.findall(text)
    if secret_file:
        flags.append("含密钥文件引用(可记)")
    user_path = USER_PATH_RE.findall(text)
    if user_path:
        flags.append("含用户名绝对路径(需泛化)")
    if flags:
        return "REFERENCE", "; ".join(flags), []
    lines = [l for l in text.splitlines() if l.strip()]
    hint_lines = [l for l in lines if CONCLUSION_HINT.search(l)]
    if len(hint_lines) >= 2:
        return "A", "含 %d 处结论特征句" % len(hint_lines), []
    return "B", "以过程流水/指针为主", []


def scan():
    results = []
    mem_files = []
    for p in WORKBUDDY.rglob(".workbuddy/memory/*.md"):
        if p.is_file():
            mem_files.append(p)
    for p in sorted(mem_files):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        cat, note, flags = classify(text)
        hints = []
        for line in text.splitlines():
            if CONCLUSION_HINT.search(line) and line.strip():
                hints.append(line.strip()[:80])
            if len(hints) >= 3:
                break
        rel = p.relative_to(WORKBUDDY)
        results.append({
            "file": str(rel),
            "category": cat,
            "note": note,
            "flags": flags,
            "bytes": len(text.encode("utf-8")),
            "hints": hints,
        })
    return results


def main():
    results = scan()
    stats = {}
    for r in results:
        stats[r["category"]] = stats.get(r["category"], 0) + 1
    out = {"total": len(results), "stats": stats, "items": results}
    out_path = Path(r"C:\Users\super\WorkBuddy\2026-11-10-20-12-59\盘点清单.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total": len(results), "stats": stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
