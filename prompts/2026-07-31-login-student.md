# 学生端 AI 助教对话页（m/index.html）提示词

将以下内容完整复制并粘贴到你使用的 AI 工具中。

---

为学生端 ChemAI 助教创建一个移动端对话页面的单文件 HTML（m/index.html）。所有数据为静态数据，无 API 调用，无 JavaScript 框架。使用内联 CSS（放在 `<style>` 标签内），原生 JavaScript 仅用于侧边栏抽屉的打开/关闭交互。页面面向移动端视口。

## 全局
- 移动端容器：`max-width: 390px`，`width: 100%`，`height: 100vh`，水平居中（`margin: 0 auto`），带阴影 `0 0 40px rgba(0,0,0,0.15)` 模拟手机效果。
- 外层 body 背景 `#e8e8e8`，容器内部背景 `#faf8f5`（暖纸色）。
- 使用 `<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">`。
- 主色：`#002045`（牛津蓝）
- 强调色：`#13696a`（深青）
- 正文字体：`'IBM Plex Sans', sans-serif`（Google Fonts）
- 标题字体：`'Cormorant Garamond', serif`（Google Fonts）

## 组件（从上到下）

### 1. 顶部标题栏（height 56px，牛津蓝 `#002045` 背景，白色文字，padding 0 12px）
- Flex 横向布局，`align-items: center`，`justify-content: space-between`：
  - **左侧**：汉堡菜单按钮（3 条白色横线，每条 2px 高，5px 间距，总宽 24px，用 3 个 `<span>` 实现）。
  - **居中**：标题"ChemAI 助教"（16px，加粗，非 Cormorant 用 IBM Plex Sans），使用 `position: absolute; left: 50%; transform: translateX(-50%)` 居中。
  - **右侧**：新建对话按钮（"+" 号 SVG 图标，28×28px，白色）。

### 2. 侧边栏抽屉（width 280px，深色背景 `#1a1a2e`，z-index 100，transition 0.3s）
- 默认 `position: fixed`，`left: -280px`（隐藏），展开时添加 `.open` 类 → `left: 0`。`transition: left 0.3s ease`。
- 全高度，flex-column 布局，内部可滚动。

  **学生信息区**（padding 20px，flex-column，居中对齐，gap 10px）：
  - 48px 圆形灰色头像占位（`#555` 背景），内嵌人物 SVG 图标（灰色 `#ccc`）
  - 姓名"张三"（白色，16px，font-weight 600）
  - 班级"高一(3)班"（灰色 `#999`，13px）

  **分割线**：`1px solid rgba(255,255,255,0.1)`

  **历史对话列表**（flex-grow，overflow-y auto，5 条）：
  每条（padding 12px 20px，cursor pointer，hover 背景 `rgba(255,255,255,0.05)`）：
  - 标题（白色 90% 不透明度，14px，font-weight 500，单行省略号）
  - 时间戳（白色 40% 不透明度，12px）

  5 条示例数据：
  | 标题 | 时间 |
  |------|------|
  | 氧化还原反应讲解 | 今天 14:30 |
  | 化学方程式配平练习 | 昨天 16:20 |
  | 离子反应知识点 | 7月29日 |
  | 元素周期表记忆技巧 | 7月28日 |
  | 化学键与分子结构 | 7月25日 |

  **底部"退出登录"**（红色 `#c0392b` 文字，14px，font-weight 500，padding 20px，上分割线）。

- **遮罩层**（黑色 `rgba(0,0,0,0.4)`，`position: fixed`，`inset: 0`，`z-index: 99`）：默认 `opacity: 0; pointer-events: none`，展开时添加 `.show` 类 → `opacity: 1; pointer-events: auto`。`transition: opacity 0.3s ease`。点击调用 `closeDrawer()`。

