# gui-v2

## Purpose

定义 letme-remember 记忆控制台 GUI 的 v2 重构需求：从单文件只读原型升级为 Vite + Vue 3 + Ant Design Vue 的可编译工程，并补足无障碍、响应式、主题一致性。GUI 是记忆仓库的「结论优先观察窗」，当前阶段只读、写/编辑口子预留，供后续开放。

## Requirements

### Requirement: 工程化与技术栈

GUI SHALL 从单文件 HTML 原型重构为 Vite + Vue 3 + TypeScript + Ant Design Vue 的可编译工程，位于 `gui/` 目录，构建产出 `gui/dist/` 静态文件。

#### Scenario: 可编译构建
- **WHEN** 在 `gui/` 目录执行构建命令
- **THEN** 产出 `dist/index.html` 及静态资源
- **AND** 构建产物无需后端即可被静态服务器 serve

#### Scenario: 后端服务静态目录
- **WHEN** 用户通过 `python mem.py gui` 启动
- **THEN** 后端 SHALL serve `gui/dist/` 目录下的静态文件
- **AND** 保留全部 6 个只读 JSON API 不变

### Requirement: 四个视图完整迁移

GUI SHALL 保留四个视图：总览、系统状态、记忆浏览、记忆体检，功能与原原型一致。

#### Scenario: 总览视图
- **WHEN** 用户打开 GUI 首页
- **THEN** 显示一句话健康判定、类型分布、数据状态、来源分布
- **AND** 数据来自 `/api/overview` 接口

#### Scenario: 系统状态视图
- **WHEN** 用户切换到系统状态
- **THEN** 显示向量库、embedding、常驻服务的运行状态
- **AND** 数据来自 `/api/status` 接口

#### Scenario: 记忆浏览视图
- **WHEN** 用户切换到记忆浏览
- **THEN** 支持关键词搜索、类型过滤、被取代过滤、分页
- **AND** 数据来自 `/api/memories` 接口

#### Scenario: 记忆体检视图
- **WHEN** 用户切换到记忆体检
- **THEN** 显示逐条记忆的健康诊断（冲突/过期/缺来源）
- **AND** 数据来自 `/api/health` 接口

### Requirement: 主题一致性

GUI SHALL 使用浅色主题，与用户 IDE 的 light 主题一致，不再使用深色背景。

#### Scenario: 浅色主题
- **WHEN** 页面加载
- **THEN** 背景为浅色、正文为深色文字
- **AND** 语义色（涨红跌绿等）在浅色底上保持可读

### Requirement: 无障碍

GUI SHALL 满足 WCAG 2.2 AA 基线：键盘路径、可见焦点、语义结构、对比度。

#### Scenario: 键盘与焦点
- **WHEN** 用户使用键盘 Tab 导航
- **THEN** 所有交互元素 SHALL 可聚焦且有可见焦点样式
- **AND** 不依赖鼠标即可完成主要操作

#### Scenario: 对比度与动效
- **WHEN** 文本与背景呈现
- **THEN** 正文对比度 SHALL 达到 4.5:1
- **AND** 系统偏好减少动效时 SHALL 降级动画

### Requirement: 响应式布局

GUI SHALL 在窄屏（手机/窄窗）下可用，不因固定宽度溢出。

#### Scenario: 窄屏重排
- **WHEN** 视口宽度缩小到 320px
- **THEN** 布局 SHALL 重排为单列，不产生横向滚动
- **AND** 侧边导航折叠为可触达的入口

### Requirement: 概念字段对齐

GUI SHALL 使用改名后的概念字段：排序乘数用 `boost`，不再使用 `weight`；审批/筛选阀用 `gate_level`/`keep_score`，不再使用 `importance`。

#### Scenario: 排序乘数展示
- **WHEN** 记忆卡片展示排序信息
- **THEN** 显示 `boost` 字段值，不显示 `weight`
- **AND** 不存在 `weight`/`importance` 字段引用

### Requirement: 写操作口子预留

GUI SHALL 明确标注「当前只读」，并为后续写/编辑操作预留口子，不将只读表述为永久状态。

#### Scenario: 只读文案
- **WHEN** 页面呈现只读状态
- **THEN** 文案 SHALL 表述为「当前只读 / 写·编辑待开放」
- **AND** 不出现「永久只读」或「写操作未开放」这类终态表述
