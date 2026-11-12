"""待审队列（lmr.queue）单元测试：L1/L2 候选的异步入库审批。"""

from __future__ import annotations

import json

from lmr import queue, store
from lmr.errors import NotFoundError, ValidationError

from tests.base import MemTestCase, candidate

import pytest

pytestmark = pytest.mark.integration


class QueueEnqueueTest(MemTestCase):
    def test_enqueue_l1_creates_pending(self):
        data = queue.enqueue(self.paths, self.settings, candidate(), "L1")
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["level"], "L1")
        pending = queue.list_pending(self.paths)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], data["id"])
        # 未写入真相源
        self.assertEqual(len(self.files()), 0)

    def test_enqueue_rejects_l0(self):
        with self.assertRaises(ValidationError):
            queue.enqueue(self.paths, self.settings, candidate(), "L0")

    def test_enqueue_requires_conclusion(self):
        with self.assertRaises(ValidationError):
            queue.enqueue(self.paths, self.settings, {"name": "x"}, "L1")


class QueueApproveTest(MemTestCase):
    def test_approve_writes_through_store(self):
        data = queue.enqueue(self.paths, self.settings, candidate(), "L1")
        result = queue.approve(self.paths, self.settings, data["id"])
        # 已入库
        self.assertEqual(len(self.files()), 1)
        self.assertIn("id", result["result"])
        # 队列清空
        self.assertEqual(len(queue.list_pending(self.paths)), 0)

    def test_approve_missing_id(self):
        with self.assertRaises(NotFoundError):
            queue.approve(self.paths, self.settings, "nonexistent")

    def test_approve_twice_fails(self):
        data = queue.enqueue(self.paths, self.settings, candidate(), "L1")
        queue.approve(self.paths, self.settings, data["id"])
        with self.assertRaises(ValidationError):
            queue.approve(self.paths, self.settings, data["id"])

    def test_approve_runs_redaction(self):
        # 含密钥形状的候选，approve 时仍应被脚本红线打码（不绕过安全闸门）。
        secret = candidate(
            name="含密钥候选",
            conclusion="我的 key 是 sk-abcdef1234567890abcdef",
        )
        data = queue.enqueue(self.paths, self.settings, secret, "L1")
        result = queue.approve(self.paths, self.settings, data["id"])
        # 入库成功但正文中的密钥形状被打了码
        entry_id = result["result"]["id"]
        text = store.show(self.paths, entry_id)
        self.assertNotIn("sk-abcdef1234567890abcdef", text)


class QueueRejectTest(MemTestCase):
    def test_reject_does_not_write(self):
        data = queue.enqueue(self.paths, self.settings, candidate(), "L1")
        result = queue.reject(self.paths, data["id"])
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(len(self.files()), 0)
        self.assertEqual(len(queue.list_pending(self.paths)), 0)

    def test_reject_missing_id(self):
        with self.assertRaises(NotFoundError):
            queue.reject(self.paths, "nonexistent")


class QueueExpireTest(MemTestCase):
    def test_expire_moves_to_archive(self):
        data = queue.enqueue(self.paths, self.settings, candidate(), "L1")
        # 手工把 created 改到很久以前，模拟超时
        path = self.paths.proposals / ("queue-%s.json" % data["id"])
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["created"] = "2000-01-01T00:00:00+00:00"
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result = queue.expire(self.paths, timeout_days=7)
        self.assertIn(data["id"], result["expired"])
        # 队列清空
        self.assertEqual(len(queue.list_pending(self.paths)), 0)
        # archive 保留了完整内容
        archived = self.paths.archive / ("queue-%s.json" % data["id"])
        self.assertTrue(archived.is_file())
        archived_data = json.loads(archived.read_text(encoding="utf-8"))
        self.assertEqual(archived_data["status"], "expired")
        self.assertIn("conclusion", archived_data["candidate"])

    def test_expire_ignores_fresh(self):
        data = queue.enqueue(self.paths, self.settings, candidate(), "L1")
        result = queue.expire(self.paths, timeout_days=7)
        self.assertEqual(result["expired"], [])
        self.assertEqual(len(queue.list_pending(self.paths)), 1)
        self.assertEqual(queue.list_pending(self.paths)[0]["id"], data["id"])
