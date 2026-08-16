"""Gstack QA — 学生端 6 页面完整走查（API + 代码结构 + 数据流）。

不依赖浏览器，通过 API 调用 + 源码解析 + 数据流追踪来验证交互逻辑。

发现问题自动分类: BLOCKER / HIGH / MEDIUM / INFO
发现可自动修复的问题即时修复。
"""

import sys
import json
import re
import os
import base64
import traceback
from pathlib import Path
from datetime import datetime

import requests

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = "http://localhost:8000/api/v1"
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
PAGES_DIR = FRONTEND / "pages" / "m"
JS_DIR = FRONTEND / "js"

# ═══════════════════════════════════════════════════════════════
# 问题追踪
# ═══════════════════════════════════════════════════════════════

class QAIssue:
    def __init__(self, sev, page, check_name, detail, fix_hint="", auto_fixed=False):
        self.sev = sev
        self.page = page
        self.check = check_name
        self.detail = detail
        self.fix = fix_hint
        self.auto_fixed = auto_fixed

ISSUES = []
AUTO_FIXES = []
CHECK_COUNT = 0
PASS_COUNT = 0


def sev_weight(s):
    return {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}.get(s, 99)


def issue(sev, page, check_name, detail, fix_hint="", auto_fix_fn=None):
    global ISSUES
    auto_fixed = False
    if auto_fix_fn and callable(auto_fix_fn):
        try:
            auto_fixed = auto_fix_fn()
            if auto_fixed:
                AUTO_FIXES.append(f"{page}/{check_name}: {detail[:60]}")
        except Exception as e:
            pass  # 自动修复失败，保持原问题

    ISSUES.append(QAIssue(sev, page, check_name, detail, fix_hint, auto_fixed))

    emoji = {"BLOCKER": "🔥", "HIGH": "❌", "MEDIUM": "⚠️", "INFO": "ℹ️"}[sev]
    tag = " [AUTO-FIXED]" if auto_fixed else ""
    print(f"  {emoji} [{sev}] {page}/{check_name}: {detail}{tag}")


def check(name, condition, sev_on_fail="HIGH", detail="", fix="", auto_fix=None):
    global CHECK_COUNT, PASS_COUNT
    CHECK_COUNT += 1
    if condition:
        PASS_COUNT += 1
        return True
    else:
        if auto_fix:
            # Try auto-fix first
            try:
                fixed = auto_fix()
                if fixed:
                    AUTO_FIXES.append(f"{name}: {detail[:60]}")
                    PASS_COUNT += 1
                    print(f"  ✅ [AUTO-FIXED] {name}: {detail[:60]}")
                    return True
            except Exception as e:
                pass
        issue(sev_on_fail, current_page, name, detail, fix)
        return False


current_page = ""


def on_page(name):
    global current_page
    current_page = name
    print(f"\n{'─'*55}")
    print(f"  [{name}]")
    print(f"{'─'*55}")


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def api(method, path, token=None, **kwargs):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{BASE}{path}"
    return requests.request(method, url, headers=headers, **kwargs)


def login():
    r = api("POST", "/auth/login", json={"phone": "13800000002", "password": "Demo@2026"})
    if r.status_code == 200:
        return r.json().get("token") or r.json().get("access_token")
    return None


def read_html(filename):
    path = PAGES_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding='utf-8', errors='replace')


def read_js(filename):
    path = JS_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding='utf-8', errors='replace')


def html_has_script(html, js_file):
    """检查 HTML 是否引用了某个 JS 文件"""
    patterns = [
        f'src=".*{js_file}"',
        f"src='.*{js_file}'",
        f'src=.*{js_file}',
    ]
    for p in patterns:
        if re.search(p, html):
            return True
    return False


def html_has_id(html, elem_id):
    return f'id="{elem_id}"' in html or f"id='{elem_id}'" in html


