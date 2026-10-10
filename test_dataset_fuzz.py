"""
DATASET FUZZ TEST (no AI, minutes)

Makes many DIFFERENT synthetic datasets (naming styles, what a row is, money
written as text, percentages, date formats, missing values, awkward category
names like "Other", "All", "Home & Kitchen"), then checks:

  1. UNDERSTANDING: did the engine work out which columns are numbers,
     categories, dates and IDs? (the generator knows the truth)
  2. ANSWERS: the whole question bank on each file: no confident-wrong answer.
  3. CRASHES: nothing may raise an error.

    python test_dataset_fuzz.py                 (30 datasets)
    python test_dataset_fuzz.py 60 100          (60 datasets, seeds from 100)
    python test_dataset_fuzz.py 20 1 --hard     (messier: units in headers, numeric codes, empty columns ...)
    python test_dataset_fuzz.py --save 17       (write dataset 17 to fuzz_17.csv to look at it)
"""
import copy
import random
import sys
import traceback
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import question_bank as qb
from ask_engine import AskEngine

ENTITIES = [("order", "orders"), ("employee", "employees"), ("patient", "patients"),
            ("student", "students"), ("ticket", "tickets"), ("booking", "bookings"),
            ("invoice", "invoices"), ("claim", "claims"), ("shipment", "shipments")]

POOLS = {
    "region": ["North", "South", "East", "West", "Central"],
    "city": ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata", "Hyderabad", "Pune", "Ahmedabad"],
    "department": ["Sales", "Marketing", "Finance", "Engineering", "HR", "Support", "Operations"],
    "category": ["Electronics", "Home & Kitchen", "Fashion", "Toys/Games", "Beauty", "Sports", "Books", "Grocery"],
    "segment": ["Consumer", "Corporate", "Home Office", "Small Business"],
    "status": ["Active", "Inactive", "Pending", "Closed"],
    "priority": ["Low", "Medium", "High", "Critical"],
    "channel": ["Online", "Store", "Phone", "Partner", "Other"],
    "payment_method": ["Credit Card", "Debit Card", "UPI", "Cash", "Net Banking", "Wallet"],
    "gender": ["Male", "Female", "Other"],
    "tier": ["All", "Basic", "Plus", "Pro", "Total"],
    "branch": ["In-store", "Mall", "Airport", "Downtown"],
}

FLAGS = ["returned", "is_active", "churned", "approved", "cancelled", "verified"]
FLAG_VALUES = [("Yes", "No"), ("Y", "N"), ("True", "False")]

MEASURES = {
    "money": ["amount", "revenue", "order_value", "total_price", "salary", "cost", "fee", "sales_value"],
    "quantity": ["quantity", "units", "items"],
    "rating": ["rating", "customer_rating"],
    "percent": ["discount_percent", "margin_pct", "growth_rate", "completion_percentage", "attrition_rate"],
    "age": ["age", "customer_age"],
    "score": ["satisfaction_score", "performance_score"],
    "days": ["delivery_days", "tenure_days", "wait_days"],
    "profit": ["profit", "net_gain"],
}

DATE_NAMES = ["order_date", "created_at", "joined_on", "admission_date", "due_date", "ship_date"]
DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y", "%Y/%m/%d"]


def styled(words, style):
    if style == "snake":
        return "_".join(words)
    if style == "camel":
        return words[0] + "".join(w.capitalize() for w in words[1:])
    if style == "pascal":
        return "".join(w.capitalize() for w in words)
    if style == "title":
        return " ".join(("ID" if w == "id" else w.capitalize()) for w in words)
    return "_".join(words).upper()


