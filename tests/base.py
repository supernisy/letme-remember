"""测试公共装置：每个用例独享一个临时数据目录，不触碰任何真实记忆。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from lmr import config, store


def candidate(**overrides):
    """构造一条完全虚构的候选记忆。"""
    raw = {
        "name": "虚构-记忆条目",
        "abstract": "虚构测试条目：长期记忆采用纯文本文件",
        "type": "decision",
        "conclusion": "在虚构场景中，记忆以纯文本文件作为唯一真相源",
        "reason": "因为纯文本便于版本管理与本地检索；本条只用于测试，不代表任何真实偏好",
        "author": "unit-test",
    }
    raw.update(overrides)
    return raw


class MemTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_env = os.environ.get(config.ENV_DATA_DIR)
        os.environ[config.ENV_DATA_DIR] = self.tmp.name
        self.addCleanup(self._restore_env)
        self.paths = store.init_data_dir(Path(self.tmp.name), sample=False)
        # 显式固定设置，避免用户级配置影响测试结果
        self.settings = dict(config.DEFAULT_SETTINGS)

    def _restore_env(self):
        if self.previous_env is None:
            os.environ.pop(config.ENV_DATA_DIR, None)
        else:
            os.environ[config.ENV_DATA_DIR] = self.previous_env

    def files(self):
        return sorted(self.paths.store.glob("*.md"))

    def make(self, **overrides):
        return store.record(self.paths, self.settings, candidate(**overrides))
