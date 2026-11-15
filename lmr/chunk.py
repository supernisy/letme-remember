"""超长文本分块蒸馏：按「说话人轮次」切分（v2 方向④）。

设计依据（design.md D2）：
- 访谈/面试/会议转写首选 speaker-turn 分块——按说话人切换切，
  天然保证「一个问答不拆两半」，不逐句 embedding。
- 真实转写格式（飞书/腾讯会议）：
      「讲话人 N  MM:SS」 换行  内容
      用空行分隔每段。
- 兜底：单块超过 token 上限时按空行/句边界二次切分，避免单块超长仍截断。

本模块只做「确定性切分」，不调模型、不联网，产出 chunk 文本列表。
"""

from __future__ import annotations

import re

# 转写「讲话人 + 时间戳」行：`讲话人 1  00:08` 或 `Speaker 1  00:08`。
SPEAKER_LINE = re.compile(r"^(?:讲话人|说话人|发言人|Speaker|SPK|嘉宾|主持人)\s*\d+\s+\d{1,2}:\d{2}(?::\d{2})?\s*$")
# 时间戳行兜底：独立一行的 `00:08` 或 `[00:08]`。
TIME_LINE = re.compile(r"^\s*\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*$")
# 角色冒号开头：`面试官：` / `候选人：` / `Q:` / `A:`。
ROLE_PREFIX = re.compile(r"^(?:面试官|候选人|面试者|提问者|回答者|Q|A|问|答|Interviewer|Candidate)\s*[:：]\s*")

# 默认单块字符上限（约 6000 汉字 ≈ 12000+ token 的保守下界；中文口语转写
# 平均 1 汉字 ≈ 1.5~2 token，6000 字 ≈ 9000~12000 token，留出 prompt 余量）。
DEFAULT_MAX_CHARS = 6000


def _is_speaker_boundary(line: str) -> bool:
    """判断一行是否是「说话人/时间戳」边界（应作为新块起点）。"""
    s = line.strip()
    if not s:
        return True  # 空行是天然分隔
    if SPEAKER_LINE.match(s):
        return True
    if TIME_LINE.match(s):
        return True
    return False


def _is_role_turn(line: str) -> bool:
    """判断一行是否是「角色冒号」开头的问答轮次（如「面试官：」）。"""
    return bool(ROLE_PREFIX.match(line.strip()))


def _split_long_block(block: str, max_chars: int) -> list[str]:
    """单块超上限时按空行优先、其次句边界二次切分。"""
    if len(block) <= max_chars:
        return [block] if block.strip() else []
    pieces: list[str] = []
    buf = ""
    for para in block.split("\n\n"):
        if len(buf) + len(para) + 2 > max_chars and buf:
            pieces.append(buf)
            buf = para
        else:
            buf = (buf + "\n\n" + para) if buf else para
        # 段落本身仍超限：按句号切。
        while len(buf) > max_chars:
            cut = max_chars
            # 尽量在句末切。
            for ch in ("。", "！", "？", ".", "!", "?"):
                idx = buf.rfind(ch, 0, max_chars)
                if idx > max_chars // 2:
                    cut = idx + 1
                    break
            pieces.append(buf[:cut])
            buf = buf[cut:]
    if buf.strip():
        pieces.append(buf)
    return pieces


def chunk_transcript(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[dict]:
    """把转写文本切成若干块，返回 [{index, chars, text}]。

    切分策略（按段落累积，段落=说话人单元）：
    1. 空行分隔的「段落」是天然说话人单元（`讲话人 N 时间戳` + 内容）；
    2. 逐段累积，逼近 max_chars 时才在当前段落边界封块——保证块大小均匀、
       且永远在完整说话人单元之间切，不把「一个问答」拆两半；
    3. 单个段落本身超限时，按句边界二次切分兜底。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paras:
        if not current:
            current = para
            continue
        if len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = current + "\n\n" + para

    if current:
        chunks.append(current)

    # 二次切分：合并后仍超限的块（罕见，单段超长）按空行/句边界再切。
    result: list[dict] = []
    for block in chunks:
        for piece in _split_long_block(block, max_chars):
            result.append({"index": len(result), "chars": len(piece), "text": piece})
    return result


def chunk_file(path: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[dict]:
    """读文件并分块，等价于 chunk_transcript(文本)。"""
    from pathlib import Path
    text = Path(path).read_text(encoding="utf-8")
    return chunk_transcript(text, max_chars=max_chars)
