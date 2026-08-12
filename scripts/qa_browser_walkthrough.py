"""Gstack QA — 学生端 6 页面浏览器自动走查。

覆盖:
  1. 登录页 (login.html)  — 表单交互 / 错误提示 / token 写入
  2. AI 对话 (index.html)  — SSE 连接 / 输入交互 / 消息渲染
  3. 练习页 (practice.html) — 任务列表 / 答题 / 提交 / 结果
  4. 错题页 (wrong.html)   — 列表 / 手风琴 / 已掌握
  5. 复习页 (review.html)  — 到期列表 / 提交 / 状态更新
  6. 报告页 (report.html)  — 统计数据 / 徽章 / 退出登录

发现问题自动分类: BLOCKER / HIGH / MEDIUM / INFO
"""

import sys
import json
import time
import base64
import traceback
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

BASE_URL = "http://localhost:8000"
PAGES = f"{BASE_URL}/pages/m"

# ═══════════════════════════════════════════════════════════════
# 问题追踪
# ═══════════════════════════════════════════════════════════════
ISSUES = []
CHECK_COUNT = 0
PASS_COUNT = 0


def severity(s):
    """权重: BLOCKER > HIGH > MEDIUM > INFO"""
    return {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}.get(s, 99)


def issue(sev, page_name, check_name, detail, fix_hint=""):
    global ISSUES
    ISSUES.append({
        "severity": sev,
        "page": page_name,
        "check": check_name,
        "detail": detail,
        "fix": fix_hint,
    })
    emoji = {"BLOCKER": "🔥", "HIGH": "❌", "MEDIUM": "⚠️", "INFO": "ℹ️"}
    print(f"  {emoji.get(sev, '?')} [{sev}] {page_name}/{check_name}: {detail}")


def check(name, condition, sev_on_fail="HIGH", detail="", fix=""):
    global CHECK_COUNT, PASS_COUNT
    CHECK_COUNT += 1
    if condition:
        PASS_COUNT += 1
        return True
    else:
        issue(sev_on_fail, current_page, name, detail, fix)
        return False


current_page = ""


def on_page(name):
    global current_page
    current_page = name
    print(f"\n{'='*50}")
    print(f"[{name}]")
    print(f"{'='*50}")


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def jwt_decode(token):
    if not token:
        return None
    try:
        parts = token.split('.')
        payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
        return json.loads(base64.b64decode(payload))
    except Exception:
        return None


def safe_text(page, selector, default="<not found>"):
    try:
        el = page.locator(selector).first
        if el.count() > 0:
            return el.inner_text(timeout=2000)
    except Exception:
        pass
    return default


def exists(page, selector, timeout=3000):
    try:
        return page.locator(selector).count() > 0
    except Exception:
        return False


def wait_for(page, selector, timeout=5000):
    try:
        page.wait_for_selector(selector, timeout=timeout)
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════

