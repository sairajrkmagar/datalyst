"""
NUMBER FORMATS (no AI, seconds)

"How many orders have amount above 5 lakh?" must give the right count or a
safe refusal, in every way people write a number. A wrong count is a bug.

    python test_number_formats.py
"""
import copy
import random
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from ask_engine import AskEngine
from question_understanding import QuestionUnderstanding

rng = np.random.default_rng(5)
n = 4000
df = pd.DataFrame({
    "order_id": [f"O{i}" for i in range(n)],
    "region": rng.choice(["North", "South", "East", "West"], n),
    "amount": (rng.gamma(2, 150000, n)).round(0),                 # up to ~20 lakh
    "profit": rng.normal(2000, 50000, n).round(2),                # negatives too
    "discount_percentage": rng.uniform(0, 90, n).round(1),
    "rating": rng.uniform(1, 5, n).round(1),
    "quantity": rng.integers(1, 12, n),
})

engine = AskEngine(df)
d = engine.df
passed = refused = 0
wrong = []

PLANS = {
    "count/row_count": dict(intent="count", column=None, group_column=None, value_column=None, filter_value=None, operation="row_count"),
    "no plan at all":  dict(intent=None, column=None, group_column=None, value_column=None, filter_value=None, operation=None),
}

# (question text, the true count from pandas)
def cases():
    yield "How many orders have amount above 500000?", int((d.amount > 500000).sum())
    yield "How many orders have amount above 5,00,000?", int((d.amount > 500000).sum())
    yield "How many orders have amount above ₹5,00,000?", int((d.amount > 500000).sum())
    yield "How many orders have amount above ₹500000?", int((d.amount > 500000).sum())
    yield "How many orders have amount above $500,000?", int((d.amount > 500000).sum())
    yield "How many orders have amount above 5 lakh?", int((d.amount > 500000).sum())
    yield "How many orders have amount above 5 lakhs?", int((d.amount > 500000).sum())
    yield "How many orders have amount above 5L?", None                      # unknown format: answer right or refuse
    yield "How many orders have amount above 1 crore?", int((d.amount > 1e7).sum())
    yield "How many orders have amount above 300k?", int((d.amount > 300000).sum())
    yield "How many orders have amount above 0.5 million?", int((d.amount > 500000).sum())
    yield "How many orders have amount below 2 lakh?", int((d.amount < 200000).sum())
    yield "How many orders have amount between 1 lakh and 3 lakh?", int(((d.amount >= 100000) & (d.amount <= 300000)).sum())
    yield "How many orders have amount between ₹1,00,000 and ₹3,00,000?", int(((d.amount >= 100000) & (d.amount <= 300000)).sum())
    yield "How many orders have profit below -20000?", int((d.profit < -20000).sum())
    yield "How many orders have profit below -₹20,000?", int((d.profit < -20000).sum())
    yield "How many orders have profit below 0?", int((d.profit < 0).sum())
    yield "How many orders have profit above -5000?", int((d.profit > -5000).sum())
    yield "How many orders have profit between -10000 and 10000?", int(((d.profit >= -10000) & (d.profit <= 10000)).sum())
    yield "How many orders have discount percentage above 12.5%?", int((d.discount_percentage > 12.5).sum())
    yield "How many orders have discount percentage above 12.5 percent?", int((d.discount_percentage > 12.5).sum())
    yield "How many orders have discount percentage below 50%?", int((d.discount_percentage < 50).sum())
    yield "How many orders have discount percentage at least 80?", int((d.discount_percentage >= 80).sum())
    yield "How many orders have rating above 4.5?", int((d.rating > 4.5).sum())
    yield "How many orders have rating at most 2?", int((d.rating <= 2).sum())
    yield "How many orders have quantity at least 10?", int((d.quantity >= 10).sum())
    yield "How many orders have quantity more than 10?", int((d.quantity > 10).sum())
    yield "How many orders have quantity less than 3?", int((d.quantity < 3).sum())
    yield "How many orders have quantity no more than 3?", int((d.quantity <= 3).sum())
    yield "How many orders have quantity not more than 3?", int((d.quantity <= 3).sum())
    yield "How many orders have quantity not less than 10?", int((d.quantity >= 10).sum())
    yield "How many orders have quantity not above 3?", int((d.quantity <= 3).sum())
    yield "How many orders have quantity not below 10?", int((d.quantity >= 10).sum())
    yield "How many orders have quantity up to 3?", int((d.quantity <= 3).sum())
    yield "How many orders have quantity exactly 5?", None                  # equality: refuse, never ignore
    yield "How many orders have quantity equal to 5?", None
    yield "How many orders have quantity less than or equal to 3?", int((d.quantity <= 3).sum())
    yield "How many orders have quantity greater than or equal to 10?", int((d.quantity >= 10).sum())
    yield "How many orders have quantity above ten?", None                   # numbers in words: never guess
    yield "How many orders have amount above five lakh?", None
    yield "How many orders have quantity above 1,0?", None                   # nonsense number
    yield "How many North orders have amount above 5 lakh?", int(((d.amount > 500000) & (d.region == "North")).sum())
    yield "What is the total amount for orders with quantity above 8?", float(d[d.quantity > 8].amount.sum())


for plan_name, plan in PLANS.items():
    for question, truth in cases():
        QuestionUnderstanding.understand = lambda self, q, plan=plan: copy.deepcopy(plan)
        answer = engine.ask(question)
        if answer["status"] != "success":
            refused += 1
            continue
        if truth is None:
            # a format the code does not know: it may answer ONLY if the answer is right for some reading
            wrong.append((plan_name, question, "answered although the number format is unknown", answer["result"]))
            continue
        got = answer["result"]
        ok = abs(float(got) - float(truth)) < 1e-6 * max(1, abs(truth))
        if ok:
            passed += 1
        else:
            wrong.append((plan_name, question, truth, got))

total = passed + refused + len(wrong)
print(f"{total} question/plan combinations: {passed} correct, {refused} safely refused, {len(wrong)} WRONG")
for plan_name, question, want, got in wrong[:12]:
    print(f"  WRONG [{plan_name}] {question}  expected {want}  got {got}")
print(f"{total} checks, {len(wrong)} FAILED")
