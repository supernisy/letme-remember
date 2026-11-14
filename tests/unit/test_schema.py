"""身份名与文件名规则（lmr.schema）的边界测试。

覆盖 testing capability 的覆盖率门禁：schema 是 domain 核心层，
需 ≥80%。v2.0 起 type 对齐 CoALA 三类，放弃 key_fields 分组，
本文件补齐类型规范化（canonical_type）、文件名、非法字符、超长截断等分支。
"""

import unittest

import pytest

from lmr import schema

pytestmark = pytest.mark.unit


class TestCanonicalType(unittest.TestCase):
    def test_canonical_keeps_three_types(self):
        self.assertEqual(schema.canonical_type("semantic"), "semantic")
        self.assertEqual(schema.canonical_type("episodic"), "episodic")
        self.assertEqual(schema.canonical_type("procedural"), "procedural")

    def test_canonical_maps_legacy_types(self):
        self.assertEqual(schema.canonical_type("fact"), "semantic")
        self.assertEqual(schema.canonical_type("decision"), "semantic")
        self.assertEqual(schema.canonical_type("preference"), "semantic")
        self.assertEqual(schema.canonical_type("experience"), "semantic")
        self.assertEqual(schema.canonical_type("procedure"), "procedural")
        self.assertEqual(schema.canonical_type("reference"), "episodic")
        self.assertEqual(schema.canonical_type("event"), "episodic")

    def test_canonical_unknown_returns_none(self):
        self.assertIsNone(schema.canonical_type("不存在的类型"))
        self.assertIsNone(schema.canonical_type(""))


class TestSchemaBoundaries(unittest.TestCase):
    def test_safe_slug_forbidden_chars(self):
        with self.assertRaises(ValueError):
            schema.safe_slug("含/非法\\字符")

    def test_safe_slug_long_name_hashes(self):
        long_name = "很长的名字" * 20  # 远超 60 字符
        slug = schema.safe_slug(long_name)
        self.assertLessEqual(len(slug), 69)  # 60 字符 + "-" + 8 位哈希
        self.assertIn("-", slug)

    def test_filename_for_unknown_type(self):
        with self.assertRaises(ValueError):
            schema.filename_for("未知", "name")

    def test_filename_for_known_type(self):
        self.assertEqual(schema.filename_for("semantic", "主题"), "semantic--主题.md")
        self.assertEqual(schema.filename_for("episodic", "主题"), "episodic--主题.md")
        self.assertEqual(schema.filename_for("procedural", "主题"), "procedural--主题.md")

    def test_filename_rejects_legacy_type(self):
        # 落盘必须用三类；旧类型名不再被 filename_for 接受（canonical 后才落盘）。
        with self.assertRaises(ValueError):
            schema.filename_for("fact", "主题")

    def test_entry_id_strips_extension(self):
        self.assertEqual(schema.entry_id("semantic--主题.md"), "semantic--主题")
        self.assertEqual(schema.entry_id("no_ext"), "no_ext")


if __name__ == "__main__":
    unittest.main()
