# ChemAI 问题总清单（QA + 安全 + 基线）

- **汇总日期**：2026-08-16
- **分支上下文**：父仓库 `phase-7/ship`（验收分支），后端子模块 `chemai-backend` @ `master`
- **来源**：QA 全量验收（`/qa-only`）、安全审计（`/cso`）、质量门禁评测（`run_evals --level all --compare baseline.json`）
- **总计**：18 项（CRITICAL 3 · HIGH 5 · MEDIUM 5 · LOW 3 · 环境/缺口 2）
- **发布门禁**：8 项硬阻断（3 CRITICAL + 5 HIGH），清零后方可进入 `v1.0.0-rc.1`

---

## 一、🔴 CRITICAL（3 项 — 全部阻断发布）

| # | 来源 | 问题 | 位置 | 影响 |
|---|---|---|---|---|
| 1 | 🔐 安全 | JWT 密钥 = 硬编码默认值 `change-me-in-production`（10/10） | `app/config.py:68` | 任何人可伪造任意角色 token → 全站账号接管 |
| 2 | 🧪 QA | 出题工作台 401：token key 不匹配（读 `access_token`，登录写 `chemai_token`） | `frontend/pages/exam-v2.html` | 出题工作台完全不可用 |
| 3 | 🧪 QA | 教师仪表盘「加载失败」：`teacher` 表 0 行，账号无教师档案 | `teacher.html` + 种子数据 | 教师仪表盘无法加载 |

**修复建议**

1. **JWT 密钥**：`openssl rand -hex 32` 生成强密钥写入 `.env`；启动时检测默认值直接 `raise RuntimeError`；轮换所有已签发 token。
2. **token key**：统一前端读写同一 key（推荐统一为 `chemai_token`），或加一个兼容读取层。
3. **教师档案**：`scripts/seed_test_data.py` 补建 Teacher 档案并与账号 `13800000001` 关联。

---

## 二、🟠 HIGH（5 项 — 全部阻断发布）

| # | 来源 | 问题 | 位置 | 影响 |
|---|---|---|---|---|
| 4 | 🔐 安全 | 真实数据 `data/chemai.db.bak` 入库且已推 GitHub（10/10，已泄露） | `data/chemai.db.bak` | 学生/家长 PII + bcrypt 哈希泄露，需清历史 + 轮换凭证 |
| 5 | 🔐 安全 | `/students/batch` 鉴权绕过：无 Layer-2，中间件只查 Bearer 头存在性（9/10） | `app/api/v1/auth.py:101` | 未认证批量建号 |
| 6 | 🔐 安全 | XSS：LaTeX 转义逃逸，`$...$` 块原样入 innerHTML（8/10） | `frontend/js/agent-renderer.js:218` | web_search → 窃取 localStorage token |
| 7 | 🔐 安全 | `/audit/equation` + `/audit/extract` 鉴权绕过（9/10） | `app/api/v1/audit.py:53,83` | 未认证调用审核引擎 |
| 8 | 🧪 QA | demo 数据未种子化：题库/试卷/预警/教师档案全空 | `scripts/seed_test_data.py` | 核心业务无数据可演示 |

**修复建议**

4. **DB 泄露**：`git rm --cached data/chemai.db.bak` → `.gitignore` 追加 → `git filter-repo` 清历史 → force-push → 轮换库内账号密码。
5. **鉴权**：`/students/batch` 加 `Depends(require_permission("student", "create"))`。
6. **XSS**：LaTeX 块内容同样做 HTML 转义，或改为 KaTeX `renderToString`（安全输出）后再入 innerHTML。
7. **鉴权**：`audit.py` 两个端点加 `Depends(get_current_user)`。
8. **种子化**：补全 demo 种子链（教师档案 + 题库 + 试卷 + 预警），对齐登录页文案。

---

## 三、🟡 MEDIUM（5 项 — 发布前应处理）

