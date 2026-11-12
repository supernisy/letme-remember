## Why

v1.3 导入预处理落地后，用真实存量源做了一次端到端验收，暴露两个实现缺陷：

1. **「无 frontmatter 但结构清晰」的规则文件被误判为「明确排除」**。spec 里「明确排除」= 日志流水、过程推演、重复备份、会话原文（语义垃圾）；而一个普通 Markdown 规则文件（有「结论+理由」结构，只是没套 frontmatter）是有价值的存量，语义上应归「待裁决」（提示补 frontmatter 后确认），而不是「明确排除」直接丢弃。

2. **`_split_entries` 把普通 Markdown 的 `---` 水平线误当 frontmatter 块边界**，导致一个完整规则文件被切成 3 段。frontmatter 的 `---` 后面紧跟 `key: value` 行；水平线后面是正文，两者应区分。

这两个缺陷导致：真实规则/身份/过程文档类存量（无 frontmatter）会被预处理层整体拦下丢弃，正好违背「预处理是安全进仓库的闸门」而非「误杀高价值存量」的初衷。

## What Changes

- **修正「无 frontmatter」的判定语义**：无 frontmatter 但正文含「结论 + 理由」结构的文本，从「明确排除」改为「待裁决」，标注 `needs-human: missing-frontmatter`；只有「无 frontmatter 且无结论/理由结构」的碎片才判「明确排除」。
- **修正条目切分**：`_split_entries` 只把「后面紧跟 `key: value` 行」的 `---` 视为 frontmatter 分隔线；普通 Markdown 水平线（`---` 后是正文/标题）不参与切分，整段作为一条交给判定层。
- 判定顺序调整：先做「来源类别 / 过程标记」排除，再尝试解析 frontmatter；解析失败时改查「正文是否含结论+理由」决定 review 还是 exclude。

## Capabilities

### Modified Capabilities

- `import-preprocessing`: 修正「无 frontmatter」条目的判定边界（有价值缺形状 → 待裁决，碎片 → 排除），并修正条目切分逻辑，使普通 Markdown 水平线不误切。

## Impact

- 仅改 `lmr/importprep.py`（`_split_entries` + `_verdict_for` 两处），复用既有 `frontmatter.body_sections` 判断正文结构。
- 报告新增 `needs_human` 信号 `missing-frontmatter`；规则编号新增 `review:missing-frontmatter`。
- 测试补充：无 frontmatter 有结论理由 → review；无 frontmatter 无结构 → exclude；含 `---` 水平线的普通 Markdown → 不误切。
- 落库侧零改动，读路径零 LLM 约束不变。

## Non-goals

- 不做「自动给无 frontmatter 的文本补 frontmatter」——那属于提炼/蒸馏，仍由人确认后走三审。
- 不改变「卡片 ≠ 记忆」「报告脱敏」「幂等去重」既有约束。
