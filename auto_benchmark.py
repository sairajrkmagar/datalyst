"""
Test the AI on ANY csv file. No hand-written tests needed.

How to run:
    python auto_benchmark.py your_file.csv
    python auto_benchmark.py your_file.csv 60      (60 questions at most)

It writes questions using YOUR column names and real values,
calculates the correct answers with pandas, asks the AI the same
questions, and reports:
    CORRECT : the right number
    REFUSED : the app said "I can't do that safely" (no wrong number)
    WRONG   : the app gave a confident wrong number  <- the dangerous one
"""

from semantics import non_additive_reason
import copy
import math
import sys
import time

import pandas as pd

from ask_engine import AskEngine
from filters import to_dates
from plan_repair import pick_date_column


# Newer question types, scored separately so you can see progress
ADVANCED = [
    "filtered_count", "top_n", "top_n_bottom", "date_filter",
    "date_and_filter", "multi_filter", "boolean_count",
]

YES_NO = {"yes", "no", "true", "false", "0", "1", "y", "n"}

# Words that usually mark the main revenue column (best first)
PREFERRED_MONEY = ["revenue", "sales", "total", "amount", "income", "profit"]


def words(name):
    return str(name).replace("_", " ")


def rows_where(data, column, value):
    return data[data[column].astype(str).str.lower() == str(value).lower()]


def plan(intent, operation, column=None, group=None, value=None, filt=None):
    return {
        "intent": intent,
        "column": column,
        "group_column": group,
        "value_column": value,
        "filter_value": filt,
        "operation": operation,
    }


# ------------------------------------------------------------
# Write the questions + the correct answers
# ------------------------------------------------------------

