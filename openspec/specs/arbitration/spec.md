# arbitration

## Purpose

定义库内多宿主冲突仲裁：同一记忆仓库里，不同宿主（workbuddy / dsh / qianwen / manual）对同一主题写入相矛盾或相重叠的结论时，如何发现冲突、按「三结局」裁决、以及何时静默何时交人。

## Requirements

### Requirement: 宿主维度

记忆条目 SHALL 携带独立的 `host`（宿主）字段，与 `author`（谁写的）、`provenance`（来源链）解耦。

#### Scenario: 三字段分工

- **WHEN** 一条记忆被写入
- **THEN** `host` 记录归一化后的宿主（workbuddy / dsh / qianwen / manual 等）
- **AND** `author` 记录写入主体，`provenance` 记录可回溯来源链，三者不混用

#### Scenario: 宿主值只归一化不枚举

- **WHEN** 写入方声明宿主
- **THEN** 系统 SHALL 对 host 值做归一化（去前缀、小写、去空白）
- **AND** MUST NOT 用封闭枚举拒绝合法宿主

#### Scenario: 存量迁移补默认宿主

- **WHEN** 对存量记忆执行 host 回填
- **THEN** 从 `author` 前缀推导 host（import:workbuddy-* → workbuddy，import:user-direct / user-direct → manual）
- **AND** 迁移只补 host，不改 author / provenance，不破坏历史审计

### Requirement: 冲突候选发现

系统 SHALL 能发现库中「同主题 + 多宿主」的冲突候选组，且读路径零网络、零 LLM。

#### Scenario: 候选聚类

- **WHEN** 触发冲突扫描
- **THEN** 系统用本地索引检索相似条目，把「同主题 + 不同 host」的条目聚成冲突候选组
- **AND** 该过程不调模型、不联网

#### Scenario: 扫描时机

- **WHEN** 系统需要检测冲突
- **THEN** 支持在宿主平台启动或长运行定时触发扫描
- **AND** 支持 GUI 手动按钮触发扫描

### Requirement: 条件重叠检测

系统 SHALL 在裁决前先做「条件重叠检测」，用 applicability 字段的确定性比对区分「条件不同」与「条件重叠」。脚本只做字段比对，不判语义矛盾。

#### Scenario: 条件不同则并存

- **WHEN** 两条记忆的 applicability 某个槽位值明确不同（如 audience 分别为面试官、猎头）
- **THEN** 判定为条件不同，SHALL 各自保留，不视为冲突

#### Scenario: 条件重叠加结论互斥才真冲突

- **WHEN** 两条记忆 applicability 槽位值相同或都空，且结论相反
- **THEN** 判定为条件重叠加结论互斥，进入取代或交人判断

#### Scenario: 粒度不同或键对不齐则疑似

- **WHEN** 一方有某槽值另一方该槽空，或 extra 键对不齐无法机械比对
- **THEN** 判定为「疑似」，MUST NOT 硬拍，上浮交模型细看

### Requirement: 三结局裁决

系统 SHALL 按「三结局」裁决冲突，规则能确定的静默处理，判不准的一律交人。

#### Scenario: 取代

- **WHEN** 同主题两条真矛盾（条件重叠加结论互斥），且能确定新旧先后
- **THEN** 旧条目标 superseded_by（不失效、降权保留）
- **AND** 不静默删除或失效旧条目

#### Scenario: 并存

- **WHEN** 同主题但条件不同或不同侧面、彼此不矛盾
- **THEN** 两条各自保留，不做取代标记

#### Scenario: 交人

- **WHEN** 两条矛盾但无日期或来源可定先后，或条件重叠判定为「疑似」、规则判不准
- **THEN** 系统 MUST NOT 静默选一条，SHALL 生成仲裁提案交用户裁决
- **AND** 裁决前两条都保留并标注「待裁决」

### Requirement: 三层判断分工

冲突判断 SHALL 分三层，各层职责不同：脚本做条件重叠检测，大模型做语义初步判断，人做争议或高后果终裁。

#### Scenario: 脚本层只做条件比对

- **WHEN** 脚本层处理冲突候选
- **THEN** 脚本 SHALL 只做 applicability 槽位的确定性比对，MUST NOT 尝试判定语义矛盾

#### Scenario: 模型层做语义判断

- **WHEN** 条件重叠判定为「疑似」或需区分矛盾、互补、冗余
- **THEN** 交由大模型做语义初步判断，简单有规律的由模型直接定

#### Scenario: 人层做终裁

- **WHEN** 模型拿不准、或有争议、或高后果
- **THEN** SHALL 交人终裁，判断权归用户

### Requirement: 交人粒度

仲裁 SHALL 按「后果乘置信度」决定静默还是交人，判断权归用户。

#### Scenario: 低后果静默

- **WHEN** 冲突低后果、且有明确新旧
- **THEN** 系统按 recency 静默处理，不交人

#### Scenario: 高后果或裁不动交人

- **WHEN** 冲突高后果（决策、权限、不可逆）或规则裁不动
- **THEN** 系统交人裁决，不静默

#### Scenario: 置信度上浮

- **WHEN** 裁决置信度低于 0.7
- **THEN** 系统 SHALL 上浮为交人，不静默

### Requirement: 来源信任分级只做 tie-breaker

来源信任 SHALL 只分两档（显式用户陈述高于模型推断），且只在冲突裁决需要破局、且无日期可定时作为最后 tie-breaker，MUST NOT 进入常规检索排序。

#### Scenario: 两档信任

- **WHEN** 记录一条记忆的来源
- **THEN** 区分 explicit（用户显式陈述）与 inferred（模型推断）两档

#### Scenario: 不进检索排序

- **WHEN** 执行常规检索排序
- **THEN** 排序仍由 boost 乘 recency 乘 supersede_penalty 决定，来源信任 MUST NOT 掺入

#### Scenario: 仅作裁决破局

- **WHEN** 冲突裁决无日期可定先后、需要破局
- **THEN** 来源信任 SHALL 作为最后 tie-breaker 参考，explicit 优先于 inferred