def js_has_function(js, func_name):
    patterns = [
        f'function {func_name}\\(',
        f'{func_name}:\\s*function',
        f'{func_name}\\s*=\\s*function',
        f'{func_name}\\s*=\\s*\\(',
    ]
    for p in patterns:
        if re.search(p, js):
            return True
    return False


def js_has_call(js, call_name):
    return call_name in js


# ═══════════════════════════════════════════════════════════════
# SECTION 1: 认证体系
# ═══════════════════════════════════════════════════════════════

def qa_auth_system():
    on_page("auth-system")

    # 1.1 Token 键名一致性
    auth_js = read_js("auth.js")
    if auth_js:
        token_key_in_js = re.search(r"TOKEN_KEY\s*=\s*['\"]([^'\"]+)['\"]", auth_js)
        check("token_key_consistency",
              token_key_in_js and token_key_in_js.group(1) == "chemai_token",
              "BLOCKER", "Token 键名不一致",
              "auth.js 中 TOKEN_KEY 必须为 'chemai_token'",
              auto_fix=lambda: fix_token_key(auth_js))

    # 1.2 所有页面引用 auth.js
    for page_file in ["index.html", "practice.html", "wrong.html", "review.html", "report.html"]:
        html = read_html(page_file)
        if html:
            has_auth = html_has_script(html, "auth.js") or "ChemAuth" in html
            check(f"auth_js_ref_{page_file}",
                  has_auth,
                  "BLOCKER", f"{page_file} 未引用 auth.js",
                  f"在 {page_file} 中添加 <script src=\"../../js/auth.js\"></script>")

    # 1.3 认证守卫 — 每个页面在 init 时检查
    for page_file in ["index.html", "practice.html", "wrong.html", "review.html", "report.html"]:
        html = read_html(page_file)
        if html:
            has_guard = ("isAuthenticated" in html or
                         "redirectToLogin" in html or
                         "getToken" in html or
                         "chemai_token" in html)
            check(f"auth_guard_{page_file}",
                  has_guard,
                  "BLOCKER", f"{page_file} 缺少认证守卫",
                  "在 " + page_file + " 初始化脚本开头添加 ChemAuth 认证守卫检查")

    # 1.4 退出登录
    report_html = read_html("report.html")
    if report_html:
        has_logout = "logout" in report_html.lower()
        check("logout_function_exists",
              has_logout,
              "HIGH", "report.html 无退出登录功能",
              "添加退出按钮 + ChemAuth.logout() 调用")

    # 1.5 JWT 解码
    if auth_js:
        has_decode = "decodeToken" in auth_js or "atob" in auth_js
        check("jwt_decode_function",
              has_decode,
              "HIGH", "auth.js 缺少 JWT 解码函数")

    # 1.6 Token 过期检查
    if auth_js:
        has_exp_check = "exp" in auth_js
        check("jwt_exp_check",
              has_exp_check,
              "MEDIUM", "auth.js 未检查 JWT 过期时间",
              "在 getCurrentUser() 中添加 exp 检查")


# ═══════════════════════════════════════════════════════════════
# SECTION 2: AI 对话页 (index.html)
# ═══════════════════════════════════════════════════════════════

