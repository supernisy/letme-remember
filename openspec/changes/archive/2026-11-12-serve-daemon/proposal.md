## Why

v1.3 接入语义检索后，UserPromptSubmit hook 每次提交消息都会启动一个全新 Python 进程，冷启动加载 120MB 的 MiniLM 模型并联网验证版本（国内直连 huggingface 被墙，SSL 重试 5 次各 1-8 秒），实测耗时约 100 秒，远超宿主 hook 的 15 秒超时上限，导致每次提问都报 `Hook timed out after 15000ms`、召回功能完全不可用。

根因不是「向量库慢」，而是「每次都要重新启动模型」——hook 的进程生命周期太短，模型缓存无法跨进程复用。用户明确要求：装向量库就是要用语义检索，不许为了不超时而砍功能；正确解法是让模型常驻，检索毫秒级，同时做好超时兜底，出问题不影响会话。

## What Changes

- **常驻召回服务**：新增 `mem.py serve` 命令，模型只加载一次、常驻内存，通过本地 TCP（127.0.0.1:7867）对外提供毫秒级召回；`mem.py serve-shutdown` 通知服务退出。
- **离线加载**：服务进程强制 `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`，加载纯本地缓存模型（约 11 秒），不再联网验证，砍掉原先 100 秒里 89 秒的联网等待。
- **hook 客户端化 + 双层兜底**：`lmr_recall.py` 改为先向常驻服务请求语义召回（2 秒超时）；服务不可用/超时/异常时，自动降级为本地纯关键词召回（`LMR_DISABLE_EMBEDDING=1`），保证绝不让主流程卡死。
- **生命周期绑定**：新增 `lmr_serve_start.py`（挂 SessionStart，后台拉起服务）与 `lmr_serve_stop.py`（挂 SessionEnd，关闭服务）；服务自带空闲超时自退（默认 30 分钟）与端口锁（防重复拉起），即使 SessionEnd 未触发也不会残留僵尸进程。

## Capabilities

### Modified Capabilities

- `retrieval`: 语义检索从「每次冷启动加载模型」演进为「常驻服务 + 毫秒级召回 + 客户端超时降级」，补充「读路径性能与故障隔离」的行为约束。
- `cli`: 新增 `serve`、`serve-shutdown` 两个操作，其余操作保持兼容。

## Impact

- 新增 `lmr/serve.py`（常驻服务核心，零新依赖，只用标准库 socket/json/threading）。
- `lmr/cli.py` 新增 `serve` / `serve-shutdown` 两个子命令与 handler。
- WorkBuddy hook 侧：`lmr_recall.py` 改为客户端模式，新增 `lmr_serve_start.py` / `lmr_serve_stop.py` 两个生命周期 hook 脚本；`~/.workbuddy/settings.json` 注册 SessionStart / SessionEnd 两事件。
- 读路径零 LLM、零网络的核心原则 SHALL 不变（语义计算仍是纯本地）。
- 既有检索行为不回归：服务不可用时自动降级关键词，检索结果仍可用。

## Non-goals

- 不做跨设备/跨进程的分布式召回（服务只监听 127.0.0.1 本机回环）。
- 不改动语义模型的选型与融合算法（仍用现有 MiniLM + RRF，语义权重不变）。
- 不做向量索引的常驻服务化之外的任何检索性能调优。
