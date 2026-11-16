## Context

现有 `distill` 是单次调用，两个能力缺口：长面试转写（几万 token）超过模型上下文上限会截断丢信息；多次类似面试只能去重、不能识别「这次比上次深在哪」。见 proposal.md - Why。

业界结论（已查证）：长文本摘要两条成熟路线是 Map-Reduce（分块→各自提炼→合并）与 Refine（逐块串行精炼），本项目目标是 N 条结论级记忆而非流畅摘要，用 Map-Reduce；转写分块首选说话人轮次（speaker-turn）边界；增量提取用「结论级显式 diff」而非再造四操作（四操作 consolidate 已有）。

## Goals / Non-Goals

**Goals:**

- 长文本分块蒸馏，不截断丢信息。
- 结论级增量 diff，识别「本次新增/深化」。
- 确定性分块，零模型零网络（读路径约束不变）。

**Non-Goals:**

- 不做句子级 diff + 原文溯源。
- 不新造「同主题合并去重」——复用 consolidate。
- 不改模型选型、不改 DISTILL_PROMPT 核心产出格式。
- 不做实时/事件驱动增量，保持批量触发。

## Decisions

### 决策 1：Map-Reduce 分块蒸馏

**为什么**：目标不是「一段流畅摘要」而是「N 条结论级记忆」，每条独立、天然可并行可合并；Refine 慢、不可并行，适合叙事摘要而非事实抽取。

**做法**：长文本按问答/说话人轮次分块 → 每块用现有 DISTILL_PROMPT 提炼候选 → 合并去重复用现有 consolidate。

### 决策 2：分块用规则识别问答边界，不逐句 embedding

**为什么**：speaker-turn 分块天然保证「一个问答不拆两半」；语义分块（逐句 embedding 算相似度）慢、要调阈值、块大小不可控。

**做法**：边界信号用 `Q:`/`A:` 前缀、时间戳、角色名、空行、Markdown 标题；单块超上限按句边界二次切分兜底。

### 决策 3：结论级增量 diff

**为什么**：同一项目多次面试，需要识别「这次比上次深在哪」；但句子级溯源是个人场景的过度设计。

**做法**：把「上一版结论集」与「这一版新候选」交 LLM 对比，产出 added/deepened/unchanged 清单。

## Risks / Trade-offs

- **分块后单块丢失完整上下文** → 分块器按轮次边界切、块大小均匀，缓解截断；但跨块连贯性损失是 Map-Reduce 固有代价，本项目结论级抽取可接受。
- **episodic 索引的原文文件名回填率可能下降** → 分块蒸馏后接 `resolve_reference_path` 回填（已有能力，需接入），列为本变更待办。
- **增量 diff 依赖上一版结论集显式传入** → 未来可自动从库按主题召回（复用 find_related_entries），列为后续优化。

## Migration Plan

- 新增模块 `lmr/chunk.py`（分块器）与 `lmr/incremental.py`（增量 diff），不改既有 distill 路径。
- CLI 新增 `distill-chunk` 命令，扩展 `batch-distill` 支持 `--chunk` 与 `--diff-against`。
- 无数据迁移，无破坏性变更，既有蒸馏路径不回归。

## Open Questions

- 分块大小上限默认值：建议按模型上下文 75% 兜底（如 12000 token）。
- 增量 diff 的「上一版结论」来源：从库按主题召回（复用 find_related_entries）还是显式传上一版候选 JSON，实现期定。
