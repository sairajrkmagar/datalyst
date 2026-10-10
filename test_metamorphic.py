"""
METAMORPHIC TEST: answers must change exactly as mathematics says they must.

We never need to know the "right" answer. We change the DATA in a way whose effect is certain, ask the
same question again, and check the relationship:

  shuffle the rows            every answer stays the same
  double every row            sums and counts double; averages, medians, shares, growth stay the same
  multiply a column by 10     sums, medians, percentiles x10; counts, shares, correlations stay the same
  rename the columns          every answer stays the same (only the words in the question change)
  add an unrelated column     every answer stays the same
  split the data              the parts add up to the whole (groups, years, values)

A single wrong number anywhere in the engine breaks at least one of these relations.

    python test_metamorphic.py            (about 2 minutes)
"""
import math
import re
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import analyst_data
import clarify
from dashboard import uses_total
import question_understanding as qu
from ask_engine import AskEngine

passed, failed = 0, []
compared = 0


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


PLANS = {}
qu.QuestionUnderstanding.understand = lambda self, q: dict(PLANS.get(q, dict(intent=None)))


def plan(intent, column=None, group=None, op="sum", value=None):
    return dict(intent=intent, column=column, group_column=group, value_column=column,
                filter_value=value, operation=op)


def close(a, b, tolerance=1e-7):
    a, b = float(a), float(b)
    return abs(a - b) <= tolerance * max(1.0, abs(a), abs(b))


def has_ties(pairs):
    values = [round(float(v), 9) for _, v in pairs]
    return len(values) != len(set(values))


def compare(first, second, factor, name_ok=True):
    """Does `second` equal `first` with every VALUE multiplied by `factor`? Returns a problem or None."""

    if isinstance(first, (int, float, np.integer, np.floating)) and not isinstance(first, bool):
        if not isinstance(second, (int, float, np.integer, np.floating)):
            return f"type {type(first).__name__} -> {type(second).__name__}"
        return None if close(float(first) * factor, second) else f"{first} x {factor} != {second}"

    if isinstance(first, tuple):
        if not isinstance(second, tuple) or len(second) != 2:
            return "tuple shape changed"
        if name_ok and str(first[0]).lower() != str(second[0]).lower():
            return f"name {first[0]!r} -> {second[0]!r}"
        return None if close(float(first[1]) * factor, second[1]) else f"value {first[1]} x {factor} != {second[1]}"

    if isinstance(first, dict):
        if not isinstance(second, dict) or set(first) != set(second):
            return "keys changed"
        for key, value in first.items():
            if not close(float(value) * factor, second[key]):
                return f"{key}: {value} x {factor} != {second[key]}"
        return None

    if isinstance(first, list):
        if not isinstance(second, list) or len(first) != len(second):
            return "list length changed"
        values_a = sorted(round(float(v) * factor, 6) for _, v in first)
        values_b = sorted(round(float(v), 6) for _, v in second)
        if not all(close(x, y) for x, y in zip(values_a, values_b)):
            return f"values {values_a[:3]} != {values_b[:3]}"
        if not has_ties(first) and [str(n).lower() for n, _ in first] != [str(n).lower() for n, _ in second]:
            return "order or names changed"
        return None

    return None if first == second else f"{first!r} != {second!r}"


