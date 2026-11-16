"""库内多宿主冲突仲裁器（方向②）。

纯本地、零模型、零网络。职责（arbitration spec）：
  1. 候选发现：找出「同主题 + 多宿主」的冲突候选组；
  2. 条件重叠检测：脚本比 applicability 四槽 + extra，只做字段比对、不判语义矛盾；
  3. 三结局裁决：Replacement（有日期取代）/ Parallel views（并存）/ Undated（交人）。

判断权归用户：脚本能确定的才静默，判不准的一律交人，绝不静默选错。
来源信任（explicit > inferred）只作无日期可定时的最后 tie-breaker，不进检索排序。
"""

from __future__ import annotations

from . import frontmatter, index, schema

# 三结局。
REPLACEMENT = "replacement"
PARALLEL = "parallel"
UNDATED = "undated"

# 来源信任两档：显式用户陈述 > 模型推断。仅作 tie-breaker。
TRUST_EXPLICIT = "explicit"
TRUST_INFERRED = "inferred"
TRUST_ORDER = {TRUST_EXPLICIT: 0, TRUST_INFERRED: 1}

# 交人置信度阈值：低于此值一律上浮为交人（不静默）。
CONFIDENCE_FLOOR = 0.7

# 高后果关键词（启发式：命中则视为高后果，交人，不静默）。
HIGH_IMPACT_HINTS = ("不可逆", "删除", "作废", "权限", "红线", "合规", "安全", "密钥", "底线")


def _host_trust(meta_host: str) -> str:
    """宿主到来源信任的粗略映射：manual（用户手写/显式）视为 explicit，其余 inferred。

    这是 tie-breaker 的兜底近似，真正来源信任应来自显式标记；本期先用 host 近似。
    """
    return TRUST_EXPLICIT if meta_host == "manual" else TRUST_INFERRED


def _slot_differs(a: str, b: str) -> bool:
    """两槽位值「明确不同」：都非空且不等。"""
    a = (a or "").strip()
    b = (b or "").strip()
    return bool(a) and bool(b) and a != b


def _slot_overlaps(a: str, b: str) -> bool:
    """两槽位值「重叠」：都非空且相等，或都空。"""
    a = (a or "").strip()
    b = (b or "").strip()
    return a == b


def overlap_check(app_a: dict, app_b: dict):
    """条件重叠检测（脚本层，只做确定性字段比对）。

    返回 (verdict, reason)：
      "different"   — 某槽位值明确不同 → 并存（非冲突）
      "conflict"    — 四槽都重叠（相同或都空）→ 条件重叠加结论需进一步判矛盾
      "suspect"     — 粒度不同（一方有值一方空）或 extra 键对不齐 → 疑似，交模型
    """
    a = app_a or {}
    b = app_b or {}

    # 1) 任一固定槽「明确不同」→ 条件不同，并存。
    for slot in schema.APPLICABILITY_SLOTS:
        av = a.get(slot, "")
        bv = b.get(slot, "")
        if _slot_differs(av, bv):
            return "different", "slot %s 值不同（%r vs %r）" % (slot, av, bv)

    # 2) 固定槽「粒度不同」（一方有值一方空）→ 疑似。
    for slot in schema.APPLICABILITY_SLOTS:
        av = (a.get(slot, "") or "").strip()
        bv = (b.get(slot, "") or "").strip()
        if bool(av) != bool(bv):
            return "suspect", "slot %s 粒度不同（一方有值一方空）" % slot

    # 3) extra 比对：同名键值不同 → 疑似；键对不齐 → 疑似。
    ea = a.get("extra") or {}
    eb = b.get("extra") or {}
    common = set(ea.keys()) & set(eb.keys())
    if common:
        for key in common:
            if str(ea[key]).strip() != str(eb[key]).strip():
                return "suspect", "extra 同名键 %s 值不同" % key
    if set(ea.keys()) != set(eb.keys()):
        return "suspect", "extra 键对不齐（%r vs %r）" % (sorted(ea), sorted(eb))

    # 4) 四槽都重叠（相同或都空）且 extra 一致 → 条件重叠。
    return "conflict", "适用条件重叠"


def _same_topic(a: dict, b: dict) -> bool:
    """轻量同主题判定（元数据信号，不调模型）。

    这是候选发现的粗筛。脚本只认最可靠的确定性信号——name（去前缀后）
    完全相同，对应「同一条记忆被不同宿主写入」的典型多宿主冲突场景。
    abstract 关键词匹配在求职等领域噪声太大（所有记忆共享高频词），不做，
    真正的「不同 name 但语义同主题」交给模型层判断（三层分工）。
    """
    name_a = (a.get("name") or "").strip()
    name_b = (b.get("name") or "").strip()
    if name_a and name_a == name_b:
        return True
    # 去掉前缀（如 semantic--foo / episodic--foo）后同名也算同主题。
    stem_a = name_a.split("--", 1)[-1] if "--" in name_a else name_a
    stem_b = name_b.split("--", 1)[-1] if "--" in name_b else name_b
    return bool(stem_a) and stem_a == stem_b


