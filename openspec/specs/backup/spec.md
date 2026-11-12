# backup Specification

## Purpose
定义记忆数据的加密备份与云端同步契约：数据目录在本地加密后同步到云端，云端只存密文，密钥永不上云，支持定期与实时两种同步方式，并能在换机或数据丢失时恢复。

## Requirements

### Requirement: 本地加密后上传

备份 SHALL 在本地完成加密，云端只存密文；加密密钥 SHALL 永不上云，与密文分离存放。

「上传」SHALL 落地为：备份目录作为独立 git 仓库，提交后 push 到配置的云端远端（`backup.remote`）。备份目录 SHALL 通过 `.gitignore` 白名单只 track 密文（`.enc`）与 `.gitignore` 本身，SHALL NOT track 任何明文（`.md`/`.json` 源文件）。

#### Scenario: 加密后同步

- **WHEN** 执行备份同步（backup-sync）
- **THEN** 系统 SHALL 在本地加密数据目录，把密文提交并 push 到配置的云端远端，云端不出现任何明文

#### Scenario: 密钥分离

- **WHEN** 备份流程使用密钥
- **THEN** 密钥 SHALL 仅存本地（或离线介质），SHALL NOT 随密文一同上传

#### Scenario: 云端只含密文

- **WHEN** 云端远端被非授权方查看
- **THEN** 远端仓库 SHALL 只含 `.enc` 密文与 `.gitignore`，不含任何 `.md`/`.json` 明文源文件

### Requirement: 定期与实时同步

系统 SHALL 支持定期同步（按计划周期）与实时同步两种方式，同步方式可配置。

#### Scenario: 定期自动备份

- **WHEN** 到达配置的备份周期
- **THEN** 系统 SHALL 自动执行「加密 → 同步」一次，无需用户手动操作

#### Scenario: 云端密文泄露不解密

- **WHEN** 云端存储的密文被非授权方获取
- **THEN** 因密钥不在云端，密文 SHALL NOT 可被解密，明文不泄露

### Requirement: 恢复

系统 SHALL 提供恢复流程，换机或数据丢失时，用本地保存的密钥解密密文并恢复数据目录。

恢复 SHALL 支持从云端拉取：`restore --from-cloud` 在备份目录已是远端 clone 出的 git 时 pull，否则 clone 远端到备份目录，再取最新密文用本地密钥解密恢复。

#### Scenario: 换机恢复

- **WHEN** 在新机器上用密钥执行 `restore --from-cloud`
- **THEN** 系统 SHALL 从云端远端拉取（clone 或 pull）密文、解密并恢复完整的数据目录，记忆不丢失

#### Scenario: 密钥缺失无法恢复

- **WHEN** 密钥丢失且云端仅有密文
- **THEN** 系统 SHALL 明确报告无法恢复，不得静默产出损坏数据

#### Scenario: 未配置云端目标

- **WHEN** 未配置 `backup.remote` 却执行 `restore --from-cloud`
- **THEN** 系统 SHALL 明确提示「未配置云端目标」，不得报内部错误、不得产出损坏数据

### Requirement: 备份不干扰核心读写

备份功能 SHALL 为可选能力；未配置备份时，核心记忆读写 SHALL 完全不受影响。

#### Scenario: 未配置备份

- **WHEN** 宿主未配置备份的加密工具或云端目标
- **THEN** 系统 SHALL 照常读写记忆，备份相关命令提示未配置而非报错中断

#### Scenario: 未配置远端仅本地加密

- **WHEN** 已装加密库但未配置 `backup.remote`，执行备份同步
- **THEN** 系统 SHALL 完成本地加密并提示「未配置云端目标」，返回 synced=False，不报错中断
