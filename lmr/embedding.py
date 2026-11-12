"""本地语义向量（design D11 / 可选依赖）。

对齐 lmr 既有设计哲学：文件是真相源、索引可重建、可选依赖优雅降级。
sentence-transformers 未安装时，语义检索自动降级为「仅关键词检索」，
不影响任何现有功能；向量本身存在 SQLite 缓存表，删掉可重建。

模型选择（首次加载时按需下载到本地缓存，之后离线可用）：
  默认 paraphrase-multilingual-MiniLM-L12-v2（~120MB，中英多语，
  384 维，语义质量与体积的平衡点）。可用 env LMR_EMBED_MODEL 覆盖。
"""

from __future__ import annotations

import os

from .config import ENV_DISABLE_EMBEDDING

# 默认模型：多语 MiniLM，中文可用、体积小、CPU 友好。
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_model = None
_model_name = None
_tried = False
_embedding_fn = None


def _load():
    """惰性加载 sentence-transformers，缓存模型实例；未安装返回 None。"""
    global _model, _model_name, _tried, _embedding_fn
    if _tried:
        return _embedding_fn
    _tried = True
    if os.environ.get(ENV_DISABLE_EMBEDDING) == "1":
        return None
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except ImportError:
        return None
    try:
        name = os.environ.get("LMR_EMBED_MODEL") or DEFAULT_MODEL
        # 国内直连 huggingface.co 常被墙；默认走 hf-mirror 镜像下载。
        # 模型已落本地缓存时（~/.cache/huggingface）不会再走网络。
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        _model = SentenceTransformer(name)
        _model_name = name

        def _embed(texts):
            # normalize_embeddings=True 便于余弦相似度直接用点积
            return _model.encode(list(texts), normalize_embeddings=True)

        _embedding_fn = _embed
    except Exception:
        # 模型下载失败 / 网络不通 / 加载异常：降级为无语义，不抛错
        _model = None
        _model_name = None
        _embedding_fn = None
    return _embedding_fn


def available():
    """语义能力是否可用（依赖已装且模型可加载）。"""
    return _load() is not None


def embed(texts):
    """把若干文本编码为归一化向量列表；不可用时返回 None。"""
    fn = _load()
    if fn is None:
        return None
    if isinstance(texts, str):
        texts = [texts]
    return fn(texts)


def model_name():
    _load()
    return _model_name


def reset_cache():
    """测试用：切换环境变量后重新探测。"""
    global _tried, _model, _model_name, _embedding_fn
    _tried = False
    _model = None
    _model_name = None
    _embedding_fn = None


def vector_blob(vec):
    """把 numpy 向量序列化为 blob 存 SQLite。"""
    import struct
    return struct.pack(">%df" % len(vec), *[float(v) for v in vec])


def vector_from_blob(blob, dim):
    """从 blob 还原 numpy 向量。"""
    import struct
    import numpy as np
    return np.array(struct.unpack(">%df" % (len(blob) // 4), blob), dtype=np.float32)
