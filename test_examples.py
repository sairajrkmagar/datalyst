"""
EXAMPLES TEST (no AI, seconds): every example in "What can I ask?" must give an ANSWER
(never a refusal) on every dataset, and there must be a good spread of groups.

    python test_examples.py
"""
import warnings
warnings.filterwarnings("ignore")

import pandas as pd

import analyst_data
import examples
from ask_engine import AskEngine
from question_understanding import QuestionUnderstanding

passed, failed = 0, []
asked = 0


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


def run(name, df):
    global asked
    e = AskEngine(df.copy())
    groups = examples.build(e)
    check(len(groups) >= 3, f"{name}: only {len(groups)} groups of examples")
    questions = [i["q"] for g in groups for i in g["items"]]
    check(len(questions) == len(set(questions)), f"{name}: duplicate example questions")
    check(all(len(g["items"]) <= 4 and g["items"] for g in groups), f"{name}: a group is empty or too long")

    main = e.profile.get("revenue_column") or (list(e.profile["measures"]) or [None])[0]

    for g in groups:
        for item in g["items"]:
            ai = item["plan"] or dict(intent="total", column=main, group_column=None, value_column=main, filter_value=None, operation="sum")
            QuestionUnderstanding.understand = lambda self, q, ai=ai: dict(ai)
            a = e.ask(item["q"])
            asked += 1
            check(a["status"] == "success", f"{name} [{g['title']}]: {item['q']!r} -> {a.get('message', '')[:90]}")


for builder in analyst_data.BUILDERS:
    run(builder, analyst_data.BUILDERS[builder]()[0])
for path in ["ecommerce_sales_34500.csv", "sample_sales.csv", "Cleaned_HR_Data_Analysis.csv", "amazon.csv"]:
    run(path.split("_")[0].split(".")[0], pd.read_csv(path))


# ============================================================
# CONTENT: the RIGHT examples appear, for the right files
# ============================================================
import numpy as np

rng = np.random.default_rng(9)
N = 600


def sales_frame(profit=True, spend=False, clicks=False, customers=True, dates=True, second_dim=True, rating_main=False):
    data = {
        "order_id": [f"O{i}" for i in range(N)],
        "region": rng.choice(["North", "South", "East", "West"], N),
        "revenue": rng.integers(10, 900, N),
        "quantity": rng.integers(1, 9, N),
    }
    if second_dim:
        data["channel"] = rng.choice(["Web", "Store", "App"], N)
    if profit:
        data["profit"] = rng.integers(1, 300, N)
    if spend:
        data["spend"] = rng.integers(5, 400, N)
    if clicks:
        data["clicks"] = rng.integers(1, 90, N)
        data["impressions"] = rng.integers(100, 9000, N)
    if customers:
        data["customer_id"] = [f"C{i % 150}" for i in range(N)]
    if dates:
        data["order_date"] = pd.to_datetime(rng.choice(pd.date_range("2022-01-01", "2024-06-30"), N)).strftime("%Y-%m-%d")
    return pd.DataFrame(data)


def questions(frame):
    e = AskEngine(frame)
    groups = examples.build(e)
    return e, {g["title"]: [i["q"] for i in g["items"]] for g in groups}


