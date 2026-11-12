"""宿主集成层（lmr.host）单元测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lmr import host as host_module
from lmr.errors import ValidationError
from lmr.host.workbuddy import WorkBuddyAdapter


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

        # 用 fake paths（install 只用到生成脚本，不真正读 paths）。
        self.paths = mock.Mock()

    def test_install_generates_scripts_and_registers(self):
        adapter = WorkBuddyAdapter()
        result = adapter.install(self.paths)
        # 生成了两个脚本
        self.assertTrue(result["stop_script"].endswith("lmr_stop.py"))
        self.assertTrue(result["start_script"].endswith("lmr_session_start.py"))
        # 注册了两个 hook
        self.assertTrue(result["registered"]["stop"])
        self.assertTrue(result["registered"]["session_start"])

    def test_install_idempotent(self):
        adapter = WorkBuddyAdapter()
        adapter.install(self.paths)
        result = adapter.install(self.paths)  # 第二次
        # 已注册，不重复添加
        self.assertFalse(result["registered"]["stop"])
        self.assertFalse(result["registered"]["session_start"])

    def test_on_session_start_returns_inject(self):
        adapter = WorkBuddyAdapter()
        self.assertIn("inject", adapter.on_session_start())

    def test_on_session_end_returns_distill(self):
        adapter = WorkBuddyAdapter()
        self.assertIn("batch-distill", adapter.on_session_end("/tmp/transcript.txt"))
