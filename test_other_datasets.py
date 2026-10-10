"""
OTHER DATASETS
--------------
The same engine, tested on files it has never seen: an HR file and an
Amazon products file. Each question has its correct answer from pandas.

    python test_other_datasets.py Cleaned_HR_Data_Analysis.csv
    python test_other_datasets.py amazon.csv

(The file name decides which question list is used.)
"""

import sys
import time

import pandas as pd

from ask_engine import AskEngine
from auto_benchmark import _best, matches, rows_where
from filters import to_dates


def plan(intent, operation, column=None, group=None, value=None, filt=None):
    return {
        "intent": intent, "column": column, "group_column": group,
        "value_column": value, "filter_value": filt, "operation": operation,
    }


def pct(part, whole):
    return float(part) / float(whole) * 100


def by_mean(d, group, value):
    return {str(k): v for k, v in d.groupby(group)[value].mean().items()}


def rank_mean(d, group, value, highest=True):
    means = d.groupby(group)[value].mean()
    target = means.max() if highest else means.min()
    return ({str(n).lower() for n in means[means == target].index}, target)


def rank_count(d, group):
    counts = d.groupby(group).size()
    return ({str(n).lower() for n in counts[counts == counts.max()].index}, counts.max())


HR_COST = "Training Cost"

# (question, correct answer, plan a typical AI would give)
HR = [
    ("How many employees do we have?", lambda d: len(d),
     plan("unique", "unique", "Employee ID", None, "Employee ID")),
    ("How many employees are Active?",
     lambda d: len(rows_where(d, "EmployeeStatus", "Active")), plan("count", "row_count")),
    ("What is the average age of employees?", lambda d: d["Age"].mean(),
     plan("average", "average", "Age", None, "Age")),
    ("What is the total training cost?", lambda d: d[HR_COST].sum(),
     plan("total", "sum", HR_COST, None, HR_COST)),
    ("What is the average training cost for Leadership Development?",
     lambda d: rows_where(d, "Training Program Name", "Leadership Development")[HR_COST].mean(),
     plan("average", "average", HR_COST, "Training Program Name", HR_COST, "Leadership Development")),
    ("Which department has the highest total training cost?",
     lambda d: _best(d, "DepartmentType", HR_COST, True),
     plan("top", "group_sum", HR_COST, "DepartmentType", HR_COST)),
    # the plan your real AI gave (it once caused a wrong refusal)
    ("What share of employees are female?",
     lambda d: pct(len(rows_where(d, "GenderCode", "Female")), len(d)),
     {"intent": None, "column": "GenderCode", "group_column": None,
      "value_column": None, "filter_value": "Female", "operation": "unique"}),
    ("Show average satisfaction score by department type",
     lambda d: by_mean(d, "DepartmentType", "Satisfaction Score"),
     plan("average", "average", "Satisfaction Score", None, "Satisfaction Score")),
    ("How many employees have an engagement score above 3?",
     lambda d: int((d["Engagement Score"] > 3).sum()), plan("count", "row_count")),
    ("What is the total training cost in 2023?",
     lambda d: d[to_dates(d["Training Date"]).dt.year == 2023][HR_COST].sum(),
     plan("total", "sum", HR_COST, None, HR_COST)),
    ("Which state has the most employees?",
     lambda d: rank_count(d, "State"), plan("top", "group_sum", "Age", "State", "Age")),
    ("How many employees are in IN?",
     lambda d: len(rows_where(d, "State", "IN")), plan("count", "row_count")),
    ("What is the average training cost by training type?",
     lambda d: by_mean(d, "Training Type", HR_COST),
     plan("average", "average", HR_COST, None, HR_COST)),
    ("Which business unit has the highest average engagement score?",
     lambda d: rank_mean(d, "BusinessUnit", "Engagement Score", True),
     plan("top", "group_sum", "Engagement Score", "BusinessUnit", "Engagement Score")),
    ("How many employees had a failed training outcome?",
     lambda d: len(rows_where(d, "Training Outcome", "Failed")), plan("count", "row_count")),
    ("What is the most common performance score?",
     lambda d: rank_count(d, "Performance Score"),
     plan("top", "group_sum", "Age", "Performance Score", "Age")),
    ("How many missing values are there?", lambda d: int(d.isnull().sum().sum()),
     plan("missing", "missing_count")),
]

