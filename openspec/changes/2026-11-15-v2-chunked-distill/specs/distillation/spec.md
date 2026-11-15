## ADDED Requirements

### Requirement: 超长文本分块蒸馏

超长文本（超过单次调用安全上限）SHALL 采用 Map-Reduce 范式蒸馏：先分块、再逐块提炼、最后合并去重，避免单次调用截断丢信息。

#### Scenario: 分块后逐块提炼

- **WHEN** 输入文本超过单块上限
- **THEN** 系统 SHALL 先把文本切成若干块，再对每块独立调用提炼器产出候选
- **AND** 各块的候选 SHALL 汇总后统一合并

#### Scenario: 合并去重复用既有判定

- **WHEN** 分块提炼产生跨块重复的候选
- **THEN** 系统 SHALL 按 name 确定性去重（同 name 保留最后一条）
- **AND** 更深的语义去重（ADD/UPDATE/SUPERSEDE/NOOP）SHALL 交由既有 consolidate 完成，不在分块蒸馏内新造

#### Scenario: 单块蒸馏失败不阻断整批

- **WHEN** 某一块的提炼调用失败
- **THEN** 系统 SHALL 记录并跳过该块、继续处理其余块，MUST NOT 因单块失败中断整批

### Requirement: 说话人轮次分块

访谈/面试/会议类转写 SHALL 按「说话人轮次」边界分块，保证一个问答不被拆两半。

#### Scenario: 按说话人边界切分

- **WHEN** 分块器处理带「讲话人 + 时间戳」结构的转写文本
- **THEN** 系统 SHALL 以空行分隔的说话人段落为最小单元累积，逼近块上限时才在段落边界封块
- **AND** 块 SHALL 总是从完整说话人单元开始，不在问答中间切断

#### Scenario: 单段超长兜底

- **WHEN** 单个说话人段落本身超过块上限
- **THEN** 系统 SHALL 按句边界二次切分该段落，避免单块仍超限

#### Scenario: 分块零模型零网络

- **WHEN** 分块器切分文本
- **THEN** 分块 SHALL 是纯确定性操作，MUST NOT 调用大模型、MUST NOT 访问网络

### Requirement: 结论级增量 diff

同一主题的多次结论 SHALL 支持结论级增量对比，显式产出「本次新增 / 深化 / 未变」清单，而非只做去重。

#### Scenario: 产出增量清单

- **WHEN** 对「上一版结论集」与「这一版候选集」做增量分析
- **THEN** 系统 SHALL 产出三类清单：added（旧集没有、本次全新）、deepened（旧集已有、本次补充细节）、unchanged（基本一致）
- **AND** 附一句话总结本次相对上次的整体变化

#### Scenario: 结论级而非句子级

- **WHEN** 执行增量对比
- **THEN** 对比 SHALL 在结论粒度进行（每条结论的新增/深化/未变），MUST NOT 做句子级原文溯源

#### Scenario: 首次无上一版可降级

- **WHEN** 不存在上一版结论集（首次蒸馏）
- **THEN** 增量 diff SHALL 可跳过或标记「首次、无历史对比」，MUST NOT 阻断分块蒸馏主流程
