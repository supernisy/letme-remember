## MODIFIED Requirements

### Requirement: 大模型软判断暂留接口，接 LLM 为后续诉求

v1 阶段 SHALL 只预留大模型软判断的接口与结构化报告格式，用规则产出报告跑通流程；v1.1 SHALL 把该接口升级为可插拔 LLM 提炼器，接入真实 LLM 做第二审，但裁决仍由代码按固定阈值完成，LLM 不自行拍板要不要人。

#### Scenario: v1 用规则产出体检报告
- **WHEN** v1 阶段需要产出一条候选的体检报告
- **THEN** 由代码规则生成报告（冲突用显式关联字段近似判断），不调用真实 LLM

#### Scenario: v1.1 接入真实 LLM
- **WHEN** 后续接入 LLM
- **THEN** 大模型按同一套结构化报告格式产出软判断，代码仍按固定阈值裁决，不因接 LLM 而让模型自行拍板

#### Scenario: 可插拔 LLM 提炼器

- **WHEN** 宿主配置了 LLM 接入信息（base_url / model / key）
- **THEN** 写入时由 LLM 按结构化体检报告格式产出软判断，覆盖六个升级触发器与 importance / confidence / missing 字段

#### Scenario: LLM 不可用时降级

- **WHEN** LLM 未配置、网络失败或返回不可解析结果
- **THEN** 系统 MUST 退回 v1 的规则体检报告，流程照常，不阻断写入

#### Scenario: 裁决仍归代码

- **WHEN** LLM 产出了软判断报告
- **THEN** 代码 MUST 按固定阈值把报告映射为 L0 / L1 / L2，MUST NOT 让 LLM 直接决定是否需要人审批

## ADDED Requirements

### Requirement: 冲突检测增强

LLM 软判断 SHALL 在写入时把候选与检索出的相似已有结论做比较，显式判断 ADD / UPDATE / SUPERSEDE / NOOP，并与时间轴（invalid_at / superseded_by）联动。

#### Scenario: 冲突显式判定

- **WHEN** 候选与库中已有结论存在矛盾或重叠
- **THEN** LLM 在体检报告的 conflict 字段标注冲突对象与建议操作（UPDATE / SUPERSEDE / NOOP），供代码与后续人审批参考
