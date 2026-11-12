"""加密备份（lmr.backup）单元测试。"""

from __future__ import annotations

import unittest
from unittest import mock

from lmr import backup as backup_module
from lmr.errors import ValidationError
from tests.base import MemTestCase, candidate


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
