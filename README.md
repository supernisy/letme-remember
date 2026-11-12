# letme-remember

一个**通用的长期记忆仓库**：面向多个 AI Agent 平台共享，作为「对我非常了解」的跨宿主辅助记忆。
大模型本身无状态；这里做的是**每轮重新决定给模型看什么**。

## 核心理念

- **文件是唯一真相源**：Markdown 文件人可读、可 git、可迁移；索引只是可重建缓存。
- **结论级粒度，按类型定义**：每条记忆带类型、带理由、带时间轴（何时成立 → 何时失效 → 被谁取代）。
- **三审写入**：脚本校验与形状红线 → 提炼器产出候选 → 人审批提案；要不要人审批由脚本分类表写死，不由模型自行决定。
- **永不物理删除**：过期结论只标记失效 + 归档，可按历史时点查回当时的真相。
- **读路径零模型、零网络**：检索只用本地算法，不消耗模型调用。

## 当前状态

- **v1 最小闭环**：写入一条结论 → 中文关键词查得到 → 按日期查回当时的真相，带可撤销的私有 git 审计。
- **v1.1 冲突检测 + LLM 蒸馏**：可插拔 LLM 软判断（第二审）、冲突检测（ADD/UPDATE/SUPERSEDE/NOOP）、自动去重合并 `consolidate`、批量蒸馏（结论 + reference 双轨）、SUPERSEDE 时间维度守卫。
- **v1.2 无感集成 + 待审队列 + 备份**：宿主无感集成层（`setup --host`）、待审队列（L1/L2 异步入库审批）、加密备份（密钥不上云）。

开发方式为 OpenSpec 规范驱动（spec-driven），规范在 `openspec/specs/`，变更提案在 `openspec/changes/`。

## 隐私边界（最重要）

公开仓库里**只有代码、规范、测试和完全虚构的示例**。真实记忆数据在**代码仓库之外**的私有目录：

- 默认路径：`~/.letme-remember/data`；可用环境变量 `LMR_DATA_DIR` 或命令行 `--data-dir` 指定。
- 数据目录内单独维护一个**私有 git** 做审计；索引缓存 `.index/` 可随时删除重建。
- 记忆文件永不随本仓库发布；**克隆本仓库 ≠ 拿到记忆**，宿主需自行配置数据目录。

## 安装

需要 Python 3.11+（本机实测 3.13.14、SQLite 3.53.1、FTS5 可用）。

```bash
pip install -r requirements.txt
```

唯一运行时依赖是中文分词库（固定版本）。**降级**：未安装该依赖时自动切到内置分词 + 两字短词子串兜底，检索仍可返回结果，不会报错中断；也可设 `LMR_DISABLE_TOKENIZER=1` 主动验证降级路径。固定版本是硬要求——写入端与查询端若分词版本不一致，会出现「写进去却搜不到」，索引因此记录分词器版本并在变化时自动全量重建。

## 快速开始

所有命令用 `python mem.py <命令>` 调用（下例简写为 `mem`）。

```bash
mem init                       # 在代码仓库外初始化私有数据目录 + 私有 git
mem record --name 示例-决策 \
  --abstract "虚构示例：记忆用纯文本保存" \
  --type decision \
  --conclusion "记忆以纯文本文件作为唯一真相源" \
  --reason "便于版本管理与本地检索" \
  --author workbuddy
mem recall 记忆                # 中文两字词也能命中
mem recall 记忆 --as-of 2026-10-01   # 查该日期成立的真相（含后来失效的条目）
mem show <定位标识>            # 读回完整正文（含结论与理由）
mem invalidate <定位标识> --by <新标识>   # 只标记失效，文件不删
mem rebuild                    # 删掉索引后从真相源重建，零知识丢失
mem list                       # 输出一句话摘要目录
```

`--candidate <JSON 文件>` 可一次提交完整候选；`mem <命令> --help` 查看全部参数。