def make_dataset(seed, hard=False):
    """Returns (dataframe, truth, description). truth = the real roles of each column.
    hard=True adds the mess found in real files: units and spaces in headers,
    numeric category codes, constant and empty columns, huge outliers."""

    r = random.Random(seed)
    rng = np.random.default_rng(seed)
    n = r.choice([150, 400, 1200, 3000])
    style = r.choice(["snake", "camel", "pascal", "title", "upper"])
    noun, plural = r.choice(ENTITIES)

    def col(name):
        return styled(name.split("_"), style)

    data, truth = {}, {"measures": [], "dims": [], "dates": [], "ids": [], "flags": []}

    id_name = col(r.choice([f"{noun}_id", f"{noun}_number", f"{noun}_no"]))
    data[id_name] = [f"{noun[:3].upper()}{i:05d}" if r.random() < 0.6 else i + 1 for i in range(n)]
    if isinstance(data[id_name][0], int):
        data[id_name] = [i + 1 for i in range(n)]
    truth["ids"].append(id_name)

    if r.random() < 0.6:
        pool = rng.integers(0, max(5, n // 4), n)
        data[col("customer_id")] = [f"C{v:04d}" for v in pool]
        truth["ids"].append(col("customer_id"))

    for key in r.sample(list(POOLS), r.randint(2, 5)):
        data[col(key)] = rng.choice(POOLS[key], n, p=np.array(rng.dirichlet(np.ones(len(POOLS[key])) * 2)))
        truth["dims"].append(col(key))

    if r.random() < 0.7:
        flag = r.choice(FLAGS)
        yes, no = r.choice(FLAG_VALUES)
        data[col(flag)] = rng.choice([yes, no], n, p=[0.15, 0.85])
        truth["flags"].append(col(flag))

    text_numbers = {}
    for kind in r.sample(list(MEASURES), r.randint(2, 4)):
        name = col(r.choice(MEASURES[kind]))
        if name in data:
            continue
        if kind == "money":
            values = (rng.gamma(2, 400, n)).round(2)
        elif kind == "quantity":
            values = rng.integers(1, 15, n)
        elif kind == "rating":
            values = rng.uniform(1, 5, n).round(1)
        elif kind == "percent":
            values = rng.uniform(0, 60, n).round(1)
        elif kind == "age":
            values = rng.integers(18, 70, n)
        elif kind == "score":
            values = rng.integers(0, 100, n)
        elif kind == "days":
            values = rng.integers(1, 40, n)
        else:
            values = rng.normal(150, 900, n).round(2)

        shown = pd.Series(values)

        # some money and percentages arrive as TEXT
        if kind == "money" and r.random() < 0.5:
            symbol = r.choice(["₹", "$", ""])
            shown = shown.map(lambda v: f"{symbol}{v:,.2f}")
            text_numbers[name] = kind
        elif kind == "percent" and r.random() < 0.5:
            shown = shown.map(lambda v: f"{v:.1f}%")
            text_numbers[name] = kind

        data[name] = shown.tolist()
        truth["measures"].append(name)

    for name in r.sample(DATE_NAMES, r.choice([0, 1, 1, 1, 2])):
        fmt = r.choice(DATE_FORMATS)
        start = pd.Timestamp("2022-01-01") + pd.Timedelta(days=int(rng.integers(0, 200)))
        stamps = start + pd.to_timedelta(rng.integers(0, 700, n), unit="D")
        text = np.array(stamps.strftime(fmt), dtype=object)
        text[rng.random(n) < 0.02] = None
        text[rng.random(n) < 0.005] = "N/A"
        data[col(name)] = text
        truth["dates"].append(col(name))

    df = pd.DataFrame(data)

    # blanks and repeated rows
    for c in list(df.columns):
        if c in truth["ids"]:
            continue
        if r.random() < 0.4:
            df.loc[rng.random(n) < r.choice([0.005, 0.02, 0.05]), c] = None
    if r.random() < 0.3:
        df = pd.concat([df, df.sample(max(1, n // 100), random_state=seed)], ignore_index=True)

    if hard:

        # numeric CODES that are really categories (department 101..105)
        code_name = col(r.choice(["dept_code", "branch_code", "zone", "grade_level"]))
        df[code_name] = rng.choice([101, 102, 103, 104, 105], len(df))
        truth["dims"].append(code_name)

        # a column that never changes, and one that is completely empty
        df[col("country")] = "India"
        df[col("notes")] = None

        # one huge outlier in a number column
        if truth["measures"]:
            target = truth["measures"][0]
            if target not in text_numbers:
                df.loc[df.index[0], target] = float(df[target].max()) * 1000

        # headers as they come out of real exports: units, symbols, stray spaces
        rename = {}
        for c in df.columns:
            roll = r.random()
            if roll < 0.15:
                rename[c] = f"{c} "
            elif roll < 0.30:
                rename[c] = f"  {c}"
            elif roll < 0.42 and c in truth["measures"]:
                rename[c] = f"{c} (₹)"
            elif roll < 0.50 and c in truth["measures"]:
                rename[c] = f"{c} (units)"
        df = df.rename(columns=rename)

        for key in truth:
            truth[key] = [rename.get(c, c) for c in truth[key]]

    df = df[r.sample(list(df.columns), len(df.columns))]          # shuffle the column order

    return df, truth, f"seed {seed}: {n} rows, {style} names, rows are {plural}, columns {list(df.columns)}"


def understanding_problems(engine, truth):
    """(serious, minor): what the engine got wrong about the structure of the file."""

    u = engine.dataset_understanding
    identifiers = set(engine.profile.get("identifier_columns", []))
    serious, minor = [], []

    # the engine tidies stray spaces in headers, so compare the tidied names
    truth = {key: [str(c).strip() for c in names] for key, names in truth.items()}

    for c in truth["measures"]:
        if c not in u["measures"]:
            where = "an ID" if c in identifiers else ("a category" if c in u["dimension_values"] or c in u["dimensions"] else "something else")
            serious.append(f"number column '{c}' was treated as {where}")

    for c in truth["dates"]:
        if c not in u["date_columns"]:
            serious.append(f"date column '{c}' was not found as a date")

    for c in truth["dims"] + truth["flags"]:
        if c in u["measures"]:
            serious.append(f"category column '{c}' was treated as a number")
        elif c not in u["dimension_values"] and c not in identifiers:
            minor.append(f"category column '{c}' is not offered as a category")

    for c in truth["ids"][:1]:
        if c not in identifiers:
            minor.append(f"the ID column '{c}' was not recognised as an ID")

    return serious, minor


def main():
    args = [a for a in sys.argv[1:]]

    if "--save" in args:
        seed = int(args[args.index("--save") + 1])
        df, truth, text = make_dataset(seed, "--hard" in args)
        df.to_csv(f"fuzz_{seed}.csv", index=False)
        print(text, "\nwritten to", f"fuzz_{seed}.csv")
        return

    hard = "--hard" in args
    numbers = [a for a in args if a.isdigit()]
    count = int(numbers[0]) if numbers else 30
    start = int(numbers[1]) if len(numbers) > 1 else 1
    modes = ["ideal", "noplan"]

    questions = wrong = unsafe = crashes = serious_total = minor_total = 0
    first_bad, first_serious, first_minor = [], [], []

    for seed in range(start, start + count):

        df, truth, text = make_dataset(seed, hard)

        try:
            engine = AskEngine(df)
            serious, minor = understanding_problems(engine, truth)
        except Exception:
            crashes += 1
            first_bad.append(f"CRASH while reading the file | {text[:90]} | {traceback.format_exc().splitlines()[-1][:120]}")
            continue

        serious_total += len(serious)
        minor_total += len(minor)
        first_serious += [f"seed {seed}: {s}" for s in serious]
        first_minor += [f"seed {seed}: {m}" for m in minor]

        for mode in modes:
            try:
                results = qb.run_frame(df.copy(), mode)
            except Exception:
                crashes += 1
                first_bad.append(f"CRASH in the question bank ({mode}) | {text[:90]} | {traceback.format_exc().splitlines()[-1][:120]}")
                continue

            for item, outcome, got, _ in results:
                questions += 1
                if outcome == "WRONG":
                    wrong += 1
                    first_bad.append(f"WRONG [{mode}] seed {seed} {item['kind']}: {item['question'][:70]} -> {got[:80]}")
                elif outcome == "UNSAFE":
                    unsafe += 1
                    first_bad.append(f"UNSAFE [{mode}] seed {seed}: {item['question'][:70]} -> {got[:80]}")

    print(f"{count} different datasets, {questions:,} questions asked")
    print(f"  confident-wrong answers : {wrong}")
    print(f"  unsafe answers          : {unsafe}")
    print(f"  crashes                 : {crashes}")
    print(f"  structure read wrongly  : {serious_total} serious, {minor_total} minor")

    for line in first_bad[:12]:
        print("   ", line)
    for line in first_serious[:12]:
        print("    UNDERSTANDING:", line)
    for line in first_minor[:6]:
        print("    (minor)      :", line)

    failed = wrong + unsafe + crashes + serious_total
    print(f"{questions + count} checks, {failed} FAILED")


if __name__ == "__main__":
    main()
