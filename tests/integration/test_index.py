"""索引与检索：增量同步、排序、中文召回、零模型读路径、重建、预算截断。"""

import os
import socket
from pathlib import Path
from unittest import mock

from lmr import config, index, tokenizer
from tests.base import MemTestCase

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]

# @req 4.1 @req 4.2 @req 4.3 @req 4.4 @req 4.5 @req 4.6


class TestIndex(MemTestCase):
    def idx(self):
        return index.Index(self.paths, self.settings)

    def test_incremental_sync_by_hash(self):
        # @req 4.1
        self.make(name="条目甲")
        first = self.idx().sync()
        second = self.idx().sync()
        self.assertEqual(first["added"], 0)
        self.assertEqual(second["added"], 0)
        self.assertEqual(second["skipped"], 1)
        # 模拟人或另一个宿主直接改文件：内容哈希变化后只更新这一条
        path = self.files()[0]
        path.write_text(
            path.read_text(encoding="utf-8").replace("虚构测试条目", "虚构测试条目（已修改）"),
            encoding="utf-8",
        )
        third = self.idx().sync()
        self.assertEqual(third["added"], 0)
        self.assertEqual(third["updated"], 1)

    def test_ranking_and_recency_floor(self):
        # @req 4.2
        self.make(name="高权重条目", weight="5", valid_from="2026-11-01")
        self.make(name="低权重条目", weight="0.5", valid_from="2026-01-01")
        self.make(name="很旧条目", weight="1", valid_from="2020-01-01")
        hits = self.idx().recall("虚构")
        self.assertEqual(hits[0]["id"], self._id("高权重条目"))
        self.assertTrue(all(hit["score"] > 0 for hit in hits), "旧条目不得被衰减到零")

    def _id(self, name):
        from lmr import schema

        return schema.entry_id(schema.filename_for("decision", name))

    def test_chinese_short_terms_and_degradation(self):
        # @req 4.3
        self.make(name="中文检索", conclusion="记忆系统采用纯文本存储",
                 reason="纯文本便于本地检索与版本管理，本条为虚构测试数据")
        idx = self.idx()
        self.assertTrue(any(hit["id"] == self._id("中文检索") for hit in idx.recall("记忆")))
        self.assertTrue(any(hit["id"] == self._id("中文检索") for hit in idx.recall("纯文本")))
        previous = os.environ.get(config.ENV_DISABLE_TOKENIZER)
        os.environ[config.ENV_DISABLE_TOKENIZER] = "1"
        tokenizer.reset_cache()
        try:
            self.assertEqual(tokenizer.tokenizer_version(), tokenizer.BUILTIN_VERSION)
            hits = idx.recall("记忆")
            self.assertTrue(any(hit["id"] == self._id("中文检索") for hit in hits))
        finally:
            tokenizer.reset_cache()
            if previous is None:
                os.environ.pop(config.ENV_DISABLE_TOKENIZER, None)
            else:
                os.environ[config.ENV_DISABLE_TOKENIZER] = previous

    def test_read_path_zero_model_zero_network(self):
        # @req 4.4
        self.make(name="离线检索")
        original = socket.socket

        def blocked(*args, **kwargs):
            raise AssertionError("读路径不应创建网络套接字")

        socket.socket = blocked
        try:
            self.assertTrue(self.idx().recall("离线检索"))
        finally:
            socket.socket = original
        # 读路径（检索）相关模块不得引入网络库；LLM 软判断/蒸馏是独立的写路径模块，
        # 允许联网（v1.1 诉求），不在本约束范围内。
        read_modules = ("index.py", "tokenizer.py", "frontmatter.py", "store.py")
        for name in read_modules:
            text = (ROOT / "lmr" / name).read_text(encoding="utf-8")
            for banned in ("import requests", "import openai", "urllib.request", "import httpx"):
                self.assertNotIn(banned, text)

    def test_rebuild_is_lossless(self):
        # @req 4.5
        self.make(name="可重建条目")
        before = [hit["id"] for hit in self.idx().recall("虚构")]
        self.idx().rebuild()
        after = [hit["id"] for hit in self.idx().recall("虚构")]
        self.assertEqual(before, after)
        self.assertIn(".index/", (self.paths.root / ".gitignore").read_text(encoding="utf-8"))

    def test_memory_md_budget_and_regeneration(self):
        # @req 4.6
        for number in range(8):
            self.make(name="目录条目%d" % number)
        info = self.idx().build_memory_md(budget=120)
        self.assertLessEqual(info["bytes"], 120)
        self.assertLess(info["lines"], 8)
        self.paths.memory_md.unlink()
        self.idx().build_memory_md()
        self.assertTrue(self.paths.memory_md.is_file())
        self.assertIn("[", self.paths.memory_md.read_text(encoding="utf-8"))

    def test_query_injection_recalls_relevant_not_full(self):
        # 两段式第一段：inject --query 只召回相关条目，而非全量目录。
        for number in range(10):
            self.make(name="无关条目%d" % number)
        self.make(name="蚂蚁集团面试复盘", abstract="蚂蚁集团终面策略复盘")
        info = self.idx().build_memory_md(query="蚂蚁集团面试", limit=3)
        text = self.paths.memory_md.read_text(encoding="utf-8")
        self.assertIn("蚂蚁集团", text)
        self.assertLess(info["lines"], 5)

    def test_embedding_degradation_when_disabled(self):
        # embedding 禁用时，recall 结果 semantic 恒为 0，不影响关键词检索。
        # 隔离原则：不真加载 120MB 模型，直接设禁用开关短路 _load()。
        os.environ[config.ENV_DISABLE_EMBEDDING] = "1"
        try:
            from lmr import embedding
            embedding.reset_cache()
            self.make(name="缓存数据不一致", abstract="Redis 与 DB 数据不同步处理")
            hits = self.idx().recall("缓存不一致")
            self.assertTrue(len(hits) >= 1)
            self.assertEqual(hits[0]["semantic"], 0.0)
        finally:
            os.environ.pop(config.ENV_DISABLE_EMBEDDING, None)
            from lmr import embedding
            embedding.reset_cache()

    def test_embedding_available_flag(self):
        # embedding 模块：未装依赖时 available() 为 False，且不抛异常。
        # 隔离原则：mock 掉 sentence_transformers 的 import，避免在依赖已装的
        # 环境里真加载模型/联网，导致测试挂起或变慢。
        from lmr import embedding
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "sentence_transformers" or name.startswith("sentence_transformers."):
                raise ImportError("模拟未安装 sentence-transformers")
            return real_import(name, *args, **kwargs)

        embedding.reset_cache()
        with mock.patch("builtins.__import__", side_effect=fake_import):
            self.assertFalse(embedding.available())
        embedding.reset_cache()