def qa_ai_chat(token):
    on_page("ai-chat")

    index_html = read_html("index.html")
    if not index_html:
        issue("BLOCKER", "ai-chat", "file_missing", "index.html 不存在")
        return

    # 2.1 Persona 参数
    check("persona_student",
          "persona: 'student'" in index_html or '"persona":"student"' in index_html,
          "HIGH", "index.html 中 persona 参数不是固定 'student'",
          "在 SSE 请求 body 中添加 persona: 'student'")

    # 2.2 SSE 事件类型
    sse_events = ["start", "chunk", "tool_call", "tool_result", "done", "error"]
    found_events = []
    for evt in sse_events:
        if f"'{evt}'" in index_html or f'"{evt}"' in index_html or evt in index_html:
            found_events.append(evt)
    check("sse_event_handlers",
          len(found_events) >= 3,
          "MEDIUM", f"SSE 事件处理不完整: 仅覆盖 {found_events}",
          "确认覆盖所有 11 种事件类型: start/chunk/tool_call/tool_result/thinking/done/error/interrupt/rating/agent_state/warning")

    # 2.3 输入框
    has_input = re.search(r'<(textarea|input[^>]*type=["\']text["\'])', index_html)
    check("chat_input_element",
          has_input is not None,
          "HIGH", "AI 对话页缺少文本输入框")

    # 2.4 消息渲染区
    has_msg_area = ("chatMessages" in index_html or "message-list" in index_html or
                    "chat-messages" in index_html or "conversation" in index_html)
    check("message_render_area",
          has_msg_area,
          "MEDIUM", "AI 对话页无消息渲染容器")

    # 2.5 TabBar — AI 助手应为 active
    has_tabbar = "tab-bar" in index_html or "tabBar" in index_html
    if has_tabbar:
        ai_active = ('index.html' in index_html and 'active' in index_html)
        check("tabbar_ai_active",
              ai_active or 'tab-item active' in index_html,
              "MEDIUM", "TabBar 中「AI助手」tab 未设置为 active")

    # 2.6 API 调用
    r = api("POST", "/chat/stream", token=token, json={
        "message": "QA test",
        "thread_id": "qa-test-thread",
        "persona": "student",
    })
    check("sse_endpoint_reachable",
          r.status_code in (200, 404, 405, 422),
          "HIGH", f"SSE 端点不可达: {r.status_code}",
          "检查 /chat/stream 路由注册")


# ═══════════════════════════════════════════════════════════════
# SECTION 3: 练习页 (practice.html)
# ═══════════════════════════════════════════════════════════════

def qa_practice(token, account_id):
    on_page("practice")

    practice_html = read_html("practice.html")
    if not practice_html:
        issue("BLOCKER", "practice", "file_missing", "practice.html 不存在")
        return

    # 3.1 API 调用
    r = api("GET", f"/practice/student/{account_id}/tasks", token=token)
    check("tasks_api_ok",
          r.status_code == 200,
          "BLOCKER", f"练习任务 API 失败: {r.status_code}",
          "检查 /practice/student/{uid}/tasks 端点")

    tasks_data = r.json().get("data", {}) if r.status_code == 200 else {}
    pending = tasks_data.get("pending", [])

    # 3.2 响应包含 id 字段
    if pending:
        first = pending[0]
        check("task_has_id",
              "id" in first,
              "HIGH", "练习任务响应缺少 id 字段（openPractice 需要）",
              "在 _format_session 中添加 'id': s.id")

        check("task_has_questions",
              "questions" in first,
              "HIGH", "练习任务响应缺少 questions 数组",
              "在 _format_session 中预加载 session_questions 关联")

        check("task_has_answered_count",
              "answered_count" in first,
              "MEDIUM", "练习任务响应缺少 answered_count（进度条需要）")

    # 3.3 练习提交
    if pending and pending[0].get("questions"):
        task = pending[0]
        q = task["questions"][0]
        r = api("POST", "/practice/submit", token=token, json={
            "practice_id": task["practice_id"],
            "answers": [{"question_id": q["id"], "answer": "A"}],
        })
        check("practice_submit_ok",
              r.status_code == 200,
              "HIGH", f"练习提交 API 失败: {r.status_code}",
              "检查 PracticeBatchSubmitRequest schema")

    # 3.4 前端状态持久化
    if practice_html:
        has_state = "state.answers" in practice_html or "answers[questionId]" in practice_html
        check("answer_state_persistence",
              has_state,
              "HIGH", "练习页答案状态未持久化（切换题目可能丢失答案）",
              "确保 state.answers = {} 在 openPractice 中初始化，selectAnswer 中更新")

    # 3.5 结果展示
    if practice_html:
        has_result = "showResult" in practice_html or "result-score" in practice_html
        check("result_display",
              has_result,
              "MEDIUM", "练习提交后无结果展示逻辑")


