"""审计用 git（design D7）。

每次成功写入 / 维护在数据目录的私有 git 里产生一条提交。这个 git 与
公开代码仓库完全无关，撤销用标准 git 操作即可，不另造日志系统。
"""

from __future__ import annotations

import subprocess
from datetime import datetime

from .errors import InternalError, NotFoundError


def _run(args, cwd, check=True):
    result = subprocess.run(
        args, cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if check and result.returncode != 0:
        raise InternalError("git 操作失败: %s" % " ".join(args[1:3]))
    return result


def ensure_repo(root):
    if (root / ".git").exists():
        return False
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.name", "letme-remember"], root)
    _run(["git", "config", "user.email", "memory@local.invalid"], root)
    return True


def commit(root, message):
    _run(["git", "add", "-A"], root)
    staged = _run(["git", "diff", "--cached", "--quiet"], root, check=False)
    if staged.returncode == 0:
        return None
    _run(["git", "commit", "-q", "-m", message], root)
    return _run(["git", "rev-parse", "HEAD"], root).stdout.strip()


def log(root, grep=None):
    args = ["git", "log", "--format=%H%x09%s"]
    if grep:
        args += ["--grep=%s" % grep, "--fixed-strings"]
    lines = _run(args, root).stdout.strip().splitlines()
    return [tuple(line.split("\t", 1)) for line in lines if "\t" in line]


def head(root):
    result = _run(["git", "rev-parse", "HEAD"], root, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def revert_many(root, hashes):
    if not hashes:
        raise NotFoundError("没有可撤销的提交")
    for value in hashes:
        _run(["git", "revert", "--no-edit", value], root)
    return len(hashes)


def undo_last(root):
    current = head(root)
    if not current:
        raise NotFoundError("数据目录尚无提交")
    return revert_many(root, [current])


def undo_batch(root, batch):
    """整批撤销：定位该批次全部提交，按时间倒序逐个 revert。"""
    entries = log(root, grep="batch:%s" % batch)
    if not entries:
        raise NotFoundError("未找到导入批次: %s" % batch)
    return revert_many(root, [item[0] for item in entries])


def now_iso():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def is_clean(root):
    """工作树是否干净（无未提交改动）。"""
    result = _run(["git", "status", "--porcelain"], root)
    return result.stdout.strip() == ""


def push(root, remote, branch):
    """推送本地提交到远端；失败抛 InternalError。"""
    _run(["git", "push", remote, branch], root)


def pull(root, remote, branch):
    """从远端拉取；失败抛 InternalError。"""
    _run(["git", "pull", remote, branch], root)


def clone(parent, remote, name):
    """把远端仓库 clone 到 parent/name；失败抛 InternalError。"""
    _run(["git", "clone", "-q", remote, name], parent)
