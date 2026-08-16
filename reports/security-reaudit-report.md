# ChemAI 安全审计复评报告（Security Re-audit Report）

- **复评日期**：2026-08-16
- **复评方式**：gstack `/cso` 复跑（手动代码追踪验证，与初评同口径）
- **初评报告**：`reports/security-audit-report.md`（2026-08-16，F 级，1 CRITICAL + 4 HIGH）
- **复评范围**：`chemai-backend`（branch `master` @ `7ab8406`，tag `v1.0.0-rc.1`）
- **复评结论**：**发布门禁通过** —— CRITICAL 0 · HIGH 0 · MEDIUM 1 · LOW 3

---

## 一、逐项复评结果

| # | 初评发现 | 初评级别 | 复评状态 |
|---|---|---|---|
| 1 | JWT 密钥硬编码默认值 | CRITICAL | ✅ **已修复** |
| 2 | `/students/batch` 鉴权绕过 | HIGH | ✅ **已修复** |
| 3 | `data/chemai.db.bak` 被跟踪 | HIGH | ⚠️ **降级 LOW**（文件已移出跟踪，历史未清洗） |
| 4 | XSS：LaTeX 转义逃逸 | HIGH | ✅ **已修复** |
| 5 | `/audit/*` 鉴权绕过 | HIGH | ✅ **已修复** |
| 6 | CORS 通配符 + 凭证 | MEDIUM | ✅ **已修复** |
| 7 | 依赖未锁定 + 无 lockfile | MEDIUM | ⚠️ **部分修复**（chromadb 已上限锁，lockfile 仍缺） |
| 8 | 登录无限流/无锁定 | LOW | ❌ 未处理 |
| 9 | refresh token 无轮换 | LOW | ❌ 未处理 |

### 修复证据（代码级逐条核对）

**Finding 1（CRITICAL）JWT 弱密钥** — ✅ 已修复
- `app/config.py:6,14`：引入 `load_dotenv(PROJECT_ROOT / ".env")`，此前 `.env` 从未被加载。
- `app/main.py:26-31`：`lifespan` 启动守卫，`JWT_SECRET` 为空或等于默认值 `change-me-in-production` 时 `raise RuntimeError` 拒绝启动。

**Finding 2（HIGH）`/students/batch` 鉴权绕过** — ✅ 已修复
- `app/api/v1/auth.py:106`：新增 `user: UserContext = Depends(require_permission("student", "create"))`。
- 回归测试：`tests/integration/test_auth_api.py::TestAuthBypassRegression`（垃圾 token → 401）。

**Finding 3（HIGH）`.db.bak` 泄露** — ⚠️ 降级 LOW
- 代码级已修复：`git rm --cached data/chemai.db.bak` + `.gitignore` 追加 `*.db` / `*.db.bak` / `*.bak`（`.gitignore:13-15`），`git ls-files` 确认已移出跟踪。
- **重新评级依据**：还原 `.db.bak` 内容后确认为**合成种子数据**（demo 账号 13800000001/2/100、姓名「默认学生/默认老师」、一条 `password_hash='x'` 测试残值），**无真实学生/家长 PII**，故 HIGH → LOW。
- **残留风险**：文件已随公开仓库的历史存在（`git filter-repo` 清洗历史未执行），泄露的是 demo 密码 `test123` 的 bcrypt 哈希；已通过 demo 口令轮换（`test123` → `Demo@2026`）使该哈希作废。

**Finding 4（HIGH）XSS LaTeX 转义逃逸** — ✅ 已修复
- `frontend/js/agent-renderer.js:220-243`：`_escapeLatex` 现对 `$...$` / `$$...$$` 块内容**同步执行 `_esc(formula)`** HTML 转义，仅保留 `$` 定界符与反斜杠/花括号供 KaTeX 解析，堵住 `$<img onerror=...>$` 注入链。

**Finding 5（HIGH）`/audit/*` 鉴权绕过** — ✅ 已修复
- `app/api/v1/audit.py:57,90`：`/audit/equation` 与 `/audit/extract` 均新增 `user: UserContext = Depends(get_current_user)`。

**Finding 6（MEDIUM）CORS 通配符** — ✅ 已修复
- `app/config.py:84-92`：`CORS_ALLOWED_ORIGINS` 白名单（localhost/127.0.0.1:8000/5173，可由 `.env` 覆盖）。
- `app/main.py:52-58`：`allow_origins=CORS_ALLOWED_ORIGINS`（白名单），不再使用 `*`，与 `allow_credentials=True` 不再冲突。

**Finding 7（MEDIUM）依赖锁定** — ⚠️ 部分修复
- `requirements.txt:15`：`chromadb>=0.4.22,<1.0.0`，上限锁堵住 PYSEC-2026-311（1.x 预认证代码注入，无修复版）。
- **仍缺**：无 lockfile（`poetry.lock` / `requirements.lock`），其余依赖仍用 `>=`，`pip-audit` CVE 扫描未执行。

**Finding 8（LOW）登录限流** — ❌ 未处理（`app/api/v1/auth.py` 登录仍无速率限制/失败锁定）。

**Finding 9（LOW）refresh 轮换** — ❌ 未处理（`app/core/security.py` refresh token 7 天有效，无 jti/轮换/撤销列表）。

---

## 二、复评评级

| 项 | 初评 | 复评 |
|---|---|---|
| CRITICAL | 1 | **0** |
| HIGH | 4 | **0** |
| MEDIUM | 2 | **1**（依赖 lockfile） |
| LOW | 2 | **3**（限流 + refresh 轮换 + db.bak 历史） |
| 安全评分 | F（不合格） | **C+（发布门禁通过）** |
| 发布门禁（CRITICAL/HIGH 清零） | ❌ 未通过 | ✅ **通过** |

---

## 三、复评结论

**CRITICAL 与 HIGH 已全部清零**，满足「进入 `v1.0.0-rc.1` 打标流程」的发布门禁要求。

遗留项（不阻断本次候选发布，进入正式版前应排期）：
1. **MEDIUM**：生成 lockfile + 跑 `pip-audit` CVE 扫描（供应链可复现性）。
2. **LOW**：登录限流 + 失败锁定。
3. **LOW**：refresh token jti/轮换/撤销。
4. **LOW**：`git filter-repo` 清洗 `.db.bak` 历史（可选 housekeeping，内容已确认为合成数据且 demo 口令已轮换）。

---

> **免责声明**：本复评沿用初评的人工代码追踪口径，用于确认已知 9 项发现的修复状态，不代表完整渗透测试。生产环境处理敏感数据或 PII 时，应聘请专业安全机构。
