## 1. 预处理模块

- [ ] 1.1 新增 `lmr/importprep.py`：定义三类判定函数（格式合规可转 / 待裁决 / 明确排除），复用 redaction/validate/frontmatter/schema 做形状红线、字段完整、日期合法、类型猜测、同键去重；验证：单元测试覆盖三类判定各至少一个正反例
- [ ] 1.2 卡片数据结构与暂存：候选卡片含内容哈希（sha256 幂等键）、来源标注、判定状态；写 `paths.staging/`；验证：单测断言卡片只写 staging、不进 store
- [ ] 1.3 幂等去重：按内容哈希跳过已存在卡片；验证：对同一源重复预处理，第二次产卡数为 0

## 2. CLI 接入

- [ ] 2.1 在 `cli.py` 注册 `import-preprocess` 子命令（`--source` / `--source-category` / `--batch`），走标准退出码；验证：`mem.py import-preprocess --help` 退出码 0
- [ ] 2.2 空源/空暂存正常返回空结果；验证：对空目录执行，退出码 0 且报告 count 为 0

## 3. 报告脱敏

- [ ] 3.1 预处理报告只记数量、来源类别、命中规则编号、缺失字段，不含正文/原值；验证：单测构造含敏感正文的源，断言报告不含该正文与凭据原值

## 4. 校验与收尾

- [ ] 4.1 全量测试通过：新增预处理测试与既有 113 项测试全部通过；验证：`python -m unittest discover -s tests -q` 全绿
- [ ] 4.2 OpenSpec 校验通过：`openspec validate 2026-11-12-v1-3-import-preprocessing` 无 ERROR；验证：命令退出无 ERROR
- [ ] 4.3 更新 README 说明 import-preprocess 用法与「卡片≠记忆、需人确认」的语义；验证：README 含该命令说明
