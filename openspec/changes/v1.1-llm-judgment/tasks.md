# v1.1 任务清单

> LLM 软判断（第二审）与存量批量蒸馏。

## 1. LLM 接入层

- [x] 1.1 新增 `lmr/llm.py`：可插拔 OpenAI 兼容客户端（零第三方依赖，仅标准库 urllib）
- [x] 1.2 key 只从环境变量 `LMR_LLM_KEY` 或私有数据目录 config 读取，公开仓库不发布 key
- [x] 1.3 `config.py` DEFAULT_SETTINGS 增 `llm_enabled/llm_base_url/llm_model/llm_key`（默认关闭不联网）
- [x] 1.4 `config.example.json` 增 LLM 字段示例（key 留空）

## 2. LLM 软判断（第二审）

- [x] 2.1 新增 `lmr/judgment.py`：结构化体检报告（六触发器 + importance/confidence/missing）
- [x] 2.2 报告解析稳健化（容忍 markdown 代码块、多余文字）
- [x] 2.3 报告归一化（非法字段取安全默认值）
- [x] 2.4 `classify()` 代码按固定阈值映射 L0/L1/L2，不因接 LLM 让模型自行拍板

## 3. 降级路径

- [x] 3.1 新增 `rule_report()`：LLM 不可用时用纯规则产出体检报告
- [x] 3.2 规则报告置信度恒低，定级偏保守（宁 L2 不误放行）

## 4. 冲突检测增强

- [x] 4.1 软判断时把候选与「检索出的相似已有结论」比对，产出 conflict 字段
- [x] 4.2 显式判断 ADD/UPDATE/SUPERSEDE/NOOP，与时间轴联动（后续细化）

## 5. 存量批量蒸馏

- [x] 5.1 `distill.py` 新增 `LLMDistiller`：长文本 → 候选记忆列表
- [x] 5.2 `batch-distill` 命令：`--file` 指定文本，`--dry-run` 只出候选不落库
- [x] 5.3 候选照过第一审（原子预校验 + 红线）再落库

## 6. CLI 命令

- [x] 6.1 新增 `judge` 命令：对候选做软判断并定级
- [x] 6.2 新增 `batch-distill` 命令：LLM 批量蒸馏

## 7. 测试

- [x] 7.1 新增 `tests/test_llm_judgment.py`（30 项：报告解析/归一化/分级/降级/key 解析/冲突检测增强）
- [x] 7.2 修正 `test_read_path_zero_model_zero_network` 收窄到读路径模块（LLM 是写路径）
