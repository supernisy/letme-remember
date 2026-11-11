"""v1.1 LLM 软判断与批量蒸馏的单元测试。

关键点：不真连网络，用假 LLM（注入一个 stub 客户端）验证
「报告解析 → 分级裁决」与「降级路径」两条纯代码逻辑。
"""

import unittest

from lmr import judgment
from lmr.llm import LLMUnavailable, resolve_api_key


class TestParseReport(unittest.TestCase):
    def test_parse_clean_json(self):
        raw = '{"conflict": true, "importance": "high", "confidence": "high", "missing": ""}'
        report = judgment.parse_report(raw)
        self.assertTrue(report["conflict"])

    def test_parse_json_with_markdown_fence(self):
        raw = '```json\n{"conflict": false, "importance": "low", "confidence": "high"}\n```'
        report = judgment.parse_report(raw)
        self.assertFalse(report["conflict"])

    def test_parse_json_with_extra_text(self):
        raw = '好的，以下是判断结果：{"conflict": false, "importance": "low", "confidence": "high"} 以上。'
        report = judgment.parse_report(raw)
        self.assertFalse(report["conflict"])

    def test_parse_invalid_raises(self):
        with self.assertRaises(ValueError):
            judgment.parse_report("这不是 JSON")


class TestValidateReport(unittest.TestCase):
    def test_missing_fields_get_defaults(self):
        report = judgment.validate_report({})
        self.assertFalse(report["conflict"])
        self.assertEqual(report["importance"], "low")
        self.assertEqual(report["confidence"], "low")
        self.assertEqual(report["missing"], "")

    def test_invalid_enum_clamped(self):
        report = judgment.validate_report({"importance": "超高", "confidence": "很确定"})
        self.assertEqual(report["importance"], "low")
        self.assertEqual(report["confidence"], "low")


class TestClassify(unittest.TestCase):
    def test_l0_auto(self):
        report = judgment.validate_report({
            "importance": "low", "confidence": "high", "missing": ""})
        self.assertEqual(judgment.classify(report), "L0")

    def test_l1_trigger(self):
        report = judgment.validate_report({
            "conflict": True, "importance": "low", "confidence": "high"})
        self.assertEqual(judgment.classify(report), "L1")

    def test_l1_medium_importance(self):
        report = judgment.validate_report({
            "importance": "medium", "confidence": "high", "missing": ""})
        self.assertEqual(judgment.classify(report), "L1")

    def test_l2_high_impact(self):
        report = judgment.validate_report({
            "high_impact": True, "importance": "low", "confidence": "high"})
        self.assertEqual(judgment.classify(report), "L2")

    def test_l2_low_confidence(self):
        report = judgment.validate_report({
            "importance": "low", "confidence": "low"})
        self.assertEqual(judgment.classify(report), "L2")

    def test_l2_compliance(self):
        report = judgment.validate_report({
            "compliance": True, "importance": "low", "confidence": "high"})
        self.assertEqual(judgment.classify(report), "L2")


class TestRuleReport(unittest.TestCase):
    def test_high_weight_implies_high_importance(self):
        report = judgment.rule_report(
            {"type": "preference", "weight": 9, "conclusion": "x", "reason": "y"}, [])
        self.assertEqual(report["importance"], "high")
        self.assertEqual(report["confidence"], "low")  # 规则判断置信度恒低

    def test_uncertain_word_detected(self):
        report = judgment.rule_report(
            {"type": "fact", "weight": 3, "conclusion": "x", "reason": "可能需要再看"}, [])
        self.assertTrue(report["uncertain"])

    def test_missing_conclusion(self):
        report = judgment.rule_report({"type": "fact", "weight": 3, "conclusion": "", "reason": ""}, [])
        self.assertTrue(report["missing"])


class TestResolveKey(unittest.TestCase):
    def test_env_priority(self):
        import os
        os.environ["LMR_LLM_KEY"] = "env-key"
        key = resolve_api_key({}, {"llm_key": "config-key"})
        self.assertEqual(key, "env-key")
        del os.environ["LMR_LLM_KEY"]

    def test_fallback_to_config(self):
        key = resolve_api_key({}, {"llm_key": "config-key"})
        self.assertEqual(key, "config-key")

    def test_empty_when_none(self):
        self.assertEqual(resolve_api_key({}, {}), "")


class TestLLMUnavailable(unittest.TestCase):
    def test_make_client_disabled_raises(self):
        from lmr.llm import make_client
        with self.assertRaises(LLMUnavailable):
            make_client({"llm_enabled": False}, {})


if __name__ == "__main__":
    unittest.main()
