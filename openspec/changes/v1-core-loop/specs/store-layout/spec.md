## Purpose

定义记忆真相源在磁盘上的组织方式与文件格式契约：数据目录放在哪里、文件怎么命名、文件头有哪些字段、索引文件长什么样、失效条目如何归档、导入条目如何标注来源与原始时间，以及公开代码仓库与私有记忆数据之间的隔离边界。

## ADDED Requirements

### Requirement: 代码与记忆数据分离

记忆数据目录 SHALL 位于公开代码仓库之外，路径 SHALL 可由配置或环境变量指定；公开代码仓库 SHALL 不包含任何真实记忆条目，只含代码、规范、测试与完全虚构的示例数据。

#### Scenario: 初始化数据目录

- **WHEN** 在未指定路径的情况下初始化记忆仓库
- **THEN** 系统 SHALL 在代码仓库之外创建数据目录，且代码仓库的 git 状态不出现任何记忆文件

#### Scenario: 发布代码仓库

- **WHEN** 把代码仓库的全部内容发布到公开远端
- **THEN** 发布内容 SHALL 不含任何真实记忆条目、凭据或审计历史

### Requirement: 数据目录布局

数据目录 SHALL 包含 `store/`（活跃记忆）、`archive/`（归档记忆）、`MEMORY.md`（索引目录）、`.index/`（可重建索引缓存），并 SHALL 在该目录内维护一个独立的私有 git 仓库用于审计。索引缓存 SHALL 可随时删除而不影响真相源。

#### Scenario: 目录结构可识别

- **WHEN** 初始化完成后检查数据目录
- **THEN** 四类路径 SHALL 全部存在，且私有 git 可用标准 git 命令查看提交历史

#### Scenario: 索引缓存被删除

- **WHEN** `.index/` 被整体删除
- **THEN** 真相源 SHALL 不受影响，且可通过重建索引恢复检索能力

### Requirement: 一文件一条记忆与身份键

一条记忆 SHALL 对应一个 UTF-8 纯文本文件，文件名 SHALL 由类型与身份键（key）确定；同一类型下相同 key 的写入 SHALL 落到同一个文件，不得产生重复文件。

#### Scenario: 同一主题重复写入

- **WHEN** 对同一类型、同一 key 连续写入两次
- **THEN** 系统 SHALL 只保留一个文件，第二次写入更新该文件而非新建

### Requirement: 文件头字段与格式封闭

文件头（frontmatter）SHALL 只接受固定字段集合：`name`、`abstract`、`type`、`created`、`updated`、`valid_from`、`invalid_at`、`superseded_by`、`weight`、`author`、`links`、`provenance`。解析器 SHALL 拒绝未知字段、嵌套结构与富格式写法，SHALL 不引入 YAML/JSON 解析器，SHALL 不对值做任何隐式类型转换。

#### Scenario: 未知字段被拒

- **WHEN** 文件头出现集合之外的字段
- **THEN** 系统 SHALL 直接拒绝该文件并报错，不得忽略或猜测其含义

#### Scenario: 字面值保持原样

- **WHEN** 字段值形如 `yes`、`no`、`12:30` 或日期样式的字符串
- **THEN** 系统 SHALL 按原始字符串读取，不得转成布尔值、时间或数字

### Requirement: 正文与合法性校验

文件头之后 SHALL 为正文，且 SHALL 至少包含结论与理由；写入前 SHALL 校验必填字段、ISO 8601 日期、失效时间不早于生效时间、取代关系必须伴随失效区间、以及权重取值范围。任何一项不合法 SHALL 阻止写入。

#### Scenario: 无理由的裸结论

- **WHEN** 提交的候选只有结论、没有理由
- **THEN** 系统 SHALL 拒绝写入并说明缺少理由

#### Scenario: 时间区间非法

- **WHEN** 失效时间早于生效时间，或声明了取代关系却没有失效区间
- **THEN** 系统 SHALL 拒绝写入并说明具体冲突字段

### Requirement: 导入条目的来源与原始时间语义

由存量记忆导入产生的条目 SHALL 在 `provenance` 中记录来源类别、原始日期与导入批次标识；`created` SHALL 为执行导入的时间，`valid_from` SHALL 为原结论成立的时间，`author` SHALL 为导入来源标识而非宿主原名。三者 SHALL NOT 混用或互相覆盖。同一导入批次 SHALL 可作为一个整体在私有 git 历史中被定位与撤销。导入候选 SHALL 经过与常规写入相同的校验与审批路径，SHALL NOT 绕过关卡批量落库。

#### Scenario: 导入条目保留原始生效日期

- **WHEN** 导入一条在更早日期成立、于本次才被写入的结论
- **THEN** 该条目 SHALL 同时具备原始生效日期与本次导入时间，且按 `--as-of` 查询原始日期时仍成立

#### Scenario: 导入批次可整批撤销

- **WHEN** 对某个导入批次执行撤销
- **THEN** 该批次产生的全部条目 SHALL 一并恢复为导入前状态，且不影响其他批次的条目

#### Scenario: 导入候选未过审

- **WHEN** 一条导入候选缺少理由、含未打码的凭据形状或存在未裁决的冲突
- **THEN** 系统 SHALL 拒绝落库或仅生成提案，真相源不因批量导入发生未经审批的变化

### Requirement: 索引文件与失效归档

`MEMORY.md` SHALL 每行包含一条记忆的一句话摘要与定位标识，SHALL 可由真相源重新生成，且 SHALL 支持按预算截断。失效条目 SHALL 保留原文件并带失效字段；长期失效条目 SHALL 可移入 `archive/`，且归档后 SHALL 不再进入默认检索结果，但 SHALL 仍可按历史时点查到。

#### Scenario: 索引文件可重建

- **WHEN** 删除 `MEMORY.md` 后重新生成索引
- **THEN** 系统 SHALL 生成与原来等价的摘要目录，且不改动任何真相源文件

#### Scenario: 归档条目不再默认出现

- **WHEN** 某条失效记忆被移入 `archive/` 后执行一次默认检索
- **THEN** 系统 SHALL 不返回该条目，但 `--as-of` 指定其有效期间时 SHALL 仍能查到
