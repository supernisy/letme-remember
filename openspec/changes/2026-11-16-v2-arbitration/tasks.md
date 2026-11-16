## 1. 宿主维度

- [ ] 1.1 在 `lmr/schema.py` 新增 `host` 字段定义（与 author/provenance 解耦），verify：跑 `python -m pytest tests/ -q -k host` 相关用例通过、schema 校验不报未知字段
- [ ] 1.2 在 `lmr/frontmatter.py`、`lmr/store.py` 接入 `host` 读写，verify：写入一条带 host 的记忆后读回，host 值往返一致
- [ ] 1.3 写存量 host 回填脚本（从 author 前缀推导），verify：dry-run 输出 739 条推导结果，`import:workbuddy-* → workbuddy`、`user-direct → manual` 映射正确，且不改 author/provenance

## 2. 适用条件维度

- [ ] 2.1 在 `lmr/schema.py` 新增 `applicability` 字段（四槽 audience/scenario/time/precondition + 半开放 extra），verify：schema 校验接受四槽全 null、也接受 extra 任意字符串键值，拒绝 extra 非字符串值
- [ ] 2.2 改 `lmr/distill.py` 蒸馏 prompt 与输出结构，让新记忆抽出结构化 applicability，verify：对样例文本 dry-run 蒸馏，产出记忆带 applicability 字段且四槽/extra 结构正确
- [ ] 2.3 确认 `time`（适用时间窗）与 `valid_from`（写入时间）语义分离，verify：同一结论蒸馏后两字段取值不同且互不覆盖

## 3. 仲裁器核心

- [ ] 3.1 新建 `lmr/arbitrator.py`：候选发现（同主题 + 多 host 聚类，复用 Index.recall，零 LLM 零网络），verify：构造含两个 host 的同主题条目，扫描能聚成候选组；单 host 条目不误报
- [ ] 3.2 实现条件重叠检测（脚本比 applicability 四槽 + extra），verify：槽值不同→并存、槽值相同/都空且结论相反→冲突、粒度不同/键对不齐→疑似，三类用例通过
- [ ] 3.3 实现三结局裁决（Replacement 有日期取代 / Parallel views 并存 / Undated 交人），verify：四类冲突（结论/场景/不同侧面/迭代）各映射到正确结局的用例通过
- [ ] 3.4 实现交人粒度（后果×置信度二分，置信度<0.7 上浮），verify：低后果+明确新旧静默、高后果/裁不动/低置信交人的用例通过

## 4. 交人机制与来源信任

- [ ] 4.1 在 `lmr/proposal.py` 新增 `arbitrate` 操作类型进 APPROVAL_REQUIRED 表，verify：生成仲裁提案进待审队列，payload 含各条目 id+host+摘要+建议选项（不给唯一答案）
- [ ] 4.2 实现来源信任两档（explicit > inferred）仅作 tie-breaker，verify：检索排序结果不受来源信任影响（与未加该字段时一致），仅冲突破局时显式优先于推断

## 5. 入口与展示

- [ ] 5.1 在 `lmr/cli.py` 加 `arbitrate` 命令（手动触发入口），verify：`python mem.py arbitrate --dry-run` 能跑通扫描并输出候选组
- [ ] 5.2 在 `lmr/gui_server.py` 加冲突仲裁只读展示 API + 手动触发口子，verify：API 返回候选组 JSON，GUI 可只读查看、不提供写操作

## 6. 验证与回归

- [ ] 6.1 写 arbitration 相关单测/集成测试，verify：`python -m pytest -q` 全量通过（含新增仲裁用例）
- [ ] 6.2 跑三层验收：后端 pytest + GUI 契约验收（`node acceptance/gui-v2/run-acceptance.mjs`）+ `openspec validate`，verify：三层全绿