# --------------------------------------------------------------- the questions we ask of every dataset
def battery(engine):
    """[(id, question, plan or None)]: questions with known behaviour under the transformations."""

    profile, under = engine.profile, engine.dataset_understanding
    measures = list(profile.get("measures", []))
    ids = list(profile.get("identifier_columns", []))
    dates = list(under["date_columns"])
    dims = [c for c, v in under["dimension_values"].items() if c not in ids and 3 <= len(v) <= 12]
    # a column that can be ADDED UP (a rating or a percentage is averaged by design, so "total" would mean average)
    additive = [x for x in measures if uses_total(x)]
    main = profile.get("revenue_column") if profile.get("revenue_column") in additive else (additive[0] if additive else None)
    if main is None or not dims:
        return [], {}

    m = clarify.label(engine, main)
    d = clarify.label(engine, dims[0])
    noun = profile.get("count_noun") or "records"
    second = next((x for x in measures if x != main), None)
    df = engine.df
    top = str(df.groupby(dims[0])[main].sum().sort_values(ascending=False).index[0])
    plural = (d[:-1] + "ies") if d.endswith("y") else d + "s"

    q = []
    add = lambda i, text, p=None: q.append((i, text, p))

    add("median", f"What is the median {m}?")
    add("p90", f"What is the 90th percentile of {m}?")
    add("range", f"What is the range of {m}?")
    add("iqr", f"What is the interquartile range of {m}?")
    add("above", f"How many {noun} are above the average {m}?")
    add("outliers", f"Are there any outliers in {m}? How many?")
    if second:
        add("corr", f"What is the correlation between {m} and {clarify.label(engine, second)}?")
    add("rank", f"What rank is {top} by {m}?")
    add("nth", f"What is the second best {d} by {m}?")
    add("topcount", f"What are the top 3 {plural} by number of {noun}?")
    add("sharetop", f"What share of {m} comes from the top 2 {plural}?")
    if len(dims) > 1:
        add("crosstab", f"Show {m} by {d} and {clarify.label(engine, dims[1])}")
    if dates:
        stamps = pd.to_datetime(df[dates[0]], errors="coerce")
        years = sorted({int(y) for y in stamps.dt.year.dropna()})
        add("yearbest", f"Which year had the highest {m}?")
        add("weekday", f"Which day of the week has the highest {m}?")
        if len(years) >= 2:
            add("growth", f"What is the year on year growth in {m} from {years[0]} to {years[1]}?")

    # questions that go through the AI-planned path (the AI is replaced by a fixed plan)
    add("total", f"What is the total {m}?", plan("total", main))
    add("average", f"What is the average {m}?", plan("average", main, op="average"))
    add("breakdown", f"Show {m} by {d}", plan("breakdown", main, dims[0]))
    add("top", f"Which {d} has the highest {m}?", plan("top", main, dims[0], "group_sum"))
    add("count", f"How many {noun} are there?", plan("count", op="row_count"))

    return q, {"main": main, "dim": dims[0], "date": dates[0] if dates else None, "values": list(under["dimension_values"][dims[0]])}


def run(engine, items):
    results = {}
    for ident, question, p in items:
        if p is not None:
            PLANS[question] = p
        answer = engine.ask(question)
        results[ident] = answer["result"] if answer["status"] == "success" else None
    return results


# factor each answer must show for each transformation; None = no promise (skip)
DOUBLE = {"median": 1, "p90": None, "range": 1, "iqr": None, "above": 2, "outliers": None, "corr": 1, "rank": 1, "nth": 2, "topcount": 2,
          "sharetop": 1, "crosstab": 2, "yearbest": 2, "weekday": 2, "growth": 1, "total": 2, "average": 1, "breakdown": 2, "top": 2, "count": 2}
SCALE = {"median": 10, "p90": 10, "range": 10, "iqr": 10, "above": 1, "outliers": 1, "corr": 1, "rank": 1, "nth": 10, "topcount": 1,
         "sharetop": 1, "crosstab": 10, "yearbest": 10, "weekday": 10, "growth": 1, "total": 10, "average": 10, "breakdown": 10, "top": 10, "count": 1}
SAME = {k: 1 for k in DOUBLE}


def relate(label, base, other, factors, name):
    global compared
    for ident, factor in factors.items():
        if ident not in base or factor is None:
            continue
        a, b = base[ident], other.get(ident)
        compared += 1
        if a is None and b is None:
            continue
        if a is None or b is None:
            check(False, f"{name} [{label}] {ident}: answered {'before' if a is not None else 'after'} but not the other time")
            continue
        # a ranking name may change when two values tie: that is not a mistake
        problem = compare(a, b, factor, name_ok=not (ident in ("nth", "top", "yearbest", "weekday") and False))
        check(problem is None, f"{name} [{label}] {ident}: {problem}")


