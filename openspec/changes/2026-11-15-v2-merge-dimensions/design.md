## Context

方向①「合并多维」经三轮讨论收敛为：不删重复记忆、不做物理合并、不加维度字段，只修「取代」判定病根 + 检索多信号降权。见 proposal.md - Why。

现有实现（`index.py:293`）检索公式为 `score = fused × weight × recency`；`judgment.py` 的 SUPERSEDE 是「二选一」语义；`validate.py` 强制 `superseded_by` 绑定 `invalid_at`。

## Goals / Non-Goals

**Goals:**

- 修 SUPERSEDE 判定：只有「同主题且真矛盾」才取代，不同侧面各自保留。
- 检索接入 supersede_penalty：被取代条目降权而非排除。
- 解耦 superseded_by 与 invalid_at：取代不失效、只降权。

**Non-Goals:**

- 不做多维物理合并成一条。
- 不做知识图谱（实体-关系三元组）。
- 不加固定维度枚举字段。
- 不把降权幅度本期写死（留 settings 可调，后期用指标定）。

## Decisions

### 决策 1：SUPERSEDE 判定从「二选一」升级为「同主题且矛盾」

**为什么**：现有判定「能并存=UPDATE，不能并存=SUPERSEDE」会把「同一实体、不同侧面、各自都真」的信息粗暴判成取代，埋掉另一侧面的洞见。

**替代方案**：曾考虑保留二选一、只靠检索降权补救——但二选一在写入时就作废旧条目，降权无从谈起，故不可行。

**做法**：`JUDGMENT_PROMPT` 明确「只有同一主题、真矛盾才 SUPERSEDE；不同侧面 = ADD/UPDATE（各自保留）」。

### 决策 2：检索接 supersede_penalty 降权，而非排除

**为什么**：用户明确「被取代的旧结论 → 检索降权而非完全排除」；业界一致范式是「写入时追加 + 检索时裁决」（Mem0 ADD-only、SCD Type 2、多信号检索）。

**做法**：`score = fused × weight × recency × supersede_penalty`，`supersede_penalty` 为 <1 的可配置因子，不写死幅度。

### 决策 3：superseded_by 与 invalid_at 解耦（方案 A）

**为什么**：原实现强制 `superseded_by` 绑定 `invalid_at`，而检索对 `invalid_at` 条目直接排除，导致「降权」逻辑永远执行不到——语义冲突的病根。

**替代方案**：方案 B 是保留强绑定、改检索逻辑区分——但会让字段语义更纠缠。方案 A 更清晰：两字段各管各的语义。

**做法**：`superseded_by` 可不带 `invalid_at`（取代不失效、只降权）；`invalid_at` 仍表真失效（非历史检索排除）。`store.invalidate()` 加 `set_invalid` 参数；提案路径传 `set_invalid=False`。

### 决策 4：不引入 importance 做检索加权

**为什么**：`importance`（distill 1~5、judgment low/medium/high）在现有设计里是「入库前/审批时的一次性筛选阀」，`distill.py:125` 明确不落库。把它落库做检索排序违背「重要性入库时一次性裁决、入库后不保留」的既定理念。

**做法**：入库后重要度由 `weight`（用户显式权重 0~10）承担，检索已乘 `weight`，沿用即可。

## Risks / Trade-offs

- **降权幅度未标定** → 本期留 `settings` 可配置口子，后期用指标（access 召回率、人工反馈）定「该降多少」。
- **判定口诀升级依赖 LLM 遵循 prompt** → 「不同侧面 vs 真矛盾」本质是语义判断，仍有误判风险；缓解：方向②仲裁器会再引入条件重叠检测兜底。
- **解耦后字段语义需文档同步** → 已在 concept-glossary 与 governance spec 更新「取代不失效」语义，避免误读。
