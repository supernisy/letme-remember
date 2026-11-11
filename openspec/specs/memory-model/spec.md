# memory-model

## Purpose

定义长期记忆仓库中「一条记忆」是什么：它的粒度、字段、类型（typed schema）、以及时间维度如何表达「过期结论」。这是整个系统的地基，其他能力（存储、写入、检索、注入、治理）都基于这个模型。

## Requirements

### Requirement: 记忆按类型定义粒度

记忆的最小单位是「结论级」，但粒度**按类型定义**，不是全局一刀切。系统 SHALL 为每条记忆赋予一个类型（type），并由类型决定其分组键（key）与粒度边界。

#### Scenario: 不同类型的记忆粒度不同
- **WHEN** 系统定义记忆类型（如 decision 决策、preference 偏好、event 事件）
- **THEN** 每种类型各自声明其粒度边界与分组键（如 decision 按 project+subject 分组、event 按 date+subject 分组、profile 按 user 一人一文件）
- **AND** 同一类型下，分组键相同的记忆指向同一文件（key 定身份）

#### Scenario: 内置类型清单
- **WHEN** 系统初始化
- **THEN** 内置 9 类记忆类型：profile、preference、entity、event、decision、procedure、fact、experience、reference
- **AND** 类型清单可扩展（支持自定义 schema，不锁死）

### Requirement: 一条记忆的字段

系统 SHALL 确保每条记忆携带完整元数据，能回答「哪来的、什么时候写的、为什么这么定、何时可能失效」。

#### Scenario: 记忆携带完整元数据
- **WHEN** 写入一条记忆
- **THEN** 该记忆必须包含以下字段：
  - name（唯一标识）
  - abstract（一句话摘要）
  - type（类型）
  - created / updated（写入时间）
  - author（谁写的，标注宿主来源）
  - weight（权重，表示重要程度）
  - links（显式关联，指向其他记忆，做轻量关系）
  - provenance（来源追溯）
  - body（正文，完整结论 + 理由）

### Requirement: 结论必须带理由

一条「结论」不允许是无理由的裸结论。系统 SHALL 拒绝无理由的结论，要求补充理由后才允许落库。

#### Scenario: 无理由的结论
- **WHEN** 写入一条只有判断、没有理由的记忆
- **THEN** 系统 MUST 拒绝或退回（要求补充理由），不落库

### Requirement: 时间维度表达过期结论

一条记忆 SHALL 是一个**有效期区间**，用时间字段表达「何时成立、何时失效、被谁取代」，而非物理删除。

#### Scenario: 结论被新结论取代
- **WHEN** 一条记忆的结论不再成立，被新的结论取代
- **THEN** 该记忆标记 invalid_at（失效时间）与 superseded_by（被哪条取代）
- **AND** 原记忆文件 MUST NOT 被物理删除

#### Scenario: 查询历史真相
- **WHEN** 用户需要查询「某个时间点的真相」
- **THEN** 系统 MUST 支持按 --as-of 日期检索，返回该时间点仍有效的记忆

### Requirement: 记忆字段的格式封闭性

记忆的 frontmatter（文件头元数据）SHALL 采用封闭、严格的格式，防止被悄悄重解释。

#### Scenario: 富格式被拒绝
- **WHEN** frontmatter 出现超出定义范围的字段或花哨写法
- **THEN** 系统 MUST 直接报错拒绝，而非悄悄换个意思去理解
- **AND** 不引入完整 YAML/JSON 依赖，用自造的极小子集解析器
