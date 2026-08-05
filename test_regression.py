"""Regression test: Login -> Generate -> Save to Bank -> Verify"""
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
import json, sys

BASE = "http://127.0.0.1:8000/api/v1"
passed = 0
failed = 0

def check(step, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {step}")
    else:
        failed += 1
        print(f"  [FAIL] {step} -- {detail}")
        if failed >= 1:  # stop on first failure to debug
            pass

def api(method, path, token=None, body=None, params=None):
    url = BASE + path
    if params:
        url += "?" + urlencode(params)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=90) as r:
            return json.loads(r.read())
    except HTTPError as e:
        err = json.loads(e.read())
        print(f"  API ERROR {method} {path}: {err}")
        return err

print("=" * 50)
print("Step 1: Login")
login = api("POST", "/auth/login", body={"phone": "13800000000", "password": "demo123456"})
check("login returns token", login.get("token") is not None, str(login)[:200])
token = login.get("token", "")
if not token:
    print("ABORTING: no token")
    sys.exit(1)

print("\nStep 2: Generate questions")
gen = api("POST", "/questions/generate", token=token, body={
    "knowledge_points": ["氧化还原反应"],
    "difficulty": "medium",
    "quantity": 2,
    "question_types": ["choice", "choice"]
})
check("generate success", gen.get("success") is True, str(gen)[:200])
check("has questions", len(gen.get("questions", [])) > 0)
questions = gen.get("questions", [])
for i, q in enumerate(questions):
    print(f"  Q{i+1}: id={q.get('id')}, type={q.get('question_type')}, audit={q.get('audit_status')}")
check("question has id", questions[0].get("id") is not None) if questions else None

if not questions:
    print("ABORTING: no questions generated")
    sys.exit(1)

print("\nStep 3: Create bank folder")
bank = api("POST", "/question-sets", token=token, body={"name": "REGRESSION-TEST"})
check("folder created", bank.get("id") is not None, str(bank)[:200])
folder_id = bank.get("id")
if not folder_id:
    print("ABORTING: no folder id")
    sys.exit(1)

print("\nStep 4: Add questions to folder")
added = 0
for i, q in enumerate(questions):
    r = api("POST", f"/question-sets/{folder_id}/items", token=token, body={
        "question_set_id": folder_id,
        "question_id": q["id"],
        "sort_order": i + 1
    })
    ok = r.get("id") is not None
    check(f"add Q{i+1} to folder", ok, str(r)[:200])
    if ok: added += 1

check("all questions added", added == len(questions))

print("\nStep 5: Verify folder items with content")
items = api("GET", f"/question-sets/{folder_id}/items", token=token)
item_list = items if isinstance(items, list) else items.get("data", items.get("items", []))
check("items returned", len(item_list) > 0, f"items={item_list}")
check("correct count", len(item_list) == len(questions), f"expected {len(questions)}, got {len(item_list)}")

if item_list:
    item = item_list[0]
    print(f"  Item keys: {list(item.keys())}")
    check("has content", item.get("content") is not None and len(item.get("content", "")) > 0, f"content='{item.get('content','')}'")
    check("has question_type", item.get("question_type") is not None, f"type={item.get('question_type')}")
    check("has difficulty", item.get("difficulty") is not None, f"diff={item.get('difficulty')}")

print("\n" + "=" * 50)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL TESTS PASSED")
else:
    print(f"{failed} FAILURES")
    sys.exit(1)
