"""仲裁器（lmr.arbitrator）与 host 归一化（lmr.schema）的单元测试。

覆盖 arbitration capability 的核心确定性逻辑：条件重叠检测、三结局裁决、
候选发现、host 归一化。全部为纯函数/零网络，不触碰真实数据目录。
"""

import unittest

import pytest

from lmr import arbitrator, schema

pytestmark = pytest.mark.unit


def _app(audience=None, scenario=None, time=None, precondition=None, extra=None):
    return {
        "audience": audience, "scenario": scenario,
        "time": time, "precondition": precondition,
        "extra": extra or {},
    }


class TestHostNormalization(unittest.TestCase):
    def test_normalize_lower_and_strip(self):
        self.assertEqual(schema.normalize_host(" WorkBuddy "), "workbuddy")

    def test_normalize_strips_import_prefix(self):
        self.assertEqual(schema.normalize_host("import:workbuddy"), "workbuddy")

    def test_normalize_empty(self):
        self.assertEqual(schema.normalize_host(None), "")
        self.assertEqual(schema.normalize_host(""), "")

    def test_infer_from_author(self):
        self.assertEqual(schema.infer_host_from_author("import:workbuddy-project-memory"), "workbuddy")
        self.assertEqual(schema.infer_host_from_author("import:workbuddy-memory"), "workbuddy")
        self.assertEqual(schema.infer_host_from_author("import:user-direct"), "manual")
        self.assertEqual(schema.infer_host_from_author("user-direct"), "manual")
        self.assertEqual(schema.infer_host_from_author(""), "")


class TestOverlapCheck(unittest.TestCase):
    def test_slot_differs_parallel(self):
        a = _app(audience="面试官")
        b = _app(audience="猎头")
        verdict, _ = arbitrator.overlap_check(a, b)
        self.assertEqual(verdict, "different")

    def test_both_empty_conflict(self):
        a = _app()
        b = _app()
        verdict, _ = arbitrator.overlap_check(a, b)
        self.assertEqual(verdict, "conflict")

    def test_slot_equal_conflict(self):
        a = _app(audience="面试官")
        b = _app(audience="面试官")
        verdict, _ = arbitrator.overlap_check(a, b)
        self.assertEqual(verdict, "conflict")

    def test_granularity_mismatch_suspect(self):
        a = _app(audience="面试官")
        b = _app()  # audience 空
        verdict, _ = arbitrator.overlap_check(a, b)
        self.assertEqual(verdict, "suspect")

    def test_extra_key_mismatch_suspect(self):
        a = _app(extra={"预算": "50万"})
        b = _app(extra={"城市": "杭州"})
        verdict, _ = arbitrator.overlap_check(a, b)
        self.assertEqual(verdict, "suspect")


class TestAdjudicatePair(unittest.TestCase):
    def test_parallel_when_conditions_differ(self):
        a = {"id": "a", "valid_from": "2026-01-01", "applicability": _app(audience="面试官")}
        b = {"id": "b", "valid_from": "2026-06-01", "applicability": _app(audience="猎头")}
        r = arbitrator.adjudicate_pair(a, b)
        self.assertEqual(r["verdict"], arbitrator.PARALLEL)

    def test_replacement_when_dated_and_overlap(self):
        a = {"id": "a", "valid_from": "2026-01-01", "applicability": _app()}
        b = {"id": "b", "valid_from": "2026-06-01", "applicability": _app()}
        r = arbitrator.adjudicate_pair(a, b)
        self.assertEqual(r["verdict"], arbitrator.REPLACEMENT)
        self.assertEqual(r["supersede_old"], "a")  # 旧的 a 被取代
        self.assertEqual(r["superseded_by"], "b")

    def test_undated_when_no_date(self):
        a = {"id": "a", "valid_from": "", "applicability": _app()}
        b = {"id": "b", "valid_from": "", "applicability": _app()}
        r = arbitrator.adjudicate_pair(a, b)
        self.assertEqual(r["verdict"], arbitrator.UNDATED)

    def test_undated_when_one_date_only(self):
        a = {"id": "a", "valid_from": "2026-01-01", "applicability": _app()}
        b = {"id": "b", "valid_from": "", "applicability": _app()}
        r = arbitrator.adjudicate_pair(a, b)
        self.assertEqual(r["verdict"], arbitrator.UNDATED)

    def test_undated_when_suspect(self):
        a = {"id": "a", "valid_from": "2026-01-01", "applicability": _app(audience="面试官")}
        b = {"id": "b", "valid_from": "2026-06-01", "applicability": _app()}
        r = arbitrator.adjudicate_pair(a, b)
        self.assertEqual(r["verdict"], arbitrator.UNDATED)

    def test_confidence_floor_escalates(self):
        a = {"id": "a", "valid_from": "2026-01-01", "applicability": _app()}
        b = {"id": "b", "valid_from": "2026-06-01", "applicability": _app()}
        r = arbitrator.adjudicate_pair(a, b, confidence=0.5)  # < 0.7
        self.assertEqual(r["verdict"], arbitrator.UNDATED)


class TestFindCandidates(unittest.TestCase):
    def test_multi_host_group(self):
        entries = [
            {"id": "a", "name": "job-city", "abstract": "只看杭州", "host": "workbuddy"},
            {"id": "b", "name": "job-city", "abstract": "改上海优先", "host": "dsh"},
        ]
        groups = arbitrator.find_candidates(entries)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["hosts"], {"workbuddy", "dsh"})

    def test_single_host_not_candidate(self):
        entries = [
            {"id": "a", "name": "job-city", "abstract": "只看杭州", "host": "workbuddy"},
            {"id": "b", "name": "job-city", "abstract": "改上海优先", "host": "workbuddy"},
        ]
        groups = arbitrator.find_candidates(entries)
        self.assertEqual(len(groups), 0)

    def test_different_topic_not_grouped(self):
        entries = [
            {"id": "a", "name": "job-city", "abstract": "只看杭州", "host": "workbuddy"},
            {"id": "b", "name": "salary", "abstract": "薪资三数", "host": "dsh"},
        ]
        groups = arbitrator.find_candidates(entries)
        self.assertEqual(len(groups), 0)


if __name__ == "__main__":
    unittest.main()
