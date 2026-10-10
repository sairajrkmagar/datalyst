"""
THE ANALYST'S QUESTIONS
-----------------------
The questions a business analyst or data analyst really asks on
e-commerce data, grouped by business area.

Every question has a correct answer calculated with pandas, so this file
shows exactly what the app can answer TODAY and what is still missing.

How to run:
    python test_analyst_questions.py ecommerce_sales_34500.csv

Three levels:
    READY  the app must answer these correctly now
    SOON   needs group tables, percentages or rankings by count/average
    LATER  needs advanced analysis (repeat customers, statistics ...)

For SOON and LATER questions the right behaviour today is a clear
"not supported yet" (NOT YET). A confident wrong number is WRONG.
"""

import sys
import time

import pandas as pd

from ask_engine import AskEngine
from auto_benchmark import _best, _monthly, _top_names, matches, rows_where

T = "total_amount"
PROFIT = "profit_margin"


def plan(intent, operation, column=None, group=None, value=None, filt=None):
    return {
        "intent": intent, "column": column, "group_column": group,
        "value_column": value, "filter_value": filt, "operation": operation,
    }


# ---------- small helpers that compute the correct answer ----------

def dates(d):
    return pd.to_datetime(d["order_date"])


def by_sum(d, column, value=T):
    return {str(k): v for k, v in d.groupby(column)[value].sum().items()}


def by_count(d, column):
    return {str(k): v for k, v in d.groupby(column).size().items()}


def best_by_mean(d, column, value, highest):
    means = d.groupby(column)[value].mean()
    target = means.max() if highest else means.min()
    return ({str(n).lower() for n in means[means == target].index}, target)


def full_monthly(d):
    """Monthly revenue without the partly covered first and last month."""
    monthly = _monthly(d, "order_date", T)
    stamps = pd.to_datetime(d["order_date"])
    partial = set()
    if stamps.min().day > 1:
        partial.add(stamps.min().strftime("%Y-%m"))
    if stamps.max().day < stamps.max().days_in_month:
        partial.add(stamps.max().strftime("%Y-%m"))
    return {m: v for m, v in monthly.items() if m not in partial}


def best_month(d, highest=True):
    monthly = full_monthly(d)
    target = max(monthly.values()) if highest else min(monthly.values())
    return ({m.lower() for m, v in monthly.items() if v == target}, target)


def pct(part, whole):
    return float(part) / float(whole) * 100


