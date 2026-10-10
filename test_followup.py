"""
FOLLOW-UP TEST (no AI, seconds): "and for 2024?", "what about Home?", "now by region".
Each one must be rewritten to the right complete question AND give the number
calculated independently in pandas. Complete questions must never be rewritten.

    python test_followup.py
"""
import warnings
warnings.filterwarnings("ignore")

import pandas as pd

import analyst_data
from ask_engine import AskEngine
from question_understanding import QuestionUnderstanding

passed, failed = 0, []


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


def close(a, b):
    return abs(float(a) - float(b)) <= 1e-6 * max(1, abs(float(b)))


def run_dataset(name, df, measure, date, dim_a, dim_b):

    # the AI is replaced by one that always says "total": the code must do the rest
    QuestionUnderstanding.understand = lambda self, q: dict(
        intent="total", column=measure, group_column=None, value_column=measure,
        filter_value=None, operation="sum",
    )

    stamps = pd.to_datetime(df[date], errors="coerce", dayfirst=False)
    years = sorted(stamps.dt.year.dropna().unique().astype(int))
    y1, y2 = (years[0], years[1]) if len(years) > 1 else (years[0], years[0])
    values_a = df[dim_a].value_counts().index.tolist()
    va, vb = str(values_a[0]), str(values_a[1])
    label = measure.replace("_", " ")
    word_a, word_b = dim_a.replace("_", " "), dim_b.replace("_", " ")

    def total(frame):
        return float(frame[measure].sum())

    def of_year(frame, y):
        return frame[stamps.loc[frame.index].dt.year == y]

    def of_value(frame, col, v):
        return frame[frame[col].astype(str).str.strip().str.lower() == v.lower()]

    def ask_chain(first, *follow):
        e = AskEngine(df.copy())
        out = [e.ask(first)]
        for f in follow:
            out.append(e.ask(f))
        return out

    # 1. a different year
    a1, a2 = ask_chain(f"What is the total {label} in {y1}?", f"and for {y2}?")
    check(a1["status"] == "success" and close(a1["result"], total(of_year(df, y1))), f"{name}: first question")
    check(a2["status"] == "success" and a2.get("rewritten_from") == f"and for {y2}?", f"{name}: year follow-up not rewritten ({a2.get('message')})")
    check(a2["status"] == "success" and close(a2["result"], total(of_year(df, y2))), f"{name}: year follow-up number")

    # 2. a different value of the same column
    a1, a2 = ask_chain(f"What is the total {label} for {va}?", f"what about {vb}?")
    check(a2["status"] == "success" and close(a2["result"], total(of_value(df, dim_a, vb))), f"{name}: value follow-up number")
    check(a2.get("question", "").lower().find(vb.lower()) >= 0 and va.lower() not in a2.get("question", "").lower(), f"{name}: value swap text {a2.get('question')}")

    # 3. add a filter to the question before
    a1, a2 = ask_chain(f"What is the total {label} in {y1}?", f"and for {va}?")
    expected = total(of_value(of_year(df, y1), dim_a, va))
    check(a2["status"] == "success" and close(a2["result"], expected), f"{name}: add-a-value follow-up {a2.get('message') or a2.get('result')}")

    # 4. a different split
    a1, a2 = ask_chain(f"What is the total {label} by {word_a}?", f"now by {word_b}")
    expected = df.groupby(dim_b)[measure].sum()
    ok = a2["status"] == "success" and isinstance(a2["result"], dict) and set(a2["result"]) == set(map(str, expected.index))
    check(ok and all(close(a2["result"][str(k)], v) for k, v in expected.items()), f"{name}: split follow-up {a2.get('message') or a2.get('question')}")

    # 5. a chain of follow-ups uses the rewritten question each time
    if len(years) > 2:
        a1, a2, a3 = ask_chain(f"What is the total {label} in {years[0]}?", f"and for {years[1]}?", f"and for {years[2]}?")
        check(a3["status"] == "success" and close(a3["result"], total(of_year(df, years[2]))), f"{name}: chained follow-ups")

    # 6. complete questions are never rewritten
    e = AskEngine(df.copy())
    e.ask(f"What is the total {label} in {y1}?")
    for q in [f"For {vb} what is the total {label}?", f"In {y2} what is the total {label}?",
              f"What is the total {label}?", f"By {word_b} what is the total {label}?"]:
        a = e.ask(q)
        check(a.get("rewritten_from") is None, f"{name}: a complete question was rewritten: {q!r} -> {a.get('question')!r}")

    # 7. no earlier question: nothing to refer to, so no guessing
    fresh = AskEngine(df.copy())
    a = fresh.ask("and for 2024?")
    check(a.get("rewritten_from") is None and not (a["status"] == "success" and a.get("question", "").startswith("What")), f"{name}: guessed a follow-up with no earlier question")


