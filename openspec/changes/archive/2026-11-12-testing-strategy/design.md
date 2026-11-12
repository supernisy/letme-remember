## Context

项目测试已从「零散单元」走到需要「整体验收」的阶段。业界标准是测试金字塔（Mike Cohn 提出、Martin Fowler 推广）：底层大量快速单元测试、中层适量集成测试、顶层少量端到端测试。本设计把它落到 letme-remember 的 pytest 工程上，并补齐回归基线、端到端验收、覆盖率门禁。

## Goals / Non-Goals

- Goals：三层分层可分别执行；全量回归固化基线；一条从零到整的端到端验收；覆盖率门禁；测试可脱离网络/模型独立运行。
- Non-Goals：不重写业务断言、不引入 CI 流水线、不追求 100% 覆盖率、不改业务代码语义。

## Decisions

### D1：三层目录 + pytest.ini 标记（不重写测试，只归类）

- `tests/unit/`：纯逻辑、零外部依赖、毫秒级。放 frontmatter、validate、redaction、tokenizer、schema、index 的纯排序逻辑。
- `tests/integration/`：模块协作、真实 SQLite/文件系统、秒级。放 store+index、backup、queue、host 适配器、llm_judgment。
- `tests/e2e/`：真实命令全流程（subprocess 跑真 mem.py）、分钟级。放 cli_e2e、serve 常驻服务验收。
- pytest.ini 注册 `unit`/`integration`/`e2e` 三个 mark，`testpaths = tests`。
- 理由：业界标准做法；分层后可按「循环内（unit）→ 提交前（非 e2e）→ 合并前（全量）」的频率分别执行，反馈更快。
- 备选：按功能模块分目录（对当前规模过度设计）；扁平 + 仅标记（结构不清晰）。

### D2：全量回归基线固化

- 基线：`LMR_DISABLE_EMBEDDING=1 pytest tests/ -q` 全量 116 项 + 20 子测试全过，约 60 秒。
- 每次业务改动后必跑全量；新增功能同步补测试。
- 理由：回归基线是「不回归」的硬门禁，没有基线就无法判断改动是否引入破坏。

### D3：端到端验收 = 一条真实用户旅程

- 旅程：`init → record → recall → show → inject --query → embed → serve → 语义召回 → invalidate → rebuild`，断言每步退出码与数据一致。
- 独立成 `tests/e2e/test_acceptance_journey.py`，作为发版前必跑的完整验收。
- 理由：端到端测试守住关键路径，回答「用户完整走一遍还通不通」。

### D4：覆盖率门禁

- 引入 pytest-cov，目标 domain/service 层（store、index、retrieval、redaction、validate、frontmatter、distill）≥80%。
- 覆盖率报告定位未测死角，作为补测试的依据。
- 理由：覆盖率是找死角的工具，不是考核口号；高覆盖≠高质量，但低覆盖=有明显盲区。

### D5：测试隔离铁律

- 所有测试必须可脱离网络、模型、外部服务独立运行。
- 禁止在测试里真加载大模型（如 sentence-transformers）、真联网（如请求 huggingface）；依赖已装的环境下也必须能 mock 掉。
- 本 change 落地时，同步修补已知违反隔离的用例（`test_embedding_available_flag` 已 mock，`_embedding_on` 已补环境开关）。
- 理由：上一轮全量回归挂起（SIGTERM）的直接教训——测试依赖环境状态（模型已装/网络可达）就不可靠。
