## Why

`backup.py` 只实现了「本地加密 + 恢复」，spec `backup` 里「本地加密后上传」的**上传侧**一直悬空。云端同步目前靠手工 `git push`（私有仓库 `supernisy/letme-remember-backup`），没有固化进代码，换机恢复也就没有「从云端拉取」的落地命令。

本期把「加密 → 云端同步」这条链路固化成可一键执行的能力：密文目录作为独立 git 仓库，提交后 push 到配置的远端，云端永远只有密文、没有明文，密钥永不上云。

## What Changes

- **新增云端同步**：`backup` 产出密文后，把备份目录（只含 `.enc` 密文 + `.gitignore`）作为一个独立 git 仓库提交并 `git push` 到配置的远端。
- **新增 `backup-sync` 子命令**：一键完成「加密 → 提交 → 推送」，未配置远端时优雅降级为「仅本地加密，提示未配置云端目标」，绝不报内部错误、绝不把明文推上云。
- **恢复侧补齐「从云端拉取」**：`restore` 增加从远端 `git pull` 拉取密文的能力，换机时先拉密文再本地解密恢复。
- **gitutil 扩展**：新增 `push()` / `pull()` / `is_clean()`，复用既有 `_run` 基础设施，与审计 git 的解耦约束一致。

## Capabilities

### Modified Capabilities

- `backup`: 落地「本地加密后上传」的上传侧——密文经独立 git 仓库推送至云端远端，云端只存密文；恢复侧补齐从云端拉取密文。

## Impact

- 新增 `lmr/backup.py::sync()`（加密 → 提交 → 推送），扩展 `gitutil`（`push`/`pull`/`is_clean`），CLI 注册 `backup-sync`。
- 备份目录内用 `.gitignore` 保证只 track `.enc` 密文；`.git/` 与密钥一律不进备份包、不上云。
- 远端未配置 → `sync`/`restore --from-cloud` 明确提示「未配置云端目标」并降级，不报内部错误。
- 测试补充：加密后密文仓库不含明文关键词、`sync` 未配置远端时优雅降级、`restore --from-cloud` 拉取后解密恢复。

## Non-goals

- 不做自动定时同步的调度器（spec「定期同步」由宿主 cron / 计划任务触发，本期只落地「单次同步」原语）。
- 不做密钥托管 / 多设备密钥分发——密钥仍只在本地，靠用户离线保存。
- 不改审计 git 与备份 git 的隔离约定（两者是独立的仓库）。
