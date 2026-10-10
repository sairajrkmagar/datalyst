"""
Natural, messy questions the way real people type them.
(lowercase, no question mark, slang, "revenue" / "sales" / "money" ...)

How to run:
    python test_human_questions.py ecommerce_sales_34500.csv

Three groups:
  SHOULD ANSWER   the app must give the right number
  SHOULD REFUSE   not supported yet: refusing is correct, a number is DANGEROUS
  KNOWN GAPS      features not built yet: shows what to build next
"""

import sys
import time

import pandas as pd

from ask_engine import AskEngine
from auto_benchmark import _best, _monthly, _top_names, matches, rows_where

T = "total_amount"


def plan(intent, operation, column=None, group=None, value=None, filt=None):
    return {
        "intent": intent, "column": column, "group_column": group,
        "value_column": value, "filter_value": filt, "operation": operation,
    }


def _most_orders(data, column):
    """The group with the most rows (not the most revenue)."""
    counts = data.groupby(column).size()
    target = counts.max()
    return ({str(n).lower() for n in counts[counts == target].index}, target)


def year_of(d):
    return pd.to_datetime(d["order_date"]).dt.year


def month_of(d):
    return pd.to_datetime(d["order_date"]).dt.month


# (group, question, correct answer from pandas, plan a good AI would give)
QUESTIONS = [
    ("ANSWER", "how much money did we make in total?",
     lambda d: d[T].sum(), plan("total", "sum", T, None, T)),
    ("ANSWER", "what's our average order value?",
     lambda d: d[T].mean(), plan("average", "average", T, None, T)),
    ("ANSWER", "what is the biggest single order?",
     lambda d: d[T].max(), plan("maximum", "max", T, None, T)),
    ("ANSWER", "how many orders do we have?",
     lambda d: len(d), plan("count", "row_count")),
    ("ANSWER", "how many customers do we have?",
     lambda d: d["customer_id"].nunique(),
     plan("unique", "unique", "customer_id", None, "customer_id")),
    ("ANSWER", "how many different products are there?",
     lambda d: d["product_id"].nunique(),
     plan("unique", "unique", "product_id", None, "product_id")),
    ("ANSWER", "what is the total sales for electronics",
     lambda d: rows_where(d, "category", "Electronics")[T].sum(),
     plan("total", "sum", T, "category", T, "electronics")),
    ("ANSWER", "revenue from the north region",
     lambda d: rows_where(d, "region", "North")[T].sum(),
     plan("total", "sum", T, "region", T, "north")),
    ("ANSWER", "how much did we earn from COD orders?",
     lambda d: rows_where(d, "payment_method", "COD")[T].sum(),
     plan("total", "sum", T, "payment_method", T, "COD")),
    ("ANSWER", "total revenue from paypal",
     lambda d: rows_where(d, "payment_method", "PayPal")[T].sum(),
     plan("total", "sum", T, "payment_method", T, "paypal")),
    ("ANSWER", "how many orders came from south in 2024?",
     lambda d: len(rows_where(d, "region", "South")[year_of(rows_where(d, "region", "South")) == 2024]),
     plan("count", "row_count")),
    ("ANSWER", "average order value in 2025",
     lambda d: d[year_of(d) == 2025][T].mean(), plan("average", "average", T, None, T)),
    ("ANSWER", "total profit for beauty",
     lambda d: rows_where(d, "category", "Beauty")["profit_margin"].sum(),
     plan("total", "sum", "profit_margin", "category", "profit_margin", "beauty")),
    ("ANSWER", "how many orders were returned in 2024?",
     lambda d: len(d[(d["returned"] == "Yes") & (year_of(d) == 2024)]),
     plan("count", "row_count")),
    ("ANSWER", "what is the total revenue in december 2024?",
     lambda d: d[(year_of(d) == 2024) & (month_of(d) == 12)][T].sum(),
     plan("total", "sum", T, None, T)),
    ("ANSWER", "which region makes the most money?",
     lambda d: _best(d, "region", T, True), plan("top", "group_sum", T, "region", T)),
    ("ANSWER", "which category is the worst performer by revenue?",
     lambda d: _best(d, "category", T, False), plan("bottom", "group_sum", T, "category", T)),
    ("ANSWER", "who is our best customer?",
     lambda d: _best(d, "customer_id", T, True),
     plan("top", "group_sum", T, "customer_id", T)),
    ("ANSWER", "top 5 customers by revenue",
     lambda d: _top_names(d, "customer_id", T, 5, True),
     plan("top", "group_sum", T, "customer", T)),
    ("ANSWER", "show me revenue by month",
     lambda d: _monthly(d, "order_date", T),
     plan("trend", "time_series", T, "order_date", T)),
    ("ANSWER", "monthly revenue for electronics in 2024",
     lambda d: _monthly(rows_where(d, "category", "Electronics")[year_of(rows_where(d, "category", "Electronics")) == 2024], "order_date", T),
     plan("trend", "time_series", T, "order_date", T)),
    ("ANSWER", "how many orders have a price above 500?",
     lambda d: int((d["price"] > 500).sum()), plan("count", "row_count")),
    ("ANSWER", "average delivery time for returned orders",
     lambda d: d[d["returned"] == "Yes"]["delivery_time_days"].mean(),
     plan("average", "average", "delivery_time_days", None, "delivery_time_days")),
    ("ANSWER", "average discount for electronics",
     lambda d: rows_where(d, "category", "Electronics")["discount"].mean(),
     plan("average", "average", "discount", "category", "discount", "electronics")),
    ("ANSWER", "total shipping cost in 2024",
     lambda d: d[year_of(d) == 2024]["shipping_cost"].sum(),
     plan("total", "sum", "shipping_cost", None, "shipping_cost")),
    ("ANSWER", "number of orders by credit card",
     lambda d: len(rows_where(d, "payment_method", "Credit Card")), plan("count", "row_count")),
    ("ANSWER", "how many orders did male customers place?",
     lambda d: len(rows_where(d, "customer_gender", "Male")), plan("count", "row_count")),
    ("ANSWER", "how many orders did female customers place?",
     lambda d: len(rows_where(d, "customer_gender", "Female")), plan("count", "row_count")),

    # --- the app must REFUSE these (not supported yet)
    ("ANSWER", "revenue by category",
     lambda d: {str(k): v for k, v in d.groupby("category")[T].sum().items()},
     plan("total", "sum", T, None, T)),
    ("ANSWER", "compare electronics and home revenue",
     lambda d: {"Electronics": rows_where(d, "category", "Electronics")[T].sum(), "Home": rows_where(d, "category", "Home")[T].sum()},
     plan("total", "sum", T, "category", T, "electronics")),
    ("REFUSE", "what was the revenue last month?", None, plan("total", "sum", T, None, T)),
    ("ANSWER", "how many orders are above the average order value?",
     lambda d: int((d[T] > d[T].mean()).sum()),
     plan("count", "row_count")),

    # --- features that do not exist yet (shows what to build next)
    ("ANSWER", "which payment method is most popular?",
     lambda d: _most_orders(d, "payment_method"),   # popular = MOST ORDERS
     plan("top", "group_sum", T, "payment_method", T)),
    ("ANSWER", "what percentage of orders were returned?",
     lambda d: float((d["returned"] == "Yes").mean() * 100), plan("count", "row_count")),
    ("ANSWER", "what share of revenue comes from electronics?",
     lambda d: float(rows_where(d, "category", "Electronics")[T].sum() / d[T].sum() * 100),
     plan("total", "sum", T, "category", T, "electronics")),
]


