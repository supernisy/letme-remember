"""分块器（lmr.chunk）与增量模块（lmr.incremental）确定性部分的单元测试。

只测不依赖 LLM 的分支：分块策略、name 去重、JSON 提取。
LLM 调用部分在集成测试 / 端到端验证里覆盖（避免单测联网）。
"""

import unittest

import pytest

from lmr import chunk as chunk_module
from lmr import incremental as incremental_module

pytestmark = pytest.mark.unit


# 模拟飞书/腾讯会议转写格式：`讲话人 N MM:SS` + 内容，空行分隔。
SAMPLE_TRANSCRIPT = """讲话人 1  00:08
哈喽哈喽。

讲话人 2  00:09
能听到吗？嗯，可以听到哦。

讲话人 1  00:11
你稍等一下，我们还有一位面试官。

讲话人 2  00:33
我9月30号离职了哦。
"""


class TestChunkTranscript(unittest.TestCase):
    def test_short_text_single_chunk(self):
        chunks = chunk_module.chunk_transcript(SAMPLE_TRANSCRIPT, max_chars=10000)
        self.assertEqual(len(chunks), 1)
        self.assertIn("讲话人 1", chunks[0]["text"])

    def test_chunks_respect_max_chars(self):
        chunks = chunk_module.chunk_transcript(SAMPLE_TRANSCRIPT, max_chars=40)
        for c in chunks:
            self.assertLessEqual(c["chars"], 40)

    def test_chunk_starts_at_speaker_boundary(self):
        # 用极小块强制多块，验证每块都从「讲话人」行开始。
        chunks = chunk_module.chunk_transcript(SAMPLE_TRANSCRIPT, max_chars=30)
        for c in chunks:
            self.assertTrue(
                c["text"].startswith("讲话人"),
                "块应以说话人行开头: %r" % c["text"][:20],
            )

    def test_empty_text(self):
        self.assertEqual(chunk_module.chunk_transcript(""), [])
        self.assertEqual(chunk_module.chunk_transcript("   \n\n  "), [])

    def test_crlf_normalized(self):
        text = SAMPLE_TRANSCRIPT.replace("\n", "\r\n")
        chunks = chunk_module.chunk_transcript(text, max_chars=10000)
        self.assertEqual(len(chunks), 1)
        self.assertNotIn("\r", chunks[0]["text"])

    def test_role_prefix_boundary(self):
        text = "面试官：你叫什么？\n候选人：我叫张三。\n\n面试官：会什么？\n候选人：会写代码。"
        chunks = chunk_module.chunk_transcript(text, max_chars=1000)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertIn("面试官", chunks[0]["text"])


class TestSplitLongBlock(unittest.TestCase):
    def test_under_limit_unchanged(self):
        self.assertEqual(chunk_module._split_long_block("短文本", 100), ["短文本"])

    def test_split_on_sentence(self):
        text = "第一句。第二句。第三句。" * 20
        pieces = chunk_module._split_long_block(text, 10)
        self.assertGreater(len(pieces), 1)
        for p in pieces:
            self.assertLessEqual(len(p), 10)


class TestMergeByName(unittest.TestCase):
    def test_dedup_keeps_last(self):
        cands = [
            {"name": "a", "v": 1},
            {"name": "b", "v": 2},
            {"name": "a", "v": 3},
        ]
        merged = incremental_module._merge_by_name(cands)
        self.assertEqual([c["v"] for c in merged], [3, 2])

    def test_skips_non_dict_and_empty_name(self):
        cands = [{"name": "a", "v": 1}, "not-dict", {"name": "", "v": 9}]
        merged = incremental_module._merge_by_name(cands)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["name"], "a")


class TestExtractJsonObject(unittest.TestCase):
    def test_clean_object(self):
        raw = '{"added":["a"],"deepened":[],"unchanged":[],"note":"x"}'
        self.assertEqual(incremental_module._extract_json_object(raw)["note"], "x")

    def test_strips_markdown_fence(self):
        raw = '```json\n{"added":[]}\n```'
        self.assertEqual(incremental_module._extract_json_object(raw)["added"], [])

    def test_extra_text_around(self):
        raw = '前缀 {"added":["a"]} 后缀'
        self.assertEqual(incremental_module._extract_json_object(raw)["added"], ["a"])

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            incremental_module._extract_json_object("没有JSON")


if __name__ == "__main__":
    unittest.main()
