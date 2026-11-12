## 1. 常驻服务核心

- [x] 1.1 新增 `lmr/serve.py`：实现 `serve_forever()`（监听 127.0.0.1:7867、串行处理请求、空闲超时自退）、`_load_engine()`（离线加载模型 + 引擎预热）、`_handle()`（处理 recall/shutdown/ping 三种 op）、`client_recall()` / `client_shutdown()`（客户端）；验证：手动起服务，`client_recall` 能拿回带 semantic 分的结果
- [x] 1.2 端口锁与自退：`_already_running()` 检测已有实例则静默跳过；空闲超过 `LMR_SERVE_IDLE_TIMEOUT`（默认 1800s）自动退出；验证：重复起服务不报错，端口被占时不冲突

## 2. CLI 接入

- [x] 2.1 在 `cli.py` 注册 `serve` / `serve-shutdown` 两个子命令与 handler，走标准退出码；验证：`mem.py serve --help` 退出码 0
- [x] 2.2 `cmd_serve` 里在加载模型前设离线环境变量，`cmd_serve_shutdown` 调 `client_shutdown` 并静默成功；验证：`serve-shutdown` 对未运行的服务返回成功

## 3. hook 客户端化与兜底

- [x] 3.1 改写 `lmr_recall.py`：先 `_recall_from_serve()` 请求服务（2 秒超时），拿不到再降级 `inject --query`（LMR_DISABLE_EMBEDDING=1）；验证：服务在线走语义（<1s），服务宕机降级关键词（<3s），均无报错
- [x] 3.2 新增 `lmr_serve_start.py`（SessionStart 后台拉起，不阻塞）与 `lmr_serve_stop.py`（SessionEnd 关闭）；验证：start 脚本退出码 0、服务后台就绪，stop 脚本能关闭服务

## 4. 注册与收尾

- [x] 4.1 在 `~/.workbuddy/settings.json` 注册 SessionStart（matcher startup）与 SessionEnd（matcher other）两事件，并把 `_UserPromptSubmit` 改回正确的 `UserPromptSubmit`；验证：settings.json 为合法 JSON
- [x] 4.2 OpenSpec 校验通过：`openspec validate 2026-11-12-serve-daemon` 无 ERROR；验证：命令退出无 ERROR
- [x] 4.3 提交代码到 git（commit 234ff4d，含 serve.py 与 cli.py 改动）；验证：`git log` 含该提交
