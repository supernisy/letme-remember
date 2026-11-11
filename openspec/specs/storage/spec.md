# storage

## Purpose

定义长期记忆仓库的存储形态：载体、结构、索引三个正交维度如何落地。核心原则是「文件是唯一真相源，索引是可重建的缓存」。

## Requirements

### Requirement: Markdown 文件是唯一真相源

记忆的权威存储 SHALL 是 Markdown 文件，人可读、可 git、可迁移。

#### Scenario: 索引损坏可重建
- **WHEN** SQLite 索引文件损坏或被删除
- **THEN** 系统 MUST 能仅凭 Markdown 文件重建索引，不丢失任何记忆
- **AND** 真相源始终是文件，索引只是缓存

### Requirement: 索引层与真相源解耦

SQLite 索引 SHALL 用于加速检索，与 Markdown 真相源解耦，可随时重建。

#### Scenario: 增量同步
- **WHEN** 某个记忆文件内容变化
- **THEN** 系统通过内容哈希识别变化，仅对变化文件重建索引，非全量重扫

### Requirement: 结构用 typed 记忆 + 显式关联

记忆结构 SHALL 采用 typed 记忆（每条带类型），关系用「条目内 links 字段」近似，v1 不做真知识图谱。

#### Scenario: 轻量关系
- **WHEN** 需要表达两条记忆之间的关联
- **THEN** 通过 links 字段指向其他记忆，而非引入图引擎
- **AND** v1 MUST NOT 引入真知识图谱（Neo4j/Graphiti 等）

### Requirement: 向量检索延后到 v1.1

v1 SHALL 只做关键词检索（FTS5），向量语义检索作为后续迭代加入。

#### Scenario: v1 检索能力
- **WHEN** v1 阶段进行检索
- **THEN** 使用 SQLite FTS5 关键词检索 + 显式分类/标签筛选
- **AND** 不引入向量 embedding（延后到 v1.1）

### Requirement: 纯本地、可迁移

仓库 SHALL 是纯本地的，任何未来宿主（WorkBuddy / DSH / 千问办公）都能访问同一份文件。

#### Scenario: 跨宿主访问
- **WHEN** 一个新的宿主需要加载记忆
- **THEN** 它能直接访问 Markdown 文件目录，无需专有服务或云
