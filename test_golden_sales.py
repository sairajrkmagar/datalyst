import math
import time

import pandas as pd

from ask_engine import AskEngine


# ------------------------------------------------------------
# A DIFFERENT dataset than test_golden.py (the AI never saw it)
# ------------------------------------------------------------

df = pd.read_csv("sample_sales.csv")


# ------------------------------------------------------------
# Helpers that compute the CORRECT answer straight from pandas
# ------------------------------------------------------------

def rows_where(data, column, value):
    return data[data[column].astype(str).str.lower() == value.lower()]


def total(value_column, group=None, value=None):
    def truth(data):
        if group:
            data = rows_where(data, group, value)
        return data[value_column].sum()
    return truth


def average(value_column, group=None, value=None):
    def truth(data):
        if group:
            data = rows_where(data, group, value)
        return data[value_column].mean()
    return truth


def maximum(value_column):
    return lambda data: data[value_column].max()


def minimum(value_column):
    return lambda data: data[value_column].min()


def top(group, value_column="total_amount"):
    def truth(data):
        sums = data.groupby(group)[value_column].sum()
        return (sums.idxmax(), sums.max())
    return truth


def bottom(group, value_column="total_amount"):
    def truth(data):
        sums = data.groupby(group)[value_column].sum()
        return (sums.idxmin(), sums.min())
    return truth


def unique(column):
    return lambda data: data[column].nunique()


def monthly(value_column="total_amount"):
    def truth(data):
        dates = pd.to_datetime(data["order_date"])
        sums = data.groupby(dates.dt.to_period("M"))[value_column].sum()
        return {str(month): value for month, value in sums.items()}
    return truth


ROW_COUNT = lambda data: len(data)
DUPLICATES = lambda data: int(data.duplicated().sum())
MISSING = lambda data: int(data.isnull().sum().sum())


# ------------------------------------------------------------
# THE QUESTIONS  (question, how to compute the correct answer)
# ------------------------------------------------------------

GOLDEN = [
    # totals
    ("What is the total revenue?", total("total_amount")),
    ("How much did we sell in total?", total("total_amount")),
    ("What is the total revenue for Electronics?",
     total("total_amount", "product_category", "Electronics")),
    ("How much revenue came from the North region?",
     total("total_amount", "region", "North")),
    ("Total sales for Furniture",
     total("total_amount", "product_category", "Furniture")),
    ("How many units did we sell in total?", total("quantity")),

    # averages
    ("What is the average order value?", average("total_amount")),
    ("What is the average revenue for Clothing?",
     average("total_amount", "product_category", "Clothing")),

    # single biggest / smallest value
    ("What is the maximum order amount?", maximum("total_amount")),
    ("What is the minimum order amount?", minimum("total_amount")),

    # best / worst groups
    ("Which product category earns the most revenue?",
     top("product_category")),
    ("Which region has the lowest revenue?", bottom("region")),
    ("Which region generates the most sales?", top("region")),
    ("Which customer spent the most?", top("customer_name")),
    ("Who is our best customer?", top("customer_name")),
    ("Who bought the least?", bottom("customer_name")),

    # counting
    ("How many orders are there?", ROW_COUNT),
    ("How many customers do we have?", unique("customer_name")),
    ("How many different product categories are there?",
     unique("product_category")),
    ("How many regions are there?", unique("region")),

    # data quality
    ("Are there duplicate orders?", DUPLICATES),
    ("How many missing values are there?", MISSING),

    # trend
    ("Show me monthly revenue", monthly()),
    ("What is the revenue trend over time?", monthly()),
]


# ------------------------------------------------------------
# Compare the app's answer with the correct answer
# ------------------------------------------------------------

def close(a, b):
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-6)
    except (TypeError, ValueError):
        return False


def matches(actual, expected):

    if isinstance(expected, tuple):
        return (
            isinstance(actual, (tuple, list))
            and len(actual) == 2
            and str(actual[0]).lower() == str(expected[0]).lower()
            and close(actual[1], expected[1])
        )

    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(close(actual[key], expected[key]) for key in expected)
        )

    return close(actual, expected)


def run():

    engine = AskEngine(df)

    understanding = engine.dataset_understanding

    print("What the AI was told about the data:")
    print("  measures  :", understanding["measures"])
    print("  dimensions:", understanding["dimensions"])
    print("  dates     :", understanding["date_columns"])
    print()

    passed = 0
    failures = []

    print(f"Running {len(GOLDEN)} questions...\n", flush=True)

    for number, (question, truth) in enumerate(GOLDEN, start=1):

        started = time.time()

        answer = engine.ask(question)

        seconds = time.time() - started

        expected = truth(df)

        if answer["status"] != "success":
            ok = False
            got = "ERROR: " + answer["message"]
        else:
            got = answer["result"]
            ok = matches(got, expected)

        if ok:
            passed += 1
        else:
            plan = answer.get("plan")
            failures.append((question, expected, got, plan))

        status = "PASS" if ok else "FAIL"

        repairs = answer.get("repairs")
        extra = f"   [repaired: {'; '.join(repairs)}]" if repairs else ""

        print(f"{number:>2}. {status}  {seconds:4.0f}s  {question}{extra}",
              flush=True)

    percent = round(100 * passed / len(GOLDEN))

    print("\n" + "=" * 60)
    print(f"SCORE: {passed} / {len(GOLDEN)} correct answers  ({percent}%)")
    print("=" * 60)

    if failures:
        print("\nWHAT WENT WRONG:\n")
        for question, expected, got, plan in failures:
            print(f"Q: {question}")
            print(f"   expected: {expected!r}")
            print(f"   got     : {got!r}")
            print(f"   plan    : {plan}")
            print()


if __name__ == "__main__":
    run()
