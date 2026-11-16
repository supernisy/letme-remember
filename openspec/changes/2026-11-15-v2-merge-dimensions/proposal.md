## Why

方向①「合并多维」经三轮讨论收敛为：不删重复记忆、不做物理合并、不加维度字段，只修「取代（SUPERSEDE）」判定的病根，并把已有的时间轴字段真正接进检索。

病根是：现有 `judgment.py` 的 SUPERSEDE 是「二选一」语义（能并存=UPDATE，不能并存=SUPERSEDE，整体作废旧条目），但现实中大量信息是「同一实体、不同侧面、各自都真」，被粗暴判成取代后另一侧面的洞见被埋掉。此外，`superseded_by` 被校验规则强制绑定 `invalid_at`，而检索对带 `invalid_at` 的条目直接排除，导致「降权保留」逻辑永远执行不到。

## What Changes

- 修 `judgment.py` SUPERSEDE 判定：从「能并存=UPDATE，不能并存=SUPERSEDE」升级为「同主题且矛盾=SUPERSEDE，不同侧面=各自保留」。
- 检索排序从 `fused × weight × recency` 改为 `fused × weight × recency × supersede_penalty`：被取代条目降权保留（非排除），降权幅度用可配置默认值、不写死。
- 解耦 `superseded_by` 与 `invalid_at`：`superseded_by` 可不带 `invalid_at`（取代不失效、只降权）；`invalid_at` 仍表真失效（非历史检索排除）。
- 不引入 `importance` 做检索加权：入库后重要度由 `weight`（用户显式权重）承担，`importance` 仍为入库前筛选阀、不落库。

## Capabilities

### New Capabilities

（无——本 change 为纯代码重构，无新增能力。）

### Modified Capabilities

（无——本 change 不改变任何既有 spec 的行为契约，`skip_specs: true`。规范层面的「三结局裁决」语义变更由方向② `2026-11-16-v2-arbitration` change 承载。）

## Impact

- 代码：`lmr/judgment.py`、`lmr/index.py`、`lmr/config.py`、`lmr/validate.py`、`lmr/store.py`、`lmr/proposal.py`、`tests/`。
- 数据：无数据迁移（`superseded_by`/`invalid_at` 语义调整不改存量数据）。
- 依赖：无新增外部依赖。
