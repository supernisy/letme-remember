## 1. 判定语义修正（无 frontmatter → review）

- [x] 1.1 `_verdict_for`：`frontmatter.parse` 失败时，改查正文 `body_sections` 是否含「结论」「理由」两节；含 → `review:missing-frontmatter`（needs_human 加 `missing-frontmatter`），不含 → `exclude:no-frontmatter`；验证：无 frontmatter 有结论理由 → review，无 frontmatter 无结构 → exclude
- [x] 1.2 判定顺序保持「来源类别/过程标记排除」在最前，不受影响；验证：`log` 类别 + 有结论理由 仍判 exclude（来源类别优先）

## 2. 条目切分修正（水平线不误切）

- [x] 2.1 `_split_entries`：仅当 `---` 后下一非空行是合法字段行（key 属 `frontmatter.FIELDS`）才视为 frontmatter 起始；否则当水平线忽略，整段作一条；验证：含多个 `---` 水平线的普通 Markdown 文件 → total_entries == 1
- [x] 2.2 混合场景：合法 frontmatter 块之间夹杂水平线时，只按合法块切分，水平线保留正文；验证：多条标准 frontmatter 记忆（含正文水平线）仍正确切成 N 条

## 3. 测试与校验

- [x] 3.1 补单元测试：无 frontmatter 有结论理由 → review；无 frontmatter 无结构 → exclude；水平线普通 Markdown → 1 条；多 frontmatter 块 + 水平线 → 正确切分
- [x] 3.2 全量回归：既有 157+20 子测试全过，新增用例全绿（现 161 + 20 子测试）
- [x] 3.3 `openspec validate 2026-11-12-import-preprocess-fixes` 无 ERROR
- [x] 3.4 用真实源复验：规则文件（无 frontmatter 但有结论理由）→ review；日志流水 → exclude；有 frontmatter 规则 → ok
