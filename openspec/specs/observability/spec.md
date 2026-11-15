# observability

## Purpose

定义记忆仓库的可观测性能力：只读控制台（GUI）如何让用户快速判断「系统是否良好运行、和什么系统交互、有什么急迫问题」。核心原则是「先给结论、可下钻」——不是罗列库存统计，而是呈现健康信号，并把每条信号串成三层下钻路径。本规范只覆盖观测与诊断，**不覆盖写操作**（编辑/删除/取代/归档只留口子，本期不实现）。

## Requirements

### Requirement: 三层下钻信息架构

观测界面 SHALL 按三层下钻组织，三层必须通过「点击」串起来，跳不动的层视为未实现。

#### Scenario: 分层职责

- **WHEN** 用户打开观测界面
- **THEN** 依次可用三层：
  - L1 总览：回答「一切正常吗」，含一句健康判定 + 系统状态灯 + 分级待办
  - L2 定位：回答「哪条出问题了」，含记忆列表（人话标题 + 健康标记）+ 搜索/过滤
  - L3 诊断：回答「这条具体怎么了」，含单条健康四维 + 指标口径 + 绑定动作

#### Scenario: 下钻路径可点通

- **WHEN** 用户需要从总览定位到问题
- **THEN** L1 待办条目 SHALL 能跳到 L2 并过滤出相关记忆；L2 点某条记忆 SHALL 打开 L3 详情；L3 的问题记忆 SHALL 能跳回 L1 或给出处理动作

### Requirement: 结论优先的呈现

观测界面 SHALL 先给结论、后给数据；列表标题用人类可读的摘要，机器名降级为次要信息；缺数据源的指标 SHALL 标「未接入」，MUST NOT 造假数。

#### Scenario: 标题用人话

- **WHEN** 列表展示一条记忆
- **THEN** 标题 SHALL 用 `abstract`（一句话人话摘要），机器名 `name` SHALL 降级为灰色等宽小字

#### Scenario: 详情结论前置

- **WHEN** 打开单条记忆详情
- **THEN** 「结论」与「理由」SHALL 前置加粗显示，MUST NOT 藏在正文尾部

#### Scenario: 缺数据不造假

- **WHEN** 某指标的数据源尚未埋点或能力未落地
- **THEN** 界面 SHALL 明确标注「未接入/无法计算」，MUST NOT 填 0 或编造占位值

### Requirement: 健康四维（mem-gc 模型）

记忆健康 SHALL 用四维评估，每维各占 25%；能算真值的算真值，不能算的诚实标注缺口。

#### Scenario: 四维构成

- **WHEN** 评估记忆健康
- **THEN** 计算四维：新鲜度（freshness）、唯一性（uniqueness）、一致性（consistency）、检索效用（retrieval utility）

#### Scenario: 检索效用来自访问埋点

- **WHEN** 计算某记忆的检索效用
- **THEN** 系统 SHALL 从访问日志（access 表）读取被召回次数与最近召回时间，而非凭空估计

#### Scenario: 未落地维度诚实标注

- **WHEN** 某维度所需能力尚未落地（如唯一性依赖「合并/去重」、隐性矛盾检测依赖「内部冲突仲裁」）
- **THEN** 该维度 SHALL 返回「无法计算」并标注依赖方向，MUST NOT 返回虚假分数

### Requirement: 系统运行状态三态

观测界面 SHALL 以三态呈现常驻召回服务状态，靠状态文件区分「正常空闲」与「异常」。

#### Scenario: 三态判定

- **WHEN** 查询常驻服务状态
- **THEN** 判定为三态之一：running（端口可连，绿）/ idle（端口不可连但状态文件表明正常退出，黄）/ error（端口不可连且状态文件非正常退出，红）

#### Scenario: 状态文件作为依据

- **WHEN** 常驻服务退出
- **THEN** 服务 SHALL 在退出时写入状态文件（记录 running / idle-exit / shutdown / crashed），供观测界面区分「空闲自退」与「异常退出」

### Requirement: 分级待办（P0-P3）

观测界面 SHALL 用分级待办呈现需要用户处理的问题，每条待办 MUST 同时具备「明确动作」与「级别」；没有动作的条目 SHALL 降级为「信息」，不当作待办。

#### Scenario: 待办分级

- **WHEN** 系统发现需要用户处理的问题
- **THEN** 按级别呈现：P0 紧急（系统已坏，立刻处理）/ P1 重要（应尽快）/ P2 观察（先记着）/ P3 信息（纯提示）

#### Scenario: 无动作不算待办

- **WHEN** 某条目无法给出明确动作
- **THEN** 该条目 SHALL 降级为「信息」展示，MUST NOT 冒充待办

### Requirement: 指标密度纪律（3-3-3）

观测界面每页 SHALL 遵守密度纪律，超出即拆层而非堆叠。

#### Scenario: 3-3-3 约束

- **WHEN** 组织某页内容
- **THEN** 每页 SHALL 不超过 3 个面板；每面板 SHALL 不超过 3 个关键指标；每个指标 SHALL 一句话能说清

### Requirement: 只读边界

观测后端 SHALL 只读，MUST NOT 写入 store / index / audit；写操作能力留接口但不实现。

#### Scenario: 只读后端

- **WHEN** 观测服务处理请求
- **THEN** 所有 API SHALL 仅查询，MUST NOT 修改真相源、索引或审计日志

#### Scenario: 写操作留口不实现

- **WHEN** 用户需要编辑/删除/取代/归档记忆
- **THEN** 后端 SHALL 不提供写接口；前端写入口 SHALL 置灰，仅架构上预留

### Requirement: 敏感信息不泄露

观测界面与审计展示 SHALL 不泄露密钥、令牌等敏感信息。

#### Scenario: 审计展示脱敏

- **WHEN** 展示审计日志或记忆内容
- **THEN** 系统 SHALL 不显示密钥/令牌原值，命中处保持打码或仅标规则编号
