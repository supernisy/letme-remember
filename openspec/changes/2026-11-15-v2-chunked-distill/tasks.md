# 方向④ 分块蒸馏 + 增量 diff 任务清单

## 实现

- [x] `lmr/chunk.py`：说话人轮次分块器（`chunk_transcript` / `chunk_file`），确定性切分、零模型零网络
- [x] `lmr/incremental.py`：Map-Reduce 编排（`distill_chunked`）+ 结论级增量 diff（`diff_conclusions`）
- [x] `lmr/cli.py`：注册 `distill-chunk` 命令（`--file` / `--max-chars` / `--dry-run` / `--diff-against`）
- [x] `tests/unit/test_chunk_incremental.py`：14 项单测覆盖分块/去重/JSON 提取

## 验证

- [x] 分块器对真实转写（57KB 面试二面）切成 4 块、大小均匀（5959/5984/5949/3908 字符）
- [x] 分块蒸馏 dry-run：4 块 → 17 条候选，类型正确（semantic/episodic/procedural）
- [x] 增量 diff dry-run：正确产出 added 13 条 / deepened 4 条，note 总结准确
- [x] 既有蒸馏集成测试不回归（10 passed）
- [x] 单元测试全绿（68 passed + 20 subtests）

## 待办（后续优化，非本变更范围）

- [ ] 分块后 LLM 更难看到完整上下文，episodic 索引的「原文文件名」回填率可能下降——需在分块蒸馏后接 `resolve_reference_path` 回填（已有能力，需接入）
- [ ] 增量 diff 的「上一版结论集」目前需显式传 `--diff-against`；未来可自动从库里按主题召回（复用 `find_related_entries`）
