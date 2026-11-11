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

### Requirement: 区分「过时结论」与「错误/无效记忆」的退出机制

「过时结论」与「错误/无效记忆」SHALL 走不同的退出路径：前者只失效归档、保留历史；后者应可真正删除。

#### Scenario: 过时结论只失效不删
- **WHEN** 一条结论曾经正确、后来因事实变化而过时
- **THEN** 系统 SHALL 标记 invalid_at 并归档，MUST NOT 物理删除，历史可 --as-of 追溯

#### Scenario: 错误或无效记忆可真正删除
- **WHEN** 一条记忆明显错误、纯属虚构、或为测试残留（例如占位示例、写错的条目），而非「曾正确后过时」
- **THEN** 系统 SHALL 提供真正的删除出口（物理移除），且该删除属于高影响不可逆操作，MUST 走审批（L2 强制人工）

#### Scenario: 删除不可逆且留痕
- **WHEN** 一条记忆被真正删除
- **THEN** 系统 MUST 在审计日志中记录删除动作（谁、何时、删了什么、为何），MUST NOT 静默抹除

### Requirement: 区分「变量」与「常量」类记忆

蒸馏/写入时 SHALL 区分两类记忆的稳定性：「认知/偏好类」是变量，随用户想法与处境变化；「工程/技术类」是常量，技术正确性不变。两者 SHALL 采用不同的标注与治理方式。

#### Scenario: 认知/偏好类记忆标注为可变
- **WHEN** 蒸馏出一条「认知/偏好/策略类」结论（如城市偏好、薪资门槛、方向偏好、人际策略）
- **THEN** 该记忆 MUST 标注「以用户最新表态为准」的可变提示
- **AND** 系统 SHALL 保留其被 supersede（取代）的余地，不把可变偏好当死结论硬编码

#### Scenario: 工程/技术类记忆可记为铁律
- **WHEN** 蒸馏出一条「工程/技术类」结论（如退出码约定、安全红线、确定性规则）
- **THEN** 该记忆可记为铁律（常量），无需标注可变
- **AND** 但若它属于「曾正确后因技术演进而过时」，仍走 invalid_at + superseded_by 的时间轴路径，不物理删除

#### Scenario: 治理时优先审查变量类记忆
- **WHEN** 对存量记忆做治理/盘点
- **THEN** 系统 SHALL 优先识别并审查「认知/偏好类」的可变记忆，因为这类最易在未充分讨论时被记成一刀切，导致检索时误用过期结论
- **AND** 识别出的可疑绝对化表述（只看/只投/一刀切/废止）SHALL 整理成清单交用户逐个确认，而非由系统擅自改写

### Requirement: 记忆字段的格式封闭性

记忆的 frontmatter（文件头元数据）SHALL 采用封闭、严格的格式，防止被悄悄重解释。

#### Scenario: 富格式被拒绝
- **WHEN** frontmatter 出现超出定义范围的字段或花哨写法
- **THEN** 系统 MUST 直接报错拒绝，而非悄悄换个意思去理解
- **AND** 不引入完整 YAML/JSON 依赖，用自造的极小子集解析器
