## ADDED Requirements

### Requirement: 预处理操作

`import-preprocess` SHALL 扫描指定源（文件或目录），逐条产出候选卡片（写暂存区）与脱敏报告；操作 SHALL 只读源文件、SHALL NOT 落库。

#### Scenario: 扫描源产出卡片与报告

- **WHEN** 执行 `import-preprocess --source <dir|file> [--source-category <cat>] [--batch <id>]`
- **THEN** 系统 SHALL 只读扫描源，产出候选卡片（写暂存区）与脱敏报告，SHALL NOT 写真相源

#### Scenario: 空源正常返回

- **WHEN** 源目录无文件或暂存区为空
- **THEN** 系统 SHALL 正常返回空结果，退出码 0，SHALL NOT 报错
