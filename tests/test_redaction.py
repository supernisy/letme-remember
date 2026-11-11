"""第一审形状规则：规则表正反样例、处置分层、白名单、审计不记原值。"""

import unittest

from lmr import redaction

# @req 3.1 @req 3.2


class TestRedaction(unittest.TestCase):
    def setUp(self):
        self.rules = redaction.load_rules()
        self.settings = {"redact_b_class": False}

    def test_rule_table_positive_negative(self):
        # @req 3.1
        for rule in self.rules["rules"]:
            with self.subTest(rule=rule["id"]):
                self.assertTrue(
                    redaction.rule_hits(rule["positive"], rule["id"], self.rules),
                    "%s 的正例未命中" % rule["id"],
                )
                self.assertFalse(
                    redaction.rule_hits(rule["negative"], rule["id"], self.rules),
                    "%s 的反例被误命中" % rule["id"],
                )

    def test_a_masked_b_warned(self):
        # @req 3.2
        text = "虚构凭据 AKIA0000000000000000 与邮箱 demo@example.invalid"
        masked, findings = redaction.redact(text, self.settings, self.rules)
        self.assertIn(redaction.REDACTED, masked)
        self.assertNotIn("AKIA", masked)
        self.assertIn("demo@example.invalid", masked)
        actions = {item["rule"]: item["action"] for item in findings}
        self.assertEqual(actions.get("R-CRED-01"), "masked")
        self.assertEqual(actions.get("R-ID-03"), "warned")

    def test_b_can_be_masked_when_configured(self):
        # @req 3.2
        text = "邮箱 demo@example.invalid"
        masked, _ = redaction.redact(text, {"redact_b_class": True}, self.rules)
        self.assertNotIn("demo@example.invalid", masked)

    def test_allowlist(self):
        # @req 3.2
        text = "api_key: zerovalue000"
        masked, findings = redaction.redact(
            text, self.settings, self.rules, extra_allowlist=["zerovalue000"]
        )
        self.assertIn("zerovalue000", masked)
        self.assertEqual(findings, [])

    def test_narrative_facts_are_not_blocked(self):
        # @req 3.2
        text = "这是一段关于个人经历的叙述，没有任何机器可读的形状"
        masked, findings = redaction.redact(text, self.settings, self.rules)
        self.assertEqual(masked, text)
        self.assertEqual(findings, [])

    def test_audit_never_records_values(self):
        # @req 3.2
        _, findings = redaction.redact(
            "AKIA0000000000000000", self.settings, self.rules
        )
        lines = redaction.audit_lines(findings)
        self.assertTrue(lines)
        self.assertFalse(any("AKIA" in line for line in lines))
        self.assertFalse(any("0000000000000000" in line for line in lines))
