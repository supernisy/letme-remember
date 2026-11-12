## MODIFIED Requirements

### Requirement: 被动注入索引目录

会话开始时，宿主 SHALL 通过会话边界事件自动触发注入，把「索引文件」（记忆的一句话目录）按预算硬上限注入上下文，无需用户手动执行注入命令。

#### Scenario: 会话开始注入

- **WHEN** 宿主会话开始事件（如 SessionStart）触发
- **THEN** 宿主适配器 SHALL 自动注入 MEMORY.md 索引（每行一条记忆摘要），注入的是一句话目录而非全文

#### Scenario: 无宿主事件时手动注入

- **WHEN** 宿主未接入会话事件或需要手动触发
- **THEN** 系统 SHALL 仍提供手动注入方式作为兜底，结果与自动注入一致

## ADDED Requirements

### Requirement: 多宿主注入一致性

同一份记忆仓库接入多个宿主时，各宿主的会话开始注入 SHALL 产出一致的内容（同一份索引、同一预算上限），不因宿主不同而注入不同记忆。

#### Scenario: 跨宿主注入一致

- **WHEN** 同一份记忆仓库被 WorkBuddy 与 DSH 两个宿主分别触发会话开始注入
- **THEN** 两者注入的索引内容 SHALL 一致，行为差异只存在于宿主的 hook 注册层