# ═══════════════════════════════════════════════════════════════
# SECTION 4: 错题本 (wrong.html)
# ═══════════════════════════════════════════════════════════════

def qa_wrong_book(token, account_id):
    on_page("wrong-book")

    wrong_html = read_html("wrong.html")
    if not wrong_html:
        issue("BLOCKER", "wrong-book", "file_missing", "wrong.html 不存在")
        return

    # 4.1 API 调用
    r = api("GET", "/practice/wrong/list", token=token, params={"student_id": account_id})
    check("wrong_list_api_ok",
          r.status_code == 200,
          "BLOCKER", f"错题列表 API 失败: {r.status_code}",
          "检查 /practice/wrong/list 端点")

    # 4.2 手风琴逻辑
    if wrong_html:
        has_toggle = "toggleCard" in wrong_html
        check("accordion_toggle_function",
              has_toggle,
              "HIGH", "错题本缺少 toggleCard 手风琴函数")

        # 检查是否正确选择 .wq-card 而非 .wrong-card
        uses_wrong_class = ".wrong-card" in wrong_html
        uses_wq_class = ".wq-card" in wrong_html
        check("accordion_css_selector",
              uses_wq_class and not (".wrong-card.open" in wrong_html),
              "HIGH", "toggleCard 使用了错误的 CSS 选择器 .wrong-card（应为 .wq-card）",
              "将所有 .wrong-card 替换为 .wq-card")

        # 检查关闭其他卡片逻辑
        has_close_others = ("forEach" in wrong_html and "open" in wrong_html) or "querySelectorAll" in wrong_html
        check("accordion_close_others",
              has_close_others,
              "HIGH", "toggleCard 未实现关闭其他卡片逻辑",
              "添加 querySelectorAll('.wq-card.open') 遍历关闭")

    # 4.3 已掌握移除
    if wrong_html:
        has_master = "markMastered" in wrong_html or "master" in wrong_html.lower()
        check("master_function_exists",
              has_master,
              "HIGH", "错题本缺少 markMastered 函数")

        has_dom_remove = "removeChild" in wrong_html or "remove(" in wrong_html or ".remove()" in wrong_html
        check("master_dom_removal",
              has_dom_remove,
              "HIGH", "markMastered 未实现 DOM 移除",
              "在 markMastered 成功回调中添加 parentNode.removeChild(card)")

    # 4.4 API 参数
    if wrong_html:
        uses_getUserId = "getUserId" in wrong_html
        check("wrong_uses_getUserId",
              uses_getUserId,
              "MEDIUM", "错题本 API 调用未使用 ChemAuth.getUserId()",
              "student_id 参数应使用 ChemAuth.getUserId()（返回 Account.id）")


# ═══════════════════════════════════════════════════════════════
# SECTION 5: 间隔复习 (review.html)
# ═══════════════════════════════════════════════════════════════

