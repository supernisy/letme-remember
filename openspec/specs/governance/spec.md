# governance

## Purpose

定义记忆的长期治理：淘汰策略（不是 TTL 硬删，而是时间衰减 + 权重 + 手动归档）与审计追溯（复用 git 作为 trace）。

## Requirements

### Requirement: 永不物理删除

记忆文件 SHALL 永不物理删除，只标记失效 + 归档。

#### Scenario: 记忆失效不删除
- **WHEN** 一条记忆失效
- **THEN** 系统标记其失效（invalid_at），而非删除文件
- **AND** 失效记忆默认不进入检索结果

#### Scenario: 归档离开检索面
- **WHEN** 失效记忆需要彻底移出检索
- **THEN** 系统将其归档到 archive 目录，文件仍在磁盘、可追溯

### Requirement: 淘汰三结合

淘汰 SHALL 不是 TTL 硬删，而是「时间衰减 + 权重 + 手动归档」三结合。

#### Scenario: 淘汰机制
- **WHEN** 系统评估记忆去留
- **THEN** 综合三股力：
  - 时间衰减（越旧越沉底，自动）
  - 权重（重要记忆衰减慢、排名靠前，人工介入）
  - 手动归档（用户主动归档，彻底离开检索）

### Requirement: 淘汰只做提案

自动淘汰 SHALL 不直接执行，只做「提案」，需人确认。

#### Scenario: 淘汰提案
- **WHEN** 某记忆权重降到下限、建议淘汰
- **THEN** 系统只生成「淘汰提案」，MUST 经人确认后才生效，不自动删

### Requirement: git 作为审计日志

系统 SHALL 复用 git 作为 trace（审计日志），可查谁改的、何时改的、改了什么，可撤销。

#### Scenario: 维护动作产生 commit
- **WHEN** 系统执行一次维护（写入、修改、归档等）
- **THEN** 在 git 仓库中自动产生一次 commit，作为审计记录

#### Scenario: 审计查询
- **WHEN** 用户需要排查「某条记忆什么时候被谁改的」
- **THEN** 通过 git log 可查到完整变更历史，且可 git revert 撤销
