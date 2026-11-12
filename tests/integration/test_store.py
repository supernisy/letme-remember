"""写入链：初始化隔离、身份键、时间轴、撤销、提案、批次、提炼器拦截。"""

import tempfile
from datetime import date, timedelta
from pathlib import Path

from lmr import config, distill, frontmatter, gitutil, index, proposal, redaction, store
from lmr.errors import ValidationError
from tests.base import MemTestCase, candidate

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]

# @req 1.1 @req 1.2 @req 1.3 @req 2.3 @req 2.4
# @req 3.3 @req 3.4 @req 3.5 @req 3.6 @req 3.7


class TestInit(MemTestCase):
    def test_default_data_dir_is_outside_code_repo(self):
        # @req 1.1
        default = config.DEFAULT_DATA_DIR.resolve()
        self.assertNotEqual(default, ROOT)
        self.assertFalse(str(default).startswith(str(ROOT)))
        self.assertTrue((self.paths.root / ".git").exists())

    def test_private_git_and_fictional_sample(self):
        # @req 1.2
        with tempfile.TemporaryDirectory() as folder:
            paths = store.init_data_dir(Path(folder), sample=True)
            self.assertTrue(gitutil.log(paths.root))
            sample_files = list(paths.store.glob("*.md"))
            self.assertEqual(len(sample_files), 1)
            text = sample_files[0].read_text(encoding="utf-8")
            for word in ("薪资", "职业定位", "谈判", "公司", "前端", "全栈", "月薪"):
                self.assertNotIn(word, text)
            masked, _ = redaction.redact(text, {"redact_b_class": True})
            self.assertEqual(masked, text)

    def test_gitignore_excludes_data_and_index(self):
        # @req 1.3
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for token in (".index/", "store/", "archive/", "MEMORY.md"):
            self.assertIn(token, gitignore)
        self.assertFalse((ROOT / "store").is_dir())
        self.assertFalse((ROOT / "archive").is_dir())
        self.assertIn(".index/", (self.paths.root / ".gitignore").read_text(encoding="utf-8"))


class TestMemoryModel(MemTestCase):
    def test_same_key_single_file(self):
        # @req 2.3
        first = self.make(name="同一主题")
        second = self.make(name="同一主题", abstract="第二次写入同一条记忆")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.files()), 1)

    def test_import_entry_keeps_original_effective_date(self):
        # @req 2.4
        out = self.make(
            name="导入示例", source_category="规则文件",
            original_date="2026-01-15", batch="批次A",
        )
        meta, _ = frontmatter.read_file(Path(out["path"]))
        self.assertEqual(meta["valid_from"], "2026-01-15")
        self.assertEqual(meta["author"], "import:规则文件")
        self.assertEqual(len(meta["provenance"]), 3)
        self.assertNotEqual(meta["created"], meta["valid_from"])
        hits = index.Index(self.paths, self.settings).recall("导入示例", as_of="2026-02-01")
        self.assertTrue(any(hit["id"] == out["id"] for hit in hits))


class TestWriteChain(MemTestCase):
    def test_record_read_back_and_undo(self):
        # @req 3.3
        before = len(gitutil.log(self.paths.root))
        out = self.make(name="可撤销条目")
        self.assertEqual(len(gitutil.log(self.paths.root)), before + 1)
        self.assertIn("## 结论", store.show(self.paths, out["id"]))
        store.undo(self.paths, self.settings)
        self.assertEqual(self.files(), [])
        self.assertFalse(index.Index(self.paths, self.settings).recall("可撤销条目"))

    def test_invalid_candidate_writes_nothing(self):
        # @req 3.4
        class FakeDistiller:
            def distill(self, text):
                return [
                    candidate(name="合法候选"),
                    candidate(name="非法候选", reason=""),
                ]

        with self.assertRaises(ValidationError):
            distill.run_distiller(FakeDistiller(), "任意文本", self.paths, self.settings)
        self.assertEqual(self.files(), [])

    def test_invalidate_never_deletes(self):
        # @req 3.5
        out = self.make(
            name="会被取代的条目",
            valid_from=(date.today() - timedelta(days=10)).isoformat(),
        )
        path = Path(out["path"])
        result = store.invalidate(self.paths, self.settings, out["id"], superseded_by="新条目")
        self.assertTrue(path.is_file())
        idx = index.Index(self.paths, self.settings)
        self.assertFalse(idx.recall("会被取代的条目"))
        earlier = (date.fromisoformat(result["invalid_at"]) - timedelta(days=1)).isoformat()
        historical = idx.recall("会被取代的条目", as_of=earlier)
        self.assertTrue(any(hit["id"] == out["id"] for hit in historical))

    def test_purge_truly_deletes(self):
        # @req 3.8
        out = self.make(name="错误条目")
        path = Path(out["path"])
        self.assertTrue(path.is_file())
        result = store.purge(self.paths, self.settings, out["id"], reason="测试残留")
        self.assertTrue(result["purged"])
        self.assertFalse(path.exists())  # 物理删除，与 invalidate 的软失效不同
        idx = index.Index(self.paths, self.settings)
        self.assertFalse(idx.recall("错误条目"))  # 索引也不再返回

    def test_proposals_pending_applied_truncated(self):
        # @req 3.6
        out = self.make(name="提案目标")
        pending = proposal.create(self.paths, "delete", out["id"])
        self.assertEqual(pending["status"], "pending")
        meta, _ = frontmatter.read_file(Path(out["path"]))
        self.assertEqual(meta["invalid_at"], "")
        applied = proposal.apply(self.paths, self.settings, pending["id"])
        self.assertEqual(applied["op"], "delete")
        meta, _ = frontmatter.read_file(Path(out["path"]))
        self.assertTrue(meta["invalid_at"])

        items = [{"op": "delete", "target": out["id"]} for _ in range(6)]
        batch = proposal.create_batch(self.paths, items)
        self.assertEqual(batch["created"], proposal.MAX_PER_BATCH["delete"])
        self.assertEqual(batch["truncated"], 6 - proposal.MAX_PER_BATCH["delete"])
        self.assertIn("deterministic", proposal.classify("adjust_weight"))
        self.assertEqual(proposal.classify("unknown_op"), "unknown")

    def test_import_batch_undo(self):
        # @req 3.7
        batch_items = [
            candidate(name="导入甲", source_category="规则文件",
                      original_date="2026-01-01", batch="批次X"),
            candidate(name="导入乙", source_category="规则文件",
                      original_date="2026-01-02", batch="批次X"),
        ]
        distill.run_candidates(batch_items, self.paths, self.settings)
        self.make(name="普通条目")
        self.assertEqual(len(self.files()), 3)
        result = store.undo_batch(self.paths, self.settings, "批次X")
        self.assertEqual(result["reverted"], 2)
        remaining = [path.name for path in self.files()]
        self.assertEqual(len(remaining), 1)
        self.assertIn("普通条目", remaining[0])
