# retrieval

## Purpose

定义记忆的检索能力：三层路径（常驻索引、关键词、语义）、排序公式，以及「读路径零 LLM 调用」的核心原则。

## Requirements

### Requirement: 三层检索路径

检索 SHALL 提供三条路径，按确定性从高到低排列。

#### Scenario: 检索路径分层
- **WHEN** 系统需要检索记忆
- **THEN** 依次可用：
  - 路径一：常驻索引注入（确定性，不调模型）
  - 路径二：关键词检索（BM25 / FTS5）
  - 路径三：语义检索（向量，v1.1 加入）

### Requirement: 读路径零 LLM 调用

检索过程 SHALL 不消耗大模型 token。

#### Scenario: 检索不调模型
- **WHEN** 用户检索「某条记忆」
- **THEN** 检索路径 MUST NOT 调用任何大模型
- **AND** 纯本地关键词/向量计算完成，零网络、零 token

### Requirement: 排序公式

检索结果 SHALL 按「相关度 × 权重 × 新鲜度」排序。

#### Scenario: 排序计算
- **WHEN** 返回多条候选记忆
- **THEN** 按 relevance（相关度）× weight（权重）× recency（新鲜度）计算最终分数并排序

### Requirement: 时间衰减与兜底

新鲜度 SHALL 采用指数衰减 + 半衰期，并有下限兜底，旧的记忆沉底但不会被彻底遗忘。

#### Scenario: 旧记忆沉底而非消失
- **WHEN** 一条记忆随时间变旧
- **THEN** 其新鲜度按指数衰减（每过半衰期减半）
- **AND** 有下限兜底（recency floor），新鲜度不会降到 0

### Requirement: 关键词与语义混合可插拔

关键词检索与向量语义检索 SHALL 可插拔组合。

#### Scenario: 向量开关
- **WHEN** 向量能力未接入（v1）
- **THEN** 仅使用关键词检索，向量检索关闭
- **AND** 未来接入向量后，两者用融合算法（如 RRF）合并排名