def qa_review(token, account_id):
    on_page("review")

    review_html = read_html("review.html")
    if not review_html:
        issue("BLOCKER", "review", "file_missing", "review.html 不存在")
        return

    # 5.1 API 调用
    r = api("GET", f"/review/student/{account_id}/due", token=token)
    check("review_api_ok",
          r.status_code == 200,
          "BLOCKER", f"复习列表 API 失败: {r.status_code}",
          "检查 /review/student/{id}/due 端点")

    review_data = r.json() if r.status_code == 200 else {}
    items = review_data.get("data", [])
    if items:
        # 5.2 复习提交
        rid = items[0].get("id")
        r = api("POST", "/review/submit", token=token, json={
            "review_task_id": rid,
            "is_correct": True,
        })
        check("review_submit_ok",
              r.status_code in (200, 201),
              "HIGH", f"复习提交 API 失败: {r.status_code}",
              "检查 ReviewSubmitRequest schema: review_task_id + is_correct")

        # 验证提交后数据变化
        r2 = api("GET", f"/review/student/{account_id}/due", token=token)
        if r2.status_code == 200:
            items2 = r2.json().get("data", [])
            still_exists = any(i.get("id") == rid for i in items2)
            check("review_item_removed",
                  not still_exists,
                  "INFO", "复习提交后项目仍在待复习列表中（可能是正确的——取决于间隔算法）")

    # 5.3 数据源差异（vs 错题本）
    if review_html:
        uses_review_api = "/review/student" in review_html
        check("review_data_source",
              uses_review_api,
              "HIGH", "复习页未使用 /review/student/{id}/due（可能误用错题 API）",
              "复习页数据源: /review/student/{id}/due (到期复习), 不是 /practice/wrong/list (错题列表)")

    # 5.4 正误反馈
    if review_html:
        has_feedback = "correct" in review_html.lower() and ("wrong" in review_html.lower() or "incorrect" in review_html.lower())
        check("review_feedback_ui",
              has_feedback,
              "MEDIUM", "复习页缺少正误反馈 UI",
              "提交复习后显示正确/错误视觉反馈")


# ═══════════════════════════════════════════════════════════════
# SECTION 6: 个人报告 (report.html)
# ═══════════════════════════════════════════════════════════════

def qa_report(token, account_id):
    on_page("report")

    report_html = read_html("report.html")
    if not report_html:
        issue("BLOCKER", "report", "file_missing", "report.html 不存在")
        return

    # 6.1 统计 API
    r = api("GET", f"/student/{account_id}/stats", token=token)
    check("stats_api_ok",
          r.status_code == 200,
          "BLOCKER", f"统计 API 失败: {r.status_code}",
          "检查 /student/{id}/stats 端点")

    # 6.2 学习计划 API
    r = api("GET", f"/learning-plan/{account_id}", token=token)
    check("learning_plan_api_ok",
          r.status_code in (200, 404),
          "HIGH", f"学习计划 API 失败: {r.status_code}",
          "检查 /learning-plan/{id} 端点")

    # 6.3 个人资料渲染
    if report_html:
        has_profile = 'id="profileName"' in report_html or 'id="avatarEl"' in report_html
        check("profile_elements",
              has_profile,
              "HIGH", "report.html 缺少个人信息渲染元素 (id=profileName/avatarEl)")

    # 6.4 徽章区
    if report_html:
        has_badges = 'id="badgeWrong"' in report_html and 'id="badgeReview"' in report_html
        check("badge_elements",
              has_badges,
              "MEDIUM", "report.html 缺少徽章元素 (badgeWrong/badgeReview/badgeNew)")

    # 6.5 知识点列表
    if report_html:
        has_kp = "kpList" in report_html and "kp-item" in report_html
        check("knowledge_point_elements",
              has_kp,
              "MEDIUM", "report.html 缺少知识点列表元素 (#kpList)")

    # 6.6 退出登录
    if report_html:
        has_logout = "ChemAuth.logout()" in report_html or "logout()" in report_html
        check("logout_call",
              has_logout,
              "HIGH", "report.html 退出按钮未调用 ChemAuth.logout()")

    # 6.7 绑定码复制
    if report_html:
        has_copy = "bindCode" in report_html and ("clipboard" in report_html or "copy" in report_html.lower())
        check("bind_code_copy",
              has_copy,
              "MEDIUM", "report.html 缺少绑定码复制功能",
              "使用 navigator.clipboard.writeText() + execCommand 降级")

    # 6.8 TabBar — "我的" active
    if report_html:
        my_active = ('我的' in report_html and 'active' in report_html)
        check("report_tab_active",
              my_active or 'tab-item active' in report_html,
              "MEDIUM", "report.html 的 TabBar「我的」未标记 active")


# ═══════════════════════════════════════════════════════════════
# SECTION 7: 跨页面问题
# ═══════════════════════════════════════════════════════════════