**辅助命令**：`inject`（按字节预算输出注入用目录）、`distill`（批量候选，原子预校验）、`propose` / `apply` / `proposals`（审批提案）、`undo`、`undo-batch <批次>`、`archive`、`judge`（软判断分级）、`consolidate`（自动去重落库）、`queue`（待审队列）、`setup --host`（宿主集成）、`backup` / `restore`（加密备份）。

## 无感集成（v1.2）

```bash
mem setup --host workbuddy   # 一键把记忆能力接入 WorkBuddy（生成 hook 脚本 + 注册事件）
```

接入后，宿主在**会话结束**自动后台蒸馏候选，在**会话开始**自动注入记忆索引，用户无需手动维护。

候选蒸馏后按风险分级：L0（无冲突、低重要）静默入库；L1/L2 进入**待审队列**，用 `mem queue list` 查看、`mem queue approve <id>` / `mem queue reject <id>` 处理；超时（默认 7 天）自动降级到 archive 冷存储，绝不静默丢弃。

## 加密备份（v1.2）

```bash
mem backup            # 本地加密数据目录，产出密文备份（密钥存 ~/.letme-remember/backup.key）
mem restore <备份文件>  # 用本地密钥解密恢复
```

**红线**：备份在本地加密，云端只存密文；密钥永不上云。**请把 `backup.key` 离线备份到 U 盘或密码管理器**——密钥丢失则云端密文无法恢复。加密依赖 `cryptography`（可选），未安装时 `backup`/`restore` 会明确提示未配置，不影响核心读写。

## 一条记忆长什么样

```text
---
name: preference-示例-文本笔记
abstract: 虚构示例：偏好用纯文本记录笔记
type: preference
created: 2026-01-01T00:00:00+00:00
updated: 2026-01-01T00:00:00+00:00
valid_from: 2026-01-01
invalid_at:
superseded_by:
weight: 1.0
author: sample
links:
provenance:
---

## 结论
（虚构示例）整理笔记时偏好使用纯文本文件。

## 理由
（虚构示例）纯文本便于检索与版本管理。
```

文件头只认这 12 个固定字段，**故意不用 YAML/JSON**：遇到未知字段、嵌套或富格式直接拒绝，值一律按原始字符串读回，不做隐式类型转换。多宿主与人共同读写时，格式封闭才不会被悄悄曲解。

## 三审在 v1 的落地

| 审 | 实现 |
|---|---|
| 第一审 | 纯代码：字段校验 + 形状规则（凭据类强制打码、机器可读标识符默认只告警，白名单与校验和/熵复核降误报，审计只记规则编号） |
| 第二审 | 可插拔提炼器接口；仓库不内置任何模型调用，模型只产候选、**绝不直接落库**，全部候选先批量原子预校验，任一非法整批拒绝 |
| 第三审 | 内容变更类（合并/拆分/取代/删除/改摘要）先生成提案，人确认后由脚本应用；分类表写死在代码里，每类有单次数量上限 |

## 目录结构

```text
lmr/          实现（文件头 / 校验 / 红线 / 写入 / 索引 / 检索 / 提案 / 命令行）
tests/        单元与端到端测试（全部使用虚构中性数据）
tools/gate.py 准出闸门：失败即关闭；--shadow 为影子模式
docs/         验收记录与技术探针记录
examples/     完全虚构的示例记忆
openspec/     规范（specs）与变更提案（changes）
需求定稿.md    需求收敛记录
```

## 测试与准出

```bash
python -m unittest discover -s tests -v
python tools/gate.py            # 断言完整性 / 需求到测试追溯 / 测试 / 规范校验 / 隐私 / 批准未漂移 / 残留不确定
python tools/gate.py --shadow   # 只报告、不拦截
openspec validate --all
```

人工批准记录由批准人执行 `python tools/gate.py sign --by <批准人>` 固化；脚本只记录被批准规范文件的哈希，**不产生也不更新批准决定**，规范文件一旦改动，批准自动失效需重新确认。

## 借鉴与致谢

设计大量借鉴 [tigerless-labs/agent-memory](https://github.com/tigerless-labs/agent-memory)（typed 记忆 + 文件真相源 + 三审 + 时间轴）与 OpenClaw / Hermes 等业界实践。只取其已验证的设计决策，不 fork。
