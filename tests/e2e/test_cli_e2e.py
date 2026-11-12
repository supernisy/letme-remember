"""命令行接口与端到端验收：六个命令、退出码、按标识读正文、依赖降级、README 闭环。"""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lmr import cli

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
SENSITIVE = re.compile(r"薪资|职业定位|谈判|公司|前端|全栈|月薪|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}")

# @req 1.4 @req 5.1 @req 5.2 @req 5.3 @req 6.1 @req 6.2 @req 6.3


class TestCliE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = os.environ.copy()
        self.env["LMR_DATA_DIR"] = self.tmp.name
        init = self.run_mem("init")
        self.assertEqual(init.returncode, 0, init.stderr)

    def run_mem(self, *args, extra_env=None):
        env = dict(self.env)
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(ROOT / "mem.py"), *args],
            cwd=str(ROOT), env=env, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        )

    def test_dependency_declaration_and_degradation(self):
        # @req 1.4
        requirement = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("==", requirement, "依赖必须固定版本，避免写入端与查询端分词漂移")
        self.assertEqual(self.run_mem("record", "--name", "降级测试", "--abstract",
                                      "虚构：长期记忆采用纯文本", "--type", "fact",
                                      "--conclusion", "记忆以文件保存", "--reason",
                                      "便于本地检索").returncode, 0)
        degraded = self.run_mem("recall", "记忆", extra_env={"LMR_DISABLE_TOKENIZER": "1"})
        self.assertEqual(degraded.returncode, 0, degraded.stderr)
        self.assertTrue(json.loads(degraded.stdout))

    def test_six_commands(self):
        # @req 5.1
        for command in ("record", "recall", "show", "invalidate", "rebuild", "list"):
            result = self.run_mem(command, "--help")
            self.assertEqual(result.returncode, 0, "%s --help 失败" % command)
            self.assertIn("usage", result.stdout.lower())
        written = json.loads(self.run_mem(
            "record", "--name", "端到端条目", "--abstract", "虚构：记忆写入与检索",
            "--type", "decision", "--conclusion", "记忆以纯文本文件保存",
            "--reason", "便于版本管理与本地检索",
        ).stdout)
        self.assertEqual(self.run_mem("recall", "记忆").returncode, 0)
        self.assertEqual(self.run_mem("show", written["id"]).returncode, 0)
        self.assertEqual(self.run_mem("invalidate", written["id"], "--by", "新条目").returncode, 0)
        self.assertEqual(self.run_mem("rebuild").returncode, 0)
        self.assertEqual(self.run_mem("list").returncode, 0)

    def test_exit_codes(self):
        # @req 5.2
        self.assertEqual(self.run_mem("list").returncode, 0)
        invalid = self.run_mem("record", "--name", "缺少理由", "--abstract", "摘要",
                               "--type", "fact", "--conclusion", "只有结论")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("理由", invalid.stderr)
        not_found = self.run_mem("show", "不存在的标识")
        self.assertEqual(not_found.returncode, 3)
        def boom(args):
            raise RuntimeError("boom")

        err = io.StringIO()
        with patch.dict(cli.HANDLERS, {"list": boom}):
            with contextlib.redirect_stderr(err):
                code = cli.main(["list"])
        self.assertEqual(code, 4)
        self.assertIn("内部错误", err.getvalue())
        self.assertNotIn("AKIA", err.getvalue())

    def test_show_by_locator(self):
        # @req 5.3
        written = json.loads(self.run_mem(
            "record", "--name", "按标识读取", "--abstract", "虚构：定位标识读取正文",
            "--type", "fact", "--conclusion", "结论内容",
            "--reason", "理由内容",
        ).stdout)
        shown = self.run_mem("show", written["id"])
        self.assertEqual(shown.returncode, 0)
        self.assertIn("结论内容", shown.stdout)
        self.assertIn("理由内容", shown.stdout)

    def test_acceptance_record_exists(self):
        # @req 6.1
        record = ROOT / "docs" / "v1-acceptance.md"
        self.assertTrue(record.is_file())
        text = record.read_text(encoding="utf-8")
        self.assertIn("§7", text)
        self.assertIn("后续提案", text)

    def test_public_text_has_no_private_instances(self):
        # @req 6.2
        targets = [ROOT / "README.md", ROOT / "需求定稿.md", ROOT / "examples" / "sample_memory.md"]
        targets += sorted((ROOT / "docs").rglob("*.md"))
        targets += sorted((ROOT / "openspec" / "specs").rglob("*.md"))
        for path in targets:
            if not path.is_file():
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(
                    SENSITIVE.search(line),
                    "%s:%d 出现高敏感示例词或疑似真实凭据" % (path.name, number),
                )

    def test_readme_walkthrough(self):
        # @req 6.3
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for command in ("mem init", "mem record", "mem recall", "隐私", "降级"):
            self.assertIn(command, readme)
        # 按 README 的顺序从零跑通一次写入与一次检索
        with tempfile.TemporaryDirectory() as folder:
            env = {"LMR_DATA_DIR": folder}
            self.assertEqual(self.run_mem("init", extra_env=env).returncode, 0)
            written = self.run_mem(
                "record", "--name", "文档示例", "--abstract", "虚构：文档示例条目",
                "--type", "fact", "--conclusion", "示例结论", "--reason", "示例理由",
                extra_env=env,
            )
            self.assertEqual(written.returncode, 0, written.stderr)
            found = self.run_mem("recall", "示例", extra_env=env)
            self.assertEqual(found.returncode, 0)
            self.assertTrue(json.loads(found.stdout))
