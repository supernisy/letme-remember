## Why

现有 `distill` 是单次调用，两个能力缺口：

1. **超长截断丢信息**：半小时~一小时的面试转写（几万 token）超过模型上下文上限，单次蒸馏会截断，前半段的结论蒸不出来。
2. **只能去重、不能提取增量**：多次相似面试「讲得越来越深」，但每次蒸馏是独立单次调用，系统只能靠 consolidate 去重，无法识别「这次比上次深在哪」。

业界结论（已查证）：

- 长文本摘要只有两条成熟路线——Map-Reduce（分块→各自提炼→合并）与 Refine（逐块串行精炼）。本项目目标是「N 条结论级记忆」而非「一段流畅摘要」，用 Map-Reduce。
- 访谈/面试/会议转写分块首选「说话人轮次」边界（speaker-turn），天然保证「一个问答不拆两半」，优于逐句 embedding 的语义分块（慢、难调阈值）。
- 增量提取：Mem0 的四操作（ADD/UPDATE/DELETE/NOOP）本项目 consolidate 已有，缺的是「结论级显式 diff」——把新旧结论集交 LLM，产出「本次新增/深化」清单（MemoryLake memory-diff 思路，但面向面试进步而非行为漂移）。

## What Changes

- **新增 `lmr/chunk.py`**：确定性分块器，按「说话人轮次」（`讲话人 N MM:SS` + 空行段落）切分，块大小均匀，单块超上限按句边界兜底，不调模型、不联网。
- **新增 `lmr/incremental.py`**：Map-Reduce 分块蒸馏编排（分块 → 每块用现有 LLMDistiller 提炼 → name 级去重合并）+ 结论级增量 diff（新旧结论集交 LLM，产出 added/deepened/unchanged）。
- **CLI 新增 `distill-chunk` 命令**：`--file`（长文本/转写）、`--max-chars`（块上限）、`--dry-run`（不落库）、`--diff-against`（上一版候选 JSON，产出增量 diff）。
- 合并去重**复用现有 consolidate**（ADD/UPDATE/SUPERSEDE/NOOP），不新造去重。

## Capabilities

### Added Capabilities

- `distillation`: 超长文本分块蒸馏（Map-Reduce + 说话人轮次分块）与结论级增量 diff 的行为约束。

## Impact

- 新增 `lmr/chunk.py`、`lmr/incremental.py` 两个模块。
- `lmr/cli.py` 新增 `distill-chunk` 子命令与 handler，导入 `incremental`。
- 新增 `tests/unit/test_chunk_incremental.py`（14 项单测，覆盖分块/去重/JSON 提取）。
- 既有 `distill`、`batch-distill`、`consolidate` 行为不回归。
- 读路径零 LLM、零网络原则不变（分块本身是确定性切分，不调模型）。

## Non-goals

- 不做句子级 diff + 原文溯源（个人场景，结论级已够）。
- 不新造「同主题合并去重」——复用 consolidate。
- 不改模型选型、不改 DISTILL_PROMPT 核心产出格式。
- 不做实时/事件驱动增量，保持批量触发。