e, g = questions(sales_frame())
check(set(g) == {"Totals and counts", "Groups and rankings", "Shares and concentration", "Time and growth", "Statistics", "Business ratios", "Customers"}, f"content: groups {sorted(g)}")
check(any("How many" in q and "are there?" in q for q in g["Totals and counts"]), "content: the row-count question is missing")
check("What is the total revenue?" in g["Totals and counts"] and "What is the average revenue?" in g["Totals and counts"], f"content: total/average wording {g['Totals and counts']}")
check(g["Groups and rankings"][0] == "Show total revenue by region" and any("highest revenue" in q for q in g["Groups and rankings"]) and any("lowest revenue" in q for q in g["Groups and rankings"]), f"content: groups {g['Groups and rankings']}")
check(any("and" in q and "channel" in q for q in g["Groups and rankings"]), "content: the two-column table question is missing")
check(any("top 3 regions" in q for q in g["Shares and concentration"]) and any("What share of revenue comes from" in q for q in g["Shares and concentration"]), f"content: shares {g['Shares and concentration']}")
check("Show me monthly revenue" in g["Time and growth"] and any("Which year had the highest" in q for q in g["Time and growth"]) and any("from 2022 to 2023" in q for q in g["Time and growth"]) and any("day of the week" in q for q in g["Time and growth"]), f"content: time {g['Time and growth']}")
check("What is the median revenue?" in g["Statistics"] and any("above the average revenue" in q for q in g["Statistics"]) and any("outliers" in q for q in g["Statistics"]) and any("correlation between revenue and" in q for q in g["Statistics"]), f"content: statistics {g['Statistics']}")
check(g["Business ratios"] == ["What is the overall profit margin?"], f"content: ratios {g['Business ratios']}")
check(any("repeat customer rate" in q for q in g["Customers"]) and any("more than one order" in q for q in g["Customers"]) and any("best customer by revenue" in q for q in g["Customers"]), f"content: customers {g['Customers']}")
check(all(len(v) <= 4 for v in g.values()) and all(len(set(v)) == len(v) for v in g.values()), "content: a group is too long or has duplicates")

# ratios only when the columns exist
_, g = questions(sales_frame(profit=False)); check("Business ratios" not in g, "content: a margin question without a profit column")
_, g = questions(sales_frame(spend=True)); check("What is the return on ad spend (ROAS)?" in g.get("Business ratios", []), f"content: ROAS {g.get('Business ratios')}")
_, g = questions(sales_frame(clicks=True)); check("What is the click through rate (CTR)?" in g.get("Business ratios", []), f"content: CTR {g.get('Business ratios')}")
# the file decides which groups exist
_, g = questions(sales_frame(customers=False)); check("Customers" not in g, "content: a customer group without a customer id")
_, g = questions(sales_frame(dates=False)); check("Time and growth" not in g, "content: a time group without a date column")
_, g = questions(sales_frame(second_dim=False)); check(not any(" and channel" in q for q in g.get("Groups and rankings", [])) and not any("channel" in q for q in g.get("Groups and rankings", [])), "content: a two-column table without a second category")
one_year = sales_frame(); one_year["order_date"] = "2023-05-01"
_, g = questions(one_year); check(not any("year" in q for q in g.get("Time and growth", [])), f"content: year questions for a one-year file {g.get('Time and growth')}")
unique_ids = sales_frame(); unique_ids["customer_id"] = [f"C{i}" for i in range(N)]
_, g = questions(unique_ids); check("Customers" not in g, "content: a customer group when every id appears once")
# a rating is averaged, never totalled: no 'total' wording and no share questions
rating = pd.DataFrame({"product": [f"P{i}" for i in range(N)], "category": rng.choice(["A", "B", "C"], N), "rating": rng.uniform(1, 5, N).round(1), "votes": rng.integers(1, 999, N)})
_, g = questions(rating)
check(not any(q.startswith("What is the total") for q in g.get("Totals and counts", [])) and any("average" in q for q in g.get("Totals and counts", [])), f"content: rating wording {g.get('Totals and counts')}")
check("Shares and concentration" not in g, "content: share questions for an averaged column")

# the plural of a column name, as people write it
for word, plural in {"category": "categories", "region": "regions", "status": "statuses", "box": "boxes", "day": "days", "church": "churches", "key": "keys", "country": "countries"}.items():
    check(examples.plural_word(AskEngine(pd.DataFrame({word: rng.choice(["a", "b", "c"], 60), "amount": rng.integers(1, 99, 60)})), word) == plural, f"plural: {word}")

print(f"{passed + len(failed)} checks, {len(failed)} FAILED  ({asked} example questions asked)")
for f in failed[:16]:
    print("  FAIL:", f)
