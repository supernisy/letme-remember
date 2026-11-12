"""WorkBuddy 宿主适配器。

把 WorkBuddy 的会话边界事件映射到 lmr 引擎的统一接口。hook 脚本是薄壳：
只负责把事件转换成对 mem.py 的调用，记忆逻辑全在引擎里。

真实 hook 规范（WorkBuddy / CodeBuddy Code 同源）：
- 事件：SessionStart / SessionEnd / Stop / UserPromptSubmit / PreToolUse ...
- hook 脚本从 stdin 读取 JSON，含 transcript_path / session_id 等字段；
- 配置在 ~/.workbuddy/settings.json 的 hooks 键，命令为
  <workbuddy-python> <脚本路径>，type=command。

本适配器的动作映射：
- on_recall（读/注入）→ UserPromptSubmit（用户每次提问时召回相关记忆）；
- on_capture（写/蒸馏）→ Stop（会话结束，从 transcript_path 蒸馏）。
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import HostAdapter

# 代码仓库根：本文件位于 <repo>/lmr/host/，上溯两级即仓库根（mem.py 所在）。
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# WorkBuddy 的用户级配置与 hook 目录。
WB_DIR = Path.home() / ".workbuddy"
WB_SETTINGS = WB_DIR / "settings.json"
WB_HOOKS_DIR = WB_DIR / "hooks"
WB_PYTHON = "C:/Users/super/.workbuddy/binaries/python/envs/default/Scripts/python.exe"


def _hook_script_path(name):
    return WB_HOOKS_DIR / ("lmr_%s.py" % name)


class WorkBuddyAdapter(HostAdapter):
    name = "workbuddy"

    def on_recall(self) -> str:
        """读路径：召回相关记忆注入宿主上下文（挂 UserPromptSubmit）。"""
        return "recall"

    def on_capture(self, transcript_path: str) -> str:
        """写路径：捕获会话记录后台异步蒸馏（挂 Stop）。"""
        return "capture %s" % transcript_path

    def install(self, paths) -> dict:
        """生成 hook 脚本并注册到 WorkBuddy settings.json，幂等。"""
        WB_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
        installed = {}

        # 1. 生成 Stop hook 脚本（会话结束 → 后台蒸馏）。
        stop_script = _hook_script_path("stop")
        stop_script.write_text(self._stop_script(paths), encoding="utf-8")
        installed["stop_script"] = str(stop_script)

        # 2. 生成 UserPromptSubmit hook 脚本（提问 → 召回注入）。
        recall_script = _hook_script_path("recall")
        recall_script.write_text(self._recall_script(paths), encoding="utf-8")
        installed["recall_script"] = str(recall_script)

        # 3. 注册到 settings.json（幂等：已存在则跳过）。
        registered = self._register_hooks()
        installed.update(registered)
        return installed

    def _stop_script(self, paths) -> str:
        """Stop hook：从 stdin 读 transcript_path，后台异步蒸馏，不阻塞。"""
        mem_py = str(REPO_ROOT / "mem.py")
        data_dir = str(paths.root)
        return '''"""WorkBuddy Stop hook：会话结束后台异步蒸馏，不阻塞对话。

薄壳：从 stdin 读 hook JSON 拿 transcript_path，转成对 mem.py
batch-distill 的调用；蒸馏逻辑在 lmr 引擎里。后台执行，快速返回。
"""
import json
import subprocess
import sys

MEM_PY = %r
DATA_DIR = %r

try:
    payload = json.loads(sys.stdin.read())
    transcript = payload.get("transcript_path") or ""
except Exception:
    transcript = ""

if transcript:
    cmd = [sys.executable, MEM_PY, "batch-distill", "--data-dir", DATA_DIR,
           "--file", transcript, "--dry-run"]
    # 后台异步执行（dry-run 只产候选，不入库，交给待审队列）。
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
''' % (mem_py, data_dir)

    def _recall_script(self, paths) -> str:
        """UserPromptSubmit hook：召回相关记忆注入上下文。"""
        mem_py = str(REPO_ROOT / "mem.py")
        data_dir = str(paths.root)
        return '''"""WorkBuddy UserPromptSubmit hook：召回相关记忆注入上下文。

薄壳：调用 mem.py inject 输出记忆目录（一句话摘要），零模型零网络。
stdout 作为 additionalContext 注入宿主本轮上下文。
"""
import subprocess
import sys

MEM_PY = %r
DATA_DIR = %r

result = subprocess.run(
    [sys.executable, MEM_PY, "inject", "--data-dir", DATA_DIR],
    capture_output=True, text=True, encoding="utf-8",
)
print(result.stdout, end="")
''' % (mem_py, data_dir)

    def _register_hooks(self) -> dict:
        """把 hook 注册进 settings.json，幂等（已存在则跳过）。"""
        if not WB_SETTINGS.is_file():
            settings = {}
        else:
            try:
                settings = json.loads(WB_SETTINGS.read_text(encoding="utf-8"))
            except ValueError:
                settings = {}
        hooks = settings.setdefault("hooks", {})
        stop_path = str(_hook_script_path("stop"))
        recall_path = str(_hook_script_path("recall"))

        added = {"Stop": False, "UserPromptSubmit": False}

        # Stop 事件：追加一个 hook（若未注册）。
        stop_entries = hooks.setdefault("Stop", [])
        if not self._already_registered(stop_entries, stop_path):
            stop_entries.append({
                "hooks": [{"type": "command", "command": "%s %s" % (WB_PYTHON, stop_path), "timeout": 5}],
            })
            added["Stop"] = True

        # UserPromptSubmit 事件：追加一个 hook（若未注册）。
        recall_entries = hooks.setdefault("UserPromptSubmit", [])
        if not self._already_registered(recall_entries, recall_path):
            recall_entries.append({
                "hooks": [{"type": "command", "command": "%s %s" % (WB_PYTHON, recall_path), "timeout": 15}],
            })
            added["UserPromptSubmit"] = True

        settings["hooks"] = hooks
        WB_SETTINGS.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"registered": added}

    @staticmethod
    def _already_registered(entries, script_path):
        for entry in entries:
            for hook in entry.get("hooks", []):
                if script_path in hook.get("command", ""):
                    return True
        return False
