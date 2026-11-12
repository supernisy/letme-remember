# testing Specification

## Purpose

测试工程规范：确立测试金字塔分层（unit/integration/e2e）、全量回归基线、从零到整的端到端验收流程、覆盖率门禁，以及「测试可脱离网络/模型独立运行」的隔离铁律。目标是让测试从「散装单元」演进为「可分层执行、可回归、可整体验收」的工程质量保障，作为每一次改动的硬门禁。

## Requirements

### Requirement: 测试金字塔分层

测试套件 SHALL 按测试金字塔分三层组织，各层职责、依赖、速度预算与数量占比明确：

- **单元测试（unit）**：测单个函数/类的纯逻辑（分支、边界、错误处理、状态转换），零外部依赖（数据库/网络/文件系统全 mock），毫秒级，数量占比约 70-80%。
- **集成测试（integration）**：测模块间接口（服务+持久层、真实 SQLite/文件系统、适配层），真实依赖，秒级，数量占比约 15-25%。
- **端到端测试（e2e）**：测真实命令全流程（subprocess 跑真 mem.py），完整环境，分钟级，数量占比约 5-10%。

每层 SHALL 能通过 pytest mark（`unit` / `integration` / `e2e`）单独执行。

#### Scenario: 分层目录存在

- **WHEN** 检查 `tests/` 目录结构
- **THEN** 存在 `unit/`、`integration/`、`e2e/` 三个子目录，且各层测试文件归位正确

#### Scenario: 按层单独执行

- **WHEN** 运行 `pytest -m unit`
- **THEN** 只执行单元测试，毫秒级完成，不触碰真实数据库或网络

### Requirement: 全量回归基线

测试套件 SHALL 维护一条全量回归基线，作为「改动不回归」的硬门禁。

- 基线定义为：全量测试套件在既定环境下全部通过（当前为 116 项 + 20 子测试，约 60 秒）。
- 每次业务代码改动后 SHALL 跑全量回归；新增功能 SHALL 同步补测试。

#### Scenario: 全量回归可运行

- **WHEN** 运行 `LMR_DISABLE_EMBEDDING=1 pytest tests/ -q`
- **THEN** 全部测试通过，退出码为 0，且不挂起、不依赖网络或大模型

### Requirement: 端到端验收流程

项目 SHALL 维护一条「从零到整」的端到端验收旅程，覆盖核心用户路径，作为发版前必跑的完整验收。

- 旅程至少覆盖：初始化 → 写入 → 关键词召回 → 读正文 → 两段式召回注入 → 向量化 → 常驻服务召回 → 语义召回 → 失效 → 重建。
- 每步 SHALL 断言退出码与数据一致性（写入后可召回、失效后不可见、重建后不丢失）。

#### Scenario: 完整用户旅程走通

- **WHEN** 从零初始化数据目录并依次执行整条旅程的每一步
- **THEN** 每步退出码正确，且最终数据状态一致（召回命中写入内容、失效条目不再可见、重建不丢数据）

### Requirement: 覆盖率门禁

测试套件 SHALL 引入覆盖率度量，作为定位未测死角的工具。

- domain/service 层（store、index、retrieval、redaction、validate、frontmatter、distill）覆盖率 SHALL 达到 ≥80%。
- 覆盖率报告 SHALL 用于定位未覆盖分支，作为补测试依据。

#### Scenario: 覆盖率可生成

- **WHEN** 运行带 `--cov` 的 pytest
- **THEN** 生成覆盖率报告，能定位到具体未覆盖的模块与行

### Requirement: 测试隔离铁律

所有测试 SHALL 可脱离网络、模型、外部服务独立运行，禁止依赖环境状态（模型已装/网络可达）。

- 禁止在测试里真加载大模型（如 sentence-transformers）或真联网（如请求 huggingface）。
- 依赖已装的环境下 SHALL 通过 mock 隔离外部依赖，而非真加载。

#### Scenario: 断网环境全量通过

- **WHEN** 在 `LMR_DISABLE_EMBEDDING=1` 且断网的环境下运行全量测试
- **THEN** 全部测试通过，不因模型缺失或网络不可达而挂起或失败
