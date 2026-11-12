"""加密备份（lmr.backup）单元测试。"""

from __future__ import annotations

import unittest
from unittest import mock

from lmr import backup as backup_module
from lmr.errors import ValidationError
from tests.base import MemTestCase, candidate

import pytest

pytestmark = pytest.mark.integration


class BackupNoCryptoTest(MemTestCase):
    """未安装加密库时，backup 优雅降级为明确的未配置提示。"""

    def test_backup_without_crypto_degrades_gracefully(self):
        with mock.patch.object(backup_module, "_fernet", return_value=None):
            with self.assertRaises(ValidationError) as ctx:
                backup_module.backup(self.paths, self.settings)
            self.assertIn("未安装加密库", str(ctx.exception))

    def test_restore_without_key_fails_clearly(self):
        # 无密钥文件 + 无加密库，restore 应明确报错而非内部错误。
        with mock.patch.object(backup_module, "_load_key", return_value=None):
            with self.assertRaises(ValidationError):
                backup_module.restore(self.paths, self.settings, "nonexistent.enc")


class FakeFernet:
    """用 XOR 模拟 Fernet，验证 backup→restore 往返逻辑（不测真实加密强度）。"""

    @staticmethod
    def generate_key():
        return b"fake-key-fake-key-fake-key-fake-key-fake-key-fake-key-fake-key-fake-key=="

    def __init__(self, key):
        self.key = key

    def encrypt(self, data):
        return b"ENC:" + data

    def decrypt(self, data):
        return data[4:]


class BackupRoundTripTest(MemTestCase):
    """mock 加密库，验证备份→恢复的数据一致性。"""

    def setUp(self):
        super().setUp()
        # 写入一条真实记忆，确保有数据可备份。
        self.entry = self.make(name="备份-测试条目")
        # mock 加密库与密钥。
        self.fernet_patch = mock.patch.object(backup_module, "_fernet", return_value=FakeFernet)
        self.fernet_patch.start()
        self.addCleanup(self.fernet_patch.stop)
        # 密钥指向临时文件。
        self.key_patch = mock.patch.object(backup_module, "KEY_FILE", self.tmp_path() / "backup.key")
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def tmp_path(self):
        from pathlib import Path
        return Path(self.tmp.name)

    def test_roundtrip_preserves_data(self):
        # 备份
        result = backup_module.backup(self.paths, self.settings)
        self.assertTrue(result["encrypted"])
        backup_file = result["file"]

        # 清空 store，模拟丢失
        for f in self.files():
            f.unlink()

        # 恢复
        backup_module.restore(self.paths, self.settings, backup_file)
        # 记忆回来了
        self.assertGreaterEqual(len(self.files()), 1)

    def test_key_not_in_backup(self):
        """密钥文件不应被打进备份包。"""
        # 确保密钥文件存在
        backup_module._ensure_key()
        # 备份
        result = backup_module.backup(self.paths, self.settings)
        # 备份产物是密文，不直接含 store 明文（FakeFernet 加 ENC: 前缀模拟）
        import base64
        from pathlib import Path
        raw = base64.b64decode(Path(result["file"]).read_bytes())
        self.assertFalse(b"backup.key" in raw)


