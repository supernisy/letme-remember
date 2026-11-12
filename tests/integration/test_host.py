"""宿主集成层（lmr.host）单元测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lmr import host as host_module
from lmr.errors import ValidationError
from lmr.host.workbuddy import WorkBuddyAdapter, REPO_ROOT

import pytest

pytestmark = pytest.mark.integration


class HostRegistryTest(unittest.TestCase):
    def test_get_host_workbuddy(self):
        adapter = host_module.get_host("workbuddy")
        self.assertIsInstance(adapter, WorkBuddyAdapter)
        self.assertEqual(adapter.name, "workbuddy")

    def test_get_host_unknown(self):
        with self.assertRaises(ValidationError):
            host_module.get_host("nonexistent")

    def test_available_hosts(self):
        self.assertIn("workbuddy", host_module.available_hosts())


class WorkBuddyAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # 把 WB_DIR/WB_SETTINGS 指到临时目录，避免污染真实配置。
        self.wb_dir = Path(self.tmp.name) / "wb"
        self.wb_dir.mkdir()
        self.settings_path = self.wb_dir / "settings.json"
        self.hooks_dir = self.wb_dir / "hooks"

        patcher_dir = mock.patch.object(host_module.workbuddy, "WB_DIR", self.wb_dir)
        patcher_settings = mock.patch.object(host_module.workbuddy, "WB_SETTINGS", self.settings_path)
        patcher_hooks = mock.patch.object(host_module.workbuddy, "WB_HOOKS_DIR", self.hooks_dir)
        self.addCleanup(patcher_dir.stop)
        self.addCleanup(patcher_settings.stop)
        self.addCleanup(patcher_hooks.stop)
        patcher_dir.start()
        patcher_settings.start()
        patcher_hooks.start()

        # fake paths：只需 root（数据目录）真实存在即可。
        self.paths = mock.Mock()
        self.paths.root = Path(self.tmp.name) / "data"
        self.paths.root.mkdir()

    def test_install_generates_scripts_and_registers(self):
        adapter = WorkBuddyAdapter()
        result = adapter.install(self.paths)
        # 生成了两个脚本（stop 蒸馏 + recall 注入）
        self.assertTrue(result["stop_script"].endswith("lmr_stop.py"))
        self.assertTrue(result["recall_script"].endswith("lmr_recall.py"))
        # 注册了两个 hook（Stop + UserPromptSubmit）
        self.assertTrue(result["registered"]["Stop"])
        self.assertTrue(result["registered"]["UserPromptSubmit"])

    def test_install_idempotent(self):
        adapter = WorkBuddyAdapter()
        adapter.install(self.paths)
        result = adapter.install(self.paths)  # 第二次
        # 已注册，不重复添加
        self.assertFalse(result["registered"]["Stop"])
        self.assertFalse(result["registered"]["UserPromptSubmit"])

    def test_on_recall_returns_recall(self):
        adapter = WorkBuddyAdapter()
        self.assertIn("recall", adapter.on_recall())

    def test_on_capture_returns_capture(self):
        adapter = WorkBuddyAdapter()
        self.assertIn("capture", adapter.on_capture("/tmp/transcript.txt"))

    def test_stop_script_uses_real_mem_py_and_transcript_from_stdin(self):
        adapter = WorkBuddyAdapter()
        script = adapter._stop_script(self.paths)
        # mem.py 用代码仓库根的路径（%r 格式化为 repr，含转义），
        # 断言 mem.py 关键字与 repo 名同时出现即可。
        self.assertIn("mem.py", script)
        self.assertIn(REPO_ROOT.name, script)
        # 从 stdin 读 transcript_path，无占位符
        self.assertIn("transcript_path", script)
        self.assertNotIn("TRANSCRIPT_PLACEHOLDER", script)
        self.assertIn("batch-distill", script)
        self.assertIn("--dry-run", script)

    def test_recall_script_calls_inject(self):
        adapter = WorkBuddyAdapter()
        script = adapter._recall_script(self.paths)
        self.assertIn("inject", script)
        self.assertIn("mem.py", script)
        self.assertIn("--data-dir", script)

    def test_register_writes_valid_settings_json(self):
        adapter = WorkBuddyAdapter()
        adapter.install(self.paths)
        # settings.json 是合法 JSON，且 hooks 含 Stop 和 UserPromptSubmit
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertIn("Stop", data["hooks"])
        self.assertIn("UserPromptSubmit", data["hooks"])
        # 每个 hook 都是 command 类型
        for entry in data["hooks"]["Stop"]:
            for hook in entry["hooks"]:
                self.assertEqual(hook["type"], "command")
