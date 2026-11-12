"""封闭文件头：固定字段、拒绝富格式、字面值不隐式转换。"""

import unittest

from lmr import frontmatter as fm
from lmr.errors import FrontmatterError

import pytest

pytestmark = pytest.mark.unit

# @req 2.1


class TestFrontmatter(unittest.TestCase):
    def setUp(self):
        self.meta = fm.empty_meta()
        self.meta.update({
            "name": "虚构条目", "abstract": "一句话摘要", "type": "fact",
            "created": "2026-01-01T00:00:00+00:00",
            "updated": "2026-01-01T00:00:00+00:00",
            "valid_from": "2026-01-01", "weight": "1.0", "author": "test",
            "links": ["项目甲", "项目乙"],
            "provenance": ["规则文件", "2026-01-01", "批次A"],
        })

    def test_roundtrip(self):
        # @req 2.1
        body = fm.make_body("结论文本", "理由文本")
        back, parsed_body = fm.parse(fm.render(self.meta, body))
        self.assertEqual(back["name"], "虚构条目")
        self.assertEqual(back["links"], ["项目甲", "项目乙"])
        self.assertEqual(back["provenance"], ["规则文件", "2026-01-01", "批次A"])
        self.assertEqual(fm.body_sections(parsed_body)["理由"], "理由文本")

    def test_literal_values(self):
        # @req 2.1
        self.meta["name"] = "no"
        self.meta["abstract"] = "yes"
        self.meta["created"] = "12:30"
        self.meta["valid_from"] = "2026-01-01"
        back, _ = fm.parse(fm.render(self.meta, fm.make_body("结论", "理由")))
        self.assertEqual(back["name"], "no")
        self.assertEqual(back["abstract"], "yes")
        self.assertEqual(back["created"], "12:30")
        self.assertEqual(back["valid_from"], "2026-01-01")

    def test_reject_unknown_field(self):
        # @req 2.1
        text = fm.render(self.meta, fm.make_body("结论", "理由")).replace(
            "author: test", "author: test\nextra_field: something"
        )
        with self.assertRaises(FrontmatterError):
            fm.parse(text)

    def test_reject_rich_and_nested(self):
        # @req 2.1
        for bad in ("links: [a, b]", "  name: 缩进", "name: 虚构条目\nname: 重复"):
            with self.subTest(bad=bad):
                text = fm.render(self.meta, fm.make_body("结论", "理由")).replace(
                    "links: 项目甲|项目乙" if bad.startswith("links") else
                    "name: 虚构条目", bad
                )
                with self.assertRaises(FrontmatterError):
                    fm.parse(text)

    def test_list_item_cannot_contain_separator(self):
        # @req 2.1
        self.meta["links"] = ["含|分隔符"]
        with self.assertRaises(FrontmatterError):
            fm.render(self.meta, fm.make_body("结论", "理由"))