class BackupSyncTest(MemTestCase):
    """云端同步（sync）的优雅降级与远端读取。"""

    def setUp(self):
        super().setUp()
        self.fernet_patch = mock.patch.object(backup_module, "_fernet", return_value=FakeFernet)
        self.fernet_patch.start()
        self.addCleanup(self.fernet_patch.stop)
        self.key_patch = mock.patch.object(backup_module, "KEY_FILE", self.tmp_path() / "backup.key")
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def tmp_path(self):
        from pathlib import Path
        return Path(self.tmp.name)

    def test_sync_without_remote_degrades(self):
        """未配置 backup.remote 时，sync 只本地加密，返回 synced=False。"""
        result = backup_module.sync(self.paths, self.settings)
        self.assertFalse(result["synced"])
        self.assertIn("未配置云端目标", result["reason"])

    def test_sync_pushes_to_remote(self):
        """配置了远端时，sync 加密后 push 密文。"""
        import json
        from pathlib import Path
        remote = "https://example.com/owner/repo.git"
        # 往 config.json 写入 backup.remote
        cfg = json.loads(self.paths.config.read_text(encoding="utf-8"))
        cfg["backup"] = {"remote": remote}
        self.paths.config.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        # mock push 避免真实网络
        with mock.patch.object(backup_module.gitutil, "push") as push_mock:
            result = backup_module.sync(self.paths, self.settings)
        self.assertTrue(result["synced"])
        self.assertEqual(result["remote"], remote)
        push_mock.assert_called_once()
        # 备份目录是独立 git，且只 track 密文 + .gitignore
        target = Path(result["file"]).parent
        self.assertTrue((target / ".git").is_dir())
        self.assertTrue((target / ".gitignore").is_file())

    def test_sync_backup_dir_contains_no_plaintext(self):
        """备份目录 git 里不应含任何明文记忆。"""
        from pathlib import Path
        self.make(name="同步-明文检测条目", conclusion="明文敏感关键词xyzzy")
        result = backup_module.backup(self.paths, self.settings)
        target = Path(result["file"]).parent
        backup_module._ensure_backup_repo(target)
        backup_module.gitutil.commit(target, "test")
        # 用 git ls-files 看 track 了什么
        tracked = backup_module.gitutil._run(
            ["git", "ls-files"], target
        ).stdout.strip().splitlines()
        # 只允许 .enc 密文与 .gitignore
        for name in tracked:
            self.assertTrue(name.endswith(".enc") or name.endswith(".gitignore"), name)
        # 密文里不含明文关键词（FakeFernet 加 ENC: 前缀，原文仍在，这里只验证
        # 不 track 任何 .md 明文文件）
        self.assertFalse(any(name.endswith(".md") for name in tracked))
        # 密文必须确实被 track（.gitignore 白名单 !*.enc 要生效，防回归）
        self.assertTrue(any(name.endswith(".enc") for name in tracked),
                        "密文未被 track，检查 .gitignore 白名单 !*.enc")


class RestoreFromCloudTest(MemTestCase):
    """restore --from-cloud 的行为。"""

    def setUp(self):
        super().setUp()
        self.fernet_patch = mock.patch.object(backup_module, "_fernet", return_value=FakeFernet)
        self.fernet_patch.start()
        self.addCleanup(self.fernet_patch.stop)
        self.key_patch = mock.patch.object(backup_module, "KEY_FILE", self.tmp_path() / "backup.key")
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def tmp_path(self):
        from pathlib import Path
        return Path(self.tmp.name)

    def test_restore_from_cloud_without_remote_fails_clearly(self):
        """未配置远端时，--from-cloud 明确报错而非内部错误。"""
        # 先生成密钥，确保密钥检查先通过，才能走到「未配置远端」分支。
        backup_module._ensure_key()
        with self.assertRaises(ValidationError) as ctx:
            backup_module.restore(self.paths, self.settings, from_cloud=True)
        self.assertIn("未配置云端目标", str(ctx.exception))

    def test_restore_from_cloud_pulls_and_recovers(self):
        """配置远端后，--from-cloud 拉取密文并恢复。"""
        import json
        from pathlib import Path
        self.make(name="云端恢复-测试条目")
        remote = "https://example.com/owner/repo.git"
        cfg = json.loads(self.paths.config.read_text(encoding="utf-8"))
        cfg["backup"] = {"remote": remote}
        self.paths.config.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        # 先备份，把密文留在本地备份目录
        result = backup_module.backup(self.paths, self.settings)
        # 清空 store
        for f in self.files():
            f.unlink()
        # 换机场景：备份目录尚未 clone，走 clone 分支；mock clone 后取本地密文恢复
        with mock.patch.object(backup_module.gitutil, "clone") as clone_mock:
            restored = backup_module.restore(self.paths, self.settings, from_cloud=True)
        self.assertTrue(restored["restored"])
        clone_mock.assert_called_once()
        self.assertGreaterEqual(len(self.files()), 1)

    def test_restore_from_cloud_pull_when_already_cloned(self):
        """备份目录已是远端 clone 出的 git 时，--from-cloud 走 pull 分支。"""
        import json
        from pathlib import Path
        self.make(name="云端恢复-pull分支")
        remote = "https://example.com/owner/repo.git"
        cfg = json.loads(self.paths.config.read_text(encoding="utf-8"))
        cfg["backup"] = {"remote": remote}
        self.paths.config.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        # 先 sync 建立 git 仓库（mock push），使备份目录成为 clone 出的 git
        with mock.patch.object(backup_module.gitutil, "push"):
            backup_module.sync(self.paths, self.settings)
        for f in self.files():
            f.unlink()
        with mock.patch.object(backup_module.gitutil, "pull") as pull_mock:
            restored = backup_module.restore(self.paths, self.settings, from_cloud=True)
        self.assertTrue(restored["restored"])
        pull_mock.assert_called_once()