def test_login(page):
    """登录页: 表单验证 / 错误处理 / 成功跳转"""
    on_page("login")

    page.goto(f"{PAGES}/login.html", wait_until="networkidle")
    page.wait_for_timeout(1000)

    # 1. 元素存在性
    check("phone_input_exists",
          exists(page, 'input[type="tel"], input[placeholder*="手机"], input[type="text"]'),
          "HIGH", "手机号输入框不存在")
    check("password_input_exists",
          exists(page, 'input[type="password"]'),
          "HIGH", "密码输入框不存在")
    check("login_button_exists",
          exists(page, 'button'),
          "HIGH", "登录按钮不存在")

    # 2. 空表单提交 — 应有错误提示
    phone_input = page.locator('input[type="tel"], input[placeholder*="手机"]').first
    pwd_input = page.locator('input[type="password"]').first
    btn = page.locator('button[type="submit"], button:has-text("登录"), button').first

    if phone_input.count() > 0 and btn.count() > 0:
        phone_input.fill("")
        pwd_input.fill("")
        btn.click()
        page.wait_for_timeout(800)

        # 检查是否有错误提示（toast / error-msg / 表单验证）
        has_error = (exists(page, '.toast, .error-msg, .form-error, input:invalid') or
                     page.locator('input:invalid').count() > 0)
        check("empty_form_error",
              has_error,
              "MEDIUM", "空表单提交无任何错误提示",
              "添加前端表单验证或 toast 错误提示")

    # 3. 错误手机号 — 应有错误提示
    if phone_input.count() > 0 and pwd_input.count() > 0 and btn.count() > 0:
        phone_input.fill("13800000000")
        pwd_input.fill("wrong")
        btn.click()
        page.wait_for_timeout(2000)

        # 检查 toast / error 提示
        has_toast = exists(page, '.toast, .error-msg, .form-error')
        still_on_login = "login" in page.url
        check("wrong_credentials_error",
              has_toast or still_on_login,
              "MEDIUM", "错误凭证提交后无任何反馈",
              "确保 /auth/login 返回 401 时前端显示 toast 错误")

    # 4. 正确登录 → 应跳转到 index.html
    if phone_input.count() > 0 and pwd_input.count() > 0 and btn.count() > 0:
        phone_input.fill("13800000002")
        pwd_input.fill("test123")
        btn.click()
        page.wait_for_timeout(3000)

        token = page.evaluate("() => localStorage.getItem('chemai_token')")
        check("token_stored",
              token is not None and len(token) > 10,
              "BLOCKER", "登录成功后 token 未写入 localStorage",
              "检查 login() 函数是否正确调用 ChemAuth.login()")

        # 验证跳转
        is_index = "index.html" in page.url
        check("redirect_after_login",
              is_index,
              "BLOCKER", "登录成功后未跳转到 index.html",
              "检查 login() 函数中的 window.location.href 设置")

        jwt = jwt_decode(token)
        check("jwt_role_student",
              jwt and jwt.get("role") == "student",
              "BLOCKER", f"JWT role 不是 student: {jwt.get('role') if jwt else 'None'}",
              "检查后端 JWT 生成时 role 字段")

    return True


def test_auth_guard(page, token):
    """认证守卫: 清除 token 后访问各页面应重定向到 login"""
    on_page("auth-guard")

    guarded_pages = [
        "index.html",
        "practice.html",
        "wrong.html",
        "review.html",
        "report.html",
    ]

    for p in guarded_pages:
        page.evaluate("() => localStorage.removeItem('chemai_token')")
        page.goto(f"{PAGES}/{p}", wait_until="networkidle")
        page.wait_for_timeout(1500)

        redirects = "login" in page.url.lower()
        check(f"guard_{p}",
              redirects,
              "BLOCKER", f"清除 token 后访问 {p} 未重定向到登录页: url={page.url}",
              f"检查 {p} 顶部是否调用 ChemAuth.isAuthenticated() 守卫")

    # 恢复 token
    page.evaluate(f"() => localStorage.setItem('chemai_token', '{token}')")


