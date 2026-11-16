## 1. 取代判定与降权

- [x] 1.1 改 `lmr/judgment.py` 的 SUPERSEDE 判定 prompt（同主题且矛盾才取代，不同侧面各自保留），verify：`python -m pytest tests/ -q -k judgment` 通过，SUPERSEDE 不再误判不同侧面
- [x] 1.2 改 `lmr/index.py` 检索排序接 `supersede_penalty`，verify：带 `superseded_by` 条目检索排名靠后但仍可召回（不被排除）
- [x] 1.3 在 `lmr/config.py` 加 `supersede_penalty` 可配置项，verify：配置项可读、默认值生效

## 2. 解耦 superseded_by 与 invalid_at

- [x] 2.1 在 `lmr/validate.py` 删除「superseded_by 必须带 invalid_at」强约束，verify：只带 `superseded_by` 不带 `invalid_at` 的条目通过校验
- [x] 2.2 在 `lmr/store.py` 的 `invalidate()` 加 `set_invalid` 参数，verify：`set_invalid=False` 只标 superseded_by、不写 invalid_at
- [x] 2.3 在 `lmr/proposal.py` 的 supersede/merge/split 路径传 `set_invalid=False`，verify：提案取代不失效旧条目

## 3. 回归与验证

- [x] 3.1 补检索降权、取代判定的单测/集成测试，verify：`python -m pytest -q` 全量通过（192 passed + 20 subtests）
- [x] 3.2 跑 OpenSpec validate，verify：change 校验通过（skip_specs 生效）
