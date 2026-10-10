"""
WRONG-INTENT TEST (no AI needed, seconds)

Takes the generated questions of ANY dataset and makes the 'AI' collapse
every question into ONE calculation (always total / always average /
always count / always maximum / always minimum). The answer must then be
either right (the code repaired it) or a refusal. A confident wrong answer
is a bug.

    python test_wrong_intent.py amazon.csv
"""
import sys
import warnings; warnings.filterwarnings("ignore")
import copy
import pandas as pd
import auto_benchmark as ab
from ask_engine import AskEngine
from question_understanding import QuestionUnderstanding

path = sys.argv[1]
df = pd.read_csv(path)
engine = AskEngine(df)
df = engine.df
items = ab.generate_questions(df, engine, 120)

FORCED = {
    "total":   dict(intent="total", operation="sum"),
    "average": dict(intent="average", operation="average"),
    "count":   dict(intent="count", operation="row_count"),
    "maximum": dict(intent="maximum", operation="max"),
    "minimum": dict(intent="minimum", operation="min"),
    "missing": dict(intent="missing", operation="missing_count"),
    "duplicate": dict(intent="duplicate", operation="duplicate_count"),
}

measures = engine.dataset_understanding["measures"]

print(f"{path}: {len(items)} questions")
total_wrong = 0
for name, forced in FORCED.items():
    good = refused = wrong = 0
    shown = []
    for item in items:
        plan = copy.deepcopy(item.get("lazy") or item["plan"])
        if plan.get("intent") == forced["intent"]:
            pass                                    # the AI happens to be right
        else:
            value = plan.get("value_column") or plan.get("column")
            plan.update(forced, value_column=value, column=value if forced["intent"] != "count" else None,
                        group_column=None, filter_value=plan.get("filter_value"))
        QuestionUnderstanding.understand = lambda self, q, plan=plan: dict(plan)
        answer = engine.ask(item["question"])
        if answer["status"] != "success":
            refused += 1
        elif ab.matches(answer["result"], item["truth"](df)):
            good += 1
        else:
            wrong += 1
            shown.append((item["question"], answer["response"][:70]))
    total_wrong += wrong
    print(f"  AI always says {name:8s}  correct {good:3d}   refused {refused:3d}   WRONG {wrong}")
    for q, r in shown[:4]:
        print(f"        WRONG: {q[:60]:60s} -> {r}")
# the AI answers on ANOTHER number column than the question is about
good = refused = wrong = 0
shown = []
for item in items:
    plan = copy.deepcopy(item.get("lazy") or item["plan"])
    value = plan.get("value_column") or plan.get("column")
    if plan.get("intent") in ("total", "average", "maximum", "minimum", "top", "bottom", "trend") and value in measures and len(measures) > 1:
        other = next(m for m in measures if m != value)
        plan.update(value_column=other, column=other)
    QuestionUnderstanding.understand = lambda self, q, plan=plan: dict(plan)
    answer = engine.ask(item["question"])
    if answer["status"] != "success":
        refused += 1
    elif ab.matches(answer["result"], item["truth"](df)):
        good += 1
    else:
        wrong += 1
        shown.append((item["question"], answer["response"][:70]))
total_wrong += wrong
print(f"  AI uses ANOTHER column  correct {good:3d}   refused {refused:3d}   WRONG {wrong}")
for q, r in shown[:4]:
    print(f"        WRONG: {q[:60]:60s} -> {r}")
# ---- four more mistakes: the AI says "unique" / "top" / "bottom" / "trend" for everything
understanding = engine.dataset_understanding
identifiers = set(engine.profile.get("identifier_columns", []))
measures = understanding["measures"]
dims = [c for c in understanding["dimension_values"] if c not in identifiers]
dates = understanding["date_columns"]


def forced_group_plan(kind, plan):
    value = plan.get("value_column") or plan.get("column")
    if value not in measures:
        value = measures[0] if measures else None
    base = dict(plan, filter_value=plan.get("filter_value"))
    if kind == "unique":
        column = dims[0] if dims else value
        return dict(base, intent="unique", operation="unique", column=column, value_column=column, group_column=None)
    if kind in ("top", "bottom"):
        if not dims or value is None:
            return None
        return dict(base, intent=kind, operation="group_sum", column=value, value_column=value, group_column=dims[0])
    if kind == "trend":
        if not dates or value is None:
            return None
        return dict(base, intent="trend", operation="time_series", column=value, value_column=value, group_column=dates[0])


for kind in ("unique", "top", "bottom", "trend"):
    good = refused = wrong = skipped = 0
    shown = []
    for item in items:
        original = item.get("lazy") or item["plan"]
        if original.get("intent") == kind:
            plan = copy.deepcopy(original)
        else:
            plan = forced_group_plan(kind, copy.deepcopy(original))
            if plan is None:
                skipped += 1
                continue
        QuestionUnderstanding.understand = lambda self, q, plan=plan: dict(plan)
        answer = engine.ask(item["question"])
        if answer["status"] != "success":
            refused += 1
        elif ab.matches(answer["result"], item["truth"](df)):
            good += 1
        else:
            wrong += 1
            shown.append((item["question"], answer["response"][:70]))
    total_wrong += wrong
    print(f"  AI always says {kind:8s}  correct {good:3d}   refused {refused:3d}   WRONG {wrong}")
    for q, r in shown[:4]:
        print(f"        WRONG: {q[:60]:60s} -> {r}")

print(f"  total confident-wrong: {total_wrong}")