| # | 来源 | 问题 | 位置 |
|---|---|---|---|
| 9 | 🔐 安全 | CORS 通配符 `allow_origins=["*"]` + `allow_credentials=True` | `app/main.py:46` |
| 10 | 🔐 安全 | 依赖 `>=` 未锁定 + 无 lockfile + pip-audit 未跑（CVE 扫描缺失） | `requirements.txt` |
| 11 | 🧪 QA | 登录页演示账号文案不符（显示 `13800000000`，实际 `...001`/`...002`，密码 `test123`） | `login.html` |
| 12 | 🧪 QA | ocr-v2.html 潜伏 token key bug（同 #2，上传/批改时才触发） | `ocr-v2.html` |
| 13 | 📊 基线 | 12 个陈旧测试：诊断/对话 API 路由已重构，测试未同步（405） | `tests/evals/baseline/test_l2_api_quality.py` |

**修复建议**

9. **CORS**：`allow_origins` 收窄到白名单源；`allow_credentials=True` 时禁止通配符。
10. **依赖**：`pip install pip-tools` 生成 lockfile；`pip install pip-audit && pip-audit` 跑 CVE。
11. **文案**：登录页演示账号改为 `13800000001 / test123`（教师）、`13800000002 / test123`（学生）。
12. **token key**：同 #2，统一为 `chemai_token`。
13. **陈旧测试**：诊断用例对齐 `POST /diagnosis/run-llm/{exam_id}` 等新路由；对话用例对齐 `/chat` 前缀。

---

## 四、🟢 LOW（3 项 — 可延后）

| # | 来源 | 问题 | 位置 |
|---|---|---|---|
| 14 | 🔐 安全 | 登录无限流/无账号锁定（配弱演示密码可爆破） | `app/api/v1/auth.py` |
| 15 | 🔐 安全 | refresh token 无轮换（7 天有效） | `app/core/security.py` |
| 16 | 🧪 QA | 外部字体 404（Google Fonts cormorant woff2 失效） | 仅视觉回退 |

---

## 五、⚪ 环境 / 长期缺口（2 项 — 非代码 bug，但需处理）

| # | 来源 | 问题 | 说明 |
|---|---|---|---|
| 17 | 📊 基线 | L2 评测超时 600s | 根因是残留 **2× uvicorn 占 8000 端口 + 僵尸 pytest 进程**污染，非代码回归（L2 实际 578/578 全绿、188s） |
| 18 | 📊 基线 | L1 覆盖率 37% | 长期缺口（基线 35.9%，本次 +1.1% 无回归），距 95% 目标远 |

**处理**

17. **环境清理**：`kill` 残留 uvicorn（PID 13780、5944）与僵尸 pytest，再复测 L2 即恢复绿色。
18. **覆盖率**：属长期目标，不在本次发布阻断范围，可单独排期补测。

---

## 六、汇总统计

| 严重度 | 数量 | 阻断发布 |
|---|---|---|
| CRITICAL | 3 | ✅ 全部 |
| HIGH | 5 | ✅ 全部 |
| MEDIUM | 5 | 建议发布前 |
| LOW | 3 | 可延后 |
| 环境/缺口 | 2 | 需处理 |
| **合计** | **18** | **8 项硬阻断** |

## 七、根因综合判断

三条线交叉指向 **同一个根因——「演示/种子数据链路断裂」**：

- QA #2（token key）、#3（教师档案缺）、#8（demo 数据空）→ 种子脚本只建了 Account，未建档案与业务数据。
- 安全 #4（`.db.bak` 泄露）→ 种子/测试过程产生的真实库被误提交，与种子链路管理混乱同源。
- 安全 #1/#5/#7（鉴权）→ 分层鉴权契约未在端点层强制（中间件只查头存在性，Layer-2 漏挂）。

## 八、建议修复顺序

| 阶段 | 动作 | 对应 # |
|---|---|---|
| **立即** | 清理残留进程 + JWT 密钥轮换 + git 历史清洗 `.db.bak`（已泄露） | 17, 1, 4 |
| **今天** | 补 3 处鉴权 + 修 XSS + 修 token key | 5, 7, 6, 2, 12 |
| **明天** | 种子化 demo 数据 + 更新陈旧测试 + 收窄 CORS + 锁依赖 | 8, 3, 13, 9, 10 |
| **延后** | 登录限流 + refresh 轮换 + 字体 + 覆盖率 | 14, 15, 16, 18 |

---

> 本清单由 QA 全量验收、安全审计、质量门禁评测三份报告合并去重生成，作为验收/发布前的总待办基线。修复进展应回写本文件对应项的完成状态。
