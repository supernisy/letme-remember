"""数据目录解析与运行时配置。

隐私边界（design D3）：记忆数据目录永远位于本代码仓库之外，可由
命令行参数、环境变量或用户级配置指定。公开仓库里不放任何真实记忆。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ENV_DATA_DIR = "LMR_DATA_DIR"
ENV_DISABLE_TOKENIZER = "LMR_DISABLE_TOKENIZER"
ENV_NO_NETWORK_PROBE = "LMR_NO_NETWORK_PROBE"

DEFAULT_DATA_DIR = Path.home() / ".letme-remember" / "data"
USER_CONFIG_DIR = Path.home() / ".letme-remember"
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.json"

DEFAULT_SETTINGS = {
    "redact_b_class": False,
    "injection_budget_bytes": 8192,
    "max_results": 20,
    "recency_half_life_days": 90.0,
    "recency_floor": 0.1,
    "recency_decay_base": 0.5,
    "weight_min": 0.0,
    "weight_max": 10.0,
    "allowlist_extra": [],
}


def resolve_data_dir(explicit=None):
    """优先级：命令行 > 环境变量 > 用户级配置 > 默认值。"""
    raw = explicit or os.environ.get(ENV_DATA_DIR)
    if not raw:
        raw = load_user_config().get("data_dir")
    if not raw:
        return DEFAULT_DATA_DIR.resolve()
    return Path(str(raw)).expanduser().resolve()


def load_user_config():
    if not USER_CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(USER_CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_user_config(data_dir):
    """初始化时写一份只含路径与开关的配置，不含任何记忆内容。"""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"data_dir": str(data_dir)}
    payload.update({k: v for k, v in DEFAULT_SETTINGS.items() if k != "allowlist_extra"})
    USER_CONFIG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return USER_CONFIG_PATH


def settings_for(data_dir):
    """合并默认设置、用户级配置与数据目录内配置（后者优先级最高）。"""
    result = dict(DEFAULT_SETTINGS)
    for source in (load_user_config(), _data_config(data_dir)):
        for key, value in source.items():
            if key in DEFAULT_SETTINGS:
                result[key] = value
    return result


def _data_config(data_dir):
    path = Path(data_dir) / "config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class Paths:
    """数据目录内的固定布局。索引目录是可随时删除的缓存。"""

    def __init__(self, data_dir):
        self.root = Path(data_dir)
        self.store = self.root / "store"
        self.archive = self.root / "archive"
        self.index = self.root / ".index"
        self.db = self.index / "index.db"
        self.memory_md = self.root / "MEMORY.md"
        self.proposals = self.root / "proposals"
        self.staging = self.root / "staging"
        self.config = self.root / "config.json"
        self.audit = self.root / "audit.log"

    def all_dirs(self):
        return [self.store, self.archive, self.index, self.proposals, self.staging]

    def memory_files(self):
        """活跃与归档条目都进索引；归档条目仍可按历史时点查到。"""
        files = sorted(self.store.glob("*.md"))
        if self.archive.is_dir():
            files += sorted(self.archive.glob("*.md"))
        return files