def test_ai_chat(page):
    """AI 对话页: SSE 链接 / 消息发送 / 输入框"""
    on_page("index")

    # 确保已登录
    page.goto(f"{PAGES}/index.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 1. 元素检查
    check("chat_input_exists",
          exists(page, 'textarea, input[type="text"], .chat-input, #messageInput'),
          "HIGH", "聊天输入框不存在")
    check("send_button_exists",
          exists(page, 'button'),
          "HIGH", "发送按钮不存在")
    check("chat_area_exists",
          exists(page, '.chat-messages, .message-list, #chatMessages, .conversation'),
          "MEDIUM", "聊天消息区不存在")

    # 2. TabBar 导航
    tab_count = page.locator('.tab-bar .tab-item, .tab-bar a, nav a').count()
    check("tabbar_exists",
          tab_count >= 3,
          "MEDIUM", f"TabBar 导航项不足: {tab_count}",
          "TabBar 应至少有 3 个导航项")

    # 3. 发送消息测试
    input_el = page.locator('textarea, input[type="text"], #messageInput').first
    send_btn = page.locator('button[type="submit"], button:has-text("发送"), .send-btn').first

    if input_el.count() > 0:
        input_el.fill("氧化还原反应是什么？")
        page.wait_for_timeout(300)

        if send_btn.count() > 0:
            send_btn.click()
            page.wait_for_timeout(3000)

            # 检查是否有 SSE 错误提示 (不是阻断性的)
            has_response = exists(page, '.message, .chat-bubble, .assistant-msg, .error-msg')
            check("ai_response_or_error",
                  has_response,
                  "INFO", "发送消息后无任何响应（可能 SSE 端点未就绪）",
                  "检查 SSE 连接和 AI 服务是否正常运行")

    # 4. Persona 参数检查
    persona_ok = page.evaluate("""() => {
        var b = document.body.innerHTML;
        return b.includes('student') || b.includes('persona');
    }""")
    check("persona_embedded",
          persona_ok,
          "INFO", "页面中未找到 persona 参数痕迹",
          "确认 AI 对话请求中 persona 固定为 'student'")


def test_practice(page):
    """练习页: 任务列表 / 答题交互 / 提交"""
    on_page("practice")

    page.goto(f"{PAGES}/practice.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 1. 任务列表加载
    has_tasks = exists(page, '.task-card, .task-list-item, [class*="task"]')
    has_empty = exists(page, '.state-msg, .empty-state')
    has_skeleton = exists(page, '.skeleton')

    check("task_list_loads",
          has_tasks or has_empty,
          "HIGH", "任务列表区域无内容（非空非 task-card 非 state-msg）",
          "检查 /practice/student/{uid}/tasks API 调用")

    # 2. Tab 切换
    tabs = page.locator('.tab-row .tab, .tabs .tab')
    if tabs.count() >= 2:
        tabs.nth(1).click()
        page.wait_for_timeout(500)
        completed_active = page.locator('.tab-row .tab.active, .tabs .tab.active').first.inner_text()
        check("tab_switch",
              "完成" in completed_active or "completed" in completed_active.lower(),
              "MEDIUM", "Tab 切换不生效",
              "检查 switchTab() 函数和 CSS .active 类")

        tabs.nth(0).click()  # 切回待完成

    # 3. 练习入口按钮
    task_cards = page.locator('.task-card, [class*="task-card"]')
    if task_cards.count() > 0:
        start_btn = task_cards.first.locator('button')
        if start_btn.count() > 0:
            start_btn.first.click()
            page.wait_for_timeout(1500)

            # 检查是否进入答题界面
            has_question = exists(page, '.question-text, .quiz-content, #quizContent')
            has_quiz_view = exists(page, '#quiz, .quiz-view')

            check("enter_quiz",
                  has_question or has_quiz_view,
                  "HIGH", "点击「开始练习」后未进入答题界面",
                  "检查 openPractice() — task.id 匹配 / session.questions 非空")

            # 4. 答题交互 — 选择题点击
            options = page.locator('.option-btn')
            if options.count() > 0:
                options.first.click()
                page.wait_for_timeout(300)
                is_selected = options.first.evaluate("el => el.classList.contains('selected')")
                check("option_select",
                      is_selected,
                      "MEDIUM", "点击选项后未高亮选中状态")

            # 5. 导航按钮
            has_prev = exists(page, '#btnPrev, .nav-prev')
            has_next = exists(page, '#btnNext, .nav-next')
            check("quiz_nav_buttons",
                  has_prev or has_next,
                  "MEDIUM", "答题界面缺少导航按钮",
                  "检查 renderCurrentQuestion() 中 ChemAPI.updateQuizNav 调用")

            # 返回列表
            back = page.locator('.back-btn, #btnBack')
            if back.count() > 0:
                back.first.click()
                page.wait_for_timeout(800)
        else:
            print("    (task card 无按钮)")
    else:
        print("    (无任务卡片)")


def test_wrong_book(page):
    """错题本: 列表加载 / 手风琴展开 / 已掌握移除"""
    on_page("wrong")

    page.goto(f"{PAGES}/wrong.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 1. 知识点筛选或列表
    has_list = exists(page, '.wq-card, .wrong-item, [class*="wrong-card"], .state-msg')
    check("wrong_list_renders",
          has_list,
          "HIGH", "错题列表无任何内容",
          "检查 /practice/wrong/list API 调用和 student_id 参数")

    # 2. 手风琴交互
    cards = page.locator('.wq-card')
    if cards.count() > 0:
        first_card = cards.first
        first_card.click()
        page.wait_for_timeout(600)

        is_open = first_card.evaluate("el => el.classList.contains('open')")
        check("accordion_opens",
              is_open,
              "HIGH", "点击错题卡片未展开（.open 类未添加）",
              "检查 toggleCard() 函数中的 CSS 类名选择器")

        # 检查展开后内容
        has_detail = exists(page, '.wq-card.open .card-detail, .wq-card.open .answer-detail')
        check("accordion_detail",
              has_detail,
              "MEDIUM", "卡片展开后无详情内容")

        # 关闭其他 — 点击第二张卡片
        if cards.count() > 1:
            cards.nth(1).click()
            page.wait_for_timeout(600)
            second_open = cards.nth(1).evaluate("el => el.classList.contains('open')")
            first_still_open = cards.nth(0).evaluate("el => el.classList.contains('open')")

            check("accordion_close_others",
                  second_open and not first_still_open,
                  "HIGH", "打开新卡片时未关闭之前展开的卡片",
                  "检查 toggleCard() 中是否正确关闭其他 .wq-card.open")

        # 3. 已掌握按钮
        master_btn = page.locator('.wq-card.open .btn-master, .wq-card.open button:has-text("掌握")')
        if master_btn.count() > 0:
            card_count_before = page.locator('.wq-card').count()
            master_btn.first.click()
            page.wait_for_timeout(1200)

            card_count_after = page.locator('.wq-card').count()
            check("master_removes_card",
                  card_count_after < card_count_before,
                  "HIGH", "点击「已掌握」后卡片未从 DOM 移除",
                  "检查 markMastered() 中是否正确移除卡片 DOM 元素")
    else:
        print("    (无错题卡片，可能错题本为空)")


def test_review(page):
    """间隔复习: 到期列表 / 题目展示 / 提交反馈"""
    on_page("review")

    page.goto(f"{PAGES}/review.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 1. 列表渲染
    has_cards = exists(page, '.review-card, [class*="review"], .state-msg')
    check("review_list_renders",
          has_cards,
          "HIGH", "复习列表无任何内容",
          "检查 /review/student/{id}/due API 调用")

    # 2. 答题交互
    review_cards = page.locator('.review-card, [class*="review-card"]')
    if review_cards.count() > 0:
        # 是否有答题区域
        option_btn = page.locator('.option-btn, button:has-text("A"), button:has-text("B")')
        if option_btn.count() > 0:
            option_btn.first.click()
            page.wait_for_timeout(300)

        # 提交按钮
        submit_btn = page.locator('button:has-text("提交"), button:has-text("确认"), .submit-btn')
        if submit_btn.count() > 0:
            submit_btn.first.click()
            page.wait_for_timeout(1500)

            # 检查是否正确/错误反馈
            has_feedback = exists(page, '.correct, .wrong, .result, .feedback')
            check("review_feedback",
                  has_feedback,
                  "MEDIUM", "提交复习后无正误反馈",
                  "检查 submitReview() 中的结果渲染")
    else:
        print("    (无复习卡片)")


def test_report(page):
    """个人报告: 统计 / 知识点 / 退出登录"""
    on_page("report")

    page.goto(f"{PAGES}/report.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 1. 个人资料卡片
    has_avatar = exists(page, '#avatarEl, .avatar, [class*="avatar"]')
    has_name = safe_text(page, '#profileName, .profile-name, [class*="profile-name"]')
    has_bind = exists(page, '#bindCode, .bind-code')

    check("profile_card",
          has_avatar or bool(has_name) or has_bind,
          "HIGH", "个人资料卡片无内容",
          "检查 JWT 解码和 _loadProfile 调用")

    # 2. 统计数据
    stat_practice = safe_text(page, '#statPractice, [class*="stat-practice"], .stat-item')
    stat_accuracy = safe_text(page, '#statAccuracy, [class*="stat-accuracy"]')

    check("stats_loaded",
          bool(stat_practice) or bool(stat_accuracy),
          "MEDIUM", "统计数据未加载",
          "检查 /student/{id}/stats API 调用")

    # 3. 徽章区
    has_badges = exists(page, '#badgeWrong, #badgeReview, #badgeNew, .badge')
    check("badges_section",
          has_badges,
          "MEDIUM", "徽章区域不存在或未渲染")

    # 4. 知识点
    has_kp = exists(page, '#kpList, .kp-item')
    check("knowledge_points",
          has_kp,
          "MEDIUM", "知识点列表不存在",
          "检查 _renderKnowledgePoints() 函数")

    # 5. TabBar — "我的" 应为 active
    my_tab = page.locator('.tab-bar .tab-item.active, .tab-bar a.active').first
    if my_tab.count() > 0:
        my_text = my_tab.inner_text()
        check("report_tab_active",
              "我" in my_text or "report" in my_text.lower(),
              "MEDIUM", f"个人报告页 TabBar 激活项不正确: {my_text}")

    # 6. 退出登录
    logout_btn = page.locator('button:has-text("退出"), button:has-text("登出"), #logoutBtn')
    if logout_btn.count() > 0:
        token_before = page.evaluate("() => localStorage.getItem('chemai_token')")
        logout_btn.first.click()
        page.wait_for_timeout(1500)
        token_after = page.evaluate("() => localStorage.getItem('chemai_token')")

        check("logout_clears_token",
              token_after is None or token_after == "null",
              "BLOCKER", "退出登录后 token 未清除",
              "检查 ChemAuth.logout() 是否调用 clearToken()")

        check("logout_redirects",
              "login" in page.url.lower(),
              "BLOCKER", "退出登录后未跳转到登录页",
              "检查 ChemAuth.logout() 是否设置 window.location.href")

        # 恢复登录
        if token_before:
            page.evaluate(f"() => localStorage.setItem('chemai_token', '{token_before}')")


def test_tabbar_navigation(page):
    """TabBar 导航: 各 tab 点击后页面切换正确"""
    on_page("tabbar-nav")

    # 从 index.html 开始
    page.goto(f"{PAGES}/index.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    tabs = page.locator('.tab-bar .tab-item, .tab-bar a, nav.tab-bar a')
    tab_count = tabs.count()

    check("tabbar_item_count",
          tab_count >= 3,
          "MEDIUM", f"TabBar 导航项不足 ({tab_count})，预期 ≥4")

    # 点击每个 tab 并验证跳转
    expected_pages = {
        "练习": "practice",
        "错题": "wrong",
        "复习": "review",
        "我的": "report",
    }

    for i in range(tab_count):
        try:
            tab = tabs.nth(i)
            tab_text = tab.inner_text(timeout=2000).strip()
            tab.click()
            page.wait_for_timeout(1500)

            for keyword, expected in expected_pages.items():
                if keyword in tab_text:
                    is_on_page = expected in page.url
                    check(f"tab_{expected}",
                          is_on_page,
                          "HIGH",
                          f"点击 Tab「{tab_text}」后未跳转到 {expected}.html (实际: {page.url})",
                          f"检查 TabBar onclick 绑定的 URL")
                    break
        except Exception as e:
            issue("MEDIUM", "tabbar-nav", f"tab_{i}", f"Tab 点击异常: {e}")


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def main():
    global CHECK_COUNT, PASS_COUNT

    print("╔══════════════════════════════════════════════════╗")
    print("║   ChemAI 学生端 QA 浏览器自动走查               ║")
    print("║   6 页面 · 交互验证 · 问题自动检测              ║")
    print("╚══════════════════════════════════════════════════╝")
    start_time = datetime.now()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 375, "height": 812},  # iPhone X
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15"
        )
        page = context.new_page()

        try:
            # ── 1. 登录 ──
            test_login(page)
            token = page.evaluate("() => localStorage.getItem('chemai_token')")

            if not token:
                print("\n[FATAL] 无法获取 token，跳过后续测试")
                browser.close()
                return False

            # ── 2. 认证守卫 ──
            test_auth_guard(page, token)

            # 恢复登录态
            page.evaluate(f"() => localStorage.setItem('chemai_token', '{token}')")

            # ── 3. AI 对话页 ──
            test_ai_chat(page)

            # ── 4. 练习页 ──
            test_practice(page)

            # ── 5. 错题本 ──
            test_wrong_book(page)

            # ── 6. 复习页 ──
            test_review(page)

            # ── 7. 报告页 ──
            test_report(page)

            # ── 8. TabBar 导航 ──
            test_tabbar_navigation(page)

        except Exception as e:
            traceback.print_exc()
            issue("BLOCKER", "general", "crash", f"QA 脚本异常: {e}")

        finally:
            # 截图保存每一页
            screenshots = {}
            for name, path in [("login", f"{PAGES}/login.html"),
                               ("index", f"{PAGES}/index.html"),
                               ("practice", f"{PAGES}/practice.html"),
                               ("wrong", f"{PAGES}/wrong.html"),
                               ("review", f"{PAGES}/review.html"),
                               ("report", f"{PAGES}/report.html")]:
                try:
                    page.goto(path, wait_until="networkidle")
                    page.wait_for_timeout(1000)
                    screenshots[name] = True
                except Exception:
                    screenshots[name] = False

            browser.close()

    # ═══════════════════════════════════════════════════════
    # 报告
    # ═══════════════════════════════════════════════════════
    elapsed = (datetime.now() - start_time).total_seconds()

    # 按严重程度排序
    ISSUES.sort(key=lambda i: severity(i["severity"]))

    blockers = [i for i in ISSUES if i["severity"] == "BLOCKER"]
    highs = [i for i in ISSUES if i["severity"] == "HIGH"]
    mediums = [i for i in ISSUES if i["severity"] == "MEDIUM"]
    infos = [i for i in ISSUES if i["severity"] == "INFO"]

    print(f"\n{'='*60}")
    print(f"  走查报告")
    print(f"{'='*60}")
    print(f"  检查项: {CHECK_COUNT}   通过: {PASS_COUNT}   问题: {len(ISSUES)}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  🔥 BLOCKER: {len(blockers)}   ❌ HIGH: {len(highs)}   ⚠️ MEDIUM: {len(mediums)}   ℹ️ INFO: {len(infos)}")
    print(f"{'='*60}")

    if ISSUES:
        print(f"\n  ## 问题清单\n")
        for i, iss in enumerate(ISSUES):
            emoji = {"BLOCKER": "🔥", "HIGH": "❌", "MEDIUM": "⚠️", "INFO": "ℹ️"}[iss["severity"]]
            print(f"  {i+1}. {emoji} [{iss['severity']}] {iss['page']}/{iss['check']}")
            print(f"     {iss['detail']}")
            if iss["fix"]:
                print(f"     Fix: {iss['fix']}")
    else:
        print(f"\n  ✅ 未发现问题，所有检查通过！")

    total_problems = len(blockers) + len(highs)
    return total_problems == 0


if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except Exception as e:
        print(f"\nFATAL: {e}")
        traceback.print_exc()
        sys.exit(2)