# (area, level, question, correct answer, plan a typical AI would give, what is missing)
Q = [
    # ============================ SALES ============================
    ("Sales", "READY", "What is our total revenue?",
     lambda d: d[T].sum(), plan("total", "sum", T, None, T), ""),
    ("Sales", "READY", "How many orders did we receive?",
     lambda d: len(d), plan("count", "row_count"), ""),
    ("Sales", "READY", "What is the average order value?",
     lambda d: d[T].mean(), plan("average", "average", T, None, T), ""),
    ("Sales", "READY", "How many units were sold in total?",
     lambda d: d["quantity"].sum(), plan("total", "sum", "quantity", None, "quantity"), ""),
    ("Sales", "READY", "What was the total revenue in 2024?",
     lambda d: d[dates(d).dt.year == 2024][T].sum(), plan("total", "sum", T, None, T), ""),
    ("Sales", "READY", "What was the total revenue in Q4 2024?",
     lambda d: d[(dates(d).dt.year == 2024) & (dates(d).dt.quarter == 4)][T].sum(),
     plan("total", "sum", T, None, T), ""),
    ("Sales", "READY", "Show me the monthly revenue trend",
     lambda d: _monthly(d, "order_date", T), plan("trend", "time_series", T, "order_date", T), ""),
    ("Sales", "READY", "Which month had the highest revenue?",
     lambda d: best_month(d, True), plan("trend", "time_series", T, "order_date", T), "best month"),
    ("Sales", "READY", "What is the average monthly revenue?",
     lambda d: sum(full_monthly(d).values()) / len(full_monthly(d)),
     plan("average", "average", T, None, T), "average per month"),

    # ====================== PRODUCTS & CATEGORIES ======================
    ("Products", "READY", "Which category generates the most revenue?",
     lambda d: _best(d, "category", T, True), plan("top", "group_sum", T, "category", T), ""),
    ("Products", "READY", "Which category generates the least revenue?",
     lambda d: _best(d, "category", T, False), plan("bottom", "group_sum", T, "category", T), ""),
    ("Products", "READY", "What are the top 3 categories by revenue?",
     lambda d: _top_names(d, "category", T, 3, True), plan("top", "group_sum", T, "category", T), ""),
    ("Products", "READY", "How much revenue does Electronics generate?",
     lambda d: rows_where(d, "category", "Electronics")[T].sum(),
     plan("total", "sum", T, "category", T, "Electronics"), ""),
    ("Products", "READY", "What is the average price of Home products?",
     lambda d: rows_where(d, "category", "Home")["price"].mean(),
     plan("average", "average", "price", "category", "price", "Home"), ""),
    ("Products", "READY", "How many different products did we sell?",
     lambda d: d["product_id"].nunique(), plan("unique", "unique", "product_id", None, "product_id"), ""),
    ("Products", "READY", "Which product generated the most revenue?",
     lambda d: _best(d, "product_id", T, True), plan("top", "group_sum", T, "product_id", T), ""),
    ("Products", "READY", "Show revenue by category",
     lambda d: by_sum(d, "category"), plan("total", "sum", T, None, T), "group table"),
    ("Products", "READY", "What share of total revenue comes from Electronics?",
     lambda d: pct(rows_where(d, "category", "Electronics")[T].sum(), d[T].sum()),
     plan("total", "sum", T, "category", T, "Electronics"), "percentage"),
    ("Products", "READY", "Which category has the highest average order value?",
     lambda d: best_by_mean(d, "category", T, True), plan("top", "group_sum", T, "category", T), "ranking by average"),
    ("Products", "READY", "How many orders were placed in each category?",
     lambda d: by_count(d, "category"), plan("count", "row_count"), "group table"),

    # ============================ CUSTOMERS ============================
    ("Customers", "READY", "How many unique customers do we have?",
     lambda d: d["customer_id"].nunique(), plan("unique", "unique", "customer_id", None, "customer_id"), ""),
    ("Customers", "READY", "Who are our top 5 customers by revenue?",
     lambda d: _top_names(d, "customer_id", T, 5, True), plan("top", "group_sum", T, "customer_id", T), ""),
    ("Customers", "READY", "Which customer spent the most?",
     lambda d: _best(d, "customer_id", T, True), plan("top", "group_sum", T, "customer_id", T), ""),
    ("Customers", "READY", "What is the average age of our customers?",
     lambda d: d["customer_age"].mean(), plan("average", "average", "customer_age", None, "customer_age"), ""),
    ("Customers", "READY", "How many orders were placed by female customers?",
     lambda d: len(rows_where(d, "customer_gender", "Female")), plan("count", "row_count"), ""),
    ("Customers", "READY", "What is the average order value for male customers?",
     lambda d: rows_where(d, "customer_gender", "Male")[T].mean(),
     plan("average", "average", T, "customer_gender", T, "Male"), ""),
    ("Customers", "SOON", "What is the average revenue per customer?",
     lambda d: d[T].sum() / d["customer_id"].nunique(), plan("average", "average", T, None, T), "per-customer ratio"),
    ("Customers", "LATER", "How many customers placed more than one order?",
     lambda d: int((d.groupby("customer_id").size() > 1).sum()),
     plan("unique", "unique", "customer_id", None, "customer_id"), "repeat customers"),
    ("Customers", "LATER", "What percentage of customers are repeat buyers?",
     lambda d: pct((d.groupby("customer_id").size() > 1).sum(), d["customer_id"].nunique()),
     plan("count", "row_count"), "repeat customers"),

    # ============================ PAYMENTS ============================
    ("Payments", "READY", "How much revenue came from UPI?",
     lambda d: rows_where(d, "payment_method", "UPI")[T].sum(),
     plan("total", "sum", T, "payment_method", T, "UPI"), ""),
    ("Payments", "READY", "Which payment method is the most popular?",
     lambda d: ({str(k).lower() for k, v in by_count(d, "payment_method").items() if v == max(by_count(d, "payment_method").values())},
                max(by_count(d, "payment_method").values())),
     plan("top", "group_sum", T, "payment_method", T), "ranking by count"),
    ("Payments", "READY", "What share of orders were paid with COD?",
     lambda d: pct(len(rows_where(d, "payment_method", "COD")), len(d)),
     plan("count", "row_count"), "percentage"),
    ("Payments", "READY", "Show revenue by payment method",
     lambda d: by_sum(d, "payment_method"), plan("total", "sum", T, None, T), "group table"),

    # ============================ REGIONS ============================
    ("Regions", "READY", "Which region has the highest revenue?",
     lambda d: _best(d, "region", T, True), plan("top", "group_sum", T, "region", T), ""),
    ("Regions", "READY", "Which region has the lowest revenue?",
     lambda d: _best(d, "region", T, False), plan("bottom", "group_sum", T, "region", T), ""),
    ("Regions", "READY", "What was the revenue from the West region in 2024?",
     lambda d: rows_where(d, "region", "West")[dates(rows_where(d, "region", "West")).dt.year == 2024][T].sum(),
     plan("total", "sum", T, "region", T, "West"), ""),
    ("Regions", "READY", "How many orders came from the Central region?",
     lambda d: len(rows_where(d, "region", "Central")), plan("count", "row_count"), ""),
    ("Regions", "READY", "How many orders came from each region?",
     lambda d: by_count(d, "region"), plan("count", "row_count"), "group table"),
    ("Regions", "READY", "Which region has the fastest average delivery?",
     lambda d: best_by_mean(d, "region", "delivery_time_days", False),
     plan("bottom", "group_sum", "delivery_time_days", "region", "delivery_time_days"), "ranking by average"),

    # ======================= DELIVERY & SHIPPING =======================
    ("Delivery", "READY", "What is the average delivery time?",
     lambda d: d["delivery_time_days"].mean(),
     plan("average", "average", "delivery_time_days", None, "delivery_time_days"), ""),
    ("Delivery", "READY", "How many orders took more than 7 days to deliver?",
     lambda d: int((d["delivery_time_days"] > 7).sum()), plan("count", "row_count"), ""),
    ("Delivery", "READY", "What is the total shipping cost?",
     lambda d: d["shipping_cost"].sum(), plan("total", "sum", "shipping_cost", None, "shipping_cost"), ""),
    ("Delivery", "READY", "What is the average shipping cost per order?",
     lambda d: d["shipping_cost"].mean(), plan("average", "average", "shipping_cost", None, "shipping_cost"), ""),
    ("Delivery", "READY", "What is the average delivery time for returned orders?",
     lambda d: d[d["returned"] == "Yes"]["delivery_time_days"].mean(),
     plan("average", "average", "delivery_time_days", None, "delivery_time_days"), ""),
    ("Delivery", "READY", "What percentage of orders took more than 7 days to deliver?",
     lambda d: pct((d["delivery_time_days"] > 7).sum(), len(d)), plan("count", "row_count"), "percentage"),

    # ============================ RETURNS ============================
    ("Returns", "READY", "How many orders were returned?",
     lambda d: int((d["returned"] == "Yes").sum()), plan("count", "row_count"), ""),
    ("Returns", "READY", "What is the total value of returned orders?",
     lambda d: d[d["returned"] == "Yes"][T].sum(), plan("total", "sum", T, None, T), ""),
    ("Returns", "READY", "How many orders from Electronics were returned?",
     lambda d: len(rows_where(d, "category", "Electronics")[rows_where(d, "category", "Electronics")["returned"] == "Yes"]),
     plan("count", "row_count"), ""),
    ("Returns", "READY", "How many orders were returned in 2024?",
     lambda d: len(d[(d["returned"] == "Yes") & (dates(d).dt.year == 2024)]), plan("count", "row_count"), ""),
    ("Returns", "READY", "What is the return rate?",
     lambda d: pct((d["returned"] == "Yes").sum(), len(d)), plan("count", "row_count"), "percentage"),
    ("Returns", "READY", "What is the return rate for each category?",
     lambda d: {str(k): v for k, v in (d["returned"].eq("Yes").groupby(d["category"]).mean() * 100).items()},
     plan("count", "row_count"), "percentage by group"),

    # ============================ PROFIT ============================
    ("Profit", "READY", "What is the total profit?",
     lambda d: d[PROFIT].sum(), plan("total", "sum", PROFIT, None, PROFIT), ""),
    ("Profit", "READY", "What is the average profit per order?",
     lambda d: d[PROFIT].mean(), plan("average", "average", PROFIT, None, PROFIT), ""),
    ("Profit", "READY", "How many orders have a profit margin below 0?",
     lambda d: int((d[PROFIT] < 0).sum()), plan("count", "row_count"), ""),
    ("Profit", "READY", "Which category earns the most profit?",
     lambda d: _best(d, "category", PROFIT, True), plan("top", "group_sum", PROFIT, "category", PROFIT), ""),
    ("Profit", "READY", "Which category earns the least profit?",
     lambda d: _best(d, "category", PROFIT, False), plan("bottom", "group_sum", PROFIT, "category", PROFIT), ""),

    # ========================== DATA QUALITY ==========================
    ("Data quality", "READY", "How many missing values are there?",
     lambda d: int(d.isnull().sum().sum()), plan("missing", "missing_count"), ""),
    ("Data quality", "READY", "How many duplicate orders are there?",
     lambda d: int(d.duplicated().sum()), plan("duplicate", "duplicate_count"), ""),

    # ============================ DISCOUNTS ============================
    ("Discounts", "READY", "What is the average discount?",
     lambda d: d["discount"].mean(), plan("average", "average", "discount", None, "discount"), ""),
    ("Discounts", "READY", "How many orders have a discount above 10%?",
     lambda d: int((d["discount"] > 0.10).sum()), plan("count", "row_count"), ""),
    ("Discounts", "READY", "What is the total revenue from orders with a discount above 10%?",
     lambda d: d[d["discount"] > 0.10][T].sum(), plan("total", "sum", T, None, T), ""),

    # ========================== STATISTICS ==========================
    ("Statistics", "LATER", "What is the median order value?",
     lambda d: d[T].median(), plan("average", "average", T, None, T), "statistics"),
    ("Statistics", "LATER", "What is the correlation between price and discount?",
     lambda d: d["price"].corr(d["discount"]), plan("average", "average", "price", None, "price"), "statistics"),
    ("Statistics", "LATER", "Which day of the week has the most orders?",
     lambda d: ({n.lower() for n, v in dates(d).dt.day_name().value_counts().items() if v == dates(d).dt.day_name().value_counts().max()},
                dates(d).dt.day_name().value_counts().max()),
     plan("top", "group_sum", T, "order_date", T), "weekday patterns"),
    ("Statistics", "LATER", "Are there any outliers in order value?",
     lambda d: int(((d[T] > d[T].quantile(0.75) + 1.5 * (d[T].quantile(0.75) - d[T].quantile(0.25))) |
                    (d[T] < d[T].quantile(0.25) - 1.5 * (d[T].quantile(0.75) - d[T].quantile(0.25)))).sum()),
     plan("maximum", "max", T, None, T), "statistics"),
]


