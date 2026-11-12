## MODIFIED Requirements

### Requirement: 代码与记忆数据分离

数据目录 SHALL 与代码仓库分离；暂存区（staging）SHALL 仅存放预处理候选卡片，SHALL NOT 存放真相源记忆，也 SHALL NOT 被索引或检索。

#### Scenario: 初始化数据目录

- **WHEN** 初始化数据目录
- **THEN** 系统 SHALL 创建 store / archive / index / proposals / staging 等固定布局

#### Scenario: 发布代码仓库

- **WHEN** 发布代码仓库
- **THEN** 公开仓库 SHALL NOT 出现任何记忆内容或存量导入的候选卡片内容
