"""
ROBUSTNESS TEST  (no AI needed, runs in seconds)

Takes every READY analyst question and deliberately DAMAGES the plan the AI
would give: missing intent, wrong operation, forgotten filter, invented
number filter, forgotten column ... Then checks that the code either repairs
the plan (correct answer) or refuses safely. A confident wrong answer is a bug.

Run it after every code change:
    python test_robustness.py ecommerce_sales_34500.csv
"""

import sys
import warnings; warnings.filterwarnings("ignore")
import copy, re
import pandas as pd
import test_analyst_questions as a
from ask_engine import AskEngine
from auto_benchmark import matches
from question_understanding import QuestionUnderstanding

df = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else "ecommerce_sales_34500.csv")
engine = AskEngine(df)
ready = [(q, truth, plan) for area, level, q, truth, plan, _ in a.Q if level == "READY"]

def m_none(p):        return dict(p)
def m_no_intent(p):   return dict(p, intent=None)
def m_wrong_op(p):    return dict(p, operation="count") if p["intent"] == "count" else dict(p, operation=None)
def m_no_filter(p):   return dict(p, group_column=None if p["intent"] not in ("top","bottom","trend") else p["group_column"], filter_value=None)
def m_no_columns(p):  return dict(p, column=None, value_column=None) if p["intent"] not in ("top","bottom","trend","unique","count","duplicate","missing") else dict(p, column=p["column"])
def m_junk_filter(p, q):
    n = re.search(r"\d[\d,.]*", q)
    return dict(p, filter_value=n.group(0)) if n and p["intent"] in ("count","total","average") and p["filter_value"] is None else dict(p)
def m_text_null(p):   return {k: ("null" if v is None else v) for k, v in p.items()}
def m_count_column(p): return dict(p, column="returned", operation="count") if p["intent"] == "count" else dict(p)

def m_wrong_filter_column(p, q):
    # the AI puts the right value on the WRONG column
    if p["filter_value"] is not None and p["intent"] not in ("top", "bottom", "trend"):
        other = "region" if p["group_column"] != "region" else "category"
        return dict(p, group_column=other)
    return dict(p)

def m_year_as_filter(p, q):
    # the AI turns the year in the question into a filter on order_id
    year = re.search(r"\b(20\d{2})\b", q)
    if year and p["intent"] in ("count", "total", "average"):
        return dict(p, group_column="order_id", filter_value=year.group(1))
    return dict(p)

def m_invented_yes(p, q):
    # the AI invents the filter "Yes" although the question never says it
    if p["filter_value"] is None and "return" not in q.lower() and p["intent"] in ("count", "total", "average"):
        return dict(p, filter_value="Yes")
    return dict(p)

def m_ranking_shape(p, q):
    # the AI calls a table / percentage / rate a "ranking" (real slip seen)
    words = re.search(r"\b(each|by|per|share|percentage|percent|rate|popular)\b", q.lower())
    if words and p["intent"] not in ("top", "bottom", "trend", "unique", "duplicate", "missing"):
        return dict(p, intent="top", operation="group_sum", group_column="category",
                    value_column=p["value_column"] or "returned", filter_value=None)
    return dict(p)

def force_intent(intent, operation):
    """The AI collapses every question into one calculation (a real risk)."""
    def mutate(p, q):
        if p["intent"] == intent:
            return dict(p)
        value = p["value_column"] or p["column"]
        return dict(p, intent=intent, operation=operation, value_column=value,
                    column=value if intent != "count" else None,
                    group_column=None)
    return mutate

def m_wrong_measure(p, q):
    """The AI answers on a DIFFERENT number column than the one named in the question."""
    if p["intent"] in ("total", "average", "maximum", "minimum", "top", "bottom", "trend") and (p["value_column"] or p["column"]):
        other = "shipping_cost" if (p["value_column"] or p["column"]) != "shipping_cost" else "price"
        return dict(p, value_column=other, column=other)
    return dict(p)

mutations = [
 ("ideal plan (no damage)",              lambda p, q: m_none(p)),
 ("intent missing",                      lambda p, q: m_no_intent(p)),
 ("wrong/missing operation",             lambda p, q: m_wrong_op(p)),
 ("filter and its column forgotten",     lambda p, q: m_no_filter(p)),
 ("measure column forgotten",            lambda p, q: m_no_columns(p)),
 ("invented numeric filter",             m_junk_filter),
 ("everything written as 'null' text",   lambda p, q: m_text_null(p)),
 ("count plan points at a column",       lambda p, q: m_count_column(p)),
 ("value placed on the WRONG column",    m_wrong_filter_column),
 ("year in the question used as filter",  m_year_as_filter),
 ("invented 'Yes' filter",               m_invented_yes),
 ("table/percentage planned as ranking",  m_ranking_shape),
 ("AI answers 'total' for everything",    force_intent("total", "sum")),
 ("AI answers 'average' for everything",  force_intent("average", "mean")),
 ("AI answers 'count' for everything",    force_intent("count", "row_count")),
 ("AI uses a DIFFERENT number column",    m_wrong_measure),
 ("AI answers 'missing values' for everything", force_intent("missing", "missing_count")),
 ("AI answers 'duplicates' for everything",     force_intent("duplicate", "duplicate_count")),
]

print(f"{'damage done to the AI plan':38s} correct  safe-refusal  WRONG")
total_wrong = 0
for name, mutate in mutations:
    good = refused = wrong = 0
    wrong_qs = []
    for q, truth, plan in ready:
        mutated = mutate(copy.deepcopy(plan), q)
        QuestionUnderstanding.understand = lambda self, question, mutated=mutated: dict(mutated)
        ans = engine.ask(q)
        if ans["status"] != "success": refused += 1
        elif matches(ans["result"], truth(df)): good += 1
        else: wrong += 1; wrong_qs.append((q, ans["response"][:60]))
    total_wrong += wrong
    print(f"{name:38s} {good:>4}/{len(ready)}   {refused:>8}   {wrong:>5}")
    for q, r in wrong_qs[:4]: print(f"      WRONG: {q[:55]:55s} -> {r}")
print("\nTotal confident-wrong answers across all damage types:", total_wrong)