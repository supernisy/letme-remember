# cli Specification

## Purpose
定义宿主与人读写长期记忆时所依赖的命令行接口契约：有哪些操作、每个操作的输入输出与错误行为、读路径不得调用大模型的约束，以及中文查询必须可召回的底线。这是多宿主接入同一份记忆仓库时唯一需要遵守的外部接口。

## Requirements

### Requirement: 命令行操作集

系统 SHALL 提供 `record`、`recall`、`show`、`invalidate`、`rebuild`、`list` 六个基础操作，并新增 `setup`、`queue`、`backup`、`restore` 四个操作；每个操作 SHALL 自带 `--help` 说明，且成功时 SHALL 以退出码 0 结束。

#### Scenario: 宿主调用任一操作

- **WHEN** 宿主以合法参数调用任一已定义操作
- **THEN** 系统 SHALL 在标准输出返回该操作的结果并以退出码 0 结束

#### Scenario: 调用不存在的操作

- **WHEN** 调用一个未定义的操作名
- **THEN** 系统 SHALL 返回明确的非零退出码，并在标准错误列出可用操作

### Requirement: 写入操作的可观察行为

`record` SHALL 接收一条候选记忆（含结论、类型、理由与来源），通过校验后写入真相源并返回该条目的定位标识；未通过校验的内容 SHALL 一个字节都不写入真相源。

#### Scenario: 合法候选写入成功

- **WHEN** 提交一条通过全部校验的候选记忆
- **THEN** 系统 SHALL 写入一条记忆文件、返回其定位标识，并产生一条可定位的审计提交

#### Scenario: 非法候选被拒

- **WHEN** 提交缺少必填字段、日期非法或含凭据形状未打码的候选
- **THEN** 系统 SHALL 拒绝写入、返回非零退出码、在标准错误说明原因，且真相源不发生任何变化

### Requirement: 检索操作的可观察行为

`recall` SHALL 接收查询词与可选筛选条件（类型、时间、标签），返回按「相关度 × 权重 × 新鲜度」排序的条目摘要列表；默认 SHALL 过滤已失效条目；提供 `--as-of 日期` 时 SHALL 返回该时点成立的条目。对中文查询，系统 SHALL 支持两字及以上的词召回，且 SHALL NOT 因分词器限制出现整句无法命中的情况。读路径 SHALL 不调用任何大模型，也不依赖网络。

#### Scenario: 按关键词检索

- **WHEN** 输入一个查询词
- **THEN** 系统 SHALL 返回相关条目的摘要与定位标识，按分数从高到低排列，且全程零模型调用

#### Scenario: 按历史时点检索

- **WHEN** 输入 `--as-of` 指定一个过去的日期
- **THEN** 系统 SHALL 只返回在该日期成立的条目，包含后来已失效的条目

#### Scenario: 中文短词检索

- **WHEN** 输入一个两字中文词，且该词出现在某条记忆正文中
- **THEN** 系统 SHALL 返回该条记忆，不得因中文分词限制而零命中

#### Scenario: 分词依赖缺失时仍可检索

- **WHEN** 中文分词依赖未安装
- **THEN** 系统 SHALL 自动降级到内置分词与子串兜底，检索仍返回结果，不得报错中断

### Requirement: 查看正文与索引目录

`show` SHALL 按定位标识读回一条记忆的完整正文，调用方 SHALL 无需知道文件名；`list` SHALL 输出索引目录中的一句话摘要列表。

#### Scenario: 按定位标识读正文

- **WHEN** 用 `recall` 或 `list` 返回的定位标识调用 `show`
- **THEN** 系统 SHALL 返回该条记忆的完整正文（含结论与理由）

### Requirement: 失效与索引重建

`invalidate` SHALL 标记条目失效并写入取代关系，SHALL 不物理删除任何文件；`rebuild` SHALL 从真相源重建索引，且 SHALL 保证索引目录被删除后知识零丢失、重复重建结果一致。

#### Scenario: 标记失效

- **WHEN** 对某条记忆执行 `invalidate`
- **THEN** 系统 SHALL 在该条目写入失效时间与取代关系、保留原文件，且默认检索不再返回它

#### Scenario: 删除索引后重建

- **WHEN** 索引目录被删除后执行 `rebuild`
- **THEN** 系统 SHALL 从真相源重建索引，且重建前后的检索结果一致

### Requirement: 错误与退出行为

所有操作 SHALL 用退出码区分成功、校验失败、未找到与内部错误四类结果，错误信息 SHALL 只写到标准错误，且 SHALL 不含任何凭据或记忆正文。

#### Scenario: 四类结果可区分

- **WHEN** 分别触发成功、校验失败、目标不存在、内部错误
- **THEN** 系统 SHALL 返回四个互不相同的退出码，并在标准错误给出可读的原因

### Requirement: 写入可撤销

每次成功写入 SHALL 在私有数据目录的 git 历史中产生一条可定位的提交，任何一方 SHALL 能用标准 git 操作撤销该次写入，撤销后真相源 SHALL 回到写入前的状态。

#### Scenario: 撤销一次写入

- **WHEN** 对最近一次成功写入的提交执行撤销
- **THEN** 系统 SHALL 使真相源恢复到写入前，且不残留该条记忆的索引

### Requirement: 宿主安装操作

`setup` SHALL 接收宿主名，把对应适配器注册到该宿主的事件配置中，使会话边界自动触发记忆读写；重复安装 SHALL 幂等。

#### Scenario: 安装到指定宿主

- **WHEN** 执行 `setup --host workbuddy`
- **THEN** 系统 SHALL 生成 WorkBuddy 适配器并写入其 hook 配置，会话边界自动触发注入与蒸馏

#### Scenario: 重复安装幂等

- **WHEN** 对同一宿主重复执行 `setup`
- **THEN** 系统 SHALL 幂等处理，不产生重复的 hook 注册

### Requirement: 待审队列操作

`queue` SHALL 支持查看待审候选清单、批准、驳回三类子操作，操作 SHALL 记录可审计日志。

#### Scenario: 查看待审清单

- **WHEN** 执行 `queue list`
- **THEN** 系统 SHALL 列出所有 pending 候选的摘要，供用户批量审批

#### Scenario: 批准与驳回

- **WHEN** 执行 `queue approve <id>` 或 `queue reject <id>`
- **THEN** 系统 SHALL 分别把候选写入真相源或丢弃，并记录审计日志

### Requirement: 备份与恢复操作

`backup` SHALL 加密数据目录并同步到云端目标；`restore` SHALL 用本地密钥解密密文并恢复数据目录；两者在未配置时 SHALL 返回明确的未配置提示。

#### Scenario: 执行备份

- **WHEN** 执行 `backup` 且已配置加密工具与云端目标
- **THEN** 系统 SHALL 在本地加密后同步密文到云端，返回成功

#### Scenario: 未配置时提示

- **WHEN** 执行 `backup` 但未配置加密或云端目标
- **THEN** 系统 SHALL 返回明确的「未配置」提示，SHALL NOT 报内部错误中断
