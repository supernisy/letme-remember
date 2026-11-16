# 方向①「取代改维度追加 + 检索多信号降权」设计文档

> 读者：项目主导者（super）｜用途：固化方向①的需求收敛结论与实现边界，实现前供审。

## 一、需求收敛（经三轮讨论后的最终结论）

**一句话**：不删重复记忆、不做物理合并、不加维度字段；只做两件具体小事——修「取代」判定的病根，把已有的时间轴/重要性字段真正接进检索。

### 1.1 病根

现有 `judgment.py` 的 SUPERSEDE 是「二选一」语义：能并存=UPDATE，不能并存=SUPERSEDE（整体作废旧条目）。但现实中大量信息既非简单并存、也非矛盾，而是「同一实体、不同侧面，各自都真」。被粗暴判成取代后，另一侧面的洞见被埋掉。

### 1.2 用户明确的三条边界（不可违反）

1. **不删重复记忆**：有新增就加，没新增就不加；来源有几条、是否重复，不在意。
2. **被取代的旧结论 → 检索「降权」而非「完全排除」**；降权幅度后期用指标调，本期不写死。
3. **不加固定维度枚举字段**：记忆是通用记忆（不只面试），任何枚举都框不住。

## 二、业界依据（已查证，多来源共识）

| 来源 | 关键结论 |
|---|---|
| Mem0 官方文档 | 「ADD-only extraction」——新事实和旧事实**都保留**，从不覆盖删除；检索时靠多信号 + 时间推理选出「当下该信哪条」 |
| 数据仓库 SCD Type 2（db0 博客等） | 旧值不删、标记取代、**默认检索降权/排除但审计可查** |
| 多信号检索（Mem0/Google/多个实现） | 排序 = 相关度 × 时效性 × 重要性，**靠检索时的硬过滤 + 加权**，而非写入时合并 |
| MRMS 论文 / ChronoMem | 用「取代边/版本」标记新旧关系，而非删节点 |

**结论**：业界一致的范式是「写入时追加 + 检索时裁决」，不是「写入时合并」。

## 三、实现边界

### 3.1 写入时：修 SUPERSEDE 判定（judgment.py）

- 在 `JUDGMENT_PROMPT` 里明确「**只有同一主题、真矛盾才 SUPERSEDE；不同侧面 = ADD/UPDATE（各自保留）**」。
- 判定口诀从「能并存=UPDATE，不能并存=SUPERSEDE」升级为「**同主题且矛盾=SUPERSEDE，不同侧面=各自保留**」。
- 保留 `superseded_by` / `invalid_at` 时间轴，不作废数据，只作标记。

### 3.2 检索时：只加「被取代降权」（index.py）

- 当前公式（`index.py:293`）：`score = fused × weight × recency`
- 改造为：`score = fused × weight × recency × supersede_penalty`
  - `supersede_penalty`：条目带 `superseded_by` 时乘一个 <1 的降权因子（**本期用可配置默认值，不写死幅度**，后续用指标调）。
- **不排除**：被取代条目仍可召回，只是降权后靠后。
- **不引入 importance 做检索加权**：经核对，`importance`（distill 的 1~5、judgment 的 low/medium/high）在现有设计里都是「入库前/审批时的一次性筛选阀」，且 `distill.py:125` 明确 `importance 是内部字段、不落库`。把它落库做检索排序会违背「重要性在入库时一次性裁决、入库后不保留」的既定理念；「入库后的重要度」已由 `weight`（用户显式权重 0~10）承担，检索公式已乘 `weight`。故沿用 `weight`，不新增 importance。

### 3.2.1 方案 A：superseded_by 与 invalid_at 解耦（本轮定稿）

原实现里 `superseded_by` 被校验规则强制绑定 `invalid_at`（`validate.py`），而检索对带 `invalid_at` 的条目直接 `continue` 排除，导致「降权」逻辑永远执行不到——这是语义冲突的病根。

**方案 A**（用户拍板）：`superseded_by` **可不带** `invalid_at`。语义区分如下：

| 字段 | 语义 | 检索表现 |
|---|---|---|
| 只有 `superseded_by`（无 invalid_at） | 有新版、旧版仍有效、只是被压一头 | **降权保留**（乘 supersede_penalty） |
| 有 `invalid_at`（无论有无 superseded_by） | 真失效，历史时点后不再成立 | 非历史检索**排除**；历史时点可查 |

**代码落点**：
- `validate.py`：删除「superseded_by 必须带 invalid_at」的强约束；区间自洽检查（invalid_at 不早于 valid_from）保留，统一处理。
- `store.invalidate()`：新增 `set_invalid=True` 参数；`set_invalid=False` 时只标记 `superseded_by`、不写 `invalid_at`。
- `proposal.py`：`supersede` / `merge` / `split` 三条提案路径传 `set_invalid=False`（取代不失效）。
- `cli.py` 的 `invalidate` 命令保持默认 `set_invalid=True`（用户手动失效 = 真失效，`--by` 只是顺带记录取代者）。

### 3.3 明确不做（防过度设计）

- ❌ 不做「多维物理合并成一条」
- ❌ 不做知识图谱（实体-关系三元组）
- ❌ 不加固定维度枚举字段
- ❌ 不把降权幅度本期写死（留 `settings` 可调，后期用指标定）

## 四、待验证 / 挂起

- **降权幅度指标**：后期需制定「该降多少」的判据（如用 access 表召回率、人工反馈），本期只留配置口子。

## 五、改动文件清单（预期）

| 文件 | 改动 |
|---|---|
| `lmr/judgment.py` | 改 SUPERSEDE 判定 prompt 逻辑 |
| `lmr/index.py` | 检索排序接 supersede_penalty |
| `lmr/config.py` | 加 `supersede_penalty` 可配置项 |
| `lmr/validate.py` | 解耦 superseded_by 与 invalid_at（删除强绑定校验） |
| `lmr/store.py` | `invalidate()` 加 `set_invalid` 参数，支持「取代不失效」 |
| `lmr/proposal.py` | supersede/merge/split 路径传 `set_invalid=False` |
| `tests/` | 补检索降权、取代判定的单测/集成测试 |
