"""
CLARIFICATION TEST (no AI, seconds): every suggested button must be an honest one.
For each refusal we can cause, the suggestion must appear, and CLICKING it (asking
its question) must give the number calculated independently in pandas.

    python test_clarify.py
"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import analyst_data
import clarify
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


def ai_says(**plan):
    base = dict(intent="total", column=None, group_column=None, value_column=None, filter_value=None, operation="sum")
    base.update(plan)
    QuestionUnderstanding.understand = lambda self, q: dict(base)


def refused(engine, question):
    a = engine.ask(question)
    return a if a["status"] == "error" else None


def typo(word):
    """One letter missing from the middle."""
    mid = len(word) // 2
    return word[:mid] + word[mid + 1:]


def run(name, df, measure, dim):
    e = AskEngine(df.copy())
    label = clarify.label(e, measure)
    words_dim = dim.replace("_", " ")

    # ---- 1. a misspelt VALUE
    value = str(df[dim].value_counts().index[0])
    if len(value) >= 6 and " " not in value:
        ai_says(column=measure, value_column=measure)
        q = f"What is the total {label} for {typo(value)}?"
        a = refused(e, q)
        if a is not None:
            s = clarify.suggest(e, q, a["message"])
            check(s is not None and any(o["label"] == value for o in s["options"]), f"{name}: no 'did you mean {value}' for {q!r} ({a['message'][:50]})")
            if s:
                pick = next((o for o in s["options"] if o["label"] == value), None)
                if pick:
                    b = e.ask(pick["question"])
                    truth = df[df[dim].astype(str).str.strip().str.lower() == value.lower()][measure].sum()
                    check(b["status"] == "success" and close(b["result"], truth), f"{name}: clicking {value!r} did not give the right total ({b.get('message') or b.get('result')})")

    # ---- 2. a misspelt COLUMN name
    first = label.split()[0]
    if len(first) >= 6:
        ai_says(column=measure, value_column=measure)
        q = f"What is the total {typo(first)}?"
        a = refused(e, q)
        if a is not None:
            s = clarify.suggest(e, q, a["message"])
            check(s is not None and any(label in o["label"] or o["label"] in label for o in s["options"]), f"{name}: no column suggestion for {q!r}")
            if s:
                b = e.ask(s["options"][0]["question"])
                check(b["status"] == "success", f"{name}: clicking the column suggestion failed: {b.get('message')}")

    # ---- 3. each "which number?" refusal: the wording of every choice is tested directly
    top_value = str(df[dim].value_counts().index[0])
    templates = [
        ("Which number should I rank by? Please name it, for example 'top 5 by revenue'.", f"Which {words_dim} is the best?", "rank"),
        ("Which number should I take the share of? Please name it, for example 'share of revenue'.", f"What share comes from {top_value}?", "share"),
        ("Which number should I show by category? Please name it.", f"Show by {words_dim}", "show"),
    ]
    for message, q, kind in templates:
        s = clarify.suggest(e, q, message)
        check(s is not None and len(s["options"]) >= 1, f"{name}: no measure choices for the {kind} refusal")
        if not s:
            continue
        pick = s["options"][0]
        col = next((m for m in clarify.measures_of(e) if clarify.label(e, m) == pick["label"]), None)
        check(col is not None and pick["label"].lower() in pick["question"].lower(), f"{name}: the {kind} choice does not name the number: {pick['question']!r}")
        if kind == "rank":
            ai_says(intent="top", group_column=dim, operation="group_sum")
        else:
            ai_says(column=col, value_column=col)
        b = e.ask(pick["question"])
        check(b["status"] == "success", f"{name}: clicking the {kind} choice {pick['question']!r} failed: {b.get('message')}")
        if b["status"] == "success" and kind == "rank":
            best = df.groupby(dim)[col].sum().sort_values(ascending=False)
            check(str(b["result"][0]).lower() == str(best.index[0]).lower() and close(b["result"][1], best.iloc[0]), f"{name}: rank choice gave the wrong top: {b['result']}")
        if b["status"] == "success" and kind == "share":
            truth = df[df[dim].astype(str).str.lower() == top_value.lower()][col].sum() / df[col].sum() * 100
            check(close(b["result"], truth), f"{name}: share choice gave {b['result']} not {truth}")
        if b["status"] == "success" and kind == "show":
            truth = df.groupby(dim)[col].sum()
            check(isinstance(b["result"], dict) and all(close(b["result"][str(k)], v) for k, v in truth.items()), f"{name}: show-by choice gave the wrong table")

    # ---- 4. a statistic without a number column
    ai_says()
    q = "What is the median?"
    a = refused(e, q)
    check(a is not None, f"{name}: 'What is the median?' should be refused")
    if a is not None:
        s = clarify.suggest(e, q, a["message"])
        check(s is not None and s["options"], f"{name}: no choices for the median")
        if s:
            opt = next((o for o in s["options"] if o["label"] == label), s["options"][0])
            b = e.ask(opt["question"])
            col = next((m for m in clarify.measures_of(e) if clarify.label(e, m) == opt["label"]), None)
            check(b["status"] == "success" and col is not None and close(b["result"], df[col].median()), f"{name}: clicking {opt['question']!r}: {b.get('message') or b.get('result')}")

    # ---- 5. nothing honest to offer
    for message in ["I could not tell whether you want a ranking or a single number. Please rephrase.",
                    "I do not forecast the future.", "The file has no date column."]:
        check(clarify.suggest(e, "anything", message) is None, f"{name}: offered a button for {message[:40]!r}")

    # ---- 6. the buttons are well formed
    s = clarify.suggest(e, "What is the median?", "Which number column do you mean? Please name it.")
    if s:
        questions = [o["question"] for o in s["options"]]
        check(len(set(questions)) == len(questions) and len(questions) <= clarify.MAX_OPTIONS and all(q.strip() for q in questions), f"{name}: options not unique / too many")


# ---- a value that lives in two columns
def run_ambiguous():
    rng = np.random.default_rng(8)
    n = 600
    df = pd.DataFrame({
        "ship_city": rng.choice(["Paris", "Rome", "Oslo"], n), "bill_city": rng.choice(["Paris", "Berlin", "Madrid"], n),
        "sales": rng.integers(10, 500, n),
    })
    e = AskEngine(df)
    ai_says(column="sales", value_column="sales")
    q = "What is the total sales for Paris?"
    a = refused(e, q)
    check(a is not None and "more than one column" in a["message"], f"ambiguous: expected the two-column refusal, got {a and a['message'][:60]}")
    if a:
        s = clarify.suggest(e, q, a["message"])
        check(s is not None and len(s["options"]) == 2, "ambiguous: expected two choices")
        if s:
            truths = {"ship city": df[df.ship_city == "Paris"].sales.sum(), "bill city": df[df.bill_city == "Paris"].sales.sum()}
            for option in s["options"]:
                owner = option["label"].split(":")[0]
                b = e.ask(option["question"])
                check(b["status"] == "success" and close(b["result"], truths[owner]), f"ambiguous: {option['question']!r} -> {b.get('message') or b.get('result')}")


def run_catalog():
    """A list of products (prices and ratings), not sales: no revenue column exists."""

    rng = np.random.default_rng(12)
    n = 400
    df = pd.DataFrame({
        "product_name": [f"Item {i}" for i in range(n)], "category": rng.choice(["Cables", "Phones", "Audio"], n),
        "discounted_price": rng.integers(100, 5000, n).astype(float), "actual_price": rng.integers(200, 9000, n).astype(float),
        "rating": rng.uniform(2, 5, n).round(1), "rating_count": rng.integers(1, 900, n),
    })
    e = AskEngine(df)
    ai_says(column="discounted_price", value_column="discounted_price")
    q = "What is the total revenue?"
    a = refused(e, q)
    check(a is not None, "catalog: 'total revenue' should be refused on a file without revenue")
    if a is None:
        return
    s = clarify.suggest(e, q, a["message"])
    check(s is not None and "no" in s["prompt"].lower() and "column" in s["prompt"].lower(), "catalog: the prompt should say the file has no revenue column")
    labels = [o["label"] for o in (s or {"options": []})["options"]]
    check("discounted price" in labels and "actual price" in labels, f"catalog: amount columns not offered: {labels}")
    check(not any("rating" in l for l in labels), f"catalog: a rating was offered as an amount: {labels}")
    for option in (s or {"options": []})["options"]:
        col = option["label"].replace(" ", "_")
        b = e.ask(option["question"])
        check(b["status"] == "success" and close(b["result"], df[col].sum()), f"catalog: clicking {option['question']!r} -> {b.get('message') or b.get('result')}")
    # a file that DOES have revenue keeps working as before
    sales = pd.DataFrame({"region": ["N", "S"] * 50, "revenue": range(100)})
    e2 = AskEngine(sales)
    ai_says(column="revenue", value_column="revenue")
    check(e2.ask("What is the total revenue?")["status"] == "success", "catalog: a real revenue column stopped working")


ecommerce = pd.read_csv("ecommerce_sales_34500.csv")
run("ecommerce", ecommerce, "total_amount", "category")
retail, _ = analyst_data.retail()
run("retail", retail, "revenue", "category")
for builder, measure, dim in [("hr", "Monthly Salary", "Department"), ("saas", "mrr", "plan"), ("ops", "cost", "carrier"), ("marketing", "revenue", "campaign")]:
    frame, _ = analyst_data.BUILDERS[builder]()
    run(builder, frame, measure, dim)
run_ambiguous()
run_catalog()


# ============================================================
# synonyms, de-duplication, "Percent of what?", and when NOT to offer a button
# ============================================================
def mini_engine():
    rng = np.random.default_rng(3)
    n = 300
    return AskEngine(pd.DataFrame({
        "Monthly Salary": rng.integers(2000, 9000, n), "Revenue": rng.integers(100, 900, n),
        "Region": rng.choice(["North", "South", "East"], n), "Department": rng.choice(["Sales", "Ops", "HR", "IT"], n),
        "Customer ID": [f"C{i % 90}" for i in range(n)],
    }))


mini = mini_engine()
unmatched = lambda word: f"I could not match '{word}' to anything in your data, so I would be answering a different question than the one you asked."

# another name for a column leads to that column
for word, wanted in {"wages": "monthly salary", "payroll": "monthly salary", "pay": "monthly salary", "salaries": "monthly salary",
                     "earnings": "revenue", "turnover": "revenue", "clients": "customer id", "area": "region"}.items():
    s = clarify.suggest(mini, f"What is the total {word}?", unmatched(word))
    labels = [o["label"].lower() for o in (s or {"options": []})["options"]]
    check(wanted in labels, f"synonym: '{word}' should offer '{wanted}', got {labels}")

# a misspelt word that matches a column in two ways is offered ONCE
s = clarify.suggest(mini, "What is the total revnue?", unmatched("revnue"))
labels = [o["label"] for o in (s or {"options": []})["options"]]
check("revenue" in labels and len(labels) == len(set(labels)), f"dedupe: {labels}")

# never more than the allowed number of buttons, and each button changes ONLY the unknown word
s = clarify.suggest(mini, "What is the total wages by region?", unmatched("wages"))
check(s is not None and len(s["options"]) <= clarify.MAX_OPTIONS and all(o["question"].endswith("by region?") or o["question"].endswith("by region") for o in s["options"]), "options: a button changed more than the unknown word")

# a word with nothing close gets NO button, not a random one
check(clarify.suggest(mini, "What is the total zebra?", unmatched("zebra")) is None, "options: a button was offered for a word with nothing close")

# "Percent of what?": the buttons name the number to take the share of
percent = "Percent of what? Name what you want the share of, for example 'share of revenue from Electronics'."
s = clarify.suggest(mini, "What share comes from Sales?", percent)
check(s is not None and s["options"] and all("share of" in o["question"].lower() for o in s["options"]), f"percent of what: no 'share of' buttons: {s}")
check(any("revenue" in o["question"].lower() for o in (s or {"options": []})["options"]), "percent of what: the revenue button is missing")
check(clarify.suggest(mini, "What is the average age?", percent) is None, "percent of what: a question with no 'share' word got a button")

# "which number" for a ranking: only when the question does not already say BY something
rank = "Which number should I rank by? Please name it, for example 'top 5 by revenue'."
s = clarify.suggest(mini, "Which department is the best?", rank)
check(s is not None and all(" by " in o["question"] for o in s["options"]), "rank: the buttons do not add 'by <number>'")
check(clarify.suggest(mini, "Which department is the best by headcount?", rank) is None, "rank: a question that already says 'by' got a button")
check(clarify.suggest(mini, "Tell me about the departments", rank) is None, "rank: a question with no ranking word got a button")

# a message from somewhere else gets no button
for message in ("The data has no date column.", "I do not forecast the future.", "", "Some other error"):
    check(clarify.suggest(mini, "What is the total?", message) is None, f"other: a button was offered for {message!r}")

print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed[:14]:
    print("  FAIL:", f)
