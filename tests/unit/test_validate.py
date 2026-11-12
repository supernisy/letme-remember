"""第一审字段校验：每一项非法输入都要给出明确错误。"""

import unittest

from lmr import validate
from lmr.errors import ValidationError
from tests.base import candidate
from lmr.store import build_candidate

import pytest

pytestmark = pytest.mark.unit

# @req 2.2


def errors_for(**overrides):
    meta, body = build_candidate(candidate(**overrides))
    return validate.validate_meta(meta, body)


class TestValidate(unittest.TestCase):
    def test_valid_candidate(self):
        # @req 2.2
        self.assertEqual(errors_for(), [])

    def test_missing_reason(self):
        # @req 2.2
        self.assertTrue(any("理由" in item for item in errors_for(reason="")))

    def test_missing_required(self):
        # @req 2.2
        self.assertTrue(any("必填" in item for item in errors_for(abstract="")))

    def test_bad_date(self):
        # @req 2.2
        self.assertTrue(any("ISO 8601" in item for item in errors_for(valid_from="不是日期")))

    def test_invalid_interval(self):
        # @req 2.2
        self.assertTrue(any("invalid_at" in item for item in errors_for(
            valid_from="2026-06-01", invalid_at="2026-01-01"
        )))

    def test_superseded_without_invalidation(self):
        # @req 2.2
        self.assertTrue(any("superseded_by" in item for item in errors_for(
            superseded_by="另一条"
        )))

    def test_weight_out_of_range(self):
        # @req 2.2
        self.assertTrue(any("weight" in item for item in errors_for(weight="99")))

    def test_unknown_type(self):
        # @req 2.2
        self.assertTrue(any("未知类型" in item for item in errors_for(type="不存在的类型")))

    def test_import_time_semantics(self):
        # @req 2.4
        meta, body = build_candidate(candidate(
            source_category="规则文件", original_date="2026-01-15", batch="批次A"
        ))
        self.assertEqual(validate.validate_meta(meta, body), [])
        self.assertEqual(meta["valid_from"], "2026-01-15")
        self.assertEqual(meta["author"], "import:规则文件")
        self.assertEqual(len(meta["provenance"]), 3)
        self.assertNotEqual(meta["created"], meta["valid_from"])

    def test_import_missing_provenance_parts(self):
        # @req 2.4
        with self.assertRaises(ValidationError):
            build_candidate(candidate(
                source_category="规则文件", original_date="2026-01-15", batch=""
            ))
