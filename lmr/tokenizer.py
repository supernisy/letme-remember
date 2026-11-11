"""中文预分词（design D10）。

写入端与查询端 MUST 使用同一套分词器、同一版本，否则会出现「写进去
却搜不到」。索引里记录 tokenizer_version；版本变化会自动触发全量重建。

唯一运行时依赖是 jieba（固定版本，见 requirements.txt）。依赖缺失或
显式禁用时，降级到内置分词（单字 + 二三字滑窗）+ 两字短词子串兜底。
"""

from __future__ import annotations

import os
import re

from .config import ENV_DISABLE_TOKENIZER

JIEBA_VERSION = "jieba==0.42.1"
BUILTIN_VERSION = "builtin-1"

_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_WORD = re.compile(r"[A-Za-z0-9_]+")
_jieba_module = None
_tried = False


def _load_jieba():
    global _jieba_module, _tried
    if _tried:
        return _jieba_module
    _tried = True
    if os.environ.get(ENV_DISABLE_TOKENIZER) == "1":
        return None
    try:
        import jieba  # noqa: F401  本地词典，无网络、无模型推理
        _jieba_module = jieba
    except ImportError:
        _jieba_module = None
    return _jieba_module


def reset_cache():
    """测试用：切换环境变量后重新探测。"""
    global _tried, _jieba_module
    _tried = False
    _jieba_module = None


def tokenizer_version():
    return JIEBA_VERSION if _load_jieba() is not None else BUILTIN_VERSION


def _builtin_terms(text):
    terms = []
    position = 0
    for match in _CJK_RUN.finditer(text):
        terms.extend(w.group(0) for w in _WORD.finditer(text[position:match.start()]))
        run = match.group(0)
        terms.extend(run)
        terms.extend(run[i:i + 2] for i in range(len(run) - 1))
        terms.extend(run[i:i + 3] for i in range(len(run) - 2))
        position = match.end()
    terms.extend(w.group(0) for w in _WORD.finditer(text[position:]))
    return terms


def segment(text):
    """把文本切成空格分隔的索引文本。"""
    jieba = _load_jieba()
    if jieba is not None:
        terms = [term for term in jieba.cut_for_search(str(text)) if term.strip()]
    else:
        terms = _builtin_terms(str(text))
    return " ".join(terms)


def query_terms(query):
    """查询端与写入端使用同一个 segment，保证词形一致。"""
    return [term for term in segment(query).split(" ") if term]


def short_terms(query):
    """两字及以上的中文片段，用于 LIKE 子串兜底。"""
    terms = []
    for match in _CJK_RUN.finditer(str(query)):
        run = match.group(0)
        if len(run) >= 2:
            terms.append(run)
        terms.extend(run[i:i + 2] for i in range(len(run) - 1))
    return list(dict.fromkeys(terms))
