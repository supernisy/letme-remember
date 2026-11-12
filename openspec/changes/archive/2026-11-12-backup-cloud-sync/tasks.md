## 1. gitutil 扩展

- [x] 1.1 新增 `push(root, remote, branch)`：`git push <remote> <branch>`，失败抛 `InternalError`；复用 `_run`
- [x] 1.2 新增 `pull(root, remote, branch)`：`git pull <remote> <branch>`，失败抛 `InternalError`
- [x] 1.3 新增 `is_clean(root)`：`git status --porcelain` 为空返回 True；验证：空仓库/已提交仓库均正确判定
- [x] 1.4 新增 `clone(parent, remote, name)`：换机后空目录从远端 clone 密文

## 2. backup 云端同步

- [x] 2.1 `backup.py` 新增 `_ensure_backup_repo(target)`：确保备份目录是独立 git（复用 `gitutil.ensure_repo`），并写 `.gitignore`（`*` + `!*.enc` + `!.gitignore`）
- [x] 2.2 新增 `sync(paths, settings, target_dir=None)`：加密 → commit → 读 `backup.remote`，未配置返回 `{"synced": false, "reason": ...}`；配置了则 push，返回 `{"synced": true, "file": ..., "remote": ...}`
- [x] 2.3 `restore` 增加 `from_cloud` 参数：为 True 时在备份目录 clone/pull 拉密文，取最新 `.enc` 解密恢复；未配置远端抛 `ValidationError`
- [x] 2.4 验证密文仓库不含明文：加密后 `git ls-files` 只含 `.enc`/`.gitignore`，无 `.md`

## 3. CLI 接线

- [x] 3.1 注册 `backup-sync` 子命令（`--target` 可选），映射到 `backup_module.sync`
- [x] 3.2 `restore` 子命令新增 `--from-cloud` 开关，映射到 `restore(..., from_cloud=...)`

## 4. 测试与校验

- [x] 4.1 单测：`gitutil.is_clean` / `push`/`pull`/`clone` 参数传递；`sync` 未配置远端 → `synced:false`；`restore --from-cloud` 未配置远端 → `ValidationError`
- [x] 4.2 集成：本地 bare 远端仓库走一遍「加密 → push → 换目录 clone → 解密恢复」往返，记忆完整恢复（e2e 固化）
- [x] 4.3 全量回归：既有 161+20 子测试全绿，新增用例全绿（现 173 + 20 子测试）
- [x] 4.4 `openspec validate 2026-11-12-backup-cloud-sync` 无 ERROR
