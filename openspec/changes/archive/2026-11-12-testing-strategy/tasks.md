# Tasks

## 1. 分层框架落地

- [ ] 1.1 创建 `tests/unit/`、`tests/integration/`、`tests/e2e/` 三个目录
- [ ] 1.2 归类 12 个测试文件到对应层（frontmatter/validate/redaction→unit；store/index/backup/queue/host/llm_judgment→integration；cli_e2e→e2e）
- [ ] 1.3 调整 `tests/base.py` 与各文件的 import 路径（`from tests.base import ...` 等）
- [ ] 1.4 新增 `pytest.ini`，注册 `unit`/`integration`/`e2e` 三个 mark，`testpaths = tests`

## 2. 全量回归基线

- [ ] 2.1 固化基线：`LMR_DISABLE_EMBEDDING=1 pytest tests/ -q` 全量全过
- [ ] 2.2 验证分层后按 mark 分别执行：`pytest -m unit` / `pytest -m "not e2e"` / `pytest` 均正确

## 3. 端到端验收流程

- [ ] 3.1 新增 `tests/e2e/test_acceptance_journey.py`：init→record→recall→show→inject--query→embed→serve→语义召回→invalidate→rebuild 全链路
- [ ] 3.2 断言每步退出码与数据一致性（写入后能召回、失效后不可见、重建后不丢失）

## 4. 覆盖率门禁

- [ ] 4.1 引入 pytest-cov，配置 domain/service 层覆盖率阈值 ≥80%
- [ ] 4.2 跑覆盖率报告，定位未测死角并记录待补清单

## 5. 测试隔离铁律

- [ ] 5.1 确认所有测试在 `LMR_DISABLE_EMBEDDING=1` + 断网环境下全过（不真加载模型、不真联网）
- [ ] 5.2 修补已知违反隔离的用例（已 mock test_embedding_available_flag、已补 _embedding_on 环境开关）
