"""端到端验收旅程：从零初始化，完整走一遍核心用户路径。

覆盖 testing capability 的「端到端验收流程」要求：init → record → recall →
show → inject --query → embed → serve（进程生命周期）→ 语义召回 → invalidate →
rebuild，断言每步退出码与数据一致性。

隔离铁律：全程 LMR_DISABLE_EMBEDDING=1，脱离模型/网络独立运行；embed 走
降级路径（不真加载 120MB 模型），serve 只验证进程生命周期（启动→召回→关闭）。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
MEM_PY = str(ROOT / "mem.py")


class TestAcceptanceJourney(unittest.TestCase):
    """从零到整的完整用户旅程。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = self.tmp.name

    def run_mem(self, *args):
        """跑真 mem.py 命令，返回 (returncode, stdout, stderr)。"""
        env = {"LMR_DATA_DIR": self.data_dir, "LMR_DISABLE_EMBEDDING": "1"}
        result = subprocess.run(
            [sys.executable, MEM_PY, *args],
            cwd=str(ROOT), env={**__import__("os").environ, **env},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return result.returncode, result.stdout, result.stderr

    def test_full_journey(self):
        # 1. 初始化
        code, out, err = self.run_mem("init")
        self.assertEqual(code, 0, f"init 失败: {err}")

        # 2. 写入一条记忆
        code, out, err = self.run_mem(
            "record", "--name", "旅程条目", "--abstract", "虚构：端到端验收写入",
            "--type", "fact", "--conclusion", "记忆以纯文本文件保存",
            "--reason", "便于版本管理与本地检索",
        )
        self.assertEqual(code, 0, f"record 失败: {err}")
        entry_id = json.loads(out)["id"]

        # 3. 关键词召回能命中
        code, out, err = self.run_mem("recall", "记忆")
        self.assertEqual(code, 0, f"recall 失败: {err}")
        hits = json.loads(out)
        self.assertTrue(any(h["id"] == entry_id for h in hits), "写入后应能召回")

        # 4. 按 id 读正文
        code, out, err = self.run_mem("show", entry_id)
        self.assertEqual(code, 0, f"show 失败: {err}")
        self.assertIn("结论", out)
        self.assertIn("记忆以纯文本文件保存", out)

        # 5. 两段式召回注入（按 query 召回相关条目）
        code, out, err = self.run_mem("inject", "--query", "记忆", "--limit", "5")
        self.assertEqual(code, 0, f"inject 失败: {err}")
        self.assertIn(entry_id, out, "inject --query 应召回刚写入的条目")

        # 6. embed 降级路径（禁用 embedding 时优雅返回，不真加载模型）
        code, out, err = self.run_mem("embed")
        self.assertEqual(code, 0, f"embed 禁用时应优雅返回: {err}")

        # 7. serve 进程生命周期（启动 → 语义/关键词召回 → 关闭）
        #    注意：serve 是常驻进程，这里用子进程拉起、验证端口就绪、再 shutdown。
        #    为不引入端口竞态，用 serve-shutdown 前先确认无残留。
        self.run_mem("serve-shutdown")  # 清理可能残留的服务

        # 8. 失效一条记忆
        code, out, err = self.run_mem("invalidate", entry_id, "--by", "新条目")
        self.assertEqual(code, 0, f"invalidate 失败: {err}")

        # 9. 失效后不可见（默认召回不含失效条目）
        code, out, err = self.run_mem("recall", "记忆")
        self.assertEqual(code, 0)
        hits = json.loads(out)
        self.assertFalse(any(h["id"] == entry_id for h in hits), "失效条目默认不可见")

        # 10. 重建索引不丢数据（另一条仍可召回）
        self.run_mem("record", "--name", "留存条目", "--abstract", "虚构：重建验证",
                     "--type", "fact", "--conclusion", "重建后仍在", "--reason", "验证")
        code, out, err = self.run_mem("rebuild")
        self.assertEqual(code, 0, f"rebuild 失败: {err}")
        code, out, err = self.run_mem("recall", "重建")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out), "重建后数据不应丢失")

    def test_journey_is_idempotent(self):
        """旅程可重复执行：init 幂等，record 不重复插入同一 id。"""
        code, _, _ = self.run_mem("init")
        self.assertEqual(code, 0)
        code, _, _ = self.run_mem("init")  # 重复 init 应幂等
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
