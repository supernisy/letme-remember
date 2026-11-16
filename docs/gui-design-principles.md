# GUI 设计理念（letme-remember 记忆控制台）

> 读者：AI（接手 GUI 开发时快速对齐，避免「从头查」）
> 更新：2026-11-16（GUI v2 重构：Vite + Vue3 + Ant Design Vue，OpenSpec 完整模式验收）

## 一句话定位

GUI 是「**结论优先的观察窗**」——不是堆数据的仪表盘，而是先告诉你「系统正不正常、有没有要你处理的事」，再让你下钻看细节。这跟整个项目「判断权归用户、AI 只备稿」的哲学一致。

## 五条核心设计理念

### 1. 只读是「当前阶段」，不是永久原则

- **现状**：所有 API 只查询，绝不写 store / index / audit。
- **方向**：写/编辑（增删改、取代、归档）是**明确要做的后续功能**，路由与口子已预留。
- **落地约定**：GUI 所有「只读」文案必须写成「当前只读 / 写·编辑待开放」，**禁止**写成「永久只读」或「写操作未开放」这类把现状当终态的语气。

### 2. 后端零新依赖；界面层走标准工程化

- **后端**（`lmr/gui_server.py`）：只用标准库 `http.server` + `json` + `sqlite3` + `urllib`，不引 Flask/FastAPI。这条不变。
- **界面层**（`gui/`）：v2 起改为 **Vite + Vue 3 + TypeScript + Ant Design Vue** 工程（用户拍板 C 档全面重构）。构建产物 `gui/dist/` 由后端静态 serve。`dist/`、`node_modules/`、`*.tsbuildinfo` 不入库（可重建，与「索引可重建不入库」哲学一致）。
- 首次使用：`cd gui && pnpm install && pnpm build`，再 `python mem.py gui`。

### 3. 复用 lmr 内核，服务无状态、可重建

GUI 是 `lmr` 的一层薄壳：`config.Paths` 定位数据、`frontmatter` 解析、`index.Index` 读索引。全部数据来自 SQLite + store 文件，服务本身不存任何状态，重启即重建。界面层同理：6 个 JSON API 是前后端唯一契约，界面重构不改 API。

### 4. 结论优先的信息架构（最有辨识度的一条）

页面层级刻意「先判断、后数据」：

```
顶部一句话健康判定（verdict：绿/黄/红）
  ↓
系统运行状态（serve/向量库/embedding 红绿灯）
  ↓
需要你处理（分级待办 P0/P1/P2/信息）
  ↓
记忆资产概况（类型分布环形图 + 数据状态）
  ↓
逐条明细（记忆浏览 / 记忆体检）
```

### 5. 浅色主题对齐 IDE + 语义令牌

- v2 起 GUI 用**浅色主题**（旧版深色 `#0f1115` 与 IDE light 主题割裂，已废弃）。
- 颜色不硬编码，走 `gui/src/styles/tokens.css` 语义令牌：状态色（红/绿/琥珀）、文字/表面色阶。
- **圆点只表达真状态**（总览健康判定、系统启停）。记忆类型不用彩色圆点——圆点容易被误读成「状态有问题」，且多类型多色造成混淆；类型统一用中文文字标签 `.ttag`（语义记忆/情景记忆/程序记忆），浏览与体检两视图标签样式和位置一致。类型三色令牌在 tokens.css 保留作概念锚点，但界面不引用。
- 无障碍基线：可见 `:focus`、`aria` 语义（tab 导航用 `role=tab` + `aria-selected`）、`prefers-reduced-motion` 降级、响应式断点。

## 验收体系（OpenSpec 完整模式，用户拍板必走）

GUI 的需求与验收走用户自己的工具链，**不接受「AI 说做好了」式验收**：

```
① openspec/specs/gui-v2/spec.md      需求（WHEN/THEN 锁死，openspec validate 过）
② acceptance/gui-v2/contract.yaml    specgate bridge 出的验收契约（12 条，lint 退出码 0）
③ gui/ 实现 + pnpm build             构建产出 dist/
④ verify-suite 采集比对               ax-collect-pw.mjs 采语义指纹，对契约逐条验
```

- specgate 本体：`~/.workbuddy/specgate/`（`node src/cli.js bridge|lint`）；项目根有 `constraints.yaml`（约束源，lint 用）。
- verify-suite：`~/WorkBuddy/2026-10-18-19-39-24/verify-suite/`（最新副本）；其 `ui-testing-workflow` skill 已装到项目 `.workbuddy/skills/`。
- 改 GUI 需求 → 先改 spec.md → 重跑 bridge/lint → 再改实现。**禁止**绕过契约直接改界面。
- 已知坑：`bridge --keep-verify` 会清空手工补的 `invariants`，正确顺序是 bridge → 手工补 invariants → lint。

## 概念对齐红线（改名后必须遵守）

字段命名已统一（见 `docs/concept-glossary.md`），GUI 前后端必须一致：

| 落库字段 | 语义 | GUI 里的正确叫法 |
|---|---|---|
| `boost` | 入库后·排序乘数（0~10） | boost（**不是** weight） |
| `gate_level` / `keep_score` | 入库前·审批阀/筛选阀（内部字段，不落库） | 不直接出现在 GUI 数据，只在「待补口子」文案里提及 |
| `superseded_by` | 被取代（降权不排除，方案 A） | 「已被取代」 |

**坑**：后端 overview 返回 `has_boost`（旧 `has_importance` 是死变量，已修）；`font-weight`（CSS 字体粗细）是合法词，改名时**不要**误伤。

## 已实现 vs 待做（写/编辑方向）

已实现（只读）：overview / status / health / memories / memory/{id} / audit 六个 GET 接口 + 四个视图（总览/系统状态/记忆浏览/记忆体检），v2 界面层构建、静态 serve、浅色主题、语义令牌均已落地。

待做（写/编辑，口子已预留）：
- 记忆增删改、手动取代/归档
- 自动蒸馏、自动写入开关
- 向量库开关
- Honeypot 观测层（方向规划中）
- 方向②「跨平台仲裁」的三结局裁决、来源信任分级的可视化

## 文件边界

- 后端：`lmr/gui_server.py`（路由 + 数据读取 + `gui/dist/` 静态 serve，全部只读函数）
- 界面工程：`gui/`（Vite + Vue3 + TS + AntD；`src/views/` 四视图、`src/api/` 接口封装、`src/styles/` 语义令牌）
- 旧版单文件界面：`gui-demo/index.html`（仅作对照参考，新界面验收通过后删除）
- 需求/契约：`openspec/specs/gui-v2/spec.md`、`acceptance/gui-v2/contract.yaml`
- 启动：`python mem.py gui [--port 8787]`，打开 `http://127.0.0.1:8787`
