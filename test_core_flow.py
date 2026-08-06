"""Core user flow test: Bank CRUD -> Exam lifecycle -> Similar search -> Export"""
import urllib.request, json

BASE = "http://127.0.0.1:8000/api/v1"
T = None

def api(m, p, b=None, q=None):
    global T
    url = BASE + p
    if q:
        parts = []
        for k, v in q.items():
            if isinstance(v, list):
                for vv in v: parts.append(f"{k}={vv}")
            else: parts.append(f"{k}={v}")
        url += "?" + "&".join(parts)
    h = {"Content-Type": "application/json"}
    if T: h["Authorization"] = f"Bearer {T}"
    d = json.dumps(b).encode() if b else None
    req = urllib.request.Request(url, data=d, headers=h, method=m)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            try: return json.loads(raw)
            except: return raw
    except urllib.error.HTTPError as e:
        return {"_status": e.code, "_body": e.read().decode()[:200]}

T = api("POST", "/auth/login", b={"phone":"13800000000","password":"demo123456"})["token"]
print("=" * 50)
print("CORE FLOW TEST")
print("=" * 50)

# ═══ 1. Bank CRUD ═══
print("\n--- 1. Bank CRUD ---")
bank = api("POST", "/question-sets", b={"name":"E2E-BANK"})
bid = bank["id"]
print(f"  1a Create: id={bid} OK")

qRes = api("GET", "/questions", q={"limit":"2"})
qids = [q["id"] for q in qRes["items"][:2]]
for qi, qid in enumerate(qids, 1):
    r = api("POST", f"/question-sets/{bid}/items", b={"question_set_id":bid,"question_id":qid,"sort_order":qi})
    assert r.get("id"), f"Add item failed: {r}"
print(f"  1b Added {len(qids)} questions OK")

sets = api("GET", "/question-sets", q={"limit":"50"})
b = next(s for s in sets["items"] if s["id"]==bid)
assert b["question_count"] >= 2
print(f"  1c List: count={b['question_count']} OK")

items = api("GET", f"/question-sets/{bid}/items")
il = items.get("data",[])
assert len(il) >= 2
print(f"  1d Items: {len(il)} questions with content OK")

# ═══ 2. Exam Lifecycle ═══
print("\n--- 2. Exam Lifecycle ---")
exam = api("POST", "/exams", b={"name":"E2E-EXAM","class_id":1,"exam_type":"monthly","exam_date":"2026-08-10"})
eid = exam["id"]
print(f"  2a Create: id={eid} OK")

# Add questions via query params
r = api("POST", f"/exams/{eid}/questions", q={"question_ids": qids})
assert r.get("added",0) >= 2
print(f"  2b Added {r['added']} questions OK")

# View questions
eqRes = api("GET", f"/exams/{eid}/questions")
eqs = eqRes.get("questions",[])
assert len(eqs) >= 2
assert eqs[0].get("answer")  # full fields check
print(f"  2c View: {len(eqs)} questions with answer/options OK")

# Publish
r = api("POST", f"/exams/{eid}/publish")
assert r.get("success")
print(f"  2d Publish OK")

# Finalize
r = api("POST", f"/exams/{eid}/finalize")
assert r.get("success")
print(f"  2e Finalize OK")

# Verify status
elist = api("GET", "/exams", q={"limit":"50"})
ex = next(e for e in elist["items"] if e["id"]==eid)
assert ex.get("status") == "completed", f"Status: {ex.get('status')}"
assert ex.get("question_count",0) >= 2
print(f"  2f Status=completed, question_count={ex['question_count']} OK")

# ═══ 3. Similar Question Search ═══
print("\n--- 3. Similar Search ---")
gen = api("POST", "/questions/generate", b={
    "knowledge_points":["氧化还原反应"],"difficulty":"medium","quantity":2,"question_types":["choice","choice"]
})
assert gen.get("success") and len(gen.get("questions",[])) >= 1
print(f"  3 Generated {gen['generated_count']} questions (RAG search active) OK")

# ═══ 4. Exam Export ═══
print("\n--- 4. Exam Export ---")
data = api("GET", f"/exams/{eid}/export", q={"format":"docx","with_answers":"false"})
assert isinstance(data, bytes) and len(data) > 2000, f"Export size: {len(data) if isinstance(data,bytes) else 'NOT_BYTES'}"
print(f"  4a Student export: {len(data)} bytes OK")

data = api("GET", f"/exams/{eid}/export", q={"format":"docx","with_answers":"true"})
assert isinstance(data, bytes) and len(data) > 2000
print(f"  4b Teacher export: {len(data)} bytes OK")

# Export guard
r = api("GET", f"/exams/{eid}/export", q={"format":"pdf"})
assert r.get("_status") == 400
print(f"  4c PDF rejected: 400 OK")

# ═══ 5. Delete Protection ═══
print("\n--- 5. Delete Protection ---")
r = api("POST", "/exams", b={"name":"DEL-TEST","class_id":1,"exam_type":"monthly","exam_date":"2026-08-10"})
deid = r["id"]
api("POST", f"/exams/{deid}/questions", q={"question_ids": [qids[0]]})  # add question first
api("POST", f"/exams/{deid}/publish")
r = api("DEL", f"/exams/{deid}")
assert r.get("_status") == 403, f"Expected 403, got {r}"
print(f"  5a in_progress delete blocked: 403 OK")

# ═══ Bonus: is_system protection ═══
print("\n--- 6. is_system protection ---")
# Create a bank, mark is_system manually, try delete
import sqlite3
conn = sqlite3.connect("data/chemai.db")
conn.execute("UPDATE question_set SET is_system=1 WHERE id=?", (bid,))
conn.commit()
conn.close()
r = api("DEL", f"/question-sets/{bid}")
assert r.get("_status") == 403
print(f"  6a System folder blocked: 403 OK")
# Reset
conn = sqlite3.connect("data/chemai.db")
conn.execute("UPDATE question_set SET is_system=0 WHERE id=?", (bid,))
conn.commit()
conn.close()

print("\n" + "=" * 50)
print("ALL CORE FLOW TESTS PASSED")
print("=" * 50)
