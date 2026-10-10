"""FEEDBACK LOG TEST (seconds): saves, reads back, survives damage, never stores rows."""
import json, os, tempfile, threading
import feedback as fb

passed, failed = 0, []
def check(ok, message):
    global passed
    if ok: passed += 1
    else: failed.append(message)

path = os.path.join(tempfile.mkdtemp(), "log.jsonl")
ok_answer = {"status": "success", "response": "Total revenue is 5,900,000.", "plan": {"intent": "advanced", "advanced": {"kind": "median"}}}
bad_answer = {"status": "error", "message": "I could not match 'wages' to anything in your data."}

e1 = fb.record("What is the median revenue?", ok_answer, "up", "sales.csv", ["order_id", "revenue"], path=path)
e2 = fb.record("total wages", bad_answer, "down", "hr.csv", ["Monthly Salary"], comment="should use salary", path=path)
e3 = fb.record("Ünïcode question 你好 😀 " + "x" * 5000, ok_answer, "down", "a.csv", [f"c{i}" for i in range(500)], comment="y" * 5000, path=path)
check(e1["how"] == "median" and e2["how"] is None, "kind of answer")
check(len(e3["question"]) <= fb.MAX_TEXT and len(e3["comment"]) <= 500 and len(e3["columns"]) <= 80, "text is capped")

with open(path, "a", encoding="utf-8") as h:
    h.write("this line is damaged\n{\"rating\": \"maybe\"}\n\n[1,2]\n")
rows = fb.read_all(path)
check(len(rows) == 3, f"damaged lines skipped: {len(rows)} entries")
s = fb.summary(rows)
check(s == {"total": 3, "up": 1, "down": 2, "refused_but_wanted": 1}, f"summary {s}")
check(fb.read_all(path + ".missing") == [], "no file is not an error")

try:
    fb.record("q", ok_answer, "meh", path=path); check(False, "a bad rating was accepted")
except ValueError:
    check(True, "")

def worker(i):
    for j in range(20): fb.record(f"q{i}-{j}", ok_answer, "up", path=path)
threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
[t.start() for t in threads]; [t.join() for t in threads]
check(len(fb.read_all(path)) == 3 + 120, f"parallel writes: {len(fb.read_all(path))}")

# no rows of data are ever written: only what was passed (question, text, column NAMES)
raw = open(path, encoding="utf-8").read()
check("order_id" in raw and "SECRET-ROW-VALUE" not in raw, "only names are stored")
print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed[:6]: print("  FAIL:", f)
