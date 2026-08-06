"""Verify exam question add (checklist) and view (previewDataList)"""
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
login = api("POST", "/auth/login", b={"phone":"13800000000","password":"demo123456"})
TOKEN = login["token"]
print("[1] Login OK")

# Create exam
exam = api("POST", "/exams", b={"name":"view-test","class_id":1,"exam_type":"monthly","exam_date":"2026-08-10"})
eid = exam["id"]
print(f"[2] Create exam {eid} OK")

# Generate 3 questions
gen = api("POST", "/questions/generate", b={
    "knowledge_points":["氧化还原反应"],"difficulty":"medium","quantity":3,"question_types":["choice","choice","fill_blank"]
})
qids = [q["id"] for q in gen["questions"]]
print(f"[3] Generated {len(qids)} questions OK")

# Add questions via query params (simulating checklist modal)
r = api("POST", f"/exams/{eid}/questions", q={"question_ids": qids})
added = r.get("added", 0)
print(f"[4] Added {added} questions OK")
assert added == 3

# View questions
qres = api("GET", f"/exams/{eid}/questions")
qs = qres.get("questions", qres.get("data",{}).get("questions", []))
print(f"[5] View: {len(qs)} questions OK")
assert len(qs) == 3

# Verify each question has required fields for previewDataList
for i, q in enumerate(qs):
    assert q.get("content"), f"Q{i+1} missing content"
    print(f"    Q{i+1}: type={q.get('question_type')} answer={q.get('answer','?')[:20]} content_len={len(q.get('content',''))}")

# Verify bank questions available for checklist
bank = api("GET", "/questions", q={"limit": "5"})
bankQs = bank.get("data", bank.get("items", []))
print(f"[6] Bank has {len(bankQs)} questions for checklist OK")

# Verify historical exams available
hist = api("GET", "/historical-exams", q={"limit": "5"})
histQs = hist.get("data", hist.get("items", []))
print(f"[7] History has {len(histQs)} exams for checklist OK")

print("\nALL PASSED")
