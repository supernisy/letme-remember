## Why

方向②「跨平台仲裁」经讨论拆为两层：库内多宿主冲突仲裁（本期做）与跨平台仲裁（挂起，需平台开放记忆接口）。要做的核心问题是：同一记忆仓库里，不同宿主（WorkBuddy / DSH / 千问办公 / 手写）对同一主题写入相矛盾或相重叠的结论时，如何发现并裁决。

盘查发现两个前置缺口：一是 `author` 字段当前存的是「导入来源」而非「宿主」，区分不出宿主；二是记忆没有「适用条件」维度，无法机械判断「真矛盾 vs 条件化多面」。要做出真正可用的仲裁，必须先补这两个维度。

## What Changes

- 新增 `host`（宿主）字段，与 `author`（谁写的）、`provenance`（来源链）解耦；存量数据从 `author` 前缀推导补 `host` 默认值。
- 新增 `applicability`（适用条件）字段：固定四槽（audience / scenario / time / precondition）+ 半开放 `extra` 键值兜底，蒸馏时由大模型抽出结构化填值。
- 新增仲裁器能力：候选发现（同主题 + 多宿主聚类，零 LLM 零网络）+ 条件重叠检测（脚本比 applicability 槽位）+ 三结局裁决（Replacement / Parallel views / Undated）+ 交人提案 + 来源信任 tie-breaker。
- 复用 `proposal.py` 审批队列新增 `arbitrate` 操作类型，GUI 加只读展示与手动触发口子。

## Capabilities

### New Capabilities

- `arbitration`: 库内多宿主冲突仲裁——宿主维度、适用条件维度、候选发现、条件重叠检测、三结局裁决、交人粒度、来源信任分级。

### Modified Capabilities

- `memory-model`: 新增「记忆携带适用条件 applicability」需求，扩展一条记忆的字段定义（四槽 + extra）。

## Impact

- 代码：`lmr/schema.py`、`lmr/frontmatter.py`、`lmr/store.py` 加 `host`/`applicability` 字段；`lmr/distill.py` 蒸馏加 applicability 输出；新增 `lmr/arbitrator.py`；`lmr/proposal.py` 加 arbitrate 操作；`lmr/cli.py` 加 arbitrate 命令；`lmr/gui_server.py` 加只读展示与手动触发。
- 数据：存量 739 条记忆回填 `host`（只补 host，不改 author/provenance）；applicability 本期不回填（无多宿主数据）。
- 依赖：无新增外部依赖，读路径零网络零 LLM 硬约束不变。