def test_dataset(label, df):
    base_engine = AskEngine(df.copy())
    items, info = battery(base_engine)
    if not items:
        return
    base = run(base_engine, items)
    answered = sum(v is not None for v in base.values())
    check(answered >= 10, f"{label}: only {answered} of the questions were answered")

    # 1. shuffle
    shuffled = df.sample(frac=1, random_state=4).reset_index(drop=True)
    relate(label, base, run(AskEngine(shuffled), items), SAME, "shuffle rows")

    # 2. double every row
    relate(label, base, run(AskEngine(pd.concat([df, df], ignore_index=True)), items), DOUBLE, "double rows")

    # 3. multiply the main measure by 10
    scaled = df.copy()
    scaled[info["main"]] = scaled[info["main"]] * 10
    relate(label, base, run(AskEngine(scaled), items), SCALE, "scale x10")

    # 4. an unrelated column
    extra = df.copy()
    extra["zz_unrelated_note"] = np.random.default_rng(1).choice(["alpha", "beta", "gamma"], len(extra))
    relate(label, base, run(AskEngine(extra), items), SAME, "extra column")

    # 5. rename the columns (capitals, spaces): the question words change, the answers must not
    mapping = {c: re.sub(r"[_\s]+", " ", str(c)).title() for c in df.columns}
    if len(set(mapping.values())) == len(mapping):
        renamed = df.rename(columns=mapping)
        engine2 = AskEngine(renamed)
        items2, _ = battery(engine2)
        if [i for i, _, _ in items2] == [i for i, _, _ in items]:
            relate(label, base, run(engine2, items2), SAME, "rename columns")
        else:
            check(False, f"{label}: after renaming the columns the engine understands a different set of questions")

    # 6. the parts add up to the whole
    PLANS_total = plan("total", info["main"])
    total = base.get("total")
    breakdown = base.get("breakdown")
    if total is not None and breakdown is not None:
        check(close(sum(breakdown.values()), total), f"{label}: the groups of the breakdown ({sum(breakdown.values())}) do not add up to the total ({total})")
    if info["date"] and total is not None:
        stamps = pd.to_datetime(df[info["date"]], errors="coerce")
        years = sorted({int(y) for y in stamps.dt.year.dropna()})
        parts = 0.0
        m = clarify.label(base_engine, info["main"])
        ok = True
        for y in years:
            question = f"What is the total {m} in {y}?"
            PLANS[question] = PLANS_total
            answer = base_engine.ask(question)
            if answer["status"] != "success":
                ok = False
                break
            parts += float(answer["result"])
        undated = int(stamps.isna().sum())
        if ok and undated == 0:
            check(close(parts, total), f"{label}: the yearly totals ({parts}) do not add up to the total ({total})")
    values = [v for v in info["values"] if str(v).strip().lower() not in ("other", "total", "all", "average")]
    if 2 <= len(values) <= 8 and total is not None:
        parts, ok = 0.0, True
        m = clarify.label(base_engine, info["main"])
        d = clarify.label(base_engine, info["dim"])
        for v in values:
            question = f"What is the total {m} for {v}?"
            PLANS[question] = plan("total", info["main"], value=str(v))
            answer = base_engine.ask(question)
            if answer["status"] != "success":
                ok = False
                break
            parts += float(answer["result"])
        if ok and len(values) == df[info["dim"]].nunique():
            check(close(parts, total), f"{label}: the totals for each {d} ({parts}) do not add up to the total ({total})")


datasets = {name: builder()[0] for name, builder in analyst_data.BUILDERS.items()}
try:
    datasets["sample_sales"] = pd.read_csv("sample_sales.csv")
    datasets["ecommerce"] = pd.read_csv("ecommerce_sales_34500.csv").head(12000)
except FileNotFoundError:
    pass

for label, frame in datasets.items():
    test_dataset(label, frame)

print(f"{passed + len(failed)} checks, {len(failed)} FAILED  ({compared} answers compared across {len(datasets)} datasets and 5 transformations)")
for f in failed[:14]:
    print("  FAIL:", f[:240])