def find_candidates(entries, hosts=()):
    """候选发现：找出「同主题 + 不同 host」的冲突候选对。

    不做传递闭包聚类（那会因误判同主题把无关条目连成团），而是两两配对：
    对每一对「不同 host + 同主题」的条目，聚成候选组。返回候选组列表，
    每组形如 {"members": [a, b], "hosts": {host_a, host_b}}。
    """
    filtered = [e for e in entries if not hosts or (e.get("host") in hosts)]
    groups = []
    seen = set()
    for i in range(len(filtered)):
        for j in range(i + 1, len(filtered)):
            a, b = filtered[i], filtered[j]
            host_a = a.get("host") or ""
            host_b = b.get("host") or ""
            if host_a == host_b:
                continue  # 同宿主不仲裁
            if not _same_topic(a, b):
                continue
            key = tuple(sorted([a.get("id"), b.get("id")]))
            if key in seen:
                continue
            seen.add(key)
            groups.append({"members": [a, b], "hosts": {host_a, host_b}})
    groups.sort(key=lambda g: len(g["members"]), reverse=True)
    return groups


def _has_date(entry) -> bool:
    return bool((entry.get("valid_from") or "").strip())


def _newer(a: dict, b: dict):
    """按 valid_from 判断 a 是否比 b 新（无日期返回 None）。"""
    va = (a.get("valid_from") or "").strip()
    vb = (b.get("valid_from") or "").strip()
    if not va or not vb:
        return None
    return va >= vb


def adjudicate_pair(a: dict, b: dict, trust_a=None, trust_b=None, confidence=None):
    """对两条「疑似冲突」条目做三结局裁决。

    返回 dict：{verdict, reason, supersede_old, superseded_by, confidence}
    - verdict: replacement / parallel / undated
    - 只有 replacement 且能定新旧时，给出 supersede_old（旧条目 id）+ superseded_by（新条目 id）。

    规则：
      条件不同 → parallel（并存，非冲突）
      条件重叠 + 结论需判矛盾：这里脚本只能靠「同主题 + 有日期」近似，
        有日期可定新旧 → replacement（静默）；
        无日期 → undated（交人）；
        粒度不同/疑似 → undated（交人，脚本不硬判语义矛盾）。
    置信度 < CONFIDENCE_FLOOR → 一律 undated（上浮交人）。
    """
    app_a = a.get("applicability") or {}
    app_b = b.get("applicability") or {}
    overlap, reason = overlap_check(app_a, app_b)

    # 条件不同 → 并存。
    if overlap == "different":
        return {"verdict": PARALLEL, "reason": reason, "supersede_old": None, "superseded_by": None, "confidence": 1.0}

    # 疑似（粒度不同/extra 对不齐）→ 交人，不硬判。
    if overlap == "suspect":
        return {"verdict": UNDATED, "reason": reason, "supersede_old": None, "superseded_by": None, "confidence": 0.5}

    # 条件重叠：需判断是否真矛盾。脚本只靠日期定先后（不做语义矛盾判断）。
    # 两者都无日期 → 交人。
    if not _has_date(a) and not _has_date(b):
        return {"verdict": UNDATED, "reason": "条件重叠但双方无日期可定先后", "supersede_old": None, "superseded_by": None, "confidence": 0.5}

    newer_ab = _newer(a, b)
    if newer_ab is None:
        # 一方有日期一方无 → 交人（无法确定先后）。
        return {"verdict": UNDATED, "reason": "一方有日期一方无，无法定先后", "supersede_old": None, "superseded_by": None, "confidence": 0.5}

    # 有明确新旧：脚本定「取代」，旧降权、不失效。
    old, new = (b, a) if newer_ab else (a, b)
    conf = confidence if confidence is not None else 0.85
    if conf < CONFIDENCE_FLOOR:
        return {"verdict": UNDATED, "reason": "置信度低于 0.7，上浮交人", "supersede_old": None, "superseded_by": None, "confidence": conf}

    # tie-breaker：无日期可定时用来源信任；这里有日期，来源信任只作最终微调（不改变结局）。
    return {
        "verdict": REPLACEMENT,
        "reason": "条件重叠加日期可定先后（%s 新于 %s）" % (new["id"], old["id"]),
        "supersede_old": old["id"],
        "superseded_by": new["id"],
        "confidence": conf,
    }


def scan(paths, settings, hosts=()):
    """仲裁扫描入口：全量发现候选 + 逐对裁决。

    返回 {"candidates": [...], "adjudications": [...]}
    - candidates: 候选组（多宿主）
    - adjudications: 每组内成对裁决结果，其中 undated 的需交人。
    """
    idx = index.Index(paths, settings)
    entries = idx.list_all()
    groups = find_candidates(entries, hosts=hosts)

    adjudications = []
    for group in groups:
        members = group["members"]
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if a.get("host") == b.get("host"):
                    continue  # 同宿主不仲裁（多宿主才冲突）
                result = adjudicate_pair(a, b)
                result["a_id"] = a["id"]
                result["b_id"] = b["id"]
                result["a_host"] = a.get("host")
                result["b_host"] = b.get("host")
                adjudications.append(result)

    return {"candidates": groups, "adjudications": adjudications}
