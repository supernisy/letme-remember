## 目标

修两个缺陷，不改「三类判定」的宏观契约，只细化和修正两处边界：

1. 「无 frontmatter」的条目如何分流
2. 条目切分如何区分 frontmatter 分隔线与 Markdown 水平线

## 判定顺序（修正后）

```
对每条源内容：
  1) 来源类别 ∈ 流水类（log/session/backup/transcript…）→ 明确排除
  2) 正文命中过程标记（推演/本次会话/TODO…）→ 明确排除
  3) 尝试解析 frontmatter：
     a) 解析成功 → 走「形状红线 → 字段/日期 → 类型/取代/凭据」原链路
     b) 解析失败（无 frontmatter）→ 查正文是否含「结论+理由」两节：
        - 含 → 待裁决，标注 needs_human=[missing-frontmatter]
        - 不含 → 明确排除（碎片）
```

## 切分（修正后）

`_split_entries` 判定一个 `---` 行是否为 frontmatter 起始分隔线，需满足：

- 该 `---` 是独立成行（`line.strip() == "---"`），且
- 下一非空行形如 `key: value`（`key` 是 frontmatter 的 12 字段之一），且
- 该块在有限行内有一个闭头 `---`

不满足则视为 Markdown 水平线，不参与切分。整个文件若没有「合法 frontmatter 块」，则**整段作为一条**交给判定层（走 3b 路径）。

判定「下一非空行是否 `key: value`」复用 `frontmatter.FIELDS`（12 字段白名单），避免把正文 `- 列表项` 或 `# 标题` 误判为字段行。

## 边界

- 一个文件里「合法 frontmatter 块」和「水平线」可能混存：只按合法块切分，水平线保留在正文里。
- `review:missing-frontmatter` 与 `exclude:no-conclusion-reason` 是互斥的两条路径：前者是「有结论理由但缺 frontmatter」，后者是「连结论理由都没有」。
- 报告仍只记数量/类别/规则编号/缺失字段，不新增任何原值泄露面。
