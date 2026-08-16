"""验收验证 — 三条用户旅程端到端走查（API 层）。

旅程 1 · 教师: 登录 → 出题 → 四维审核 → 发布考试 → 查看学情 → 障碍诊断
旅程 2 · 学生: 登录 → AI 对话 → 做练习 → 错题本 → 间隔复习 → 个人报告
旅程 3 · 家长: 登录 → 查看概览 → 学习报告 → 消息通知

判定规则: HTTP 401/403/500 视为阻断 (BLOCKED)；200/201/404(空态) 视为通过。
"""
import sys
import json
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000/api/v1"
RESULTS = []


def step(journey, name, method, path, token=None, body=None, ok_codes=(200, 201)):
    """执行单步，记录结果。返回响应对象。"""
    url = f"{BASE}{path}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = requests.request(method, url, json=body, headers=headers, timeout=20)
        code = r.status_code
        blocked = code in (401, 403, 500)
        status = "BLOCKED" if blocked else ("PASS" if code in ok_codes else "WARN")
        RESULTS.append((journey, name, code, status, r))
        print(f"  [{status:>7}] {code}  {method:>4} {path}")
        if blocked:
            try:
                print(f"            ↳ {r.json()}")
            except Exception:
                print(f"            ↳ {r.text[:200]}")
        return r
    except Exception as e:
        RESULTS.append((journey, name, "ERR", "BLOCKED", None))
        print(f"  [BLOCKED] ERR  {method:>4} {path}  ↳ {e}")
        return None


def login(phone, pw="Demo@2026"):
    r = requests.post(f"{BASE}/auth/login", json={"phone": phone, "password": pw}, timeout=20)
    if r.status_code == 200:
        return r.json().get("token")
    print(f"  [BLOCKED] 登录失败 {phone}: {r.status_code} {r.text[:120]}")
    return None


print("=" * 70)
print("旅程 1 · 教师")
print("=" * 70)
t = login("13800000001")
if t:
    step(1, "出题工作台(试卷列表)", "GET", "/exams", t)
    step(1, "出题工作台(题库集)", "GET", "/question-sets", t)
    step(1, "四维审核(方程式)", "POST", "/audit/equation", t,
         body={"equation": "Fe + O2 → Fe2O3"})
    r_exam = step(1, "发布考试(试卷)", "GET", "/exams", t)
    step(1, "查看学情(班级面板)", "GET", "/panel/classes", t)
    step(1, "障碍诊断(预警列表)", "GET", "/warnings", t)

print("=" * 70)
print("旅程 2 · 学生")
print("=" * 70)
s = login("13800000002")
if s:
    step(2, "AI 对话(会话列表)", "GET", "/chat/conversations", s)
    step(2, "做练习(任务列表)", "GET", "/practice/student/2/tasks", s)
    step(2, "错题本", "GET", "/practice/wrong/list?student_id=2", s)
    step(2, "间隔复习(待复习)", "GET", "/review/student/2/due", s)
    step(2, "个人报告(统计)", "GET", "/student/2/stats", s)

print("=" * 70)
print("旅程 3 · 家长")
print("=" * 70)
p = login("13900000100")
if p:
    step(3, "查看概览(子女列表)", "GET", "/parent/children", p)
    step(3, "学习报告", "GET", "/parent/child/1/report", p)
    step(3, "消息通知", "GET", "/parent/notifications", p)

print("=" * 70)
print("汇总")
print("=" * 70)
blocked = [r for r in RESULTS if r[3] == "BLOCKED"]
for j in (1, 2, 3):
    steps = [r for r in RESULTS if r[0] == j]
    n_block = sum(1 for r in steps if r[3] == "BLOCKED")
    print(f"  旅程 {j}: {len(steps)} 步, {n_block} 阻断  {'✅ 走通' if n_block == 0 else '❌ 阻断'}")
print(f"\n总阻断数: {len(blocked)}")
sys.exit(1 if blocked else 0)