AMAZON = [
    ("How many different products are there?", lambda d: d["product_id"].nunique(),
     plan("unique", "unique", "product_id", None, "product_id")),
    ("What is the average discounted price?", lambda d: d["discounted_price"].mean(),
     plan("average", "average", "discounted_price", None, "discounted_price")),
    ("What is the average rating?", lambda d: d["rating"].mean(),
     plan("average", "average", "rating", None, "rating")),
    ("Which category has the highest average rating?",
     lambda d: rank_mean(d, "category_main", "rating", True),
     plan("top", "group_sum", "rating", "category", "rating")),
    ("Show average discount percentage by category",
     lambda d: by_mean(d, "category_main", "discount_percentage"),
     plan("average", "average", "discount_percentage", None, "discount_percentage")),
    ("How many products have a rating above 4.5?",
     lambda d: int((d["rating"] > 4.5).sum()), plan("count", "row_count")),
    ("What is the total rating count for Electronics?",
     lambda d: rows_where(d, "category_main", "Electronics")["rating_count"].sum(),
     plan("total", "sum", "rating_count", "category", "rating_count", "Electronics")),
    ("What is the highest actual price?", lambda d: d["actual_price"].max(),
     plan("maximum", "max", "actual_price", None, "actual_price")),
    ("What share of products are in Home&Kitchen?",
     lambda d: pct(len(rows_where(d, "category_main", "Home&Kitchen")), len(d)),
     plan("count", "row_count")),
    ("Which category has the most products?",
     lambda d: rank_count(d, "category_main"), plan("top", "group_sum", "rating", "category", "rating")),
    ("What is the average discount percentage for Electronics?",
     lambda d: rows_where(d, "category_main", "Electronics")["discount_percentage"].mean(),
     plan("average", "average", "discount_percentage", "category", "discount_percentage", "Electronics")),
    ("How many missing values are there?", lambda d: int(d.isnull().sum().sum()),
     plan("missing", "missing_count")),
]


def questions_for(path):

    name = path.lower()

    if "hr" in name:
        return "HR", HR

    if "amazon" in name:
        return "Amazon", AMAZON

    return None, None


def run(path, warm_up=True):

    label, items = questions_for(path)

    if items is None:
        print("This test has questions for the HR and Amazon files only.")
        print("For any other file use:  python auto_benchmark.py your_file.csv")
        return

    engine = AskEngine(pd.read_csv(path))
    d = engine.df

    print(f"{label} file: {path}  ({len(d):,} rows, {len(d.columns)} columns)")

    if engine.conversions:
        print("What the app tidied up by itself:")
        for column, note in engine.conversions.items():
            print(f"   {column}: {note}")

    if warm_up:
        print("\nGetting the AI ready (first time only)...", flush=True)
        engine.warm_up()

    print(f"\nAsking {len(items)} questions...\n", flush=True)

    correct = refused = wrong = 0
    problems = []

    for number, (question, truth, _) in enumerate(items, start=1):

        started = time.time()
        answer = engine.ask(question)
        seconds = time.time() - started

        expected = truth(d)

        if answer["status"] != "success":
            outcome, got = "REFUSED", answer["message"]
            refused += 1
        elif matches(answer["result"], expected):
            outcome, got = "CORRECT", answer["result"]
            correct += 1
        else:
            outcome, got = "WRONG", answer["result"]
            wrong += 1

        repairs = answer.get("repairs")
        extra = f"  [repaired: {'; '.join(repairs)}]" if repairs else ""
        print(f"{number:>2}. {outcome:8s}{seconds:3.0f}s  {question}{extra}", flush=True)

        if outcome != "CORRECT":
            problems.append((question, outcome, expected, got,
                             getattr(engine.pipeline, "last_raw_plan", None)))

    print("\n" + "=" * 66)
    print(f"{label}: {correct} / {len(items)} correct, {refused} refused, {wrong} WRONG")
    print("=" * 66)

    for question, outcome, expected, got, raw in problems:
        print(f"\n[{outcome}] {question}")
        print(f"   expected : {str(expected)[:150]}")
        print(f"   got      : {str(got)[:150]}")
        print(f"   AI plan  : {raw}")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python test_other_datasets.py Cleaned_HR_Data_Analysis.csv")
        sys.exit(1)

    run(sys.argv[1])