### 3. 对话区域
- 高度：`calc(100vh - 56px - 56px - 70px)`（视口高度减去顶部标题栏、底部标签栏和输入区）。
- 可滚动（`overflow-y: auto`），内边距 `16px 12px`，底部额外留白 140px 以容纳输入区和标签栏。
- 背景 `#faf8f5`。
- Flex column 布局，gap 12px 间距。

  消息气泡格式（每条消息包裹在 `.bubble-row` 中，内含 `.bubble-wrapper` > `.bubble` + `.bubble-time`）：

  **AI 消息（3 条，左对齐）**：
  - 气泡：背景 `#e0f2f1`（浅青），`border-radius: 12px`，左下角 4px，`max-width: 80%`，padding 12px，14px 字号，行高 1.6。
  - 时间戳：11px，灰色 `#888`，左对齐。

  AI 消息 1："你好！我是 ChemAI 助教，可以帮你解答化学问题、配平方程式、讲解知识点。有什么需要帮助的吗？"（14:28）

  AI 消息 2："氧化还原反应的实质是**电子的转移**（得失或偏移）。在反应中：• **失去电子**的物质被**氧化**，是**还原剂** • **得到电子**的物质被**还原**，是**氧化剂**。例如：Zn + Cu²⁺ → Zn²⁺ + Cu，Zn 失去电子被氧化，Cu²⁺ 得到电子被还原。"（14:29）

  AI 消息 3："好的！这里有几道关于氧化还原反应的选择题：**1.** 下列反应中，属于氧化还原反应的是？A. CaO + H₂O → Ca(OH)₂ B. 2Na + Cl₂ → 2NaCl C. NaOH + HCl → NaCl + H₂O D. CaCO₃ → CaO + CO₂↑ **2.** 在反应 Fe + CuSO₄ → FeSO₄ + Cu 中，被氧化的物质是？A. CuSO₄ B. Fe C. Cu D. FeSO₄ 想做更多练习可以说'再来几道'哦！"（14:30）

  **用户消息（2 条，右对齐）**：
  - 气泡：白色背景，`1px solid #ddd` 边框，`border-radius: 12px`，右下角 4px，`max-width: 80%`，padding 12px。
  - 时间戳：右对齐。
  - 右对齐通过 `margin-left: auto` 或 `.bubble-row.user { justify-content: flex-end }` 实现。

  用户消息 1："帮我讲解一下氧化还原反应"（14:29）
  用户消息 2："能给我出几道练习题吗？"（14:30）

### 4. 快捷芯片行
- 水平可滚动容器（`overflow-x: auto`，`white-space: nowrap`，`-webkit-overflow-scrolling: touch`），隐藏滚动条。
- 白色背景，上边框 `1px solid #eee`，padding 12px，flex 排列，gap 8px。
- 5 个芯片（`flex-shrink: 0`）：白色背景，`1px solid #ddd` 边框，`border-radius: 16px`，`padding: 8px 16px`，13px 字号。
- 按压态（`:active`）：背景 `#e0f2f1`，边框色深青。
- 文本："帮我讲解这个知识点""配平这个方程式""做几道练习题""查看我的错题""总结今天学习"

### 5. 底部输入区（height 70px，白色背景，flex 布局）
- 上边框 `1px solid #eee`，padding `8px 12px`，`align-items: center`，gap 8px。
- **附件按钮**（36×36px，透明背景，灰色，📎 字符或回形针 SVG）
- **输入框**（`flex-grow: 1`，`height: 40px`，`border-radius: 20px`，背景 `#f0f0f0`，`border: none`，`padding: 0 16px`，14px 字号，placeholder "输入你的问题…" 灰色 `#aaa`）
- **发送按钮**（40×40px 圆形，牛津蓝背景，白色，内嵌纸飞机 SVG 图标（18×18px），`border-radius: 50%`，按压态稍深 `#003366`）

### 6. 底部 4Tab 导航栏（height 56px，白色背景，flex 等宽排列）
- 上边框 `1px solid #eee`。
- 每个标签项（`flex: 1`，flex-column 垂直居中，gap 4px，`cursor: pointer`）：
  - 图标占位（20×20px，SVG 图标 18×18px）
  - 文字标签（10px）

| 标签 | 激活态 | 图标说明 |
|------|--------|----------|
| AI助教 | **激活**（牛津蓝文字和图标色） | 时钟/对话圆形图标 |
| 练习 | 未激活（灰色 `#888`） | 文档/列表矩形图标 |
| 错题 | 未激活（灰色 `#888`） | 感叹号圆形图标 |
| 我的 | 未激活（灰色 `#888`） | 人物圆形图标 |

激活态（`.tab-item.active`）：图标和文字颜色为牛津蓝 `#002045`。

## JavaScript
- `toggleDrawer()`：检查 `#drawer` 是否有 `open` 类，有则关闭（移除 `open` 类 + 移除遮罩 `show` 类），无则打开（添加两个类）。
- `closeDrawer()`：移除抽屉 `open` 类和遮罩 `show` 类。由遮罩层 `onclick` 触发。
- 使用原生 JavaScript，无框架。

## 设计润色
- 可交互元素使用 `transition` 平滑过渡。
- 全局使用 `box-sizing: border-box`。
- 手机外层容器添加明显阴影模拟真机效果。
- 侧边栏遮罩和抽屉动画流畅自然（0.3s ease）。

## 输出
返回完整的 `m/index.html` 文件，放在单个代码块中。可直接在浏览器中打开，无需构建步骤，除 Google Fonts CSS 外无外部依赖。所有内容为静态中文内容。
