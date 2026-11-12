"""备份云端同步端到端：加密 → push 到 bare 远端 → clone → 密钥解密恢复。

隔离铁律：全程用真实 cryptography（本机已装），但走本地 file:// bare 仓库
模拟云端，不触碰任何真实网络或真实数据目录。
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from lmr import backup, config, store

import pytest

pytestmark = pytest.mark.e2e


class TestBackupSyncE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lmr-backup-e2e-")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.paths = store.init_data_dir(Path(self.tmp) / "data", sample=False)
        self.settings = dict(config.DEFAULT_SETTINGS)
        # 独立密钥文件，避免污染真实密钥
        self.key_file = Path(self.tmp) / "backup.key"
        self._key_patch = None

    def _seed_memory(self):
        return store.record(self.paths, self.settings, {
            "name": "e2e-云端同步验证", "abstract": "验证加密→push→clone→恢复全链路",
            "type": "decision", "conclusion": "云端只存密文，密钥不上云",
            "reason": "端到端验收", "author": "e2e",
        })

    def _set_remote(self, remote_url):
        cfg = json.loads(self.paths.config.read_text(encoding="utf-8"))
        cfg["backup"] = {"remote": remote_url}
        self.paths.config.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def test_encrypt_push_clone_restore_roundtrip(self):
        # 密钥落在临时 KEY_FILE，先确保密钥存在
        original_key_file = backup.KEY_FILE
        backup.KEY_FILE = self.key_file
        self.addCleanup(lambda: setattr(backup, "KEY_FILE", original_key_file))

        self._seed_memory()
        # bare 远端模拟云端
        remote_repo = Path(self.tmp) / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote_repo)], check=True)
        self._set_remote(remote_repo.as_uri())

        # sync：加密 → push
        result = backup.sync(self.paths, self.settings)
        self.assertTrue(result["synced"])

        # 云端只含密文 + .gitignore，无明文 .md
        tree = subprocess.run(
            ["git", "-C", str(remote_repo), "ls-tree", "-r", "--name-only", "master"],
            capture_output=True, text=True,
        ).stdout.strip().splitlines()
        self.assertTrue(any(n.endswith(".enc") for n in tree), "云端无密文")
        self.assertFalse(any(n.endswith(".md") for n in tree), "云端含明文")

        # 换机：clone 密文到新目录，用密钥解密恢复
        clone_dir = Path(self.tmp) / "new-backup"
        subprocess.run(["git", "clone", "-q", remote_repo.as_uri(), str(clone_dir)], check=True)
        new_data = Path(self.tmp) / "new-data"
        new_paths = store.init_data_dir(new_data, sample=False)
        encs = sorted(clone_dir.glob("*.enc"))
        self.assertTrue(encs, "clone 目录无密文")
        restored = backup.restore(new_paths, self.settings, backup_file=str(encs[-1]))
        self.assertTrue(restored["restored"])
        self.assertGreaterEqual(len(list(new_paths.store.glob("*.md"))), 1)
