# governance

## Purpose

定义记忆的长期治理：淘汰策略（不是 TTL 硬删，而是时间衰减 + 排序乘数 + 手动归档）与审计追溯（复用 git 作为 trace）。

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

淘汰 SHALL 不是 TTL 硬删，而是「时间衰减 + 排序乘数 + 手动归档」三结合。

#### Scenario: 淘汰机制
- **WHEN** 系统评估记忆去留
- **THEN** 综合三股力：
  - 时间衰减（越旧越沉底，自动）
  - 排序乘数（重要记忆衰减慢、排名靠前，人工介入）
  - 手动归档（用户主动归档，彻底离开检索）

### Requirement: 淘汰只做提案

自动淘汰 SHALL 不直接执行，只做「提案」，需人确认。

#### Scenario: 淘汰提案
- **WHEN** 某记忆排序乘数降到下限、建议淘汰
- **THEN** 系统只生成「淘汰提案」，MUST 经人确认后才生效，不自动删

### Requirement: 上游缓存 / 下游权威（单一真相源）

letme-remember SHALL 与宿主 Agent 平台的内置记忆构成「单向上下游」，不做平行系统：宿主平台记忆为上游现场缓存，letme-remember 为下游权威沉淀层，数据只单向流入下游，下游不反向回写上游。

同一事实存在多条结论时，SHALL 按「三结局」裁决，而非一律收敛成先后关系（方向②「跨平台仲裁」定稿，取代旧「取代链收敛」一刀切）：

#### Scenario: 真矛盾靠取代收敛（Replacement）
- **WHEN** 同一事实存在先后两条**真矛盾**结论（如旧结论「只看杭州」、新结论「可接受上海」），且能确定新旧先后
- **THEN** 新结论写入时旧的标记 superseded_by 降权（方案 A：取代不失效，见 merge-dimensions 设计）
- **AND** 检索时旧结论降权靠后，新结论优先

#### Scenario: 不同侧面各自保留（Parallel views）
- **WHEN** 两条结论**同一主题但不同侧面**（如同一段经历的「技术深度」vs「业务价值」），彼此不矛盾、都真
- **THEN** 两者 MUST 各自保留，NOT 用 superseded_by 互相埋掉
- **AND** 检索时两者都可召回，由场景/查询决定命中哪条

#### Scenario: 无日期可裁则交人（Undated pair）
- **WHEN** 两条结论矛盾，但没有日期或来源能定出先后（undated pair）
- **THEN** 系统 MUST NOT 静默选一条，SHALL 将这对冲突交用户裁决
- **AND** 裁决前两条都保留、都标注为「待裁决冲突」

#### Scenario: 上游不反向写回
- **WHEN** 宿主平台记忆与 letme-remember 结论冲突
- **THEN** 以「用户本人 + 下游权威」为准，上游缓存不反向写回下游、不参与定义真相

#### Scenario: 只读导入为单向入口
- **WHEN** 把宿主平台已积累记忆导入下游做存量
- **THEN** 导入 SHALL 为单向只读蒸馏，不建立双向同步、不反向推送

### Requirement: git 作为审计日志

系统 SHALL 复用 git 作为 trace（审计日志），可查谁改的、何时改的、改了什么，可撤销。

#### Scenario: 维护动作产生 commit
- **WHEN** 系统执行一次维护（写入、修改、归档等）
- **THEN** 在 git 仓库中自动产生一次 commit，作为审计记录

#### Scenario: 审计查询
- **WHEN** 用户需要排查「某条记忆什么时候被谁改的」
- **THEN** 通过 git log 可查到完整变更历史，且可 git revert 撤销
