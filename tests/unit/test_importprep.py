"""预处理三类判定：格式合规可转 / 待裁决 / 明确排除（import-preprocessing/spec.md）。"""

import unittest

import pytest

from lmr import importprep

pytestmark = pytest.mark.unit


def _ok_text():
    return """---
name: preference-笔记工具
abstract: 偏好用纯文本记笔记
type: preference
created: 2026-01-01T00:00:00+00:00
updated: 2026-01-01T00:00:00+00:00
valid_from: 2026-01-01
invalid_at:
superseded_by:
weight: 1.0
author: human
links:
provenance:
---

## 结论

偏好用纯文本记录笔记。

## 理由

纯文本便于版本管理与检索。
"""


class TestVerdict(unittest.TestCase):
    def test_ok_when_complete(self):
        # 格式合规可转：形状红线 + 字段完整 + 日期合法 + 类型可猜
        verdict, detail = importprep._verdict_for(_ok_text(), "preference")
        self.assertEqual(verdict, importprep.VERDICT_OK)
        self.assertEqual(detail["rule"], "ok")

    def test_exclude_log_category(self):
        # 明确排除：来源类别是日志流水
        verdict, detail = importprep._verdict_for(_ok_text(), "log")
        self.assertEqual(verdict, importprep.VERDICT_EXCLUDE)
        self.assertEqual(detail["rule"], "exclude:source-category")

    def test_exclude_process_marker(self):
        # 明确排除：正文命中过程流水标记
        text = _ok_text() + "\n今天下午修了 X 的 bug。\n"
        verdict, detail = importprep._verdict_for(text, "other")
        self.assertEqual(verdict, importprep.VERDICT_EXCLUDE)
        self.assertEqual(detail["rule"], "exclude:process-marker")

    def test_exclude_no_frontmatter(self):
        # 明确排除：无文件头（碎片）
        verdict, detail = importprep._verdict_for("随便一段没有结构的文本", "other")
        self.assertEqual(verdict, importprep.VERDICT_EXCLUDE)
        self.assertEqual(detail["rule"], "exclude:no-frontmatter")

    def test_exclude_no_conclusion_reason(self):
        # 明确排除：有文件头但正文无「结论」「理由」两节
        text = """---
name: x
type: fact
---
\n\n只是一句话，没有结论理由。\n"""
        verdict, detail = importprep._verdict_for(text, "other")
        self.assertEqual(verdict, importprep.VERDICT_EXCLUDE)
        self.assertEqual(detail["rule"], "exclude:no-conclusion-reason")

    def test_review_when_validation_fails(self):
        # 待裁决：形状合规但字段校验失败（缺理由/日期非法等）
        text = _ok_text().replace("## 理由", "## 理由\n\n（空）").replace(
            "valid_from: 2026-01-01", "valid_from: 不是日期")
        verdict, detail = importprep._verdict_for(text, "other")
        self.assertEqual(verdict, importprep.VERDICT_REVIEW)
        self.assertEqual(detail["rule"], "review:validation")

    def test_review_when_type_unknown(self):
        # 待裁决：类型无法确定（type 缺失，validate 会拦「必填字段为空」）
        text = _ok_text().replace("type: preference", "type: ")
        verdict, detail = importprep._verdict_for(text, "unknown-category")
        self.assertEqual(verdict, importprep.VERDICT_REVIEW)
        # 无论走 review:validation 还是 review:needs-human，都属「待裁决」大类
        self.assertTrue(detail["rule"].startswith("review"))

    def test_review_when_supersede_signal(self):
        # 待裁决：疑似取代关系（superseded_by 缺 invalid_at，validate 拦）
        text = _ok_text().replace("superseded_by:", "superseded_by: 另一条")
        verdict, detail = importprep._verdict_for(text, "other")
        self.assertEqual(verdict, importprep.VERDICT_REVIEW)
        self.assertTrue(detail["rule"].startswith("review"))

    def test_review_when_credential_shape(self):
        # 待裁决：命中 A/B 类凭据形状（合规边界）
        text = _ok_text() + "\n密钥是 sk-1234567890abcdef1234567890abcdef。\n"
        verdict, detail = importprep._verdict_for(text, "other")
        self.assertEqual(verdict, importprep.VERDICT_REVIEW)
        self.assertIn("credential-shape", detail["needs_human"])


class TestHelpers(unittest.TestCase):
    def test_content_hash_stable(self):
        self.assertEqual(
            importprep.content_hash("abc"),
            importprep.content_hash("abc"),
        )

    def test_content_hash_differs(self):
        self.assertNotEqual(
            importprep.content_hash("abc"),
            importprep.content_hash("abd"),
        )

    def test_split_entries_with_frontmatter(self):
        text = _ok_text() + "\n---\n" + _ok_text().replace("笔记", "日志")
        entries = importprep._split_entries(text)
        self.assertGreaterEqual(len(entries), 2)

    def test_split_entries_plain(self):
        entries = importprep._split_entries("没有文件头的纯文本")
        self.assertEqual(len(entries), 1)


class TestReportDesensitized(unittest.TestCase):
    def test_report_does_not_contain_body(self):
        # 报告脱敏：不含正文、原值
        text = _ok_text()
        result = importprep.preprocess(
            __import__("pathlib").Path(__file__), "other")
        # 报告行只含元信息
        for row in result["report"]:
            self.assertNotIn("纯文本便于版本管理", str(row))

    def test_build_report_counts(self):
        rep = importprep.build_report({
            "source": "x.md",
            "total_entries": 3,
            "report": [
                {"verdict": "ok", "rule": "ok", "missing_fields": [], "needs_human": []},
                {"verdict": "review", "rule": "review:validation",
                 "missing_fields": ["理由"], "needs_human": []},
                {"verdict": "exclude", "rule": "exclude:source-category",
                 "missing_fields": [], "needs_human": []},
            ],
        })
        self.assertEqual(rep["verdict_counts"]["ok"], 1)
        self.assertEqual(rep["verdict_counts"]["review"], 1)
        self.assertEqual(rep["verdict_counts"]["exclude"], 1)
        self.assertEqual(rep["rule_hits"]["ok"], 1)
        self.assertIn("理由", rep["missing_fields_summary"])


if __name__ == "__main__":
    unittest.main()
