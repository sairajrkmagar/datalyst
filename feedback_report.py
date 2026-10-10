"""
FEEDBACK REPORT: what real users found wrong.

    python feedback_report.py            list the problems
    python feedback_report.py --csv      also write feedback_problems.csv (send me this file)
"""
import csv
import sys

import feedback

entries = feedback.read_all()
s = feedback.summary(entries)

print(f"{s['total']} reactions: {s['up']} helpful, {s['down']} not right "
      f"({s['refused_but_wanted']} of those were refusals the person wanted answered)\n")

problems = [e for e in entries if e["rating"] == "down"]

for e in problems[:40]:
    kind = "REFUSED " if e.get("status") == "error" else "WRONG?  "
    print(f"{kind} [{e.get('dataset', '')[:24]}] {e['question']}")
    print(f"         said: {e.get('said', '')[:110]}")
    if e.get("comment"):
        print(f"         note: {e['comment']}")

if "--csv" in sys.argv:
    with open("feedback_problems.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "dataset", "question", "status", "said", "intent", "how", "comment", "columns"])
        writer.writeheader()
        for e in problems:
            writer.writerow({k: (", ".join(e[k]) if k == "columns" else e.get(k, "")) for k in writer.fieldnames})
    print("\nwritten: feedback_problems.csv")
