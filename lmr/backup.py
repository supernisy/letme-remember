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


_BACKUP_GITIGNORE = "*\n!*.enc\n!.gitignore\n"


def _backup_dir(paths, target_dir=None):
    return Path(target_dir) if target_dir else (paths.root / "backup")


def _ensure_backup_repo(target):
    """确保备份目录是独立 git，且只 track 密文与 .gitignore。"""
    target.mkdir(parents=True, exist_ok=True)
    ignore = target / ".gitignore"
    if not ignore.is_file():
        ignore.write_text(_BACKUP_GITIGNORE, encoding="utf-8")
    gitutil.ensure_repo(target)


def _remote(paths, settings=None):
    """从配置读云端远端 URL；未配置返回 None。

    优先读数据目录内 config.json 的 backup.remote，其次读合并后的
    settings（backup 键）。两者都没有则返回 None（未配置）。
    """
    import json

    if paths.config.is_file():
        try:
            data = json.loads(paths.config.read_text(encoding="utf-8"))
            remote = (data or {}).get("backup", {}).get("remote")
            if remote:
                return remote
        except (OSError, ValueError):
            pass
    backup_cfg = (settings or {}).get("backup") or {}
    return backup_cfg.get("remote")


def sync(paths, settings, target_dir=None):
    """加密数据目录并把密文推送到配置的云端远端。

    未配置云端目标时优雅降级为「仅本地加密」，返回 synced=False；
    配置了则提交并 push，云端只含密文。密钥永不上云。
    """
    result = backup(paths, settings, target_dir=target_dir)
    target = Path(result["file"]).parent
    _ensure_backup_repo(target)
    gitutil.commit(target, "backup %s" % result["file"])
    remote = _remote(paths, settings)
    if not remote:
        return dict(result, synced=False, reason="未配置云端目标（backup.remote）")
    gitutil.push(target, remote, "master")
    return dict(result, synced=True, remote=remote)


def _latest_enc(target):
    """返回备份目录里最新的密文文件；无密文返回 None。"""
    encs = sorted(target.glob("*.enc"), key=lambda p: p.stat().st_mtime)
    return encs[-1] if encs else None


def _pull_from_remote(target, remote):
    """把云端密文拉到本地备份目录。

    目录已是远端 clone 出的 git → 直接 pull；否则（换机后空目录）clone。
    """
    if (target / ".git").is_dir():
        gitutil.pull(target, remote, "master")
    else:
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        gitutil.clone(parent, remote, target.name)


def restore(paths, settings, backup_file=None, from_cloud=False):
    """用本地密钥解密备份并恢复数据目录。

    - from_cloud=False：用本地密文文件（backup_file 必填）。
    - from_cloud=True：从云端远端拉取密文后取最新一份解密恢复。
    密钥缺失或远端未配置时明确报错。
    """
    key = _load_key()
    if key is None:
        raise ValidationError("本地无备份密钥（%s），无法恢复" % KEY_FILE)
    if from_cloud:
        remote = _remote(paths, settings)
        if not remote:
            raise ValidationError("未配置云端目标（backup.remote），无法从云端恢复")
        target = _backup_dir(paths)
        _pull_from_remote(target, remote)
        path = _latest_enc(target)
        if path is None:
            raise ValidationError("云端备份目录无密文，无法恢复")
    else:
        if not backup_file:
            raise ValidationError("缺少备份文件路径（或指定 --from-cloud）")
        path = Path(backup_file)
        if not path.is_file():
            raise ValidationError("备份文件不存在: %s" % backup_file)
    cipher = base64.b64decode(path.read_bytes())
    plain = _decrypt_bytes(cipher, key)
    _unpack_store(paths, plain)
    return {"file": str(path), "restored": True}
