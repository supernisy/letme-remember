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


class TestConflictDetection(unittest.TestCase):
    """冲突检测增强（#10）：conflict 字段归一化 + 相似结论检索。"""

    def test_normalize_conflict_none(self):
        self.assertIsNone(judgment._normalize_conflict(None))
        self.assertIsNone(judgment._normalize_conflict(False))

    def test_normalize_conflict_bool_true(self):
        result = judgment._normalize_conflict(True)
        self.assertEqual(result, {"ids": [], "action": ""})

    def test_normalize_conflict_object(self):
        result = judgment._normalize_conflict(
            {"ids": ["a", "b"], "action": "SUPERSEDE"})
        self.assertEqual(result, {"ids": ["a", "b"], "action": "SUPERSEDE"})

    def test_normalize_conflict_bad_action_clamped(self):
        result = judgment._normalize_conflict(
            {"ids": ["a"], "action": "DELETE"})
        self.assertEqual(result["action"], "")

    def test_normalize_conflict_bad_ids_clamped(self):
        result = judgment._normalize_conflict({"ids": "not-a-list", "action": "UPDATE"})
        self.assertEqual(result["ids"], [])

    def test_validate_report_conflict_object_passthrough(self):
        report = judgment.validate_report({
            "conflict": {"ids": ["x"], "action": "UPDATE"}, "importance": "low",
            "confidence": "high", "missing": ""})
        self.assertEqual(report["conflict"]["action"], "UPDATE")

    def test_classify_conflict_object_triggers_l1(self):
        report = judgment.validate_report({
            "conflict": {"ids": ["x"], "action": "SUPERSEDE"},
            "importance": "low", "confidence": "high"})
        self.assertEqual(judgment.classify(report), "L1")

    def test_find_related_empty_query(self):
        result = judgment.find_related(None, {})
        self.assertEqual(result, [])

    def test_find_related_index_failure_degrades(self):
        class BoomIndex:
            def recall(self, query, limit):
                raise RuntimeError("boom")
        result = judgment.find_related(BoomIndex(), {"abstract": "求职城市", "name": "city"})
        self.assertEqual(result, [])

    def test_find_related_returns_readable_lines(self):
        class FakeIndex:
            def recall(self, query, limit):
                return [
                    {"id": "p1", "type": "preference", "abstract": "期望在北京工作"},
                    {"id": "p2", "type": "preference", "abstract": "期望在上海工作"},
                ]
        result = judgment.find_related(FakeIndex(), {"abstract": "工作城市偏好", "name": "city"})
        self.assertEqual(len(result), 2)
        self.assertIn("p1", result[0])
        self.assertIn("期望在北京工作", result[0])

    def test_find_related_uses_abstract_over_conclusion(self):
        seen = {}

        class SpyIndex:
            def recall(self, query, limit):
                seen["query"] = query
                return []
        judgment.find_related(
            SpyIndex(), {"abstract": "求职城市", "conclusion": "我以后想在北京发展", "name": "city"})
        # 查询词应优先用 abstract + name，不含 conclusion 全文。
        self.assertIn("求职城市", seen["query"])
        self.assertNotIn("我以后想在北京发展", seen["query"])

    # ---- decide_action：自动去重分流的裁决依据 ----

    def test_decide_action_no_conflict_is_add(self):
        self.assertEqual(judgment.decide_action({"conflict": None}), "ADD")
        self.assertEqual(judgment.decide_action({}), "ADD")

    def test_decide_action_reads_conflict_action(self):
        self.assertEqual(
            judgment.decide_action({"conflict": {"ids": ["x"], "action": "SUPERSEDE"}}),
            "SUPERSEDE")
        self.assertEqual(
            judgment.decide_action({"conflict": {"ids": ["x"], "action": "NOOP"}}),
            "NOOP")

    def test_decide_action_bad_action_falls_back_add(self):
        # 非法 action 已在 _normalize_conflict 钳成空串，这里兜底为 ADD。
        self.assertEqual(
            judgment.decide_action({"conflict": {"ids": [], "action": ""}}),
            "ADD")

    def test_decide_action_bool_true_conflict_no_action(self):
        # 降级路径 conflict=True 时无 action，视为 ADD（宁可新增也不误丢）。
        self.assertEqual(
            judgment.decide_action({"conflict": {"ids": [], "action": ""}}),
            "ADD")


class TestSupersedeTimeGuard(unittest.TestCase):
    """SUPERSEDE 的时间维度守卫：候选比被取代结论更旧时禁止取代。"""

    def test_older_candidate_blocked(self):
        cand = {"name": "old-mixed", "original_date": "2026-05-01"}
        related = [{"id": "city-flexible", "valid_from": "2026-11-09"}]
        allow, note = judgment.supersede_time_guard(cand, related)
        self.assertFalse(allow)
        self.assertIn("方向相反", note)

    def test_newer_candidate_allowed(self):
        cand = {"name": "new", "original_date": "2026-11-10"}
        related = [{"id": "city-flexible", "valid_from": "2026-11-09"}]
        allow, _ = judgment.supersede_time_guard(cand, related)
        self.assertTrue(allow)

    def test_same_day_allowed(self):
        cand = {"name": "same", "original_date": "2026-11-09"}
        related = [{"id": "city-flexible", "valid_from": "2026-11-09"}]
        allow, _ = judgment.supersede_time_guard(cand, related)
        self.assertTrue(allow)

    def test_candidate_without_date_not_blocked(self):
        cand = {"name": "nodate"}
        related = [{"id": "city-flexible", "valid_from": "2026-11-09"}]
        allow, _ = judgment.supersede_time_guard(cand, related)
        self.assertTrue(allow)

    def test_related_without_date_not_blocked(self):
        cand = {"name": "old", "original_date": "2026-05-01"}
        related = [{"id": "x", "valid_from": ""}]
        allow, _ = judgment.supersede_time_guard(cand, related)
        self.assertTrue(allow)

    def test_empty_related_not_blocked(self):
        cand = {"name": "old", "original_date": "2026-05-01"}
        allow, _ = judgment.supersede_time_guard(cand, [])
        self.assertTrue(allow)


class TestFindRelatedEntries(unittest.TestCase):
    """find_related_entries 返回结构化条目，保留 valid_from 供时间裁决。"""

    def test_returns_structured_hits(self):
        class FakeIndex:
            def recall(self, query, limit):
                return [
                    {"id": "p1", "type": "preference", "abstract": "在北京",
                     "valid_from": "2026-08-22", "invalid_at": ""},
                ]
        result = judgment.find_related_entries(
            FakeIndex(), {"abstract": "城市", "name": "city"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "p1")
        self.assertEqual(result[0]["valid_from"], "2026-08-22")

    def test_index_failure_degrades_to_empty(self):
        class BoomIndex:
            def recall(self, query, limit):
                raise RuntimeError("boom")
        result = judgment.find_related_entries(
            BoomIndex(), {"abstract": "城市", "name": "city"})
        self.assertEqual(result, [])

    def test_empty_query_returns_empty(self):
        self.assertEqual(judgment.find_related_entries(None, {}), [])


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
