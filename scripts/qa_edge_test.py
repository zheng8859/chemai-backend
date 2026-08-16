"""QA Phase 4: Edge cases and error handling."""
import json
import urllib.request
import urllib.error
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = "http://localhost:8000"

# Get valid token
data = json.dumps({"phone": "13800000002", "password": "Demo@2026"}).encode()
req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=data,
                              headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as resp:
    student_token = json.loads(resp.read())["token"]

# Teacher token
data = json.dumps({"phone": "13800000001", "password": "Demo@2026"}).encode()
req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=data,
                              headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as resp:
    teacher_token = json.loads(resp.read())["token"]

print("=" * 60)
print("[Phase 4] Edge Cases & Error Handling")
print("=" * 60)

issues = []

def test(label, method, path, token=None, body=None, expected_status=200):
    url = f"{BASE}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data_bytes = json.dumps(body).encode() if body else None
    if body:
        headers["Content-Type"] = "application/json"

    # Handle invalid token case
    if token == "INVALID":
        headers["Authorization"] = "Bearer invalid.token.here"

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = resp.getcode()
            if code == expected_status:
                print(f"  ✅ {label}")
                return True
            else:
                print(f"  ❌ {label} — expected {expected_status}, got {code}")
                issues.append(label)
                return False
    except urllib.error.HTTPError as e:
        if e.code == expected_status:
            print(f"  ✅ {label} — HTTP {e.code} (expected)")
            return True
        else:
            body = e.read().decode()[:150]
            print(f"  ❌ {label} — expected {expected_status}, got {e.code}: {body}")
            issues.append(label)
            return False
    except Exception as e:
        print(f"  ❌ {label} — {str(e)[:100]}")
        issues.append(label)
        return False

# ── Auth tests ──
print("\n[Auth & Token]")
test("No token on protected endpoint", "GET", "/api/v1/practice/student/2/tasks", expected_status=401)
test("Invalid JWT token", "GET", "/api/v1/practice/student/2/tasks", token="INVALID", expected_status=401)
test("Empty Authorization header", "GET", "/api/v1/practice/student/2/tasks", token="", expected_status=401)

# ── Input validation ──
print("\n[Input Validation]")
test("Missing required body fields", "POST", "/api/v1/practice/submit", token=student_token,
     body={"practice_id": "test"}, expected_status=422)  # answers missing
test("Invalid data type (string for int)", "GET", "/api/v1/practice/student/abc/tasks",
     expected_status=422)
test("Negative limit", "GET", "/api/v1/practice/wrong/list?student_id=2&limit=-1",
     token=student_token, expected_status=422)
test("Limit > 100", "GET", "/api/v1/practice/wrong/list?student_id=2&limit=999",
     token=student_token, expected_status=422)
test("Empty body on POST", "POST", "/api/v1/review/submit", token=student_token,
     body=None, expected_status=422)

# ── Boundary & nonexistent ──
print("\n[Boundary & Nonexistent]")
test("Student ID 0", "GET", "/api/v1/practice/student/0/tasks", token=student_token)
test("Student ID negative", "GET", "/api/v1/practice/student/-1/tasks",
     token=student_token, expected_status=422)
test("Student ID 999999", "GET", "/api/v1/practice/student/999999/tasks", token=student_token)
test("Nonexistent review task submit", "POST", "/api/v1/review/submit", token=student_token,
     body={"review_task_id": 99999, "is_correct": True}, expected_status=404)
test("Nonexistent practice_id submit", "POST", "/api/v1/practice/submit", token=student_token,
     body={"practice_id": "PR-DEADBEEF", "answers": [{"question_id": 1, "answer": "test"}]},
     expected_status=404)

# ── Authorization ──
print("\n[Authorization]")
test("Student accessing teacher endpoint (assign)", "POST", "/api/v1/practice/assign",
     token=student_token, body={"student_id": 1, "question_count": 3},
     expected_status=403)
test("Teacher accessing student tasks (should work)", "GET",
     "/api/v1/practice/student/2/tasks", token=teacher_token)

# ── Rate limiting & concurrency ──
print("\n[Race Condition / Duplicate]")
# Submit same practice twice
test("Duplicate review submit", "POST", "/api/v1/review/submit", token=student_token,
     body={"review_task_id": 1, "is_correct": True})  # Already submitted earlier

# ── Special characters in input ──
print("\n[Special Characters]")
test("SQL injection in query param", "GET",
     "/api/v1/practice/wrong/list?student_id=2&kp_filter=' OR 1=1--",
     token=student_token, expected_status=200)  # Should sanitize, return empty

# ── Summary ──
print("\n" + "=" * 60)
print(f"[Phase 4] Complete: {len(issues)} issues found")
for i in issues:
    print(f"  ❌ {i}")
print("=" * 60)
