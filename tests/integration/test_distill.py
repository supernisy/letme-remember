"""批量蒸馏器（lmr.distill）的单元测试。

覆盖 testing capability 的覆盖率门禁：distill 是 domain 核心层。
关键点：不真连网络，用 stub client（注入假 chat 方法）验证蒸馏器的
核心逻辑——JSON 提取、importance 截断、导入字段完整性校验。
"""

import unittest

import pytest

from lmr import distill
from lmr.errors import ValidationError

pytestmark = pytest.mark.integration


class StubClient:
    """假 LLM 客户端：返回预设的 chat 结果，不真调外部 API。"""

    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.raw


class TestExtractJsonArray(unittest.TestCase):
    def test_plain_array(self):
        self.assertEqual(distill._extract_json_array('[{"a": 1}]'), [{"a": 1}])

    def test_markdown_fence(self):
        raw = '```json\n[{"a": 1}]\n```'
        self.assertEqual(distill._extract_json_array(raw), [{"a": 1}])

    def test_no_array_raises(self):
        with self.assertRaises(ValueError):
            distill._extract_json_array("没有数组")


class TestLLMDistiller(unittest.TestCase):
    def test_distill_filters_low_importance(self):
        raw = (
            '[{"name": "高重要性", "importance": 5},'
            ' {"name": "低重要性", "importance": 1},'
            ' {"name": "无importance字段", "importance": 3}]'
        )
        client = StubClient(raw)
        d = distill.LLMDistiller(client, importance_min=3)
        result = d.distill("任意长文本")
        # importance < 3 的丢弃；importance 字段被剥掉
        self.assertEqual([c["name"] for c in result], ["高重要性", "无importance字段"])
        self.assertTrue(all("importance" not in c for c in result))

    def test_distill_non_dict_dropped(self):
        raw = '[{"name": "有效"}, "字符串而非字典"]'
        d = distill.LLMDistiller(StubClient(raw), importance_min=3)
        result = d.distill("文本")
        self.assertEqual([c["name"] for c in result], ["有效"])

    def test_filter_importance_invalid_value(self):
        raw = '[{"name": "a", "importance": "不是数字"}, {"name": "b", "importance": 5}]'
        d = distill.LLMDistiller(StubClient(raw), importance_min=3)
        # importance 非法时按 IMPORTANCE_MIN 处理，等于阈值 → 保留
        result = d.distill("文本")
        self.assertEqual([c["name"] for c in result], ["a", "b"])


class TestEnforceImportFields(unittest.TestCase):
    def test_all_three_present(self):
        candidates = [{"name": "x", "source_category": "chat", "original_date": "2026-01-01", "batch": "b1"}]
        distill.enforce_import_fields(candidates)  # 不应抛错

    def test_partial_import_fields_raises(self):
        candidates = [{"name": "x", "source_category": "chat"}]  # 缺 original_date 和 batch
        with self.assertRaises(ValidationError):
            distill.enforce_import_fields(candidates)

    def test_no_import_fields_allowed(self):
        candidates = [{"name": "x", "conclusion": "人类手写"}]  # 三字段全空 = 手写，放行
        distill.enforce_import_fields(candidates)  # 不应抛错

    def test_non_dict_raises(self):
        with self.assertRaises(ValidationError):
            distill.enforce_import_fields(["字符串而非字典"])


if __name__ == "__main__":
    unittest.main()
