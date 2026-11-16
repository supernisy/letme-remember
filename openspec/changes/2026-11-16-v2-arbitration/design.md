## Context

存量数据 739 条，几乎全部 `author` 为 `import:workbuddy-*`（719 条），只有 5 条 `user-direct`。即当前只有 WorkBuddy 单宿主在写，DSH / 千问办公尚未接入。因此本期做的是「先建维度 + 搭框架」，等 DSH/千问真接入后仲裁器才有真实数据可跑。

现有记忆模型（memory-model）已有 `valid_from`（写入/生效时间）、`type`、`provenance`，但缺「适用条件」维度。方向①已定三结局裁决（governance），但未落地为可执行仲裁器。

## Goals / Non-Goals

**Goals:**

- 建干净、归一化的 `host` 维度，与 `author`/`provenance` 解耦。
- 建 `applicability` 维度（固定四槽 + 半开放 extra），蒸馏时抽出、扫描时脚本比对。
- 把三结局裁决落地为可执行仲裁器：候选发现 → 条件重叠检测 → 三结局 → 交人提案 + 来源信任 tie-breaker。
- 判断分三层（脚本比条件 → 模型判语义 → 人做终裁），判断权归用户。

**Non-Goals:**

- 不做跨平台仲裁（我的记忆 vs 平台自带记忆），挂起等平台接口。
- 不引入 LLM 做「谁是真相」的最终裁决。
- 不让来源信任进入常规检索排序。
- 不做知识图谱 / 实体消解。
- 本期不回填存量 `applicability`（无多宿主数据，白做功）。

## Decisions

### 决策 1：host 只归一化不枚举

`host` 值不设封闭枚举（任何枚举框不住通用记忆），只做归一化（去前缀、小写、去空白）。与方向①「不加固定维度枚举字段」哲学一致。

### 决策 2：applicability = 固定四槽 + 半开放 extra

综合业界（Minsky 框架理论 1974 / JSON Schema `additionalProperties` / 当下 AI 记忆系统的 dual-memory「schema-enforced + open-set」双通道），固定槽位 + 自由字段兜底是成熟正路。四槽 `audience`（对象）、`scenario`（场景）、`time`（适用时间窗）、`precondition`（前提）覆盖 90% 常见条件；`extra` 半开放键值对（键自由、值须字符串）兜底计划外条件。

`time` 与 `valid_from` 严格区分：`valid_from` 是写入事实时间（管 recency 衰减），`applicability.time` 是结论适用时间窗（管冲突判定）。

### 决策 3：语义解析只做一次，脚本只做比对

蒸馏时大模型把文本抽成结构化 applicability（一次性成本）；冲突扫描时脚本只消费已结构化字段做确定性比对（零成本、可重复）。脚本**不判语义矛盾**，只做「条件重叠检测」——四槽值明确相同/不同的才确定性判断，其余标记「疑似」上浮交模型。

### 决策 4：四类冲突映射三结局

| 冲突类型 | 映射结局 |
|---|---|
| 结论冲突（条件重叠+互斥，有日期） | Replacement（取代，旧标 superseded_by 降权） |
| 结论冲突（条件重叠+互斥，无日期） | Undated（交人） |
| 场景/对象型（条件不同） | Parallel views（并存，非冲突） |
| 不同侧面（互补不矛盾） | Parallel views |
| 迭代冲突（部分冲突部分互补） | 拆开看：被取代部分走 Replacement，互补部分走 Parallel views，拆不开走 Undated |

### 决策 5：交人粒度 = 后果 × 置信度二分

低后果 + 明确新旧 → 静默按 recency；高后果（决策/权限/不可逆）或规则裁不动 → 交人；置信度 < 0.7 → 上浮交人。判断权归用户，AI 只备可选项 + 信号清单。

### 决策 6：来源信任两档，仅作 tie-breaker

两档 `explicit`（显式用户陈述）> `inferred`（模型推断）。只在冲突裁决无日期可定、需破局时作最后 tie-breaker，不进常规检索排序（排序仍由 boost × recency × supersede_penalty 决定）。

## Risks / Trade-offs

- **applicability 抽取质量决定仲裁质量**（垃圾进垃圾出）：四槽抽取不准，脚本比对的确定性判断就不可靠。缓解：蒸馏 prompt 明确要求结构化输出；疑似/判不准一律交人而非硬拍。
- **条件重叠检测覆盖不全**：四槽覆盖 90%，`extra` 与粒度不同的情况只能降级交模型。缓解：接受「宁交人不误判」，与判断权归用户原则一致。
- **存量 host 回填靠前缀推导可能不准**：`author` 前缀是唯一可据信号，推导结果可能错标宿主。缓解：回填只补 host 不改历史字段，可后续人工纠正。
- **本期框架数据空转**：DSH/千问未接入前，仲裁器无真实多宿主数据可跑，只能逻辑就绪。这是预期内，不是缺陷。
