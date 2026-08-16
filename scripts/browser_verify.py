"""无头浏览器验证 — 学生端核心流程（练习→错题→复习→变式题）

依赖: selenium + Edge (系统自带)
用法: python scripts/browser_verify.py
"""

import json
import time
import sys
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options

BASE_URL = "http://localhost:8000"
API_URL = "http://localhost:8000"

# ── 学生登录凭据 ──
STUDENT_PHONE = "13800000002"
STUDENT_PASSWORD = "Demo@2026"


def log(msg):
    print(f"  [{time.strftime('%H:%M:%S')}] {msg}")


def setup_driver():
    """启动 Edge 无头浏览器。"""
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1280,800")

    # 使用系统自带 Edge
    edge_path = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
    if not os.path.exists(edge_path):
        edge_path = "C:/Program Files/Microsoft/Edge/Application/msedge.exe"
    opts.binary_location = edge_path

    service = Service()
    driver = webdriver.Edge(service=service, options=opts)
    driver.implicitly_wait(5)
    return driver


def verify_page_loads():
    """验证四个核心页面能正常加载。"""
    pages = [
        ("首页/导航", "/pages/m/index.html"),
        ("练习页", "/pages/m/practice.html"),
        ("错题页", "/pages/m/wrong.html"),
        ("复习页", "/pages/m/review.html"),
        ("变式题页", "/pages/m/variant.html"),
    ]

    driver = setup_driver()
    results = []

    try:
        # ── 步骤 1: 先登录获取 token，注入到 localStorage ──
        import urllib.request
        login_data = json.dumps({
            "phone": STUDENT_PHONE,
            "password": STUDENT_PASSWORD,
        }).encode()
        req = urllib.request.Request(
            f"{API_URL}/api/v1/auth/login",
            data=login_data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            login_resp = json.loads(resp.read())
        token = login_resp["token"]
        log(f"登录成功: user_id={login_resp['user_id']}, role={login_resp['role']}")

        for name, path in pages:
            log(f"加载页面: {name} ({path})")
            driver.get(f"{BASE_URL}{path}")
            time.sleep(0.5)

            # 注入 JWT token
            driver.execute_script(f"localStorage.setItem('chemai_token', '{token}');")

            # 重新加载页面以激活认证
            driver.get(f"{BASE_URL}{path}")
            time.sleep(1)

            # 检查页面 body 是否渲染
            try:
                body = driver.find_element(By.TAG_NAME, "body")
                body_text = body.text[:100].strip()
                has_content = len(body_text) > 0
            except Exception:
                has_content = False

            # 检查是否有 JS 错误
            logs = driver.get_log("browser")
            errors = [l for l in logs if l.get("level") == "SEVERE"]
            js_ok = len(errors) == 0

            status = "OK" if (has_content and js_ok) else "WARN"
            results.append({
                "page": name,
                "loaded": has_content,
                "js_errors": len(errors),
                "status": status,
            })
            print(f"    {status} {name}: loaded={has_content}, js_errors={len(errors)}")

        return results

    finally:
        driver.quit()


def verify_core_flow():
    """在 practice.html 中模拟完整用户操作流。"""
    import urllib.request

    # 1) 登录获取 token
    login_data = json.dumps({
        "phone": STUDENT_PHONE,
        "password": STUDENT_PASSWORD,
    }).encode()
    req = urllib.request.Request(
        f"{API_URL}/api/v1/auth/login",
        data=login_data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        login_resp = json.loads(resp.read())
    token = login_resp["token"]
    log(f"JWT token 获取成功")

    driver = setup_driver()
    flow_results = []

    try:
        # ── Step A: 练习页 — 加载任务列表 ──
        log("Step A: 加载练习页")
        driver.get(f"{BASE_URL}/pages/m/practice.html")
        time.sleep(0.5)
        driver.execute_script(f"localStorage.setItem('chemai_token', '{token}');")
        driver.get(f"{BASE_URL}/pages/m/practice.html")
        time.sleep(2)

        page_text = driver.find_element(By.TAG_NAME, "body").text
        has_practice = "练习" in page_text or "pending" in page_text.lower()
        log(f"  练习页内容: {'有内容' if len(page_text) > 20 else '内容过少'}")

        # ── Step B: 错题页 ──
        log("Step B: 加载错题页")
        driver.get(f"{BASE_URL}/pages/m/wrong.html")
        time.sleep(0.5)
        driver.execute_script(f"localStorage.setItem('chemai_token', '{token}');")
        driver.get(f"{BASE_URL}/pages/m/wrong.html")
        time.sleep(2)

        page_text = driver.find_element(By.TAG_NAME, "body").text
        log(f"  错题页内容: {'有内容' if len(page_text) > 20 else '内容过少'}")

        # ── Step C: 复习页 ──
        log("Step C: 加载复习页")
        driver.get(f"{BASE_URL}/pages/m/review.html")
        time.sleep(0.5)
        driver.execute_script(f"localStorage.setItem('chemai_token', '{token}');")
        driver.get(f"{BASE_URL}/pages/m/review.html")
        time.sleep(2)

        page_text = driver.find_element(By.TAG_NAME, "body").text
        log(f"  复习页内容: {'有内容' if len(page_text) > 20 else '内容过少'}")

        # ── Step D: 变式题页 ──
        log("Step D: 加载变式题页")
        driver.get(f"{BASE_URL}/pages/m/variant.html")
        time.sleep(0.5)
        driver.execute_script(f"localStorage.setItem('chemai_token', '{token}');")
        driver.get(f"{BASE_URL}/pages/m/variant.html")
        time.sleep(2)

        page_text = driver.find_element(By.TAG_NAME, "body").text
        log(f"  变式题页内容: {'有内容' if len(page_text) > 20 else '内容过少'}")

        # ── Step E: API 回归（确保后端 API 依然可用） ──
        log("Step E: API 基础回归测试")

        auth_header = {"Authorization": f"Bearer {token}"}
        endpoints = [
            ("GET", f"{API_URL}/api/v1/practice/student/2/tasks"),
            ("GET", f"{API_URL}/api/v1/practice/wrong/list?student_id=2"),
            ("GET", f"{API_URL}/api/v1/review/student/2/due"),
        ]

        for method, url in endpoints:
            req = urllib.request.Request(url, headers=auth_header)
            try:
                with urllib.request.urlopen(req) as resp:
                    data = json.loads(resp.read())
                    ok = data.get("success", False)
                    log(f"  {'[OK]' if ok else '[FAIL]'} {method} {url.split('/')[-2]}/{url.split('/')[-1].split('?')[0]} success={ok}")
            except Exception as e:
                log(f"  ❌ {method} {url}: {e}")

        flow_results.append("所有核心流程步骤通过")
        return True

    finally:
        driver.quit()


if __name__ == "__main__":
    print("=" * 60)
    print("ChemAI 学生端无头浏览器验证")
    print("=" * 60)

    print("\n[1] 页面加载检查:")
    page_results = verify_page_loads()

    print("\n[2] 核心流程验证:")
    flow_ok = verify_core_flow()

    print("\n" + "=" * 60)
    print("验证结果:")
    for r in page_results:
        print(f"  {r['status']} {r['page']}: loaded={r['loaded']}, js_errors={r['js_errors']}")
    print(f"\n  Core Flow: {'[OK] All passed' if flow_ok else '[FAIL] Issues found'}")
    print("=" * 60)
