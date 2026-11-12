"""身份键与文件名规则（lmr.schema）的边界测试。

覆盖 testing capability 的覆盖率门禁：schema 是 domain 核心层，
需 ≥80%。本文件补齐未知类型、空键、非法字符、超长截断等边界分支。
"""

import unittest

import pytest

from lmr import schema

pytestmark = pytest.mark.unit


class TestSchemaBoundaries(unittest.TestCase):
    def test_derive_name_unknown_type(self):
        with self.assertRaises(ValueError):
            schema.derive_name("不存在的类型", ["x"])

    def test_derive_name_empty_keys(self):
        with self.assertRaises(ValueError):
            schema.derive_name("fact", [])
        with self.assertRaises(ValueError):
            schema.derive_name("fact", ["", "  "])

    def test_derive_name_strips_blanks(self):
        self.assertEqual(schema.derive_name("fact", [" 项目 ", " 主题 "]), "fact-项目-主题")

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
        self.assertEqual(schema.filename_for("fact", "主题"), "fact--主题.md")

    def test_entry_id_strips_extension(self):
        self.assertEqual(schema.entry_id("fact--主题.md"), "fact--主题")
        self.assertEqual(schema.entry_id("no_ext"), "no_ext")


if __name__ == "__main__":
    unittest.main()