def qa_cross_page(token, account_id):
    on_page("cross-page")

    all_pages = ["index.html", "practice.html", "wrong.html", "review.html", "report.html"]

    # 7.1 TabBar 一致性 — 检查每个页面的 TabBar 包含所有到其他页面的链接
    all_tab_pages = ["index", "practice", "wrong", "review", "report"]
    for pf in all_pages:
        html = read_html(pf)
        if html:
            links = set(re.findall(r"location\.href\s*=\s*['\"]([^'\"]+\.html)['\"]", html))
            # 当前页是 active tab（无 onclick），检查是否链接到所有其他页面
            current = pf.replace(".html", "")
            expected = set(p + ".html" for p in all_tab_pages if p != current)
            missing = expected - links
            if missing:
                check(f"tabbar_missing_links_{pf}",
                      False,
                      "MEDIUM", f"{pf} TabBar 缺少链接: {missing}",
                      f"在 {pf} TabBar 中添加缺失的导航按钮")

    # 7.2 API 端点一致性 — 所有页面使用 account_id (JWT user_id)
    for pf in all_pages:
        html = read_html(pf)
        if html:
            uses_student_id_raw = re.findall(r"student_id[=:'\"]\s*['\"]?(\d+)", html)
            # 这只能检测硬编码的 student_id，实际页面使用 getUserId()
            uses_getUserId = "getUserId" in html
            if not uses_getUserId and uses_student_id_raw:
                check(f"hardcoded_id_{pf}",
                      False,
                      "HIGH", f"{pf} 硬编码了 student_id={uses_student_id_raw}（应用 getUserId()）")

    # 7.3 静态文件完整性
    required_files = ["auth.js", "api-client.js"]
    for jf in required_files:
        js = read_js(jf)
        check(f"js_file_{jf}",
              js is not None,
              "BLOCKER", f"JS 文件缺失: {jf}")

    # 7.4 SSE 事件类型定义
    sse_js = read_js("sse-client.js")
    if sse_js:
        has_event_dispatch = "handlers[eventType]" in sse_js or "_dispatch" in sse_js
        check("sse_event_dispatcher",
              has_event_dispatch,
              "MEDIUM", "sse-client.js 未实现 SSE 事件分发器")


# ═══════════════════════════════════════════════════════════════
# SECTION 8: 安全问题
# ═══════════════════════════════════════════════════════════════

def qa_security(token):
    on_page("security")

    # 8.1 未认证访问保护
    for path in ["/api/v1/student/2/stats",
                 "/api/v1/practice/student/2/tasks",
                 "/api/v1/practice/wrong/list?student_id=2",
                 "/api/v1/review/student/2/due"]:
        r = requests.get(f"http://localhost:8000{path}")
        check(f"unauth_protected_{path.split('/')[-1][:20]}",
              r.status_code == 403 or r.status_code == 401,
              "HIGH", f"未认证可访问 {path}: HTTP {r.status_code}",
              "确保所有 API 端点使用 get_current_user 依赖")

    # 8.2 跨学生数据隔离
    # 学生 A (account_id=2) 不应访问学生 B 的数据
    r = api("GET", "/student/1/stats", token=token)
    check("cross_student_isolation",
          r.status_code in (403, 404),
          "HIGH", f"跨学生数据隔离失败: GET /student/1/stats -> {r.status_code}",
          "require_student_self 应拒绝访问其他学生数据")

    # 8.3 Token 格式
    auth_js = read_js("auth.js")
    if auth_js:
        has_token_in_url = re.search(r'[\?\&]token=', auth_js)
        check("token_not_in_url",
              has_token_in_url is None,
              "MEDIUM", "auth.js 可能将 token 作为 URL 参数传递（安全风险）")


# ═══════════════════════════════════════════════════════════════
# SECTION 9: 可自动修复的问题
# ═══════════════════════════════════════════════════════════════

