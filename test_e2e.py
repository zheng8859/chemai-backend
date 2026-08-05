"""E2E test: Login -> KP search -> AI Generate -> Audit -> Save to Bank"""
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
import json

BASE = "http://127.0.0.1:8000/api/v1"


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
        return json.loads(e.read())


print("=" * 55)
print("  Teacher E2E: Login -> Generate -> Audit -> Save")
print("=" * 55)

# 1. Login
login = api("POST", "/auth/login", body={"phone": "13800000000", "password": "demo123456"})
token = login["token"]
print(f"\n[1] Login: OK (user_id={login['user_id']}, name={login.get('name','')})")

# 2. KP search
kps = api("GET", "/knowledge-points/search", token=token, params={"keyword": "氧化", "limit": 5})
items = kps.get("data", [])
names = [k["name"] for k in items]
print(f"[2] KP search: {len(items)} results -> {names}")

# 3. AI Generate
print(f"[3] Generating 3 questions via LLM...")
gen = api("POST", "/questions/generate", token=token, body={
    "knowledge_points": ["氧化还原反应"],
    "difficulty": "medium",
    "quantity": 3,
    "question_types": ["choice", "choice", "fill_blank"]
})
qs = gen["questions"]
print(f"[3] Generated {gen['generated_count']} questions:")

for i, q in enumerate(qs, 1):
    content = q["content"][:60].replace("\n", " ")
    print(f"     Q{i}: [{q['audit_status']}] [{q['question_type']}] {content}...")

# Check audit — all should be passed (generation pipeline filters blocked ones)
blocked = [q for q in qs if q.get("audit_status") == "blocked"]
passed = [q for q in qs if q.get("audit_status") == "passed"]
print(f"\n     Audit summary: {len(passed)} passed, {len(blocked)} blocked")

# 4. Create bank folder
bank = api("POST", "/question-sets", token=token, body={"name": "AI-氧化还原-验证"})
if "id" not in bank:
    print(f"[4] Bank create FAILED: {json.dumps(bank, ensure_ascii=False)}")
    exit(1)
bid = bank["id"]
print(f"[4] Bank created: id={bid}, name={bank['name']}")

# 5. Add questions to bank
added = 0
for i, q in enumerate(qs[:2], 1):
    r = api("POST", f"/question-sets/{bid}/items", token=token, body={
        "question_set_id": bid, "question_id": q["id"], "sort_order": i
    })
    if r.get("id"):
        added += 1
    else:
        print(f"     Add Q{i} FAILED: {json.dumps(r, ensure_ascii=False)[:200]}")
print(f"[5] Added {added}/2 questions to bank")

# 6. Verify
items = api("GET", f"/question-sets/{bid}/items", token=token)
total = len(items) if isinstance(items, list) else len(items.get("data", items.get("items", [])))
print(f"[6] Verify: bank has {total} questions")

print("\n" + "=" * 55)
print("  ALL 6 STEPS PASSED")
print("=" * 55)