def generate_questions(df, engine, limit):

    understanding = engine.dataset_understanding
    semantics = engine.profile["column_semantics"]

    measures = understanding["measures"]
    dates = understanding["date_columns"]
    identifiers = understanding["identifier_columns"]
    values_of = understanding["dimension_values"]

    # Money-like columns first: they are the most asked about.
    # Revenue-like names (total_amount, sales ...) come before price/cost.
    def money_rank(name):
        for position, word in enumerate(PREFERRED_MONEY):
            if word in name.lower():
                return position
        return len(PREFERRED_MONEY)

    money = sorted(
        [m for m in measures if semantics.get(m) == "monetary"],
        key=money_rank
    )
    ordered = money + [m for m in measures if m not in money]
    main = ordered[:3]

    items = []

    def add(kind, question, truth, expected_plan, lazy=None):
        # "lazy" = a sloppy plan a weak AI might give (used only by the
        # offline self-test, to prove the code repairs it)
        if all(item["question"] != question for item in items):
            items.append({
                "kind": kind,
                "question": question,
                "truth": truth,
                "plan": expected_plan,
                "lazy": lazy,
            })

    if not main:
        return items

    primary = main[0]

    # ---- numbers: total / average / maximum / minimum
    for m in main:

        label = words(m)
        is_money = semantics.get(m) == "monetary"
        is_count = any(w in m.lower() for w in ["quantity", "count", "units"])

        total_words = label if label.startswith("total") else f"total {label}"

        if is_money or is_count:

            if non_additive_reason(m, float(df[m].max())):
                # a total of a percentage / rating / age is meaningless:
                # the DEFINED behaviour is to answer with the average
                add("total", f"What is the {total_words}?",
                    lambda d, m=m: d[m].mean(),
                    plan("total", "sum", m, None, m))
            else:
                add("total", f"What is the {total_words}?",
                    lambda d, m=m: d[m].sum(),
                    plan("total", "sum", m, None, m))

        add("average", f"What is the average {label}?",
            lambda d, m=m: d[m].mean(),
            plan("average", "average", m, None, m))

        if is_money:
            add("maximum", f"What is the maximum {label}?",
                lambda d, m=m: d[m].max(),
                plan("maximum", "max", m, None, m))
            add("minimum", f"What is the minimum {label}?",
                lambda d, m=m: d[m].min(),
                plan("minimum", "min", m, None, m))

    # ---- groups: best / worst / filter / how many different
    dims = [d for d in values_of if d in df.columns][:4]
    first_filter = None
    second_filter = None

    plabel = words(primary)
    ptotal = plabel if plabel.startswith("total") else f"total {plabel}"

    for index, d in enumerate(dims):

        dlabel = words(d)

        add("top", f"Which {dlabel} has the highest {plabel}?",
            lambda x, d=d: _best(x, d, primary, True),
            plan("top", "group_sum", primary, d, primary))

        add("bottom", f"Which {dlabel} has the lowest {plabel}?",
            lambda x, d=d: _best(x, d, primary, False),
            plan("bottom", "group_sum", primary, d, primary))

        add("unique", f"How many different {dlabel} values are there?",
            lambda x, d=d: x[d].nunique(),
            plan("unique", "unique", d, None, d),
            lazy=plan("unique", "unique", None, None, None))

        if {str(v).strip().lower() for v in values_of[d]} <= YES_NO:
            continue

        common = df[d].value_counts().index[0]

        if first_filter is None:
            first_filter = (d, common)
        elif second_filter is None:
            second_filter = (d, common)

        add("filter", f"What is the {ptotal} for {common}?",
            lambda x, d=d, v=common: rows_where(x, d, v)[primary].sum(),
            plan("total", "sum", primary, d, primary, str(common)))

        add("filter", f"What is the average {plabel} for {common}?",
            lambda x, d=d, v=common: rows_where(x, d, v)[primary].mean(),
            plan("average", "average", primary, d, primary, str(common)))

        if first_filter == (d, common):
            lower = str(common).lower()
            add("filter_lowercase",
                f"What is the {ptotal} for {lower}?",
                lambda x, d=d, v=common: rows_where(x, d, v)[primary].sum(),
                plan("total", "sum", primary, d, primary, lower))

        # --- newer question types
        if first_filter == (d, common):

            add("filtered_count", f"How many records are there for {common}?",
                lambda x, d=d, v=common: len(rows_where(x, d, v)),
                plan("count", "row_count", None, d, None, str(common)),
                lazy=plan(None, "row_count"))

            add("top_n", f"What are the top 3 {dlabel} by {plabel}?",
                lambda x, d=d: _top_names(x, d, primary, 3, True),
                plan("top", "group_sum", primary, d, primary),
                lazy=plan("top", "group_sum", primary, d, primary))

            add("top_n_bottom", f"What are the 3 lowest {dlabel} by {plabel}?",
                lambda x, d=d: _top_names(x, d, primary, 3, False),
                plan("bottom", "group_sum", primary, d, primary),
                lazy=plan("top", "group_sum", primary, d, primary))

    # ---- yes/no columns: "How many records were returned?"
    for b in [d for d in values_of if d in df.columns]:

        lowered = {str(v).strip().lower(): v for v in values_of[b]}

        if set(lowered) <= YES_NO and str(b).lower().endswith("ed"):

            positive = next(
                (lowered[k] for k in lowered if k in {"yes", "true", "y", "1"}),
                None
            )

            if positive is not None:
                add("boolean_count", f"How many records were {words(b)}?",
                    lambda x, b=b, p=positive: len(rows_where(x, b, p)),
                    plan("count", "row_count", None, b, None, str(positive)),
                    lazy=plan("count", "row_count"))
                break

    # ---- two filters at once: "for Fashion in North"
    if first_filter and second_filter:

        (d1, v1), (d2, v2) = first_filter, second_filter

        add("multi_filter", f"What is the {ptotal} for {v1} in {v2}?",
            lambda x, a=d1, b=v1, c=d2, e=v2: rows_where(
                rows_where(x, a, b), c, e)[primary].sum(),
            plan("total", "sum", primary, d1, primary, str(v1)),
            lazy=plan("total", "sum", primary, d1, primary, str(v1)))

    # ---- repeating entities (customer, product ...)
    entities = [
        c for c in identifiers
        if 1 < df[c].nunique() < 0.95 * len(df)
    ][:2]

    for c in entities:

        clabel = words(c)

        add("top", f"Which {clabel} has the highest {plabel}?",
            lambda x, c=c: _best(x, c, primary, True),
            plan("top", "group_sum", primary, c, primary))

        add("unique", f"How many different {clabel}s are there?",
            lambda x, c=c: x[c].nunique(),
            plan("unique", "unique", c, None, c))

    # ---- whole-table questions
    add("rows", "How many rows are in the dataset?",
        lambda x: len(x), plan("count", "row_count"))

    add("duplicates", "How many duplicate rows are there?",
        lambda x: int(x.duplicated().sum()), plan("duplicate", "duplicate_count"))

    add("missing", "How many missing values are there?",
        lambda x: int(x.isnull().sum().sum()), plan("missing", "missing_count"))

    # ---- time
    if dates:

        # the date column that belongs to the main number
        # (Training Cost -> Training Date)
        date = pick_date_column(plabel, dates)

        add("trend", f"Show me monthly {plabel}",
            lambda x: _monthly(x, date, primary),
            plan("trend", "time_series", primary, date, primary))

        stamps = to_dates(df[date])
        middle = stamps.dropna().sort_values().iloc[len(stamps.dropna()) // 2]

        name = middle.strftime("%B %Y")

        add("date_filter", f"What is the {ptotal} in {name}?",
            lambda x, y=middle.year, mo=middle.month: x[
                (to_dates(x[date]).dt.year == y)
                & (to_dates(x[date]).dt.month == mo)
            ][primary].sum(),
            plan("total", "sum", primary, date, primary, name),
            lazy=plan("total", "sum", primary, None, primary))

        if first_filter:

            fd, fv = first_filter

            add("date_and_filter",
                f"What is the {ptotal} for {fv} in {name}?",
                lambda x, y=middle.year, mo=middle.month, a=fd, b=fv: rows_where(
                    x[
                        (to_dates(x[date]).dt.year == y)
                        & (to_dates(x[date]).dt.month == mo)
                    ], a, b)[primary].sum(),
                plan("total", "sum", primary, fd, primary, str(fv)),
                lazy=plan("total", "sum", primary, fd, primary, str(fv)))

    return items[:limit]


def _best(data, group, value, highest):
    sums = data.groupby(group)[value].sum()
    target = sums.max() if highest else sums.min()
    return ({str(n).lower() for n in sums[sums == target].index}, target)


def _top_names(data, group, value, n, highest=True):
    sums = data.groupby(group)[value].sum().sort_values(ascending=not highest)
    return ("LIST", [str(name).lower() for name in sums.index[:n]])


def _monthly(data, date, value):
    stamps = to_dates(data[date])
    sums = data.groupby(stamps.dt.to_period("M"))[value].sum()
    return {str(month): amount for month, amount in sums.items()}


# ------------------------------------------------------------
# Compare the app's answer with the correct answer
# ------------------------------------------------------------

def close(a, b):
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-6)
    except (TypeError, ValueError):
        return False


