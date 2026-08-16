"""QA Phase 1: API endpoint health check for all student-facing endpoints."""
import json
import urllib.request
import urllib.error
import sys
import os
import io

# Fix Windows GBK encoding issue
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = "http://localhost:8000"
TOKEN = None  # Will be obtained via login

def get_token():
    """Login as student and get JWT token."""
    data = json.dumps({"phone": "13800000002", "password": "Demo@2026"}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        r = json.loads(resp.read())
    return r["token"], r["user_id"]

results = []

def test(method, path, label, body=None, expect_success=True):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            r = json.loads(resp.read())
            ok = r.get("success") == expect_success
            detail = ""
            if not ok:
                detail = f"expected success={expect_success}, got success={r.get('success')}"
            results.append((label, "OK" if ok else "FAIL", detail))
            return r
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        # For endpoints expected to fail (e.g. 403), this is OK
        ok = not expect_success
        results.append((label, "OK" if ok else "FAIL", f"HTTP {e.code}: {body_text[:100]}"))
        return None
    except Exception as e:
        results.append((label, "ERROR", str(e)[:100]))
        return None

print("=" * 60)
print("[Phase 1] API Endpoint Health Check")
print("=" * 60)

# Get fresh token
TOKEN, uid = get_token()
print(f"  Token obtained: user_id={uid}")

# ── Read-only endpoints ──
print("\n  [Read-only endpoints]")

r = test("GET", f"/api/v1/practice/student/{uid}/tasks", "GET /practice/student/{uid}/tasks")
if r:
    pending = r.get("data", {}).get("pending", [])
    completed = r.get("data", {}).get("completed", [])
    print(f"    Tasks: {len(pending)} pending, {len(completed)} completed")
    if pending:
        print(f"    Sample task: practice_id={pending[0].get('practice_id')}, "
              f"question_id={pending[0].get('question_id')}")

r = test("GET", f"/api/v1/practice/effect/{uid}", "GET /practice/effect/{student_id}")
if r:
    sessions = r.get("data", {}).get("sessions", [])
    comparison = r.get("data", {}).get("comparison")
    print(f"    Effect: {len(sessions)} sessions, comparison={'present' if comparison else 'null'}")

r = test("GET", f"/api/v1/practice/wrong/list?student_id={uid}", "GET /practice/wrong/list")
if r:
    wrong_items = r.get("data", [])
    print(f"    Wrong questions: total={r.get('total', 0)}")
    if wrong_items:
        print(f"    Sample: qid={wrong_items[0].get('question_id')}, "
              f"wrong_count={wrong_items[0].get('wrong_count')}")

r = test("GET", f"/api/v1/practice/wrong-topic/knowledge-points?student_id={uid}",
         "GET /practice/wrong-topic/knowledge-points")
if r:
    kps = r.get("data", [])
    print(f"    Knowledge points: total={r.get('total', 0)}")
    if kps:
        print(f"    Top KP: {kps[0].get('name')} ({kps[0].get('wrong_count')} errors)")

r = test("GET", f"/api/v1/review/student/{uid}/due", "GET /review/student/{id}/due")
due_items = []
if r:
    due_items = r.get("data", [])
    print(f"    Due reviews: total={r.get('total', 0)}")
    if due_items:
        print(f"    Sample: task_id={due_items[0].get('id')}, "
              f"level={due_items[0].get('review_level')}")

# ── Write operations ──
print("\n  [Write operations]")

# Get pending task for submit test
r = test("GET", f"/api/v1/practice/student/{uid}/tasks", "pre-fetch tasks")
pending = r.get("data", {}).get("pending", []) if r else []

if pending:
    pid = pending[0].get("practice_id")
    qid = pending[0].get("question_id")
    print(f"    Using practice_id={pid}, question_id={qid}")

    r = test("POST", "/api/v1/practice/submit", "POST /practice/submit",
             body={"practice_id": pid, "answers": [{"question_id": qid, "answer": "2H2+O2=2H2O"}]})
    if r:
        print(f"    Submit: correct_count={r.get('data', {}).get('correct_count', '?')}")
else:
    print("    [SKIP] No pending tasks for submit test")

# Get wrong questions for variant/master/training tests
r = test("GET", f"/api/v1/practice/wrong/list?student_id={uid}", "pre-fetch wrong questions")
wrong_items = r.get("data", []) if r else []

if wrong_items:
    wqid = wrong_items[0].get("question_id")

    r = test("POST", "/api/v1/practice/wrong-topic/variant/generate",
             "POST /variant/generate",
             body={"question_id": wqid, "count": 2})
    if r:
        variants = r.get("data", [])
        if isinstance(variants, list):
            print(f"    Variants: {len(variants)} generated"
                  + (f", sample: {variants[0].get('stem', '')[:50]}" if variants else ""))
        else:
            print(f"    Variants: data={json.dumps(variants, ensure_ascii=False)[:100]}")

    r = test("POST", f"/api/v1/practice/wrong/{wqid}/master",
             "POST /wrong/{id}/master",
             body={"student_id": uid})
    if r:
        print(f"    Mark mastered: OK")

# Create and submit training (even without wrong questions, use question IDs 1,2)
r = test("POST", "/api/v1/practice/wrong-topic/training/create",
         "POST /training/create",
         body={"student_id": uid, "question_ids": [1, 2]})
if r:
    session_id = r.get("data", {}).get("session_id")
    print(f"    Training created: session_id={session_id}")
    if session_id:
        r = test("POST", "/api/v1/practice/wrong-topic/training/submit",
                 "POST /training/submit",
                 body={"student_id": uid, "session_id": session_id,
                       "answers": [{"question_id": 1, "answer": "N2+3H2=2NH3"}]})
        if r:
            print(f"    Training submit: score={r.get('data', {}).get('score', '?')}")

# Submit review (if due reviews exist)
if due_items:
    r = test("POST", "/api/v1/review/submit", "POST /review/submit",
             body={"review_task_id": due_items[0].get("id"), "is_correct": True})

# ── Permission check ──
print("\n  [Permission check]")
r = test("POST", "/api/v1/practice/assign", "POST /practice/assign (student → expect 403)",
         body={"student_id": 1, "question_count": 3}, expect_success=False)

# ── Edge cases ──
print("\n  [Edge cases]")
r = test("GET", "/api/v1/practice/student/99999/tasks", "Nonexistent student (tasks)")
r = test("GET", "/api/v1/practice/effect/99999", "Nonexistent student (effect)")
r = test("GET", "/api/v1/review/student/99999/due", "Nonexistent student (reviews)")
r = test("GET", "/api/v1/practice/wrong/list?student_id=99999", "Nonexistent student (wrong list)")

# ── Summary ──
print("\n" + "=" * 60)
print("[Phase 1] Results Summary:")
passed = sum(1 for _, s, _ in results if s == "OK")
failed = sum(1 for _, s, _ in results if s != "OK")
for label, status, detail in results:
    flag = "✅" if status == "OK" else "❌"
    print(f"  {flag} {status:10s} {label}")
    if detail:
        print(f"         {detail}")
print(f"\n  Total: {passed}/{len(results)} passed, {failed} failed")
print("=" * 60)

# Write results file
with open("/tmp/qa_phase1_results.json", "w") as f:
    json.dump({"passed": passed, "failed": failed, "total": len(results),
               "results": [(l, s, d) for l, s, d in results]}, f)
