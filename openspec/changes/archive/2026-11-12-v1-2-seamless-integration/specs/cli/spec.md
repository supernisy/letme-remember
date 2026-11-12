## MODIFIED Requirements

### Requirement: 命令行操作集

系统 SHALL 提供 `record`、`recall`、`show`、`invalidate`、`rebuild`、`list` 六个基础操作，并新增 `setup`、`queue`、`backup`、`restore` 四个操作；每个操作 SHALL 自带 `--help` 说明，且成功时 SHALL 以退出码 0 结束。

#### Scenario: 宿主调用任一操作

- **WHEN** 宿主以合法参数调用任一已定义操作
- **THEN** 系统 SHALL 在标准输出返回该操作的结果并以退出码 0 结束

#### Scenario: 调用不存在的操作

- **WHEN** 调用一个未定义的操作名
- **THEN** 系统 SHALL 返回明确的非零退出码，并在标准错误列出可用操作

## ADDED Requirements

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
