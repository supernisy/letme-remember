## 1. 分块器

- [x] 1.1 新增 `lmr/chunk.py` 说话人轮次分块器（chunk_transcript / chunk_file），确定性切分、零模型零网络，verify：`python -m pytest tests/unit/test_chunk_incremental.py -q` 分块用例通过，块边界按问答轮次不拆半句

## 2. 增量 diff

- [x] 2.1 新增 `lmr/incremental.py` Map-Reduce 编排（distill_chunked）+ 结论级增量 diff（diff_conclusions），verify：增量 diff 用例通过，正确产出 added/deepened/unchanged 三类
- [x] 2.2 合并去重复用现有 consolidate，不新造去重，verify：分块蒸馏产出的重复候选被 consolidate 按 name 确定性去重

## 3. CLI 接入

- [x] 3.1 在 `lmr/cli.py` 注册 `distill-chunk` 命令（--file / --max-chars / --dry-run / --diff-against），verify：`python mem.py distill-chunk --dry-run` 跑通不落库

## 4. 验证

- [x] 4.1 分块器对真实转写（57KB 面试二面）切块，verify：切成 4 块、大小均匀（5959/5984/5949/3908 字符）
- [x] 4.2 分块蒸馏 dry-run，verify：4 块 → 17 条候选，类型正确（semantic/episodic/procedural）
- [x] 4.3 增量 diff dry-run，verify：正确产出 added 13 条 / deepened 4 条，note 总结准确
- [x] 4.4 全量回归，verify：单元测试 68 passed + 20 subtests，既有蒸馏集成测试 10 passed 不回归
