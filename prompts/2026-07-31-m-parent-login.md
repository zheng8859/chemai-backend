# 家长端登录页（m/parent-login.html）提示词

将以下内容完整复制并粘贴到你使用的 AI 工具中。

---

为 ChemAI 家长端创建登录页面的单文件 HTML（pages/m/parent-login.html）。静态数据，使用内联 CSS。页面面向移动端 390px 视口。

## 全局
- 容器：`max-width: 390px`，`min-height: 844px`，`margin: 0 auto`，flex-column `justify-content: center`。
- 背景 `#faf8f5`（暖纸色），字体 `'IBM Plex Sans', sans-serif`。

## 组件

### 1. Logo 区（居中，margin-bottom 32px）
- 标题"ChemAI 智辅化学"（Cormorant Garamond，22px，bold，牛津蓝 `#002045`）
- 内联"家长端"标签（深青 `#13696a` 背景，白色 12px 文字，`border-radius: 9999px`，`padding: 2px 10px`，`margin-left: 8px`）
- 说明文字："使用手机号和绑定码登录，查看孩子的学习情况"（14px，灰色 `#888`，margin-top 12px）

### 2. 表单区（width 320px，margin: 0 auto）
- **手机号输入框**（48px 高，8px 圆角，`1px solid #ddd`，`padding: 0 14px 0 40px`）：左侧手机 SVG 图标，placeholder "请输入手机号"，`inputmode="tel"`
- **绑定码输入框**（同上，margin-top 12px）：左侧锁 SVG 图标，placeholder "请输入6位绑定码"，`maxlength="6"`，`inputmode="numeric"`，`pattern="[0-9]{6}"`
- 绑定码下方提示："绑定码可在孩子App的'我的'页面找到"（12px，`#aaa`，margin-top 4px）
- **登录按钮**（全宽 48px，牛津蓝背景，白色 16px 文字，8px 圆角，margin-top 24px）

**输入框聚焦态**：`border-color: #002045`，`box-shadow: 0 0 0 3px rgba(0,32,69,.1)`

### 3. 绑定码说明卡片（浅蓝背景 `#e3f2fd`，8px 圆角，padding 12px，margin-top 20px，width 320px，居中）
- 标题"什么是绑定码？"（14px，font-weight 600，深蓝 `#1a5276`）
- 说明："绑定码是6位数字，用于关联您和孩子的账号。请让孩子在他的ChemAI App中查看。"（13px，`#555`，margin-top 4px，line-height 1.5）

### 4. 底部文字（居中，margin-top 32px）
- "如何获取绑定码？"（深青 `#13696a`，14px，`text-decoration: underline`）
- 版本号"v0.1.0"（12px，浅灰 `#bbb`，margin-top 12px）

## 输出
返回完整的 `pages/m/parent-login.html` 文件，可直接在浏览器中打开。
