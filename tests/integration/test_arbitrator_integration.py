"""方向② 仲裁链路的集成测试：host/applicability 落库、arbitrate 提案 apply。

覆盖：字段端到端往返、host 推导、applicability 扁平化、arbitrate 提案裁决落地。
"""

import unittest

import pytest

from lmr import arbitrator, frontmatter, proposal, schema, store
from tests.base import MemTestCase, candidate

pytestmark = pytest.mark.integration


class TestHostAndApplicabilityField(MemTestCase):
    def test_host_from_explicit_declared(self):
        raw = candidate(host=" DSH ", name="host-显式", type="semantic")
        result = store.record(self.paths, self.settings, raw)
        meta, _ = frontmatter.read_file(self.paths.store / (result["id"] + ".md"))
        self.assertEqual(meta["host"], "dsh")  # 归一化

    def test_host_inferred_from_author(self):
        raw = candidate(
            name="host-推导", type="semantic",
            source_category="workbuddy-project-memory",
            original_date="2026-01-01", batch="batch-01",
        )
        result = store.record(self.paths, self.settings, raw)
        meta, _ = frontmatter.read_file(self.paths.store / (result["id"] + ".md"))
        self.assertEqual(meta["host"], "workbuddy")

    def test_applicability_roundtrip(self):
        raw = candidate(
            name="app-往返", type="semantic",
            applicability={
                "audience": "面试官", "scenario": "薪资谈判",
                "time": "2026上半年", "precondition": "只要在职",
                "extra": {"预算": "50万"},
            },
        )
        result = store.record(self.paths, self.settings, raw)
        meta, _ = frontmatter.read_file(self.paths.store / (result["id"] + ".md"))
        self.assertEqual(meta["applicability_audience"], "面试官")
        self.assertEqual(meta["applicability_scenario"], "薪资谈判")
        self.assertEqual(meta["applicability_time"], "2026上半年")
        self.assertEqual(meta["applicability_precondition"], "只要在职")
        self.assertIn("预算=50万", meta["applicability_extra"])
        # 还原
        app = frontmatter.meta_to_applicability(meta)
        self.assertEqual(app["audience"], "面试官")
        self.assertEqual(app["extra"], {"预算": "50万"})

    def test_applicability_all_empty_is_legal(self):
        raw = candidate(name="app-空", type="semantic", applicability={})
        result = store.record(self.paths, self.settings, raw)
        meta, _ = frontmatter.read_file(self.paths.store / (result["id"] + ".md"))
        self.assertEqual(meta["applicability_audience"], "")
        self.assertEqual(meta["applicability_extra"], [])


class TestArbitrateProposalApply(MemTestCase):
    def _write(self, name, host, valid_from, abstract, applicability=None, type_="semantic"):
        raw = candidate(
            name=name, type=type_, host=host,
            valid_from=valid_from, abstract=abstract,
            applicability=applicability or {},
        )
        return store.record(self.paths, self.settings, raw)["id"]

    def test_arbitrate_proposal_replacement(self):
        # 同名不同 type（落不同文件），不同 host，构成可靠的多宿主冲突。
        a = self._write("job-city", "workbuddy", "2026-01-01", "只看杭州", type_="semantic")
        b = self._write("job-city", "dsh", "2026-06-01", "改上海优先", type_="episodic")
        result = arbitrator.scan(self.paths, self.settings)
        adj = [x for x in result["adjudications"] if x["verdict"] == arbitrator.REPLACEMENT]
        self.assertEqual(len(adj), 1)
        self.assertEqual(adj[0]["supersede_old"], a)
        self.assertEqual(adj[0]["superseded_by"], b)

    def test_arbitrate_proposal_apply_replacement(self):
        a = self._write("job-city", "workbuddy", "2026-01-01", "只看杭州", type_="semantic")
        b = self._write("job-city", "dsh", "2026-06-01", "改上海优先", type_="episodic")
        # 手动构造 arbitrate 提案并 apply：replacement
        data = proposal.create(
            self.paths, "arbitrate", a,
            {"verdict": "replacement", "supersede_old": a, "superseded_by": b},
        )
        outcome = proposal.apply(self.paths, self.settings, data["id"])
        self.assertEqual(outcome["op"], "arbitrate")
        self.assertEqual(outcome["result"]["supersede_old"], a)
        # 旧条目被降权（superseded_by 指向新条目），未失效
        meta, _ = frontmatter.read_file(self.paths.store / (a + ".md"))
        self.assertEqual(meta["superseded_by"], b)
        self.assertEqual(meta["invalid_at"], "")

    def test_arbitrate_proposal_apply_parallel(self):
        a = self._write("job-city", "workbuddy", "2026-01-01", "只看杭州", {"audience": "面试官"})
        b = self._write("job-city", "dsh", "2026-06-01", "改上海优先", {"audience": "猎头"})
        data = proposal.create(
            self.paths, "arbitrate", a,
            {"verdict": "parallel"},
        )
        outcome = proposal.apply(self.paths, self.settings, data["id"])
        self.assertEqual(outcome["result"]["verdict"], "parallel")
        # 两条都未标记取代
        meta_a, _ = frontmatter.read_file(self.paths.store / (a + ".md"))
        meta_b, _ = frontmatter.read_file(self.paths.store / (b + ".md"))
        self.assertEqual(meta_a["superseded_by"], "")
        self.assertEqual(meta_b["superseded_by"], "")

    def test_arbitrate_proposal_apply_undated_keep_both(self):
        a = self._write("job-city", "workbuddy", "", "只看杭州")
        b = self._write("job-city", "dsh", "", "改上海优先")
        data = proposal.create(
            self.paths, "arbitrate", a,
            {"verdict": "undated", "a_id": a, "b_id": b, "choice": "keep_both"},
        )
        outcome = proposal.apply(self.paths, self.settings, data["id"])
        self.assertEqual(outcome["result"]["choice"], "keep_both")
        meta_a, _ = frontmatter.read_file(self.paths.store / (a + ".md"))
        meta_b, _ = frontmatter.read_file(self.paths.store / (b + ".md"))
        self.assertEqual(meta_a["superseded_by"], "")
        self.assertEqual(meta_b["superseded_by"], "")


if __name__ == "__main__":
    unittest.main()
