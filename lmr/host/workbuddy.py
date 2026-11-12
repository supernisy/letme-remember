"""WorkBuddy 宿主适配器。

把 WorkBuddy 的会话边界事件（Stop / SessionStart）映射到 lmr 引擎的统一
接口。hook 脚本是薄壳：只负责把事件转换成对 mem.py 的调用，记忆逻辑
全在引擎里。

hook 注册位置：~/.workbuddy/settings.json 的 hooks 键。
hook 命令格式：<workbuddy-python> <脚本路径>，type=command。
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import HostAdapter

# WorkBuddy 的用户级配置与 hook 目录。
WB_DIR = Path.home() / ".workbuddy"
WB_SETTINGS = WB_DIR / "settings.json"
WB_HOOKS_DIR = WB_DIR / "hooks"
WB_PYTHON = "C:/Users/super/.workbuddy/binaries/python/envs/default/Scripts/python.exe"


def _hook_script_path(name):
    return WB_HOOKS_DIR / ("lmr_%s.py" % name)


class WorkBuddyAdapter(HostAdapter):
    name = "workbuddy"

    def on_session_start(self) -> str:
        """会话开始注入：调用 mem.py inject，读 MEMORY.md 索引（零模型零网络）。"""
        return "python -m lmr inject"

    def on_session_end(self, transcript_path: str) -> str:
        """会话结束蒸馏：调用 mem.py batch-distill，后台异步执行。"""
        return "python -m lmr batch-distill --file %s --dry-run" % transcript_path

    def install(self, paths) -> dict:
        """生成 hook 脚本并注册到 WorkBuddy settings.json，幂等。"""
        WB_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
        installed = {}

        # 1. 生成 Stop hook 脚本（会话结束 → 后台蒸馏）。
        stop_script = _hook_script_path("stop")
        stop_script.write_text(self._stop_script(paths), encoding="utf-8")
        installed["stop_script"] = str(stop_script)

        # 2. 生成 SessionStart hook 脚本（会话开始 → 注入）。
        start_script = _hook_script_path("session_start")
        start_script.write_text(self._start_script(paths), encoding="utf-8")
        installed["start_script"] = str(start_script)

        # 3. 注册到 settings.json（幂等：已存在则跳过）。
        registered = self._register_hooks()
        installed.update(registered)
        return installed

    def _stop_script(self, paths) -> str:
        """Stop hook：会话结束触发，后台异步蒸馏，不阻塞对话。"""
        return '''"""WorkBuddy Stop hook：会话结束后台异步蒸馏，不阻塞对话。

薄壳：只把 Stop 事件转成对 mem.py 的调用；蒸馏逻辑在 lmr 引擎里。
后台执行，快速返回，避免拖慢会话收尾。
"""
import subprocess
import sys

# 后台异步跑蒸馏（dry-run 只产候选，不入库，交给待审队列）。
cmd = [sys.executable, "-m", "lmr", "batch-distill", "--dry-run", "--file", "TRANSCRIPT_PLACEHOLDER"]
subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
'''

    def _start_script(self, paths) -> str:
        """SessionStart hook：会话开始注入记忆索引。"""
        return '''"""WorkBuddy SessionStart hook：会话开始注入记忆索引。

薄壳：只把 SessionStart 事件转成对 mem.py inject 的调用；
注入读 MEMORY.md（一句话目录），零模型零网络。
"""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "lmr", "inject"],
    capture_output=True, text=True, encoding="utf-8",
)
# 注入内容写到 stdout，供宿主塞进上下文。
print(result.stdout, end="")
'''

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
        start_path = str(_hook_script_path("session_start"))

        added = {"stop": False, "session_start": False}

        # Stop 事件：追加一个 hook（若未注册）。
        stop_entries = hooks.setdefault("Stop", [])
        if not self._already_registered(stop_entries, stop_path):
            stop_entries.append({
                "hooks": [{"type": "command", "command": "%s %s" % (WB_PYTHON, stop_path), "timeout": 5}],
            })
            added["stop"] = True

        # SessionStart 事件：追加一个 hook（若未注册）。
        start_entries = hooks.setdefault("SessionStart", [])
        if not self._already_registered(start_entries, start_path):
            start_entries.append({
                "hooks": [{"type": "command", "command": "%s %s" % (WB_PYTHON, start_path), "timeout": 10}],
            })
            added["session_start"] = True

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
