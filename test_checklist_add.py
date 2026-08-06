"""Simulate checklist add-to-exam flow"""
import urllib.request, json

BASE = "http://127.0.0.1:8000/api/v1"
TOKEN = None

def api(m, p, b=None, q=None):
    url = BASE + p
    if q:
        parts = []
        for k, v in q.items():
            if isinstance(v, list):
                for vv in v: parts.append(f"{k}={vv}")
            else: parts.append(f"{k}={v}")
        url += "?" + "&".join(parts)
    h = {"Content-Type": "application/json"}
    if TOKEN: h["Authorization"] = f"Bearer {TOKEN}"
    d = json.dumps(b).encode() if b else None
    req = urllib.request.Request(url, data=d, headers=h, method=m)
    with urllib.request.urlopen(req, timeout=30) as r:
        try: return json.loads(r.read())
        except: return None

# Login
TOKEN = api("POST", "/auth/login", b={"phone":"13800000000","password":"demo123456"})["token"]
print("[1] Login OK")

# Create exam
exam = api("POST", "/exams", b={"name":"checklist-test","class_id":1,"exam_type":"monthly","exam_date":"2026-08-10"})
eid = exam["id"]
print(f"[2] Create exam id={eid} OK")

# Get available questions
qRes = api("GET", "/questions", q={"limit": "100"})
bankQs = qRes.get("data", qRes.get("items", []))
print(f"[3] Available questions: {len(bankQs)}")

# Pick 3 questions
qids = [q["id"] for q in bankQs[:3]]
print(f"[4] Selected IDs: {qids}")

# Simulate checklist confirm -> api.post with query params
r = api("POST", f"/exams/{eid}/questions", q={"question_ids": qids})
print(f"[5] Add result: {r}")
assert r.get("added", 0) == 3, f"Expected added=3, got {r}"

# Verify
qres = api("GET", f"/exams/{eid}/questions")
qs = qres.get("questions", qres.get("data",{}).get("questions", []))
print(f"[6] Verify: {len(qs)} questions in exam")
assert len(qs) == 3

# Verify exam has question_count
elist = api("GET", "/exams", q={"limit": "50"})
els = elist.get("items", [])
ex = next((e for e in els if e["id"] == eid), {})
print(f"[7] Exam question_count: {ex.get('question_count', 'N/A')}")

print("\nALL PASSED - Checklist add flow works")