def run(path):

    df = pd.read_csv(path)
    engine = AskEngine(df)

    print(f"File: {path}  ({len(df):,} rows)")
    print("Getting the AI ready (first time only)...", flush=True)
    engine.warm_up()
    print(f"Asking {len(Q)} analyst questions...\n", flush=True)

    results = []

    for number, (area, level, question, truth, _, needs) in enumerate(Q, start=1):

        started = time.time()
        answer = engine.ask(question)
        seconds = time.time() - started

        expected = truth(df)

        if answer["status"] != "success":
            outcome, got = "NOT YET", answer["message"]
        else:
            got = answer["result"]
            outcome = "CORRECT" if matches(got, expected) else "WRONG"

        print(f"{number:>2}. {outcome:8s}{seconds:3.0f}s  [{level}] {question}",
              flush=True)

        raw_plan = getattr(engine.pipeline, "last_raw_plan", None)

        results.append(
            (area, level, question, outcome, expected, got, needs, raw_plan)
        )

    report(results)


def report(results):

    def tally(rows):
        return (
            sum(1 for r in rows if r[3] == "CORRECT"),
            sum(1 for r in rows if r[3] == "NOT YET"),
            sum(1 for r in rows if r[3] == "WRONG"),
        )

    print("\n" + "=" * 70)

    for level, note in [
        ("READY", "must be answered correctly now"),
        ("SOON", "group tables, percentages, rankings"),
        ("LATER", "advanced analysis"),
    ]:
        rows = [r for r in results if r[1] == level]
        good, notyet, wrong = tally(rows)
        print(f"{level:6s} ({note}): {good} / {len(rows)} correct, "
              f"{notyet} not yet, {wrong} WRONG")

    good, notyet, wrong = tally(results)

    print("-" * 70)
    print(f"TODAY: {good} of {len(results)} analyst questions answered "
          f"correctly ({round(100 * good / len(results))}%)")
    print(f"       {notyet} safely refused (to build),  "
          f"{wrong} WRONG numbers (must be 0)")
    print("=" * 70)

    print("\nBy business area:")
    for area in dict.fromkeys(r[0] for r in results):
        rows = [r for r in results if r[0] == area]
        print(f"  {area:14s} {tally(rows)[0]:>2} / {len(rows)} correct")

    todo = {}
    for r in results:
        if r[3] != "CORRECT" and r[6]:
            todo[r[6]] = todo.get(r[6], 0) + 1

    if todo:
        print("\nWhat to build next (questions waiting for each feature):")
        for need, count in sorted(todo.items(), key=lambda x: -x[1]):
            print(f"  {count} x {need}")

    problems = [
        r for r in results
        if r[3] == "WRONG" or (r[1] == "READY" and r[3] != "CORRECT")
    ]

    if problems:
        print("\nWHAT NEEDS ATTENTION:\n")
        for area, level, question, outcome, expected, got, needs, raw in problems:
            print(f"[{level} / {outcome}] {question}")
            print(f"   expected : {str(expected)[:140]}")
            print(f"   got      : {str(got)[:140]}")
            print(f"   AI plan  : {raw}\n")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python test_analyst_questions.py your_file.csv")
        sys.exit(1)

    run(sys.argv[1])
