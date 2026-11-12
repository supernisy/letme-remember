"""gitutil 扩展（push/pull/is_clean）单元测试。"""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from lmr import gitutil

import pytest

pytestmark = pytest.mark.unit


class IsCleanTest(unittest.TestCase):
    def test_is_clean_true_when_porcelain_empty(self):
        with mock.patch.object(gitutil, "_run", return_value=mock.Mock(stdout="")):
            self.assertTrue(gitutil.is_clean("/tmp/x"))

    def test_is_clean_false_when_porcelain_nonempty(self):
        with mock.patch.object(gitutil, "_run", return_value=mock.Mock(stdout="?? a.enc\n")):
            self.assertFalse(gitutil.is_clean("/tmp/x"))


class PushPullTest(unittest.TestCase):
    def test_push_calls_git_push(self):
        with mock.patch.object(gitutil, "_run") as run_mock:
            gitutil.push("/tmp/x", "origin", "master")
        args = run_mock.call_args[0]
        self.assertEqual(args, (["git", "push", "origin", "master"], "/tmp/x"))

    def test_pull_calls_git_pull(self):
        with mock.patch.object(gitutil, "_run") as run_mock:
            gitutil.pull("/tmp/x", "origin", "master")
        args = run_mock.call_args[0]
        self.assertEqual(args, (["git", "pull", "origin", "master"], "/tmp/x"))

    def test_push_failure_raises_internal_error(self):
        from lmr.errors import InternalError
        with mock.patch.object(gitutil, "_run", side_effect=InternalError("git 操作失败")):
            with self.assertRaises(InternalError):
                gitutil.push("/tmp/x", "origin", "master")
