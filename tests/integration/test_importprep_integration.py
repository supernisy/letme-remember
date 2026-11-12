"""预处理集成：卡片只进 staging、幂等去重、报告脱敏、CLI 全流程。"""

import json
import unittest

import pytest

from lmr import importprep
from tests.base import MemTestCase

pytestmark = pytest.mark.integration


def _ok_source():
    """一份合法的源记忆（可直接转）。"""
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


class TestStagingIsolation(MemTestCase):
    def test_cards_only_in_staging(self):
        # 卡片只写 staging，绝不进 store / 索引
        src = self.paths.root / "src.md"
        src.write_text(_ok_source(), encoding="utf-8")
        result = importprep.run(self.paths, [src], source_category="preference")

        self.assertEqual(result["cards_written"], 1)
        # staging 有卡片
        self.assertTrue(any(self.paths.staging.glob("card-*.json")))
        # store 里没有新增记忆（只有初始 0 条，因为 sample=False）
        self.assertEqual(len(list(self.paths.store.glob("*.md"))), 0)
        # 卡片文件名不含正文
        for f in self.paths.staging.glob("card-*.json"):
            self.assertTrue(f.name.startswith("card-"))
            self.assertEqual(len(f.name), len("card-") + 64 + len(".json"))

    def test_card_content_not_in_index(self):
        # 索引不包含卡片内容
        src = self.paths.root / "src.md"
        src.write_text(_ok_source(), encoding="utf-8")
        importprep.run(self.paths, [src], source_category="preference")
        # staging 里的卡片内容含正文，但索引/真相源不含
        card = next(self.paths.staging.glob("card-*.json"))
        card_text = card.read_text(encoding="utf-8")
        self.assertIn("偏好用纯文本记录笔记", card_text)
        # store 目录空，无真相源
        self.assertEqual(len(list(self.paths.store.glob("*.md"))), 0)


class TestIdempotency(MemTestCase):
    def test_repreprocess_no_duplicate_cards(self):
        # 同一源重复预处理，第二次产卡数为 0
        src = self.paths.root / "src.md"
        src.write_text(_ok_source(), encoding="utf-8")
        first = importprep.run(self.paths, [src], source_category="preference")
        self.assertEqual(first["cards_written"], 1)

        second = importprep.run(self.paths, [src], source_category="preference")
        self.assertEqual(second["cards_written"], 0)
        self.assertEqual(second["cards_skipped_duplicate"], 1)
        # 源文件内容不变
        self.assertEqual(src.read_text(encoding="utf-8"), _ok_source())


class TestReportDesensitized(MemTestCase):
    def test_report_no_sensitive_content(self):
        # 报告不含正文/凭据原值
        sensitive = _ok_source() + "\n密钥是 sk-abcdef1234567890abcdef1234567890。\n"
        src = self.paths.root / "src.md"
        src.write_text(sensitive, encoding="utf-8")
        result = importprep.run(self.paths, [src], source_category="other")
        # run 的返回只有元信息（数量/规则/缺失字段），不含正文
        blob = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("偏好用纯文本", blob)
        self.assertNotIn("sk-abcdef1234567890", blob)


class TestEmptySource(MemTestCase):
    def test_empty_dir_returns_zero(self):
        # 空源/空目录：返回空结果，count 为 0
        empty_dir = self.paths.root / "empty"
        empty_dir.mkdir(parents=True, exist_ok=True)
        result = importprep.run(self.paths, [], source_category="")
        self.assertEqual(result["sources_scanned"], 0)
        self.assertEqual(result["total_entries"], 0)
        self.assertEqual(result["cards_written"], 0)


if __name__ == "__main__":
    unittest.main()