frames = {
    "ecommerce": (pd.read_csv("ecommerce_sales_34500.csv"), "total_amount", "order_date", "category", "region"),
}
retail, _ = analyst_data.retail()
frames["retail"] = (retail, "revenue", "order_date", "category", "region")

for name, args in frames.items():
    run_dataset(name, *args)


# ============================================================
# direct rules: what IS a follow-up, the month swap, and the cases that must NOT be rewritten
# ============================================================
import followup as fu

follow_yes = ["and for 2024?", "what about Home?", "now by region", "same for North", "and in March", "only for 2023", "how about South"]
follow_no = ["What is the total revenue?", "Show revenue by category", "Which category has the highest revenue?", "",
             "   ", "and for the Fashion category in 2024 please show me everything about it", "What about the total revenue for every single region in 2024 please",
             "total"]
for text in follow_yes:
    check(fu.is_followup(text), f"is_followup: {text!r} should be a follow-up")
for text in follow_no:
    check(not fu.is_followup(text), f"is_followup: {text!r} must NOT be a follow-up")

e_ret = AskEngine(retail.copy())

# a different month keeps the rest of the question
month_cases = [
    ("and for April?", "What is the total revenue in March 2024?", "what is the total revenue in april 2024?"),
    ("what about december", "How many orders in January 2024?", "how many orders in december 2024?"),
    ("and in FEBRUARY?", "What is the total revenue in June 2023?", "what is the total revenue in february 2023?"),
]
for short, previous, expected in month_cases:
    got = fu.rewrite(e_ret, short, previous)
    check(got is not None and got.lower() == expected, f"month swap: {short!r} after {previous!r} gave {got!r}")

# nothing to refer to, or not a follow-up: no rewrite
check(fu.rewrite(e_ret, "and for April?", None) is None, "rewrite: a follow-up with no earlier question was rewritten")
check(fu.rewrite(e_ret, "and for April?", "") is None, "rewrite: an empty earlier question was used")
check(fu.rewrite(e_ret, "What is the total revenue?", "What is the total revenue in March 2024?") is None, "rewrite: a complete question was rewritten")
check(fu.rewrite(e_ret, "and for April?", "What is the total revenue?") is None, "rewrite: a month was invented where the earlier question had none")
check(fu.rewrite(e_ret, "and for 2024?", "What is the total revenue?") is None, "rewrite: a year was invented where the earlier question had none")
check(fu.rewrite(e_ret, "and for April, May and June?", "What is the total revenue in March 2024?") is None, "rewrite: several months were squeezed into one")
# the words of a follow-up that are NOT understood stop the rewrite (no guessing)
check(fu.rewrite(e_ret, "and for 2024 in the moon?", "What is the total revenue in 2023?") is None, "rewrite: an extra unknown phrase was ignored")
check(fu.rewrite(e_ret, "and for Zanzibar?", "What is the total revenue for North?") is None, "rewrite: an unknown value was accepted")

print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed[:12]:
    print("  FAIL:", f)
