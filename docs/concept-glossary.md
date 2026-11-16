# 概念词典（Concept Glossary）

> 读者：AI 协作者（我 / 未来的其他 AI）｜用途：**快速对齐易混淆概念，避免每次从头查规范**
> 维护规矩：新增/改名任何记忆字段或评分概念时，同步更新本表；改名必须回答「它在哪个环节、干什么用、跟别的概念啥区别」。

---

## 一、命名总原则

记忆的生命周期分三个环节，**变量名按环节锚定**，让名字自己说出边界：

```
① 入库前（一次性）    → 决定「留不留、要不要人审、我有多确信」
② 入库后（检索时每次）→ 决定「这条排多靠前」
③ 检索时（每次）      → 决定「语义 vs 关键词各占几成」
```

**铁律**：一个概念只回答一个问题；两个概念若名字像（都带「重要/权」），说明边界没说清，必须拆名。

---

## 二、五个易混概念对照表（权威定义，改动前先看这表）

| 字段名 | 回答的问题 | 作用环节 | 作用时机 | 落库否 | 取值 | 现名（旧）→ 定名（新） |
|---|---|---|---|---|---|---|
| **`keep_score`** | 蒸馏时这条**够不够格被收** | ① 入库前·筛选阀 | 蒸馏一次性 | ❌ 内部字段 | 整数 1~5（5=跨会话关键，1=边缘可弃） | `importance`(distill) → `keep_score` |
| **`gate_level`** | 这条**要不要人审**（进不进队列） | ① 入库前·审批阀 | 第二审一次性 | ❌ 内部字段 | low/medium/high（决定 L0/L1/L2） | `importance`(judgment) → `gate_level` |
| **`confidence`** | LLM 判断**有多确信** | ① 入库前·置信度 | 第二审一次性 | ❌ 内部字段 | low/medium/high | `confidence`（不改） |
| **`boost`** | 这条**该排多靠前** | ② 入库后·排序乘数 | 检索每次 | ✅ 落库字段 | 0~10（默认 1.0） | `weight` → `boost` |
| **`semantic_mix`** | 语义 vs 关键词**各占几成** | ③ 检索·融合比例 | 检索每次 | ⚙️ 配置项 | 0~1（默认 0.5） | `semantic_weight` → `semantic_mix` |

---

## 三、为什么必须拆名（混淆的病根）

历史上三个不同的东西都挤在「weight / importance 家族」里，导致每次讨论都要重新「翻译」语义：

1. **`weight`（排序乘数）vs `importance`（筛选/审批阀）**：前者是「入库后每次检索都乘的排序系数」，后者是「入库前一次性判断要不要收/要不要审」。两者时间点不同、对象不同，但名字都像「重要程度」，`judgment.py` 还写了「importance 依 weight 推断」的映射，进一步模糊了边界。
2. **两个 `importance` 用了两套标度**：distill 用整数 1~5，judgment 用字符串 low/high——同一个词两种刻度，必须拆成 `keep_score` + `gate_level`。
3. **`semantic_weight` 不是「权重」是「比例」**：0.5 的意思是「语义和关键词各占一半」，叫 weight 会误导成「语义的重要性」，实为混合比例，故改 `semantic_mix`。

**关键设计边界（不可反悔）**：
- `keep_score` / `gate_level` / `confidence` 都是**入库前一次性**的内部字段，**永不落库**。入库后的「重要度」只由 `boost` 承担。
- 方向③「重要度分类法」若做「检索回馈上调」，上调的是 `boost`（落库字段），**不是** `keep_score`/`gate_level`（内部阀）——这二者入库后即失效。

---

## 四、来源信任分级（方向②引入，勿与上述混淆）

当两条结论冲突时要回答「**谁的来源更可信**」，这是**第五个概念**，但**与上述四个不同维度**：

- 它**只在冲突裁决的 tie-breaker（平局裁决）时用**，**不进常规检索排序公式**。
- 只做两档：**显式用户陈述 > 模型推断**（复用 `author` 字段区分 human / import: / 模型推断，无需新字段）。
- 不做 Mycelium 那种 0~1 连续信用分（那是多智能体互不信任场景，单人记忆库用不上）。

**与 `boost` 的区别**：`boost` 是「绝对重要度」（不影响冲突时该信谁），来源信任是「相对可信度」（只在冲突平局时生效）。

---

## 五、改动同步清单（改名时必查）

改名 `weight`→`boost` 等涉及以下文件的字段名，必须一并改，否则落库文件解析会报「未知字段」：

- 代码：`frontmatter.py`（FIELDS 元组）、`schema.py`、`store.py`、`index.py`、`judgment.py`、`distill.py`、`cli.py`、`queue.py`、`gui_server.py`
- 规范：`memory-model/spec.md`、`retrieval/spec.md`、`write-approval/spec.md`、`governance/spec.md`
- 文档：`design-tradeoffs-cheatsheet.md`、`project-map.md`
- 存量数据：`~/.letme-remember/data/store/*.md` 的 `weight:` 字段（需迁移脚本，先 dry-run）

---

*创建：2026-11-16 ｜ 起因：weight/importance/confidence 命名混淆，用户要求「变量名给 AI 看，注释给人看」，并沉淀成可复用锚点*