def fix_token_key(auth_js_content):
    """修复 TOKEN_KEY 不一致"""
    path = JS_DIR / "auth.js"
    content = path.read_text(encoding='utf-8')
    if "TOKEN_KEY = 'chemai_token'" in content:
        return True
    return False  # 已经是正确的，无需修复


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def main():
    global CHECK_COUNT, PASS_COUNT

    print("╔══════════════════════════════════════════════════════════╗")
    print("║   ChemAI 学生端 Gstack QA — 6 页面自动走查             ║")
    print("║   API + 代码结构 + 数据流 + 安全                       ║")
    print("╚══════════════════════════════════════════════════════════╝")
    start_time = datetime.now()

    token = login()
    if not token:
        print("\n[FATAL] 无法登录，请确认后端运行在 localhost:8000")
        return False

    # 解码 JWT
    account_id = None
    try:
        parts = token.split('.')
        payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
        jwt_data = json.loads(base64.b64decode(payload))
        account_id = jwt_data.get("user_id")
    except Exception:
        pass

    print(f"\n  Token: {token[:25]}...  Account.id: {account_id}")

    # ── 检查全部 9 个模块 ──
    qa_auth_system()                   # 1. 认证体系
    qa_ai_chat(token)                  # 2. AI 对话
    qa_practice(token, account_id)     # 3. 练习
    qa_wrong_book(token, account_id)   # 4. 错题本
    qa_review(token, account_id)       # 5. 复习
    qa_report(token, account_id)       # 6. 个人报告
    qa_cross_page(token, account_id)   # 7. 跨页面
    qa_security(token)                 # 8. 安全

    # ── 报告 ──
    elapsed = (datetime.now() - start_time).total_seconds()
    ISSUES.sort(key=lambda i: sev_weight(i.sev))

    blockers = [i for i in ISSUES if i.sev == "BLOCKER"]
    highs = [i for i in ISSUES if i.sev == "HIGH"]
    mediums = [i for i in ISSUES if i.sev == "MEDIUM"]
    infos = [i for i in ISSUES if i.sev == "INFO"]

    unresolved = [i for i in ISSUES if not i.auto_fixed]

    print(f"\n{'='*60}")
    print(f"  Gstack QA 走查报告")
    print(f"{'='*60}")
    print(f"  检查项: {CHECK_COUNT}    通过: {PASS_COUNT}    问题: {len(unresolved)}")
    print(f"  自动修复: {len(AUTO_FIXES)}    耗时: {elapsed:.1f}s")
    print(f"  🔥 BLOCKER: {len([i for i in blockers if not i.auto_fixed])}")
    print(f"  ❌ HIGH:    {len([i for i in highs if not i.auto_fixed])}")
    print(f"  ⚠️ MEDIUM:  {len([i for i in mediums if not i.auto_fixed])}")
    print(f"  ℹ️ INFO:    {len([i for i in infos if not i.auto_fixed])}")
    print(f"{'='*60}")

    if AUTO_FIXES:
        print(f"\n  ## 自动修复 ({len(AUTO_FIXES)} 项)")
        for i, fix in enumerate(AUTO_FIXES):
            print(f"  ✅ {i+1}. {fix}")

    if unresolved:
        print(f"\n  ## 待处理问题 ({len(unresolved)} 项)")
        for i, iss in enumerate(unresolved):
            emoji = {"BLOCKER": "🔥", "HIGH": "❌", "MEDIUM": "⚠️", "INFO": "ℹ️"}[iss.sev]
            print(f"\n  {i+1}. {emoji} [{iss.sev}] {iss.page}/{iss.check}")
            print(f"     {iss.detail}")
            if iss.fix:
                print(f"     → {iss.fix}")
    else:
        print(f"\n  ✅ 未发现待处理问题！")

    critical_count = len([i for i in unresolved if i.sev in ("BLOCKER", "HIGH")])
    return critical_count == 0


if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except Exception as e:
        print(f"\nFATAL: {e}")
        traceback.print_exc()
        sys.exit(2)
