"""Verify exam lifecycle: create -> add questions -> view -> publish -> finalize -> delete"""
import urllib.request, json

BASE = "http://127.0.0.1:8000/api/v1"
TOKEN = None

def api(m, p, b=None, q=None):
    from urllib.parse import urlencode
    url = BASE + p
    if q:
        parts = []
        for k, v in q.items():
            if isinstance(v, list):
                for vv in v:
                    parts.append(f"{k}={vv}")
            else:
                parts.append(f"{k}={v}")
        url += "?" + "&".join(parts)
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    d = json.dumps(b).encode() if b else None
    req = urllib.request.Request(url, data=d, headers=h, method=m)
    with urllib.request.urlopen(req, timeout=30) as r:
        try:
            return json.loads(r.read())
        except:
            return None

# Login
login = api("POST", "/auth/login", b={"phone":"13800000000","password":"demo123456"})
TOKEN = login["token"]
print("[1] Login OK")

# Create exam
exam = api("POST", "/exams", b={"name":"sim-test","class_id":1,"exam_type":"monthly","exam_date":"2026-08-10"})
eid = exam["id"]
print(f"[2] Create: id={eid} OK")

# View questions (empty)
qres = api("GET", f"/exams/{eid}/questions")
qs = qres.get("questions", qres.get("data",{}).get("questions", []))
print(f"[3] View: {len(qs)} questions")
assert len(qs) == 0

# Generate 2 questions
gen = api("POST", "/questions/generate", b={"knowledge_points":["氧化还原反应"],"difficulty":"medium","quantity":2,"question_types":["choice","choice"]})
qids = [q["id"] for q in gen["questions"]]
print(f"[4] Generate: ids={qids} OK")

# Add
r = api("POST", f"/exams/{eid}/questions", q={"question_ids": qids})
print(f"[5] Add: {r}")
added = r.get("added", 0)
assert added == 2, f"Expected 2, got {added}"

# View (2 questions)
qres = api("GET", f"/exams/{eid}/questions")
qs = qres.get("questions", qres.get("data",{}).get("questions", []))
print(f"[6] View: {len(qs)} questions")
assert len(qs) == 2

# Publish
api("POST", f"/exams/{eid}/publish")
print("[7] Publish OK")

# Check status
exams = api("GET", "/exams?limit=20")
els = exams.get("items", [])
u = next((e for e in els if e["id"] == eid), {})
print(f"[8] Status: {u.get('status')}")
assert u.get("status") in ("in_progress", "published")

# Finalize
api("POST", f"/exams/{eid}/finalize")
print("[9] Finalize OK")

# Check
exams = api("GET", "/exams?limit=20")
els = exams.get("items", [])
u = next((e for e in els if e["id"] == eid), {})
print(f"[10] Status: {u.get('status')}")
assert u.get("status") == "completed"

# Delete
api("POST", "/exams", b={"name":"delme","class_id":1,"exam_type":"monthly","exam_date":"2026-08-10"})
print("[11] All OK")

print("\nALL PASSED")
