"""
Checks the "I understood" line for every generated question of a dataset:
every filter, condition and date in the plan must be named, and so must the
number column. (Run: python test_understanding.py amazon.csv)
"""
import sys, warnings; warnings.filterwarnings("ignore")
import pandas as pd
import auto_benchmark as ab
import understanding
from ask_engine import AskEngine
from filters import effective_filters
from question_understanding import QuestionUnderstanding
from dashboard import humanize

df = pd.read_csv(sys.argv[1])
engine = AskEngine(df)
items = ab.generate_questions(engine.df, engine, 120)
oracle = {i["question"]: (i.get("lazy") or i["plan"]) for i in items}
QuestionUnderstanding.understand = lambda self, q: dict(oracle[q])

checked = bad = 0
for item in items:
    answer = engine.ask(item["question"])
    if answer["status"] != "success":
        continue
    plan = answer["plan"]
    text = " | ".join(c["text"].lower() for c in understanding.describe(plan))
    checked += 1
    problems = []
    for f in effective_filters(plan):
        if str(f.get("label") or f["value"]).lower() not in text:
            problems.append(f"filter {f}")
    for c in plan.get("conditions") or []:
        if str(c["label"]).lower() not in text:
            problems.append(f"condition {c['label']}")
    if (plan.get("date_filter") or {}).get("label") and plan["date_filter"]["label"].lower() not in text:
        problems.append("date")
    if plan["intent"] in ("total", "average", "maximum", "minimum") and plan.get("value_column") and humanize(plan["value_column"]).lower() not in text:
        problems.append("measure")
    if not text:
        problems.append("empty")
    if problems:
        bad += 1
        print("  PROBLEM:", item["question"], problems, "->", text)
print(f"{sys.argv[1]}: {checked} answers checked, {bad} with a missing detail")
