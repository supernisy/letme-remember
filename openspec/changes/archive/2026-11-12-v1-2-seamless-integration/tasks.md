## 1. 待审队列（核心，先做）

- [x] 1.1 新增 `lmr/queue.py`：定义待审候选的数据结构与存储位置（`proposals/` 目录下的 pending 状态文件），实现 `queue list` / `queue approve <id>` / `queue reject <id>` 三个操作；验证：单元测试覆盖 list 空队列、approve 后候选消失、reject 后候选消失三种情况
- [x] 1.2 在 `cli.py` 接入 `queue` 子命令，走标准退出码与 `--help`；验证：`mem.py queue --help` 退出码 0，`mem.py queue list` 对空队列返回空列表
- [x] 1.3 实现超时降级：pending 候选超过配置时限（默认 7 天）自动移至 archive 冷存储，保留完整内容；验证：单元测试模拟过期候选，断言其被移入 archive 且内容未丢
- [x] 1.4 待审队列审计：每次 approve/reject/降级记录操作者、时间、候选标识、动作到审计日志；验证：单测断言审计日志含这四项
- [x] 1.5 批准入库走完整写入链：`queue approve` 调用 `store.record`（含脚本红线 + 分级裁决），而非直接写文件；验证：单测构造含密钥形状的候选，断言 approve 时被红线拦截

## 2. 宿主集成层

- [x] 2.1 新增 `lmr/host/__init__.py`：定义统一接口 `on_session_start()`（注入）与 `on_session_end(transcript)`（蒸馏），以及宿主适配器的抽象基类；验证：接口签名定义清晰，抽象基类可被继承
- [x] 2.2 实现 `lmr/host/workbuddy.py`：WorkBuddy 适配器，把 SessionStart/SessionEnd 事件映射到统一接口，会话结束调 `batch_distill` 后台异步执行；验证：单测用 mock 事件载荷调用适配器，断言正确触发注入与蒸馏
- [x] 2.3 实现 `mem.py setup --host <name>`：生成适配器并写入宿主 hook 配置，幂等（重复安装不产生重复 hook）；验证：对同一宿主连续两次 setup，断言 hook 配置无重复条目
- [x] 2.4 后台异步蒸馏执行器：会话结束触发的蒸馏在独立进程/上下文运行（hook 脚本用 subprocess.Popen 后台执行，失败不阻塞）；验证：hook 脚本后台启动不阻塞

## 3. 备份与恢复

- [x] 3.1 新增 `lmr/backup.py`：本地加密数据目录（`cryptography` Fernet，可选依赖），产出密文；密钥留本地不上云；验证：单测加密后断言密文不可直接读明文、密钥文件未被复制到上传目录
- [x] 3.2 实现 `backup` 命令：加密后产出密文备份（云端同步目标留作扩展点，默认本地备份目录）；未配置加密库时返回明确「未配置」提示而非报错；验证：单测未配置时断言返回提示、退出码非内部错误
- [x] 3.3 实现 `restore` 命令：用本地密钥解密密文并恢复数据目录，密钥缺失时明确报错不产出损坏数据；验证：加密→删除本地→恢复→断言数据目录内容一致

## 4. 校验与收尾

- [x] 4.1 全量测试通过：新增宿主适配、待审队列、超时降级、加密往返四类测试与既有 88 项测试全部通过；验证：`python -m unittest discover -s tests -q` 全绿（110 项）
- [x] 4.2 OpenSpec 校验通过：`openspec validate v1-2-seamless-integration` 与 `openspec validate --all` 均通过；验证：两条命令退出无 ERROR（9 项全过）
- [x] 4.3 更新 README 与配置示例，说明 setup/queue/backup 的用法与备份密钥的安全要求；验证：README 含三个新命令的使用说明与密钥离线备份提示
