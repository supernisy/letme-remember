## 目标

把「本地加密 → 云端同步」固化为可执行链路，云端只存密文。落地为一个 `sync` 原语：加密产出密文后，备份目录作为独立 git 仓库提交并 push 到配置的远端。

## 数据流

```
本地数据目录（明文 .md/.json）
   │  backup()：tar 打包 → Fernet 加密 → base64
   ▼
备份目录 <data-dir>/backup/（只含 *.enc 密文 + .gitignore）
   │  sync()：git add -A → commit → push
   ▼
云端私有仓库（只有密文）
```

密钥 `~/.letme-remember/backup.key` 永不出现在上述任何一环。

## 云端目标配置

远端 URL 从 `config.json` 读取，字段 `backup.remote`（可选）：

```json
{ "backup": { "remote": "https://github.com/<owner>/<repo>.git" } }
```

- 未配置 `backup.remote` → `sync` 只做本地加密，返回 `{"synced": false, "reason": "未配置云端目标"}`，不抛异常。
- 配置了但 push 失败（网络/权限）→ 明确报 `ValidationError`（同步失败，本地密文仍在），不回滚本地密文。

## git 隔离

- 备份目录是**独立** git 仓库（`<data-dir>/backup/.git`），与数据目录的审计 git、与公开代码仓库完全无关。
- 目录内 `.gitignore` 写 `*` + `!.enc` + `!.gitignore`，保证即使误 `add -A` 也只会 track 密文。
- `push`/`pull` 复用 `gitutil._run`（subprocess + UTF-8 + errors=replace），新增 `gitutil.push(root, remote, branch)` / `gitutil.pull(root, remote, branch)` / `gitutil.is_clean(root)`。

## 恢复侧

`restore` 现有参数为本地密文文件路径。新增可选 `--from-cloud`：

- 带 `--from-cloud` 且配置了远端 → 在备份目录 `git pull` 拉到最新密文，取最新 `.enc` 文件解密恢复。
- 带 `--from-cloud` 但未配置远端 → `ValidationError`（明确「未配置云端目标」）。
- 不带 `--from-cloud` → 走既有本地文件恢复，行为不变。

## 边界

- `sync` 只同步**密文**，不校验、不解密云端内容（云端解密的唯一入口是 `restore`）。
- 密钥缺失时 `backup` 会先生成并保存本地密钥（既有行为），sync 沿用。
- 定时同步（spec「定期同步」）不在本期：由宿主调度器周期性调用 `backup-sync` 即可。
