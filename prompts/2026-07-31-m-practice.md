# 学生端练习做题页（m/practice.html）提示词

将以下内容完整复制并粘贴到你使用的 AI 工具中。

---

为学生端创建一个练习做题页面的单文件 HTML（pages/m/practice.html），包含两个 JS 切换的视图状态。所有数据为静态数据。使用内联 CSS，原生 JavaScript 实现视图切换和选项交互。页面面向移动端 390px 视口。

## 全局
- 移动端容器：`max-width: 390px`，水平居中，100vh，`overflow: hidden`，flex-column。
- 外层 body 背景 `#e8e8e8`，容器内背景 `#faf8f5`。
- 主色：`#002045`（牛津蓝），正文字体：`'IBM Plex Sans', sans-serif`。

## 视图 1 — 任务列表视图（默认显示 `.view.active`）

### 顶部标题栏（56px，牛津蓝背景，白色文字）
- 左侧返回箭头（`<` SVG 图标）+ 标题"练习"（16px，font-weight 600）+ 右侧进度"3/10"（13px，opacity 0.85）

### 两个 Tab 标签（44px，白色背景，底部 1px 灰色分割线 #eee）
- Flex 等宽两列，每个 tab 14px，font-weight 500。
- "待完成（7）"默认激活：牛津蓝文字 + 底部 2px 蓝色下划线
- "已完成（3）"：灰色 `#888` 文字，透明下划线

### 3 张练习任务卡片
每张卡片：白色背景，8px 圆角，1px 边框 `#d4d0c8`，16px 内边距，flex-column，gap 10px，margin-bottom 12px。

**卡片 1** — 氧化还原反应 — 基础练习
- 标题：16px bold
- 标签行：蓝色 chip "选择题"（12px，`#dbeafe` 背景，`#2563eb` 文字，12px 圆角）+ "中等难度"
- 进度条：灰色底 `#e0e0e0`（6px 高，3px 圆角），牛津蓝填充 60%，右侧文字"3/5"
- "继续练习"按钮：牛津蓝 `#002045`，全宽，40px 高，8px 圆角，14px 白色文字，font-weight 500

**卡片 2** — 化学键与分子结构
- 标签："选择题"+"简单难度"
- 进度条：100% 填充，文字"5/5"
- 按钮：深青色 `#13696a`，文字"查看结果"

**卡片 3** — 离子反应方程式
- 标签："填空题"+"中等难度"
- 进度条：25% 填充，文字"1/4"
- 按钮：牛津蓝，文字"继续练习"

## 视图 2 — 答题界面视图（隐藏 `.view:not(.active)`）

### 顶部标题栏（56px，牛津蓝背景）
- 返回箭头 + 标题（动态更新为任务名称）+ 倒计时"⏱ 25:30"（13px）+ 题号"3/10"

### 题目内容区（padding 20px 16px，flex-column，gap 20px）
- 题干："在氧化还原反应 2Fe + 3Cl₂ → 2FeCl₃ 中，氧化剂是？"（16px，line-height 1.7，font-weight 500）

### 4 个选项按钮
每个（全宽，56px 高，白色背景 `1px solid #ddd`，8px 圆角，padding 0 16px，flex 横向，gap 14px，15px 字号）：
- 左侧圆形字母标（32px 圆，灰色 `#f0f0f0` 背景，加粗 14px）
- 右侧选项文字

选项：
- A. Fe
- B. Cl₂
- C. FeCl₃
- D. 以上都是

正确答案为 B。

**点击交互**（JS `selectOption(btn, isCorrect)`）：
- 点击后该按钮变绿（正确：背景 `#e0f2f1`，边框 `#2c6e49`，圆形字母标变白底绿字）或变红（错误：背景 `#ffdad6`，边框 `#c0392b`，圆形字母标变白底红字）
- 同时始终高亮正确答案 B 为绿色
- `answered` 标志位防止重复点击

### 底部导航区（padding 12px 16px，白色背景，上边框 #eee，flex justify-content space-between，gap 12px）
- "← 上一题"：白色背景灰色边框，44px 高，8px 圆角
- "下一题 →"：牛津蓝背景白色文字，44px 高，8px 圆角

## 底部 4Tab 导航栏（56px，白色背景）
- "练习"为激活态（牛津蓝文字和图标色，其余灰色 `#888`）
- 4 个 tab：AI助教 / 练习(激活) / 错题 / 我的
- 每个 tab：20×20px SVG 图标 + 10px 标签文字

## JavaScript
- `openQuiz(title)`：隐藏视图 1，显示视图 2，更新标题，重置选项状态
- `backToList()`：返回视图 1
- `selectOption(btn, isCorrect)`：标记点击选项（正确/错误），同时高亮正确答案 B，设置 `answered = true` 防止重复点击
- `resetOptions()`：清除所有选项的 `correct`/`wrong` 类，重置 `answered = false`

## 设计约束
- 底部 4Tab 导航栏，"练习"为激活态
- 选项按钮点击后显示正确/错误颜色
- 视图通过切换 `.view.active` 类实现显示/隐藏（`display: none` vs `display: flex`）

## 输出
返回完整的 `pages/m/practice.html` 文件，放在单个代码块中。可直接在浏览器中打开，无需构建步骤。所有内容为静态中文内容。