def matches(actual, expected):

    if isinstance(expected, tuple) and expected and expected[0] == "LIST":
        names = [str(item[0]).lower() for item in actual] if isinstance(
            actual, (list, tuple)) and actual and isinstance(
            actual[0], (list, tuple)) else None
        return names == expected[1]

    if isinstance(expected, tuple):
        return (
            isinstance(actual, (tuple, list))
            and len(actual) == 2
            and str(actual[0]).lower() in expected[0]
            and close(actual[1], expected[1])
        )

    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(close(actual[k], expected[k]) for k in expected)
        )

    return close(actual, expected)


# ------------------------------------------------------------
# Run
# ------------------------------------------------------------

def run(path, limit=70, warm_up=True):

    df = pd.read_csv(path)

    engine = AskEngine(df)

    # the correct answers must use the same typed data as the app
    # ("₹1,099" text became the number 1099)
    df = engine.df

    if engine.conversions:
        print("Text columns turned into numbers:")
        for column, note in engine.conversions.items():
            print(f"  {column}: {note}")
        print()

    # Spy on the AI's raw plan so failures can be explained
    captured = {}
    original = engine.pipeline.question_understanding.understand

    def spy(question):
        raw = original(question)
        captured["raw"] = copy.deepcopy(raw)
        return raw

    engine.pipeline.question_understanding.understand = spy

    understanding = engine.dataset_understanding

    print(f"File      : {path}  ({len(df):,} rows, {len(df.columns)} columns)")
    print("Measures  :", understanding["measures"])
    print("Dimensions:", understanding["dimensions"])
    print("Dates     :", understanding["date_columns"])
    print()

    questions = generate_questions(df, engine, limit)

    if warm_up:
        print("Getting the AI ready (first time only)...", flush=True)
        engine.warm_up()

    print(f"Asking {len(questions)} questions...\n", flush=True)

    results = []

    for number, item in enumerate(questions, start=1):

        started = time.time()

        answer = engine.ask(item["question"])

        seconds = time.time() - started

        expected = item["truth"](df)

        if answer["status"] != "success":
            outcome = "REFUSED"
            got = answer["message"]
        else:
            got = answer["result"]
            outcome = "CORRECT" if matches(got, expected) else "WRONG"

        repairs = answer.get("repairs")
        extra = f"  [repaired: {'; '.join(repairs)}]" if repairs else ""

        print(f"{number:>2}. {outcome:7s} {seconds:3.0f}s  "
              f"[{item['kind']}] {item['question']}{extra}", flush=True)

        results.append((item, outcome, expected, got, captured.get("raw")))

    report(results)


