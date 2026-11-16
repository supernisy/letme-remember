## ADDED Requirements

### Requirement: 记忆携带适用条件 applicability

一条记忆 SHALL 在结论之外，携带独立的「适用条件」（applicability）维度，结构化表达「这条结论在什么条件下成立」。applicability 与 author（谁写的）、provenance（来源链）、valid_from（写入时间）解耦。

#### Scenario: 适用条件为固定四槽加半开放兜底

- **WHEN** 蒸馏或写入一条记忆
- **THEN** applicability SHALL 包含四个固定槽位，各允许为空（null）：audience（对象/角色）、scenario（场景/情境）、time（适用时间窗）、precondition（前提/假设）
- **AND** SHALL 另含一个半开放的 extra 键值对象，承载四槽未覆盖的计划外条件
- **AND** extra 的键自由、值 MUST 为可读字符串，不做纯自由文本

#### Scenario: 空槽位表达普适结论

- **WHEN** 一条结论是无条件的普适结论
- **THEN** 其四槽 SHALL 全部为 null，这是合法状态
- **AND** 空 vs 有值本身是冲突判定的重要信号：两个都空的普适结论才可能真冲突，一个有值一个空则大概率是粒度不同

#### Scenario: 适用时间窗与写入时间区分

- **WHEN** 记录一条带时间限制的结论
- **THEN** valid_from 记录「该记忆何时写入/生效」的事实时间（用于时间衰减）
- **AND** applicability.time 记录「结论本身在什么时间窗内成立」的适用时间（用于冲突判定）
- **AND** 两者语义不同，MUST NOT 混用

#### Scenario: 适用条件在蒸馏时产出

- **WHEN** 蒸馏一条记忆
- **THEN** 蒸馏器 SHALL 从记忆文本中抽出结构化的 applicability 填入，而非在冲突发生时临时解析
- **AND** 语义解析只发生在蒸馏这一次，后续冲突扫描只消费已结构化的 applicability 字段

#### Scenario: 存量记忆暂不回填适用条件

- **WHEN** 对存量记忆评估是否回填 applicability
- **THEN** 在不存在多宿主数据、无多宿主冲突可仲裁的阶段，MUST NOT 做无意义的存量 applicability 回填
- **AND** 回填时机延后到多宿主（DSH/千问）真实接入之后另行决策
