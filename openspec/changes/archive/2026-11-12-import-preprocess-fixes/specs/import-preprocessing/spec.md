# import-preprocessing Spec Delta

## MODIFIED Requirements

### Requirement: 三类判定

预处理 SHALL 把每条源内容判定为三类之一：格式合规可转、待裁决、明确排除。判定 SHALL 只依据机器能确定性判断的形状/格式层信号，SHALL NOT 判定「该结论现在是否成立」。

无 frontmatter 但正文含「结论 + 理由」两节的文本 SHALL 判定为「待裁决」而非「明确排除」：它是有价值但缺形状的存量，应提示补 frontmatter 后由人确认。只有「无 frontmatter 且正文不含结论/理由结构」的碎片才归「明确排除」。

#### Scenario: 格式合规可转

- **WHEN** 一条源内容通过形状红线、字段完整、日期合法、类型可猜
- **THEN** 系统 SHALL 判定为「格式合规可转」，产出候选卡片

#### Scenario: 待裁决

- **WHEN** 一条源内容形状合规但类型无法确定、疑似取代关系或命中合规边界，或「无 frontmatter 但正文含结论+理由结构」
- **THEN** 系统 SHALL 判定为「待裁决」，标注需人判断的信号（如 missing-frontmatter），SHALL NOT 自动落库

#### Scenario: 明确排除

- **WHEN** 一条源内容属于日志流水、过程推演、重复备份或会话原文，或「无 frontmatter 且正文不含结论/理由结构」的碎片
- **THEN** 系统 SHALL 判定为「明确排除」，不产出候选卡片

### Requirement: 幂等可重跑

同一源文件重复预处理 SHALL 按内容哈希识别，已确认或已排除的条目 SHALL NOT 重复生成卡片；源文件 SHALL 始终只读。

条目切分 SHALL 只把「后面紧跟合法字段行（key: value，key 属 frontmatter 字段白名单）」的 `---` 视为 frontmatter 分隔线；普通 Markdown 水平线 SHALL NOT 参与切分，以免把单条结构化内容误切成碎片。

#### Scenario: 重复预处理不重复产卡

- **WHEN** 对同一源文件重复执行预处理
- **THEN** 系统 SHALL 按内容哈希识别重复，不重复生成卡片，源文件内容不变

#### Scenario: 水平线不误切

- **WHEN** 源内容含普通 Markdown 水平线（`---` 后跟正文/标题而非字段行）
- **THEN** 系统 SHALL 将其视为正文而非 frontmatter 边界，整段作为一条内容处理
