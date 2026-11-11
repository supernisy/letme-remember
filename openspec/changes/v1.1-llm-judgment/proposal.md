## Why

v1 把「大模型软判断」这一步留成了接口，用代码规则产出体检报告，流程能跑通但判断力有限：冲突检测只能靠显式关联字段近似，缺失关键信息、重要性、置信度这些「软判断」在纯规则下要么缺失要么粗糙。要让「分级审批」真正可信，必须接入真实 LLM 做第二审——这是当初定三审流程时的本意，也是 v1 之后明确要做的事。

## What Changes

- 把 `distill.py` 的提炼器接口从「占位」升级为「可插拔 LLM 提炼器」：支持接入任意 LLM（通过配置指定 base_url / model / key，默认不连网、不依赖特定厂商）。
- LLM 按 `write-approval` 里定义的结构化体检报告格式产出软判断，覆盖六个升级触发器：`conflict` / `high_impact` / `ambiguous` / `novel_type` / `compliance` / `uncertain`，以及 `importance` / `confidence` / `missing`。
- 代码仍按固定阈值把报告映射为 L0 / L1 / L2，**不因接 LLM 而让模型自行拍板要不要人**——这是硬约束。
- LLM 不可用时的降级路径：退回 v1 的规则体检报告，流程照常，只是判断力降低。
- 冲突检测增强：LLM 在写入时把候选与「检索出的相似已有结论」做比较，显式判断 ADD / UPDATE / SUPERSEDE / NOOP，与时间轴（`invalid_at` / `superseded_by`）联动。

## Capabilities

### Modified Capabilities

- `write-approval`: 从「大模型软判断暂留接口」落实为「可插拔 LLM 提炼器 + 固定阈值裁决」，六个触发器的软判断由真实 LLM 产出，裁决仍归代码。

## Impact

- 新增一个可选运行时依赖的接入层（不强制绑定任何厂商），默认关闭、不联网。
- 配置新增 LLM 相关字段（base_url / model / key 路径 / 降级开关）。
- 现有 44 项测试不受影响；新增「LLM 软判断」与「降级路径」两类测试。
- 公开仓库不发布任何真实 key；key 走私有数据目录或环境变量。

## Non-goals

- 不做向量语义检索（仍是 v1.1 之后的另一条线）。
- 不做输出策略层、跨设备同步、后台维护进程、UI。