def report(results):

    def tally(subset):
        counts = {"CORRECT": 0, "REFUSED": 0, "WRONG": 0}
        for _, outcome, *_ in subset:
            counts[outcome] += 1
        return counts

    core = [r for r in results if r[0]["kind"] not in ADVANCED]
    advanced = [r for r in results if r[0]["kind"] in ADVANCED]

    print("\n" + "=" * 64)

    c = tally(core)
    print(f"CORE QUESTIONS     : {c['CORRECT']} / {len(core)} correct,"
          f" {c['REFUSED']} refused, {c['WRONG']} WRONG")

    if advanced:
        a = tally(advanced)
        print(f"NEWER FEATURES     : {a['CORRECT']} / {len(advanced)} correct,"
              f" {a['REFUSED']} refused, {a['WRONG']} WRONG")

    print("=" * 64)

    # per question type
    kinds = {}
    for item, outcome, *_ in results:
        kinds.setdefault(item["kind"], []).append(outcome)

    print("\nBy question type:")
    for kind, outcomes in kinds.items():
        good = outcomes.count("CORRECT")
        print(f"  {kind:17s} {good}/{len(outcomes)} correct")

    problems = [r for r in results if r[1] != "CORRECT"]

    if problems:
        print("\nWHAT WENT WRONG:\n")

    for item, outcome, expected, got, raw in problems:
        print(f"[{outcome}] {item['question']}")
        print(f"   expected : {_short(expected)}")
        print(f"   got      : {_short(got)}")
        print(f"   AI plan  : {raw}")
        print(f"   ideal    : {item['plan']}")
        print()


def _short(value):
    text = repr(value)
    return text if len(text) < 160 else text[:157] + "..."


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python auto_benchmark.py your_file.csv [max_questions]")
        sys.exit(1)

    max_questions = int(sys.argv[2]) if len(sys.argv) > 2 else 70

    run(sys.argv[1], max_questions)
