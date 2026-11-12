## MODIFIED Requirements

### Requirement: 命令行操作集

系统 SHALL 提供 `record`、`recall`、`show`、`invalidate`、`rebuild`、`list` 六个基础操作，并新增 `setup`、`queue`、`backup`、`restore`、`serve`、`serve-shutdown` 六个操作；每个操作 SHALL 自带 `--help` 说明，且成功时 SHALL 以退出码 0 结束。

#### Scenario: 宿主调用任一操作

- **WHEN** 宿主以合法参数调用任一已定义操作
- **THEN** 系统 SHALL 在标准输出返回该操作的结果并以退出码 0 结束

#### Scenario: 调用不存在的操作

- **WHEN** 调用一个未定义的操作名
- **THEN** 系统 SHALL 返回明确的非零退出码，并在标准错误列出可用操作

## ADDED Requirements

### Requirement: 常驻服务操作

`serve` SHALL 启动常驻召回服务（模型只加载一次、监听本机回环端口、空闲超时自退）；`serve-shutdown` SHALL 通知服务退出，服务未运行时 SHALL 静默成功。

#### Scenario: 启动常驻服务

- **WHEN** 执行 `serve`
- **THEN** 系统 SHALL 离线加载向量模型后监听本机端口，检索请求毫秒级返回

#### Scenario: 重复启动幂等

- **WHEN** 已有服务实例运行时再次执行 `serve`
- **THEN** 系统 SHALL 检测端口占用并静默跳过，SHALL NOT 报错或产生冲突

#### Scenario: 关闭服务

- **WHEN** 执行 `serve-shutdown`
- **THEN** 系统 SHALL 通知服务退出；服务未运行时 SHALL 静默成功、退出码 0