def run(path):

    df = pd.read_csv(path)
    engine = AskEngine(df)

    print(f"File: {path}  ({len(df):,} rows)")
    print("Getting the AI ready (first time only)...", flush=True)
    engine.warm_up()
    print(f"Asking {len(QUESTIONS)} natural questions...\n", flush=True)

    tally = {"ANSWER": [0, 0, 0], "REFUSE": [0, 0], "GAP": [0, 0, 0]}
    details = []

    for number, (group, question, truth, _) in enumerate(QUESTIONS, start=1):

        started = time.time()
        answer = engine.ask(question)
        seconds = time.time() - started

        refused = answer["status"] != "success"

        if group == "REFUSE":
            outcome = "SAFE" if refused else "DANGEROUS"
            tally["REFUSE"][0 if refused else 1] += 1

        else:
            expected = truth(df)
            if refused:
                outcome = "REFUSED"
                got = answer["message"]
            else:
                got = answer["result"]
                outcome = "CORRECT" if matches(got, expected) else "WRONG"

            index = {"CORRECT": 0, "REFUSED": 1, "WRONG": 2}[outcome]
            tally[group][index] += 1

            if outcome != "CORRECT":
                details.append((group, question, outcome, expected, got,
                                getattr(engine.pipeline, "last_raw_plan", None)))

        if group == "REFUSE" and not refused:
            details.append((group, question, outcome, "a refusal",
                            answer["response"],
                            getattr(engine.pipeline, "last_raw_plan", None)))

        repairs = answer.get("repairs")
        extra = f"  [repaired: {'; '.join(repairs)}]" if repairs else ""
        print(f"{number:>2}. {outcome:9s}{seconds:3.0f}s  [{group}] {question}{extra}",
              flush=True)

    a, r, g = tally["ANSWER"], tally["REFUSE"], tally["GAP"]
    total_answer = sum(a)

    print("\n" + "=" * 66)
    print(f"SHOULD ANSWER : {a[0]} / {total_answer} correct, {a[1]} refused, {a[2]} WRONG")
    print(f"SHOULD REFUSE : {r[0]} / {sum(r)} safely refused, {r[1]} DANGEROUS")
    print(f"KNOWN GAPS    : {g[0]} correct, {g[1]} refused, {g[2]} wrong "
          f"(these are features not built yet)")
    print("=" * 66)

    if details:
        print("\nWHAT WENT WRONG:\n")
        for group, question, outcome, expected, got, raw in details:
            print(f"[{group} / {outcome}] {question}")
            print(f"   expected : {str(expected)[:150]}")
            print(f"   got      : {str(got)[:150]}")
            print(f"   AI plan  : {raw}\n")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python test_human_questions.py your_file.csv")
        sys.exit(1)

    run(sys.argv[1])