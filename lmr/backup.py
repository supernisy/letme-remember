"""记忆数据的加密备份与云端同步（backup/spec.md 落地）。

核心原则（硬约束）：
- 备份在本地加密，云端只存密文；密钥永不上云，与密文分离。
- 备份是可选能力：加密库或云端目标未配置时，backup/restore 优雅降级
  为明确的「未配置」提示，绝不报内部错误、绝不产出明文备份。
- 加密库用 cryptography（Fernet，AES-128-CBC + HMAC），作为可选依赖。

密钥存储：~/.letme-remember/backup.key（本地，不进备份包）。
密文存储：默认本地备份目录 <data-dir>/backup/，可扩展云端目标。
"""

from __future__ import annotations

import base64
import shutil
import tarfile
from pathlib import Path

from . import gitutil
from .errors import ValidationError

KEY_DIR = Path.home() / ".letme-remember"
KEY_FILE = KEY_DIR / "backup.key"


def _fernet():
    """加载 Fernet；加密库未装返回 None（触发优雅降级）。"""
    try:
        from cryptography.fernet import Fernet
        return Fernet
    except ImportError:
        return None


def _load_key():
    if not KEY_FILE.is_file():
        return None
    return KEY_FILE.read_text(encoding="utf-8").strip()


def _ensure_key():
    """确保本地有密钥；没有则生成一个并保存（密钥不上云）。"""
    key = _load_key()
    if key is not None:
        return key
    Fernet = _fernet()
    if Fernet is None:
        return None
    key = Fernet.generate_key().decode("ascii")
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key + "\n", encoding="utf-8")
    return key


def _encrypt_bytes(data: bytes, key: str) -> bytes:
    Fernet = _fernet()
    if Fernet is None:
        raise ValidationError("未安装加密库 cryptography，无法加密备份")
    return Fernet(key.encode("ascii")).encrypt(data)


def _decrypt_bytes(data: bytes, key: str) -> bytes:
    Fernet = _fernet()
    if Fernet is None:
        raise ValidationError("未安装加密库 cryptography，无法解密备份")
    return Fernet(key.encode("ascii")).decrypt(data)


def _pack_store(paths) -> bytes:
    """把数据目录打包成 tar 字节流（不含 .index 缓存与密钥）。"""
    import io
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in sorted(paths.store.glob("*.md")):
            tar.add(path, arcname=path.name)
        if paths.proposals.is_dir():
            for path in sorted(paths.proposals.glob("*.json")):
                tar.add(path, arcname="proposals/" + path.name)
        if paths.audit.is_file():
            tar.add(paths.audit, arcname="audit.log")
        if paths.config.is_file():
            tar.add(paths.config, arcname="config.json")
    return buffer.getvalue()


def _unpack_store(paths, data: bytes):
    import io
    buffer = io.BytesIO(data)
    paths.store.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
        for member in tar.getmembers():
            # 防止路径穿越。
            target = Path(member.name)
            if target.is_absolute() or ".." in target.parts:
                continue
            if member.name.startswith("proposals/"):
                dest = paths.proposals / target.name
                paths.proposals.mkdir(parents=True, exist_ok=True)
            elif member.name in ("audit.log", "config.json"):
                dest = paths.root / member.name
            else:
                dest = paths.store / member.name
            if member.isfile():
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)


def backup(paths, settings, target_dir=None):
    """加密数据目录并产出密文备份。

    返回备份产物路径；加密库未装时抛 ValidationError（未配置降级）。
    """
    key = _ensure_key()
    if key is None:
        raise ValidationError("未安装加密库 cryptography，无法备份（可选依赖）")
    plain = _pack_store(paths)
    cipher = _encrypt_bytes(plain, key)
    target = Path(target_dir) if target_dir else (paths.root / "backup")
    target.mkdir(parents=True, exist_ok=True)
    stamp = gitutil.now_iso().replace(":", "").replace("-", "").replace("T", "_")
    out_file = target / ("backup-%s.enc" % stamp)
    out_file.write_bytes(base64.b64encode(cipher))
    return {"file": str(out_file), "bytes": len(cipher), "encrypted": True}


def restore(paths, settings, backup_file):
    """用本地密钥解密备份并恢复数据目录。密钥缺失时明确报错。"""
    key = _load_key()
    if key is None:
        raise ValidationError("本地无备份密钥（%s），无法恢复" % KEY_FILE)
    path = Path(backup_file)
    if not path.is_file():
        raise ValidationError("备份文件不存在: %s" % backup_file)
    cipher = base64.b64decode(path.read_bytes())
    plain = _decrypt_bytes(cipher, key)
    _unpack_store(paths, plain)
    return {"file": str(path), "restored": True}
