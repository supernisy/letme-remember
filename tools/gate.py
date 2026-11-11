#!/usr/bin/env python3
"""准出闸门：失败即关闭（fail-closed）的轻量 SpecGate。

用途：在「实现完成 -> 归档」之间加一道脚本硬门禁，不靠人记得检查。
OpenSpec 自带的 validate 只校验规范文件的结构，不检查代码是否兑现场景；
本脚本补上「规范 -> 测试 -> 实现」的连线与「人工批准不可漂移」。

用法：
  python tools/gate.py              # 正式闸门，任一失败即以非零码退出
  python tools/gate.py --shadow     # 影子模式：全部照跑并报告，但不拦截
  python tools/gate.py sign --by 用户   # 固化一次人工批准（只记录，不代替决定）

检查项：
  1. 测试断言未被删除或弱化（对比 git 历史，防「删断言骗绿」）
  2. 23 项任务与 6 份契约场景均有测试点名（需求到测试可追溯）
  3. 单元测试全过
  4. OpenSpec 严格校验通过
  5. 公开文本无真实私人信息与真实凭据
  6. 人工批准记录存在且被批准的规范文件未漂移
  7. 技术探针的残留不确定已显式记录
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
# v1-core-loop 已归档，路径动态解析：优先归档前位置，找不到则落到 archive 目录。
def _resolve_change_path(*parts):
    live = ROOT / "openspec" / "changes" / "v1-core-loop" / Path(*parts)
    if live.exists():
        return live
    archived = list((ROOT / "openspec" / "changes" / "archive").glob("*v1-core-loop"))
    if archived:
        return archived[0] / Path(*parts)
    return live
TASKS = _resolve_change_path("tasks.md")
CHANGE_SPECS = _resolve_change_path("specs")
PROPOSAL = _resolve_change_path("proposal.md")
SIGNOFF = ROOT / "docs" / "spec-gate" / "signoff.json"

SENSITIVE_WORDS = re.compile(r"薪资|职业定位|谈判口径|全栈|前端岗|月薪")
SECRET_SHAPES = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
WEAKENING = re.compile(r"assert\s+True\b|@unittest\.skip|pytest\.mark\.skip|pytest\.skip\b")

SCAN_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".txt"}
SCAN_EXCLUDES = {".git", ".index", ".venv", "__pycache__", "node_modules"}
# 规则表与测试用例里刻意放的是虚构占位值；闸门用「全同字符」识别它们。
SECRET_SAMPLE_EXCLUDES = {"lmr/rules.json"}
TEXT_WORD_EXCLUDES = {"tests", "tools"}


def _is_placeholder(value):
    tail = re.sub(r"^(?:gh[pousr]_|sk-|AKIA)", "", value)
    return bool(tail) and len(set(tail)) <= 1


def _assertion_count(source):
    tree = ast.parse(source)
    total = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Assert))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith("assert") or node.func.attr == "raises":
                total += 1
    return total


def check_assertions():
    """当前断言数不得低于 git 历史基线，且不得出现弱化写法。"""
    problems = []
    files = sorted(TESTS.glob("test_*.py"))
    if not files:
        return False, ["测试目录没有 test_*.py"]
    for path in files:
        current = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        baseline = subprocess.run(
            ["git", "show", "HEAD:%s" % rel], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        before = _assertion_count(baseline.stdout) if baseline.returncode == 0 else 0
        after = _assertion_count(current)
        if after < before:
            problems.append("%s 断言数下降 %d -> %d" % (rel, before, after))
        for number, line in enumerate(current.splitlines(), 1):
            if "# GATE-ALLOW" in line:
                continue
            if WEAKENING.search(line):
                problems.append("%s:%d 出现弱化写法" % (rel, number))
    return not problems, problems


def check_tests():
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    tail = [line for line in result.stdout.splitlines() + result.stderr.splitlines() if line.strip()][-6:]
    return result.returncode == 0, tail


def check_specs():
    try:
        result = subprocess.run(
            "openspec validate --all", cwd=ROOT, shell=True,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError as exc:
        return False, ["无法运行 openspec: %s" % exc]
    output = (result.stdout or "") + (result.stderr or "")
    ok = result.returncode == 0 and "0 failed" in output
    return ok, [line for line in output.splitlines() if "passed" in line or "failed" in line][-3:]


def _walk_texts():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = path.relative_to(ROOT)
        if any(part in SCAN_EXCLUDES for part in rel.parts):
            continue
        yield path, rel.as_posix()


def check_privacy():
    problems = []
    for path, rel in _walk_texts():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if rel.startswith("tests/") or rel in TEXT_WORD_EXCLUDES or path.name == "gate.py":
                pass
            elif SENSITIVE_WORDS.search(line):
                problems.append("%s:%d 出现高敏感示例词" % (rel, number))
            if rel in SECRET_SAMPLE_EXCLUDES or rel.startswith("tests/"):
                continue
            for match in SECRET_SHAPES.finditer(line):
                if not _is_placeholder(match.group(0)):
                    problems.append("%s:%d 出现疑似真实凭据形状" % (rel, number))
                    break
    return not problems, problems


def check_spikes():
    path = ROOT / "docs" / "spikes" / "README.md"
    if not path.is_file():
        return False, ["缺少技术探针记录"]
    text = path.read_text(encoding="utf-8")
    missing = [word for word in ("残留不确定", "尚未验证", "回写位置") if word not in text]
    return not missing, ["探针记录缺少: %s" % "、".join(missing)] if missing else []


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _signed_files():
    files = [PROPOSAL]
    if CHANGE_SPECS.is_dir():
        files += sorted(CHANGE_SPECS.rglob("*.md"))
    return [path for path in files if path.is_file()]


def sign(by):
    """固化一次人工批准。批准权在人；脚本只记录哈希，不产生也不更新批准状态。"""
    SIGNOFF.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "by": by,
        "recorded_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "note": "对既有人工批准的证据固化；批准权属于人，脚本不产生批准决定。任一被批准文件变更都会使本记录失效，需重新确认。",
        "files": {p.relative_to(ROOT).as_posix(): _sha256(p) for p in _signed_files()},
    }
    SIGNOFF.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def check_signoff():
    """签字记录存在、且被批准的规范文件一个字节都没漂移。"""
    if not SIGNOFF.is_file():
        return False, ["缺少人工批准记录；由批准人运行: python tools/gate.py sign --by <批准人>"]
    try:
        data = json.loads(SIGNOFF.read_text(encoding="utf-8"))
    except ValueError:
        return False, ["批准记录不是合法 JSON"]
    if not data.get("by"):
        return False, ["批准记录缺少批准人"]
    problems = []
    recorded = data.get("files", {})
    for rel, digest in recorded.items():
        path = ROOT / rel
        if not path.is_file():
            problems.append("被批准文件缺失: %s" % rel)
        elif _sha256(path) != digest:
            problems.append("漂移（批准后被改动，需重新确认）: %s" % rel)
    current = {p.relative_to(ROOT).as_posix() for p in _signed_files()}
    for rel in sorted(current - set(recorded)):
        problems.append("新增未批准的规范文件: %s" % rel)
    if not problems:
        problems.append("批准人: %s；已锁定 %d 份规范文件" % (data["by"], len(recorded)))
    return not any("漂移" in p or "缺失" in p or "未批准" in p for p in problems), problems


def check_traceability():
    """tasks.md 的每一项任务都必须被测试里的 @req 标签点名。"""
    if not TASKS.is_file():
        return False, ["找不到任务清单 tasks.md"]
    task_ids = set(re.findall(r"^- \[[ x]\] (\d+\.\d+)", TASKS.read_text(encoding="utf-8"), re.M))
    tagged = set()
    for path in TESTS.glob("*.py"):
        tagged.update(re.findall(r"#\s*@req\s+([0-9]+\.[0-9]+)",
                                 path.read_text(encoding="utf-8")))
    missing = sorted(task_ids - tagged, key=lambda value: tuple(int(n) for n in value.split(".")))
    if missing:
        return False, ["以下任务没有测试点名: %s" % "、".join(missing)]
    return True, ["任务 %d 项，全部有测试点名" % len(task_ids)]


CHECKS = [
    ("断言完整性", check_assertions),
    ("需求到测试可追溯", check_traceability),
    ("单元测试", check_tests),
    ("OpenSpec 严格校验", check_specs),
    ("公开文本隐私扫描", check_privacy),
    ("人工批准未漂移", check_signoff),
    ("探针残留不确定已记录", check_spikes),
]


def main():
    parser = argparse.ArgumentParser(description="准出闸门（轻量 SpecGate）")
    parser.add_argument("--shadow", action="store_true", help="影子模式：报告但不拦截")
    sub = parser.add_subparsers(dest="action")
    sign_cmd = sub.add_parser("sign", help="固化一次人工批准")
    sign_cmd.add_argument("--by", required=True, help="批准人标识")
    args = parser.parse_args()
    if args.action == "sign":
        payload = sign(args.by)
        print("已固化人工批准：%s（%d 份规范文件）" % (payload["by"], len(payload["files"])))
        return 0

    all_ok = True
    for name, func in CHECKS:
        ok, detail = func()
        all_ok = all_ok and ok
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        for line in detail[:8]:
            print("       %s" % line)
    if args.shadow:
        print("\nGATE: SHADOW（%s，本次不拦截）" % ("本会通过" if all_ok else "本会拦截"))
        return 0
    print("\nGATE: %s" % ("PASS" if all_ok else "FAIL"))
    if not all_ok:
        print("准出未通过：禁止归档。", file=sys.stderr)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
