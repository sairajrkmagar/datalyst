"""
REAL AI PLANS (no AI needed, runs in seconds)

Every plan below was captured from your real AI during a real test run.
Each one once caused a wrong answer or a wrong refusal. They are kept here
forever so that an old bug can never come back.

When a new test shows an AI plan that fails, add it to the list below.

    python test_real_ai_plans.py ecommerce_sales_34500.csv
"""

import sys
import warnings; warnings.filterwarnings("ignore")

import pandas as pd

from ask_engine import AskEngine
from auto_benchmark import matches, rows_where
from question_understanding import QuestionUnderstanding

T = "total_amount"


def years(d):
    return pd.to_datetime(d["order_date"]).dt.year


def plan(intent, column, group, value, filt, operation):
    return {"intent": intent, "column": column, "group_column": group,
            "value_column": value, "filter_value": filt, "operation": operation}


# (question, plan the real AI gave, correct answer or None = must refuse)
REAL_PLANS = [
    ("How many records are there for Fashion?",
     plan(None, None, None, None, None, "row_count"),
     lambda d: len(rows_where(d, "category", "Fashion"))),

    ("What are the top 3 category by total amount?",
     plan("top", T, "category", T, None, "group_sum"),
     lambda d: ("LIST", ["electronics", "home", "sports"])),

    ("How many different region values are there?",
     plan("unique", None, None, None, None, "unique"),
     lambda d: d["region"].nunique()),

    ("How many different returned values are there?",
     plan("unique", None, None, None, None, "unique"),
     lambda d: d["returned"].nunique()),

    # --- from the 65-question analyst run
    ("How many orders from Electronics were returned?",
     plan(None, None, "category", "returned", "Yes", "count"),
     lambda d: len(rows_where(d, "category", "Electronics")[rows_where(d, "category", "Electronics")["returned"] == "Yes"])),

    ("How many orders have a discount above 10%?",
     plan(None, None, None, "discount", "above 10%", None),
     lambda d: int((d["discount"] > 0.10).sum())),

    ("What is the total revenue from orders with a discount above 10%?",
     plan("total", T, None, T, "Yes", "sum"),
     lambda d: d[d["discount"] > 0.10][T].sum()),

    # --- from the 35-question human run
    ("how many orders were returned in 2024?",
     plan(None, None, "order_id", None, "2024", "count"),
     lambda d: len(d[(d["returned"] == "Yes") & (years(d) == 2024)])),

    ("how many orders have a price above 500?",
     plan(None, None, None, None, "500", "count"),
     lambda d: int((d["price"] > 500).sum())),

    ("total revenue from paypal",
     plan("total", T, None, T, "paypal", "sum"),
     lambda d: rows_where(d, "payment_method", "PayPal")[T].sum()),

    # --- these used to be refused; now they are real features
    ("which payment method is most popular?",
     plan("top", None, "payment_method", None, None, "group_sum"),
     lambda d: ({"credit card"}, int(d.groupby("payment_method").size().max()))),

    ("what percentage of orders were returned?",
     plan(None, None, None, None, None, None),
     lambda d: float((d["returned"] == "Yes").mean() * 100)),

    ("what share of revenue comes from electronics?",
     plan("total", T, "category", T, "Electronics", "sum"),
     lambda d: float(rows_where(d, "category", "Electronics")[T].sum() / d[T].sum() * 100)),

    ("Show revenue by payment method",
     plan("top", T, "payment_method", T, None, "group_sum"),
     lambda d: {str(k): v for k, v in d.groupby("payment_method")[T].sum().items()}),

    ("Which region has the fastest average delivery?",
     plan("average", "delivery_time_days", None, "delivery_time_days", None, "average"),
     lambda d: ({str(d.groupby("region")["delivery_time_days"].mean().idxmin()).lower()},
                float(d.groupby("region")["delivery_time_days"].mean().min()))),

    # --- from the 65-question run after the group/percentage features
    ("What is the return rate for each category?",
     plan("top", None, "category", "returned", None, "group_sum"),
     lambda d: {str(k): v for k, v in (d["returned"].eq("Yes").groupby(d["category"]).mean() * 100).items()}),

    # --- these used to be refused: they are answered now (statistics)
    ("What is the median order value?",
     plan("average", T, None, T, None, "average"),
     lambda d: float(d[T].median())),

    ("How many orders are above the average order value?",
     plan("count", None, None, None, None, "row_count"),
     lambda d: int((d[T] > d[T].mean()).sum())),
]


# --- real plans for the other files (each one once caused a wrong answer or a refusal)
MISSING_SLIP = plan("missing", None, None, None, None, "missing_count")   # the AI said "missing values" for "below"

AMAZON_PLANS = [
    # the exact plan the real AI gave: no intent, "count" without a column
    ("How many products have a rating above 4.5?",
     plan(None, None, None, "rating", 4.5, "count"),
     lambda d: int((d["rating"] > 4.5).sum())),
    ("How many records have discount percentage below 32?", MISSING_SLIP,
     lambda d: int((d["discount_percentage"] < 32).sum())),
    ("How many records have discount percentage between 32 and 63?", MISSING_SLIP,
     lambda d: int(((d["discount_percentage"] >= 32) & (d["discount_percentage"] <= 63)).sum())),
    ("How many records have discounted price below 320?", MISSING_SLIP,
     lambda d: int((d["discounted_price"] < 320).sum())),
    ("How many different products are there?",
     plan("unique", "product_id", None, "product_id", None, "unique"),
     lambda d: d["product_id"].nunique()),
]

SAMPLE_PLANS = [
    ("How many orders have quantity below 2?", MISSING_SLIP,
     lambda d: int((d["quantity"] < 2).sum())),
]


def plans_for(path):
    name = path.lower()
    if "amazon" in name:
        return AMAZON_PLANS
    if "sample" in name:
        return SAMPLE_PLANS
    return REAL_PLANS


def run(path):

    df = pd.read_csv(path)
    engine = AskEngine(df)

    passed = 0
    all_plans = plans_for(path)

    for question, real_plan, truth in all_plans:

        QuestionUnderstanding.understand = (
            lambda self, q, p=real_plan: dict(p)
        )

        answer = engine.ask(question)

        if truth is None:
            ok = answer["status"] != "success"
            shown = "refused" if ok else "ANSWERED: " + answer["response"][:50]
        elif answer["status"] != "success":
            ok = False
            shown = "REFUSED: " + answer["message"][:70]
        else:
            ok = matches(answer["result"], truth(engine.df))
            shown = str(answer["result"])[:40]

        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {question[:62]:62s} {shown}")

    print(f"\n{passed} / {len(all_plans)} real AI plans handled correctly")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "ecommerce_sales_34500.csv")