"""
THE ANALYST QUESTION CATALOGUE

Hundreds of questions that data analysts and business analysts ask every day,
over six realistic datasets (retail, HR, SaaS, marketing, logistics, lending),
each with its correct answer worked out independently in pandas.

Every question has a LEVEL:
    BUILT    the app should answer it correctly today
    ROADMAP  a real analyst question the app does not do yet:
             refusing is fine, a WRONG number is a bug
    OUT      forecasts, "why", missing data, impossible questions:
             the app must REFUSE (an answer is UNSAFE)

Result per question:  CORRECT / REFUSED / WRONG / SAFE / UNSAFE

    python test_analyst_catalog.py                    offline, the AI says nothing (code only)
    python test_analyst_catalog.py weak               offline, the AI always says "total"
    python test_analyst_catalog.py noplan retail      only one dataset
    python test_analyst_catalog.py real 400           your real AI, 400 questions, saved to
                                                      catalog_results.csv (safe to stop and resume)
    add  --all  to list every refused question (the roadmap)
"""

import copy
import csv
import json
import math
import os
import random
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import analyst_data
import auto_benchmark as ab
from ask_engine import AskEngine
from dashboard import humanize
from filters import to_dates
from question_understanding import QuestionUnderstanding

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

AREAS = [
    # (area, level, what it covers)
    ("Basics", "BUILT", "totals, averages, highest, lowest, counts, distinct counts"),
    ("Filters and conditions", "BUILT", "by value, number conditions, dates, combinations"),
    ("Group comparisons", "BUILT", "by category: tables, best, worst, top 3, counts, averages"),
    ("Shares and percentages", "BUILT", "share of total, percentage of rows, rates by group"),
    ("Time trends", "BUILT", "monthly series, best and worst month, quarter and year totals"),
    ("Business KPIs", "BUILT", "rates and averages analysts report every week"),
    ("Data quality", "BUILT", "missing values, repeated rows"),
    ("Phrasing", "BUILT", "the same question in different words"),
    ("Two questions in one", "BUILT", "two questions in a single sentence"),
    ("Growth and comparison", "ROADMAP", "year on year, month on month, A versus B"),
    ("Statistics", "ROADMAP", "median, spread, percentiles, mode, correlation, outliers"),
    ("Ratio KPIs", "ROADMAP", "margin, CTR, ROAS, cost per km, revenue per customer"),
    ("Customer and entity analytics", "ROADMAP", "repeat buyers, one-time buyers, per-customer figures"),
    ("Concentration and ranking", "ROADMAP", "Pareto, top 10 percent, Nth best, rank of X"),
    ("Cross-tabs and filtered rankings", "ROADMAP", "two-way tables, best X within Y"),
    ("Calendar patterns", "ROADMAP", "weekday, month of year, per-day averages"),
    ("Relative dates", "OUT", "last month, this year, last 30 days"),
    ("Forecast and what-if", "OUT", "predictions and scenarios"),
    ("Why questions", "OUT", "causes and explanations"),
    ("Impossible questions", "OUT", "missing columns, outside information, private data"),
]
LEVEL_OF = {area: level for area, level, _ in AREAS}


def plural(word):
    if word.endswith("y") and not word.endswith(("ay", "ey", "oy")):
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    return word + "s"


def nice(value):
    value = float(value)
    if value == 0:
        return 0
    magnitude = 10 ** max(0, int(math.floor(math.log10(abs(value)))) - 1)
    rounded = round(value / magnitude) * magnitude
    return int(rounded) if rounded == int(rounded) else round(rounded, 2)


def best_mean(d, column, measure, highest=True):
    s = d.groupby(column)[measure].mean()
    target = s.max() if highest else s.min()
    return ({str(k).lower() for k in s[s == target].index}, float(target))


def best_ratio(d, column, numerator, denominator, highest=True, times=1):
    s = d.groupby(column)[numerator].sum() / d.groupby(column)[denominator].sum() * times
    target = s.max() if highest else s.min()
    return ({str(k).lower() for k in s[s == target].index}, float(target))


def casual(text):
    return text.strip().rstrip("?.").lower()


# ------------------------------------------------------------
# What each dataset is about (logical column names)
# ------------------------------------------------------------

SPECS = {
    "retail": dict(
        noun="orders", primary="revenue", date="order_date", row_id="order_id", entity="customer_id", entity_word="customers",
        additive=["revenue", "profit", "cost", "quantity"],
        averaged=["unit_price", "discount_pct", "delivery_days", "rating"],
        dims=["category", "region", "channel", "customer_segment", "payment_method"],
        flag=("returned", "Yes", "were returned"), time_measure="revenue", time_verb="ordered",
        absent=["salary", "temperature", "headcount"]),
    "hr": dict(
        noun="employees", primary="monthly_salary", date="hire_date", row_id="employee_id", entity=None, entity_word="employees",
        additive=["monthly_salary", "training_hours", "overtime_hours", "absent_days"],
        averaged=["age", "performance_score", "engagement_score", "tenure_years", "bonus_pct"],
        dims=["department", "job_level", "gender", "location", "remote_work"],
        flag=("attrition", "Yes", "left the company"), time_measure=None, time_verb="hired",
        absent=["revenue", "customer rating", "shipping cost"]),
    "saas": dict(
        noun="customers", primary="mrr", date="signup_date", row_id="customer_id", entity=None, entity_word="customers",
        additive=["mrr", "seats", "support_tickets", "usage_hours"],
        averaged=["nps_score"],
        dims=["plan", "billing_cycle", "country", "industry", "acquisition_channel"],
        flag=("churned", "Yes", "churned"), time_measure=None, time_verb="signed up",
        absent=["salary", "discount", "inventory"]),
    "marketing": dict(
        noun="records", primary="revenue", date="date", row_id=None, entity=None, entity_word="records",
        additive=["impressions", "clicks", "conversions", "spend", "revenue"],
        averaged=[],
        dims=["campaign", "channel", "region"],
        flag=None, time_measure="spend", time_verb="recorded",
        absent=["salary", "customer age", "profit margin percentage"]),
    "ops": dict(
        noun="shipments", primary="cost", date="ship_date", row_id="shipment_id", entity=None, entity_word="shipments",
        additive=["cost", "weight_kg", "distance_km"],
        averaged=["delay_days", "promised_days"],
        dims=["carrier", "mode", "priority", "origin", "destination"],
        flag=("damaged", "Yes", "were damaged"), time_measure="cost", time_verb="shipped",
        absent=["salary", "customer age", "revenue"]),
    "lending": dict(
        noun="loans", primary="loan_amount", date="origination_date", row_id="loan_id", entity=None, entity_word="loans",
        additive=["loan_amount", "annual_income"],
        averaged=["interest_rate", "credit_score", "debt_to_income", "employment_years", "term_months"],
        dims=["purpose", "region", "status"],
        flag=("status", "Default", "defaulted"), time_measure="loan_amount", time_verb="originated",
        absent=["salary", "customer rating", "revenue"]),
}


# ------------------------------------------------------------
# Build every question
# ------------------------------------------------------------

def build_questions(name, df, cols):

    spec = SPECS[name]
    C = lambda key: cols[key]
    label = lambda key: humanize(cols[key])
    noun = spec["noun"]
    date = C(spec["date"]) if spec["date"] else None
    primary = C(spec["primary"])
    P = label(spec["primary"])
    additive = [C(k) for k in spec["additive"]]
    averaged = [C(k) for k in spec["averaged"]]
    dims = [C(k) for k in spec["dims"]]
    entity = C(spec["entity"]) if spec["entity"] else None

    out = []

    def add(area, question, truth, kind="value", level=None):
        out.append({"ds": name, "area": area, "level": level or LEVEL_OF[area],
                    "q": question, "truth": truth, "kind": kind})

    def refuse(area, question):
        add(area, question, None, kind="refuse")

    # words for values: a value shared by two columns must be asked with its column
    owners = {}
    for c in dims:
        for v in df[c].dropna().unique():
            owners.setdefault(str(v).strip().lower(), set()).add(c)

    def named(c, v):
        return f"{humanize(c)} {v}" if len(owners.get(str(v).strip().lower(), ())) > 1 else str(v)

    def tot(m):
        return f"total {humanize(m)}" if not humanize(m).startswith("total") else humanize(m)

    def agg(d, m, kind="sum"):
        return d[m].sum() if kind == "sum" else d[m].mean()

    # ================= BASICS
    add("Basics", f"How many {noun} are there?", lambda d: len(d))
    for m in additive:
        h = humanize(m)
        add("Basics", f"What is the {tot(m)}?", lambda d, m=m: d[m].sum())
        add("Basics", f"What is the average {h}?", lambda d, m=m: d[m].mean())
        add("Basics", f"What is the highest {h}?", lambda d, m=m: d[m].max())
        add("Basics", f"What is the lowest {h}?", lambda d, m=m: d[m].min())
    for m in averaged:
        h = humanize(m)
        add("Basics", f"What is the average {h}?", lambda d, m=m: d[m].mean())
        add("Basics", f"What is the highest {h}?", lambda d, m=m: d[m].max())
        add("Basics", f"What is the lowest {h}?", lambda d, m=m: d[m].min())
    for c in dims:
        add("Basics", f"How many different {plural(humanize(c))} are there?", lambda d, c=c: d[c].nunique())
    if entity:
        add("Basics", f"How many unique {spec['entity_word']} are there?", lambda d: d[entity].nunique())

    # ================= FILTERS AND CONDITIONS
    for c in dims[:3]:
        values = list(df[c].value_counts().index[:2])
        for v in values:
            w = named(c, v)
            add("Filters and conditions", f"What is the {tot(primary)} for {w}?", lambda d, c=c, v=v: ab.rows_where(d, c, v)[primary].sum())
            add("Filters and conditions", f"What is the average {humanize(primary)} for {w}?", lambda d, c=c, v=v: ab.rows_where(d, c, v)[primary].mean())
            add("Filters and conditions", f"How many {noun} are there for {w}?", lambda d, c=c, v=v: len(ab.rows_where(d, c, v)))
    for m in (additive + averaged)[:4]:
        s = df[m].dropna()
        hi, lo = nice(s.quantile(0.75)), nice(s.quantile(0.25))
        if hi == lo or hi <= 0:
            continue
        h = humanize(m)
        add("Filters and conditions", f"How many {noun} have {h} above {hi}?", lambda d, m=m, x=hi: int((d[m] > x).sum()))
        add("Filters and conditions", f"How many {noun} have {h} below {lo}?", lambda d, m=m, x=lo: int((d[m] < x).sum()))
        add("Filters and conditions", f"How many {noun} have {h} between {lo} and {hi}?", lambda d, m=m, a=lo, b=hi: int(((d[m] >= a) & (d[m] <= b)).sum()))
        add("Filters and conditions", f"How many {noun} have {h} at least {hi}?", lambda d, m=m, x=hi: int((d[m] >= x).sum()))
    if date:
        stamps = to_dates(df[date])
        years = sorted(stamps.dropna().dt.year.unique())
        year = int(years[len(years) // 2]) if len(years) > 1 else int(years[0])
        verb = spec["time_verb"]
        add("Filters and conditions", f"How many {noun} were {verb} in {year}?" if spec["time_verb"] != "recorded" else f"How many {noun} are there in {year}?",
            lambda d, y=year: int((to_dates(d[date]).dt.year == y).sum()))
        add("Filters and conditions", f"What is the {tot(primary)} in {year}?", lambda d, y=year: d[to_dates(d[date]).dt.year == y][primary].sum())
        middle = stamps.dropna().sort_values().iloc[len(stamps.dropna()) // 2]
        month_name = f"{MONTHS[middle.month - 1]} {middle.year}"
        add("Filters and conditions", f"What is the {tot(primary)} in {month_name}?",
            lambda d, y=middle.year, mo=middle.month: d[(to_dates(d[date]).dt.year == y) & (to_dates(d[date]).dt.month == mo)][primary].sum())
        quarter = (middle.month - 1) // 3 + 1
        add("Filters and conditions", f"What is the {tot(primary)} in Q{quarter} {middle.year}?",
            lambda d, y=middle.year, q=quarter: d[(to_dates(d[date]).dt.year == y) & (to_dates(d[date]).dt.quarter == q)][primary].sum())
        if dims:
            c = dims[0]
            v = df[c].value_counts().index[0]
            add("Filters and conditions", f"What is the {tot(primary)} for {named(c, v)} in {year}?",
                lambda d, y=year, c=c, v=v: ab.rows_where(d[to_dates(d[date]).dt.year == y], c, v)[primary].sum())
    if len(dims) >= 2:
        (c1, c2) = dims[0], dims[1]
        v1 = df[c1].value_counts().index[0]
        v2 = df[df[c1] == v1][c2].value_counts().index[0]            # a pair that really occurs
        add("Filters and conditions", f"What is the {tot(primary)} for {named(c1, v1)} in {named(c2, v2)}?",
            lambda d, c1=c1, c2=c2, v1=v1, v2=v2: ab.rows_where(ab.rows_where(d, c1, v1), c2, v2)[primary].sum())
        add("Filters and conditions", f"How many {noun} are there for {named(c1, v1)} in {named(c2, v2)}?",
            lambda d, c1=c1, c2=c2, v1=v1, v2=v2: len(ab.rows_where(ab.rows_where(d, c1, v1), c2, v2)))

    # ================= GROUP COMPARISONS
    for c in dims[:3]:
        w, pw = humanize(c), plural(humanize(c))
        add("Group comparisons", f"Show {P} by {w}", lambda d, c=c: {str(k): v for k, v in d.groupby(c)[primary].sum().items()})
        add("Group comparisons", f"Which {w} has the highest {P}?", lambda d, c=c: ab._best(d, c, primary, True))
        add("Group comparisons", f"Which {w} has the lowest {P}?", lambda d, c=c: ab._best(d, c, primary, False))
        add("Group comparisons", f"How many {noun} are there in each {w}?", lambda d, c=c: {str(k): v for k, v in d.groupby(c).size().items()})
        add("Group comparisons", f"Show average {P} by {w}", lambda d, c=c: {str(k): v for k, v in d.groupby(c)[primary].mean().items()})
        add("Group comparisons", f"Which {w} has the most {noun}?",
            lambda d, c=c: ({str(k).lower() for k, v in d.groupby(c).size().items() if v == d.groupby(c).size().max()}, float(d.groupby(c).size().max())))
        add("Group comparisons", f"What are the top 3 {pw} by {P}?", lambda d, c=c: ("TOPK", c, primary, 3, True), kind="topk")

    # ================= SHARES AND PERCENTAGES
    if dims:
        c = dims[0]
        v = df[c].value_counts().index[0]
        add("Shares and percentages", f"What share of {P} comes from {named(c, v)}?", lambda d: ab.rows_where(d, c, v)[primary].sum() / d[primary].sum() * 100)
        add("Shares and percentages", f"What percentage of {noun} are {named(c, v)}?", lambda d: len(ab.rows_where(d, c, v)) / len(d) * 100)
        add("Shares and percentages", f"What is the share of {P} by {humanize(c)}?",
            lambda d: {str(k): x / d[primary].sum() * 100 for k, x in d.groupby(c)[primary].sum().items()})
    if spec["flag"]:
        fcol, fval, fphrase = spec["flag"]
        fc = C(fcol)
        add("Shares and percentages", f"What percentage of {noun} {fphrase}?", lambda d: (d[fc].astype(str).str.strip() == fval).mean() * 100)
        add("Shares and percentages", f"How many {noun} {fphrase}?", lambda d: int((d[fc].astype(str).str.strip() == fval).sum()))
        if dims and dims[0] != fc:
            c = dims[0]
            add("Shares and percentages", f"What percentage of {noun} {fphrase} in each {humanize(c)}?",
                lambda d, c=c, fc=fc, fval=fval: {str(k): v * 100 for k, v in (d[fc].astype(str).str.strip() == fval).groupby(d[c]).mean().items()})

    # ================= TIME TRENDS
    tm = C(spec["time_measure"]) if spec["time_measure"] else None
    if date and tm:
        add("Time trends", f"Show me monthly {humanize(tm)}", lambda d: ab._monthly(d, date, tm))
        monthly = lambda d: d.assign(_m=to_dates(d[date]).dt.to_period("M").astype(str)).groupby("_m")[tm].sum()
        add("Time trends", f"Which month had the highest {humanize(tm)}?", lambda d: ({str(monthly(d).idxmax()).lower()}, float(monthly(d).max())))
        add("Time trends", f"Which month had the lowest {humanize(tm)}?", lambda d: ({str(monthly(d).idxmin()).lower()}, float(monthly(d).min())))
        add("Time trends", f"What is the average monthly {humanize(tm)}?", lambda d: float(monthly(d).mean()))

    # ================= BUSINESS KPIs (built)
    if name == "retail":
        add("Business KPIs", "What is the average order value?", lambda d: d["revenue"].mean())
        add("Business KPIs", "What is the average delivery time?", lambda d: d["delivery_days"].mean())
        add("Business KPIs", "What percentage of orders were returned?", lambda d: (d["returned"] == "Yes").mean() * 100)
        add("Business KPIs", "How many orders made a loss?", lambda d: int((d["profit"] < 0).sum()))
        add("Business KPIs", "What is the average discount for returned orders?", lambda d: d[d["returned"] == "Yes"]["discount_pct"].mean())
        add("Business KPIs", "Which category has the highest profit?", lambda d: ab._best(d, "category", "profit", True))
        add("Business KPIs", "What is the average order value by channel?", lambda d: {str(k): v for k, v in d.groupby("channel")["revenue"].mean().items()})
        add("Business KPIs", "What is the total revenue from returned orders?", lambda d: d[d["returned"] == "Yes"]["revenue"].sum())
        add("Business KPIs", "Who is our best customer by revenue?", lambda d: ab._best(d, "customer_id", "revenue", True))
        add("Business KPIs", "What are the top 5 customers by revenue?", lambda d: ("TOPK", "customer_id", "revenue", 5, True), kind="topk")
    if name == "hr":
        hc = dict(cols)
        add("Business KPIs", "What is the attrition rate?", lambda d: (d[hc["attrition"]] == "Yes").mean() * 100)
        add("Business KPIs", "What is the average tenure of employees?", lambda d: d[hc["tenure_years"]].mean())
        add("Business KPIs", "What is the total payroll?", lambda d: d[hc["monthly_salary"]].sum())
        add("Business KPIs", "Which department has the highest average monthly salary?", lambda d: best_mean(d, hc["department"], hc["monthly_salary"]))
        add("Business KPIs", "What is the average tenure of employees who left the company?",
            lambda d: d[d[hc["attrition"]] == "Yes"][hc["tenure_years"]].mean())
        add("Business KPIs", "What percentage of employees work remotely?", lambda d: (d[hc["remote_work"]] == "Yes").mean() * 100)
        add("Business KPIs", "How many employees earn more than 100000 per month?", lambda d: int((d[hc["monthly_salary"]] > 100000).sum()))
    if name == "saas":
        add("Business KPIs", "What is the churn rate?", lambda d: (d["churned"] == "Yes").mean() * 100)
        add("Business KPIs", "What is the total MRR?", lambda d: d["mrr"].sum())
        add("Business KPIs", "What is the average MRR per customer?", lambda d: d["mrr"].mean())
        add("Business KPIs", "How many customers have mrr above 0?", lambda d: int((d["mrr"] > 0).sum()))
        add("Business KPIs", "Which plan has the highest mrr?", lambda d: ab._best(d, "plan", "mrr", True))
        add("Business KPIs", "Which acquisition channel brings the most customers?",
            lambda d: ({str(k).lower() for k, v in d.groupby("acquisition_channel").size().items() if v == d.groupby("acquisition_channel").size().max()}, float(d.groupby("acquisition_channel").size().max())))
        add("Business KPIs", "How many customers have an nps score of at least 9?", lambda d: int((d["nps_score"] >= 9).sum()))
    if name == "marketing":
        mk = dict(cols)
        add("Business KPIs", "What is the total spend?", lambda d: d[mk["spend"]].sum())
        add("Business KPIs", "Which channel has the highest spend?", lambda d: ab._best(d, mk["channel"], mk["spend"], True))
        add("Business KPIs", "Which campaign has the highest revenue?", lambda d: ab._best(d, mk["campaign"], mk["revenue"], True))
        add("Business KPIs", "Which region has the lowest conversions?", lambda d: ab._best(d, mk["region"], mk["conversions"], False))
    if name == "ops":
        add("Business KPIs", "What percentage of shipments were delivered on time?", lambda d: (d["on_time"] == "Yes").mean() * 100)
        add("Business KPIs", "What is the average delay in days?", lambda d: d["delay_days"].mean())
        add("Business KPIs", "Which carrier has the highest total cost?", lambda d: ab._best(d, "carrier", "cost", True))
        add("Business KPIs", "What is the total cost by mode?", lambda d: {str(k): v for k, v in d.groupby("mode")["cost"].sum().items()})
        add("Business KPIs", "How many shipments were delayed by more than 2 days?", lambda d: int((d["delay_days"] > 2).sum()))
    if name == "lending":
        lg = dict(cols)
        add("Business KPIs", "What percentage of loans defaulted?", lambda d: (d[lg["status"]] == "Default").mean() * 100)
        add("Business KPIs", "What is the total loan amount?", lambda d: d[lg["loan_amount"]].sum())
        add("Business KPIs", "What is the average interest rate?", lambda d: d[lg["interest_rate"]].mean())
        add("Business KPIs", "What is the average loan amount by purpose?", lambda d: {str(x): v for x, v in d.groupby(lg["purpose"])[lg["loan_amount"]].mean().items()})
        add("Business KPIs", "What is the average credit score of loans that defaulted?",
            lambda d: d[d[lg["status"]] == "Default"][lg["credit_score"]].mean())
        add("Business KPIs", "How many loans have a credit score below 600?", lambda d: int((d[lg["credit_score"]] < 600).sum()))

    # ================= DATA QUALITY
    add("Data quality", "How many missing values are there?", lambda d: int(d.isnull().sum().sum()))
    add("Data quality", "Are there any duplicate rows? How many?", lambda d: int(d.duplicated().sum()))
    with_blanks = [c for c in df.columns if df[c].isnull().any() and not c.lower().endswith(("date",))][:2]
    for c in with_blanks:
        add("Data quality", f"How many missing values are there in {humanize(c)}?", lambda d, c=c: int(d[c].isnull().sum()))

    # ================= PHRASING (the same question, different words)
    for text in [f"What are our total {P}?", f"how much {P} in total", f"Total {P} please", f"{P} total", f"tell me the sum of all {P}",
                 f"What is the overall {P}?", f"What is the combined {P}?", f"WHAT IS THE TOTAL {P.upper()}?"]:
        add("Phrasing", text, lambda d: d[primary].sum())
    if name == "retail":
        for text in ["How much money did we make?", "What are our total sales?", "What is our turnover?", "What did we earn in total?"]:
            add("Phrasing", text, lambda d: d["revenue"].sum())
    for text in [f"What is the mean {P}?", f"what's the average {P}", f"avg {P}"]:
        add("Phrasing", text, lambda d: d[primary].mean())
    for text in [f"What is the biggest {P}?", f"What is the maximum {P}?", f"largest {P}"]:
        add("Phrasing", text, lambda d: d[primary].max())
    for text in [f"What is the smallest {P}?", f"minimum {P}"]:
        add("Phrasing", text, lambda d: d[primary].min())
    if dims:
        c = dims[0]
        add("Phrasing", f"Which {humanize(c)} brings in the most {P}?", lambda d: ab._best(d, c, primary, True))
        add("Phrasing", f"Best {humanize(c)} by {P}?", lambda d: ab._best(d, c, primary, True))
        add("Phrasing", f"worst performing {humanize(c)} by {P}", lambda d: ab._best(d, c, primary, False))
        add("Phrasing", f"{P} split by {humanize(c)}", lambda d: {str(k): v for k, v in d.groupby(c)[primary].sum().items()})
        add("Phrasing", f"{P} for each {humanize(c)}", lambda d: {str(k): v for k, v in d.groupby(c)[primary].sum().items()})
    for text in [f"How many {noun}?", f"number of {noun}", f"count of {noun}", f"total number of {noun}"]:
        add("Phrasing", text, lambda d: len(d))

    # ================= TWO QUESTIONS IN ONE
    other = [m for m in additive if m != primary]
    if other:
        o = other[0]
        add("Two questions in one", f"What is the {tot(primary)} and what is the {tot(o)}?", lambda d: [d[primary].sum(), d[o].sum()], kind="multi")
        add("Two questions in one", f"What is the average {P} and how many {noun} are there?", lambda d: [d[primary].mean(), len(d)], kind="multi")
        add("Two questions in one", f"What is the highest {P} and what is the lowest {P}?", lambda d: [d[primary].max(), d[primary].min()], kind="multi")

    # ================= GROWTH AND COMPARISON (roadmap)
    if date and tm:
        stamps = to_dates(df[date])
        years = sorted(stamps.dropna().dt.year.unique())
        y1, y2 = int(years[0]), int(years[1])
        yearly = lambda d, y: d[to_dates(d[date]).dt.year == y][tm].sum()
        add("Growth and comparison", f"How much did {humanize(tm)} grow from {y1} to {y2}?", lambda d: yearly(d, y2) - yearly(d, y1))
        add("Growth and comparison", f"What is the year on year growth in {humanize(tm)} from {y1} to {y2}?", lambda d: (yearly(d, y2) - yearly(d, y1)) / yearly(d, y1) * 100)
        add("Growth and comparison", f"Did {humanize(tm)} go up or down in {y2} compared with {y1}?", lambda d: (yearly(d, y2) - yearly(d, y1)) / yearly(d, y1) * 100)
        add("Growth and comparison", f"What is the percentage change in {humanize(tm)} between {y1} and {y2}?", lambda d: (yearly(d, y2) - yearly(d, y1)) / yearly(d, y1) * 100)
        monthly = lambda d: d.assign(_m=to_dates(d[date]).dt.to_period("M")).groupby("_m")[tm].sum()
        add("Growth and comparison", f"What was the month on month growth in {humanize(tm)} in March {y2}?",
            lambda d: (monthly(d)[pd.Period(f"{y2}-03")] - monthly(d)[pd.Period(f"{y2}-02")]) / monthly(d)[pd.Period(f"{y2}-02")] * 100)
        add("Growth and comparison", f"Which year had the highest {humanize(tm)}?",
            lambda d: ({str(int(y)) for y in years if yearly(d, y) == max(yearly(d, yy) for yy in years)}, float(max(yearly(d, yy) for yy in years))))
    if len(dims) >= 1:
        c = dims[0]
        vals = list(df[c].value_counts().index[:2])
        if len(vals) == 2:
            a, b = vals
            add("Growth and comparison", f"Compare {named(c, a)} and {named(c, b)} by {P}",
                lambda d, c=c, a=a, b=b: {str(a): ab.rows_where(d, c, a)[primary].sum(), str(b): ab.rows_where(d, c, b)[primary].sum()})
            add("Growth and comparison", f"What is the difference in {P} between {named(c, a)} and {named(c, b)}?",
                lambda d, c=c, a=a, b=b: ab.rows_where(d, c, a)[primary].sum() - ab.rows_where(d, c, b)[primary].sum())
            add("Growth and comparison", f"How many times bigger is {named(c, a)} than {named(c, b)} by {P}?",
                lambda d, c=c, a=a, b=b: ab.rows_where(d, c, a)[primary].sum() / ab.rows_where(d, c, b)[primary].sum())

    # ================= STATISTICS (roadmap)
    for m in [primary] + (additive + averaged)[1:2]:
        h = humanize(m)
        add("Statistics", f"What is the median {h}?", lambda d, m=m: d[m].median())
        add("Statistics", f"What is the standard deviation of {h}?", lambda d, m=m: d[m].std())
        add("Statistics", f"What is the variance of {h}?", lambda d, m=m: d[m].var())
        add("Statistics", f"What is the 90th percentile of {h}?", lambda d, m=m: d[m].quantile(0.9))
        add("Statistics", f"What is the 25th percentile of {h}?", lambda d, m=m: d[m].quantile(0.25))
        add("Statistics", f"What is the range of {h}?", lambda d, m=m: d[m].max() - d[m].min())
        add("Statistics", f"What is the interquartile range of {h}?", lambda d, m=m: d[m].quantile(0.75) - d[m].quantile(0.25))
        add("Statistics", f"How many {noun} are above the average {h}?", lambda d, m=m: int((d[m] > d[m].mean()).sum()))
        add("Statistics", f"How many {noun} are below the median {h}?", lambda d, m=m: int((d[m] < d[m].median()).sum()))
        add("Statistics", f"Are there any outliers in {h}? How many?",
            lambda d, m=m: int(((d[m] > d[m].quantile(0.75) + 1.5 * (d[m].quantile(0.75) - d[m].quantile(0.25))) | (d[m] < d[m].quantile(0.25) - 1.5 * (d[m].quantile(0.75) - d[m].quantile(0.25)))).sum()))
        add("Statistics", f"What is the most common value of {h}?", lambda d, m=m: d[m].mode().iloc[0])
    pair = (additive + averaged)[:2]
    if len(pair) == 2:
        a, b = pair
        add("Statistics", f"What is the correlation between {humanize(a)} and {humanize(b)}?", lambda d: d[a].corr(d[b]))
        add("Statistics", f"Is there a relationship between {humanize(a)} and {humanize(b)}?", lambda d: d[a].corr(d[b]))

    # ================= RATIO KPIs (roadmap)
    ratios = {
        "retail": [("What is the overall profit margin?", lambda d: d["profit"].sum() / d["revenue"].sum() * 100),
                   ("What is the average revenue per customer?", lambda d: d["revenue"].sum() / d["customer_id"].nunique()),
                   ("What is the average number of orders per customer?", lambda d: len(d) / d["customer_id"].nunique()),
                   ("Which category has the highest profit margin?", lambda d: best_ratio(d, "category", "profit", "revenue", True, 100)),
                   ("What is the revenue per unit sold?", lambda d: d["revenue"].sum() / d["quantity"].sum())],
        "hr": [("What is the average salary per department?", lambda d: {str(k): v for k, v in d.groupby(cols["department"])[cols["monthly_salary"]].mean().items()}),
               ("What is the total annual payroll?", lambda d: d[cols["monthly_salary"]].sum() * 12)],
        "saas": [("What is the annual recurring revenue (ARR)?", lambda d: d["mrr"].sum() * 12),
                 ("What is the average revenue per paying customer?", lambda d: d[d["mrr"] > 0]["mrr"].mean()),
                 ("What is the average number of seats per customer?", lambda d: d["seats"].mean())],
        "marketing": [("What is the click through rate (CTR)?", lambda d: d[cols["clicks"]].sum() / d[cols["impressions"]].sum() * 100),
                      ("What is the cost per click (CPC)?", lambda d: d[cols["spend"]].sum() / d[cols["clicks"]].sum()),
                      ("What is the cost per acquisition (CPA)?", lambda d: d[cols["spend"]].sum() / d[cols["conversions"]].sum()),
                      ("What is the return on ad spend (ROAS)?", lambda d: d[cols["revenue"]].sum() / d[cols["spend"]].sum()),
                      ("What is the conversion rate?", lambda d: d[cols["conversions"]].sum() / d[cols["clicks"]].sum() * 100),
                      ("What is the ROI of our campaigns?", lambda d: (d[cols["revenue"]].sum() - d[cols["spend"]].sum()) / d[cols["spend"]].sum() * 100),
                      ("Which channel has the highest ROAS?", lambda d: best_ratio(d, cols["channel"], cols["revenue"], cols["spend"], True))],
        "ops": [("What is the average cost per kilometre?", lambda d: d["cost"].sum() / d["distance_km"].sum()),
                ("What is the average cost per kg?", lambda d: d["cost"].sum() / d["weight_kg"].sum()),
                ("What is the average transit time in days?", lambda d: (to_dates(d["delivery_date"]) - to_dates(d["ship_date"])).dt.days.mean())],
        "lending": [("What is the loan to income ratio?", lambda d: d[cols["loan_amount"]].sum() / d[cols["annual_income"]].sum()),
                    ("What is the weighted average interest rate by loan amount?", lambda d: (d[cols["interest_rate"]] * d[cols["loan_amount"]]).sum() / d[cols["loan_amount"]].sum()),
                    ("What is the total amount of loans that defaulted?", lambda d: d[d[cols["status"]] == "Default"][cols["loan_amount"]].sum())],
    }
    for question, truth in ratios.get(name, []):
        add("Ratio KPIs", question, truth)

    # ================= CUSTOMER AND ENTITY ANALYTICS (roadmap)
    if name == "retail":
        per = lambda d: d.groupby("customer_id").size()
        add("Customer and entity analytics", "How many customers placed more than one order?", lambda d: int((per(d) > 1).sum()))
        add("Customer and entity analytics", "What is the repeat customer rate?", lambda d: (per(d) > 1).mean() * 100)
        add("Customer and entity analytics", "How many customers bought only once?", lambda d: int((per(d) == 1).sum()))
        add("Customer and entity analytics", "What is the highest number of orders placed by one customer?", lambda d: int(per(d).max()))
        add("Customer and entity analytics", "How many customers spent more than 5000 in total?", lambda d: int((d.groupby("customer_id")["revenue"].sum() > 5000).sum()))
        add("Customer and entity analytics", "What is the average spend per customer?", lambda d: d.groupby("customer_id")["revenue"].sum().mean())
        add("Customer and entity analytics", "How many customers ordered in both 2023 and 2024?",
            lambda d: len(set(d[to_dates(d["order_date"]).dt.year == 2023]["customer_id"]) & set(d[to_dates(d["order_date"]).dt.year == 2024]["customer_id"])))
        add("Customer and entity analytics", "How many customers bought from more than 3 categories?", lambda d: int((d.groupby("customer_id")["category"].nunique() > 3).sum()))
    if name == "saas":
        add("Customer and entity analytics", "How many churned customers were on the Pro plan?", lambda d: int(((d["churned"] == "Yes") & (d["plan"] == "Pro")).sum()))
        add("Customer and entity analytics", "What is the churn rate for the Free plan?", lambda d: (d[d["plan"] == "Free"]["churned"] == "Yes").mean() * 100)
        add("Customer and entity analytics", "What is the average customer lifetime in days for churned customers?",
            lambda d: (to_dates(d[d["churned"] == "Yes"]["churn_date"]) - to_dates(d[d["churned"] == "Yes"]["signup_date"])).dt.days.mean())
    if name == "hr":
        add("Customer and entity analytics", "What is the attrition rate in the Support department?",
            lambda d: (d[d[cols["department"]] == "Support"][cols["attrition"]] == "Yes").mean() * 100)
        add("Customer and entity analytics", "How many employees left in 2024?",
            lambda d: int((to_dates(d[cols["termination_date"]]).dt.year == 2024).sum()))
    if name == "lending":
        add("Customer and entity analytics", "What is the default rate for business loans?",
            lambda d: (d[d[cols["purpose"]] == "Business"][cols["status"]] == "Default").mean() * 100)

    # ================= CONCENTRATION AND RANKING (roadmap)
    if dims:
        c = dims[0]
        add("Concentration and ranking", f"What is the second best {humanize(c)} by {P}?",
            lambda d: (lambda s: ({str(s.index[1]).lower()}, float(s.iloc[1])))(d.groupby(c)[primary].sum().sort_values(ascending=False)))
        add("Concentration and ranking", f"What share of {P} comes from the top 3 {plural(humanize(c))}?",
            lambda d: d.groupby(c)[primary].sum().sort_values(ascending=False).iloc[:3].sum() / d[primary].sum() * 100)
        top_value = df.groupby(c)[primary].sum().sort_values(ascending=False).index[0]
        add("Concentration and ranking", f"What rank is {named(c, top_value)} by {P}?", lambda d: 1)
        add("Concentration and ranking", f"What are the top 5 {plural(humanize(c))} by number of {noun}?", lambda d: ("TOPCOUNT", c, 5), kind="topcount")
    if entity:
        add("Concentration and ranking", f"What share of {P} comes from the top 10 {spec['entity_word']}?",
            lambda d: d.groupby(entity)[primary].sum().sort_values(ascending=False).iloc[:10].sum() / d[primary].sum() * 100)
        add("Concentration and ranking", f"What share of {P} comes from the top 10 percent of {spec['entity_word']}?",
            lambda d: (lambda s: s.iloc[:max(1, int(len(s) * 0.1))].sum() / s.sum() * 100)(d.groupby(entity)[primary].sum().sort_values(ascending=False)))
    if name == "retail":
        add("Concentration and ranking", "How many products make up 80 percent of revenue?",
            lambda d: int((d.groupby("product_id")["revenue"].sum().sort_values(ascending=False).cumsum() / d["revenue"].sum() < 0.8).sum() + 1))

    # ================= CROSS-TABS AND FILTERED RANKINGS (roadmap)
    if len(dims) >= 2:
        c1, c2 = dims[0], dims[1]
        add("Cross-tabs and filtered rankings", f"Show {P} by {humanize(c1)} and {humanize(c2)}",
            lambda d: {f"{a} | {b}": v for (a, b), v in d.groupby([c1, c2])[primary].sum().items()})
        v2 = df[c2].value_counts().index[0]
        add("Cross-tabs and filtered rankings", f"Which {humanize(c1)} has the highest {P} in {named(c2, v2)}?",
            lambda d: ab._best(ab.rows_where(d, c2, v2), c1, primary, True))
        add("Cross-tabs and filtered rankings", f"What are the top 3 {plural(humanize(c1))} by {P} for {named(c2, v2)}?",
            lambda d: ("TOPK_FILTER", c1, primary, 3, c2, v2), kind="topk_filter")
        v1 = df[c1].value_counts().index[0]
        add("Cross-tabs and filtered rankings", f"Show {P} by {humanize(c2)} for {named(c1, v1)}",
            lambda d: {str(k): v for k, v in ab.rows_where(d, c1, v1).groupby(c2)[primary].sum().items()})

    # ================= CALENDAR PATTERNS (roadmap)
    if date and tm:
        add("Calendar patterns", f"Which day of the week has the highest {humanize(tm)}?",
            lambda d: (lambda s: ({str(s.idxmax()).lower()}, float(s.max())))(d.assign(_w=to_dates(d[date]).dt.day_name()).groupby("_w")[tm].sum()))
        add("Calendar patterns", f"Which month of the year has the highest {humanize(tm)} across all years?",
            lambda d: (lambda s: ({MONTHS[int(s.idxmax()) - 1].lower()}, float(s.max())))(d.assign(_m=to_dates(d[date]).dt.month).groupby("_m")[tm].sum()))
        add("Calendar patterns", f"What is the average daily {humanize(tm)}?",
            lambda d: d[tm].sum() / to_dates(d[date]).dt.normalize().nunique())
        add("Calendar patterns", f"How many {noun} are there on weekends?", lambda d: int((to_dates(d[date]).dt.dayofweek >= 5).sum()))
        add("Calendar patterns", f"What is the average number of {noun} per month?",
            lambda d: len(d) / to_dates(d[date]).dt.to_period("M").nunique())

    # ================= RELATIVE DATES (must refuse: the app cannot know "today" safely)
    for text in [f"What is the {tot(primary)} last month?", f"What is the {tot(primary)} this year?", f"How many {noun} in the last 30 days?",
                 f"What is the {tot(primary)} year to date?", f"Show {P} for the last quarter", f"How many {noun} were there yesterday?"]:
        refuse("Relative dates", text)

    # ================= FORECAST / WHAT-IF (must refuse)
    for text in [f"Forecast the {P} for next month", f"What will the {P} be next year?", f"Predict next quarter's {P}",
                 f"If we increase {P} by 10 percent, what will the total be?", f"What if we remove the lowest {humanize(dims[0]) if dims else 'group'}?",
                 f"Which {humanize(dims[0]) if dims else 'group'} will perform best next year?", f"Project {P} for the next 6 months"]:
        refuse("Forecast and what-if", text)

    # ================= WHY QUESTIONS (must refuse)
    for text in [f"Why did {P} drop?", f"What is causing the change in {P}?", f"Why is {humanize(dims[0]) if dims else 'it'} performing badly?",
                 f"What should we do to improve {P}?", f"Explain why {P} is high in some months", f"What are the reasons for low {P}?"]:
        refuse("Why questions", text)

    # ================= IMPOSSIBLE QUESTIONS (must refuse)
    for missing in spec["absent"]:
        refuse("Impossible questions", f"What is the average {missing}?")
        refuse("Impossible questions", f"What is the total {missing}?")
    refuse("Impossible questions", f"What is the {P} in euros?")
    refuse("Impossible questions", f"What is our market share in {P}?")
    refuse("Impossible questions", f"How do we compare with our competitors on {P}?")
    refuse("Impossible questions", "What is the phone number of the best performer?")
    refuse("Impossible questions", f"Show {P} by salesperson")
    refuse("Impossible questions", f"What is the industry benchmark for {P}?")
    refuse("Impossible questions", "What is the weather like?")
    refuse("Impossible questions", "Delete all the rows with missing values")

    return out


# ------------------------------------------------------------
# Compare answers
# ------------------------------------------------------------

def judge(item, answer, df):

    if item["kind"] == "refuse":
        if answer["status"] != "success":
            return "SAFE", answer["message"][:80]
        return "UNSAFE", answer["response"][:100]

    if answer["status"] != "success":
        return "REFUSED", answer["message"][:90]

    try:
        expected = item["truth"](df)
    except Exception as error:                                   # a truth that cannot be computed is a test bug
        return "TESTBUG", repr(error)[:90]

    got = answer["result"]
    kind = item["kind"]

    if expected is None or (isinstance(expected, float) and expected != expected):
        return "TESTBUG", "no correct answer could be computed"

    if expected == "UPDOWN":                                     # a yes/no question: any numeric answer is wrong
        return "WRONG", str(answer["response"])[:90]

    if kind == "topk":
        _, column, measure, k, highest = expected
        series = df.groupby(column)[measure].sum()
        want = sorted(series.sort_values(ascending=not highest).iloc[:k].tolist())
        pairs = list(got) if isinstance(got, list) else []
        ok = len(pairs) == min(k, len(series)) and all(ab.close(v, float(series[[x for x in series.index if str(x) == str(n)][0]])) for n, v in pairs if str(n) in {str(x) for x in series.index}) \
            and all(ab.close(a, b) for a, b in zip(sorted(v for _, v in pairs), want))
        return ("CORRECT" if ok else "WRONG"), str(answer["response"])[:90]

    if kind == "topcount":
        _, column, k = expected
        counts = df.groupby(column).size()
        want = sorted(counts.sort_values(ascending=False).iloc[:k].tolist())
        pairs = list(got) if isinstance(got, list) else []
        ok = len(pairs) == min(k, len(counts)) and all(ab.close(a, b) for a, b in zip(sorted(v for _, v in pairs), want))
        return ("CORRECT" if ok else "WRONG"), str(answer["response"])[:90]

    if kind == "topk_filter":
        _, column, measure, k, fcol, fval = expected
        sub = ab.rows_where(df, fcol, fval).groupby(column)[measure].sum()
        want = sorted(sub.sort_values(ascending=False).iloc[:k].tolist())
        pairs = list(got) if isinstance(got, list) else []
        ok = len(pairs) == min(k, len(sub)) and all(ab.close(a, b) for a, b in zip(sorted(v for _, v in pairs), want))
        return ("CORRECT" if ok else "WRONG"), str(answer["response"])[:90]

    try:
        if isinstance(expected, (int, float, np.integer, np.floating)) and not isinstance(expected, bool):
            ok = ab.matches(got, float(expected))
        else:
            ok = ab.matches(got, expected)
    except Exception:
        ok = False

    return ("CORRECT" if ok else "WRONG"), f"expected {str(expected)[:50]} | {str(answer['response'])[:80]}"


def judge_multi(item, pairs, df):
    expected = item["truth"](df)
    if len(pairs) != 2:
        return "REFUSED", f"split into {len(pairs)} part(s)"
    if any(a["status"] != "success" for _, a in pairs):
        return "REFUSED", " | ".join((a.get("response") or a["message"])[:40] for _, a in pairs)
    ok = all(ab.matches(a["result"], float(e)) for (_, a), e in zip(pairs, expected))
    return ("CORRECT" if ok else "WRONG"), " | ".join(a["response"][:45] for _, a in pairs)


# ------------------------------------------------------------
# Run
# ------------------------------------------------------------

def run_dataset(name, df, cols, mode, limit=None):

    engine = AskEngine(df)
    d = engine.df
    questions = build_questions(name, df, cols)
    primary = cols[SPECS[name]["primary"]]
    weak = ab.plan("total", "sum", primary, None, primary)
    empty = ab.plan(None, None)

    if limit and limit < len(questions):
        random.Random(5).shuffle(questions)
        questions = questions[:limit]

    if mode != "real":
        plan = weak if mode == "weak" else empty
        QuestionUnderstanding.understand = lambda self, q: copy.deepcopy(plan)

    results = []

    for item in questions:
        started = time.time()
        try:
            if item["kind"] == "multi":
                outcome, got = judge_multi(item, engine.ask_many(item["q"]), d)
            else:
                outcome, got = judge(item, engine.ask(item["q"]), d)
        except Exception as error:
            outcome, got = "CRASH", repr(error)[:100]
        results.append((item, outcome, got, time.time() - started))

    return results


def report(results, show_all=False):

    by_area = {}
    for item, outcome, got, _ in results:
        by_area.setdefault(item["area"], {}).setdefault(outcome, 0)
        by_area[item["area"]][outcome] += 1

    print(f"\n{'area':34s} {'level':8s} {'total':>5s} {'correct':>8s} {'refused':>8s} {'WRONG':>6s} {'safe':>5s} {'UNSAFE':>7s}  completed")
    totals = {}
    for area, level, _ in AREAS:
        c = by_area.get(area)
        if not c:
            continue
        total = sum(c.values())
        right = c.get("CORRECT", 0) + c.get("SAFE", 0)
        bad = c.get("WRONG", 0) + c.get("UNSAFE", 0) + c.get("CRASH", 0) + c.get("TESTBUG", 0)
        print(f"{area:34s} {level:8s} {total:5d} {c.get('CORRECT', 0):8d} {c.get('REFUSED', 0):8d} {c.get('WRONG', 0):6d} {c.get('SAFE', 0):5d} {c.get('UNSAFE', 0):7d}  {right / total * 100:5.0f}%" + (f"   <-- {bad} BUG(S)" if bad else ""))
        for k, v in c.items():
            totals[k] = totals.get(k, 0) + v

    n = sum(totals.values())
    bugs = totals.get("WRONG", 0) + totals.get("UNSAFE", 0) + totals.get("CRASH", 0) + totals.get("TESTBUG", 0)
    print(f"{'ALL':34s} {'':8s} {n:5d} {totals.get('CORRECT', 0):8d} {totals.get('REFUSED', 0):8d} {totals.get('WRONG', 0):6d} {totals.get('SAFE', 0):5d} {totals.get('UNSAFE', 0):7d}")
    print(f"\n  answered correctly or safely refused: {(n - bugs) / n * 100:.1f}%   BUGS (wrong / unsafe / crash / test bug, must be 0): {bugs}")

    for label in ("WRONG", "UNSAFE", "CRASH", "TESTBUG"):
        rows = [(i, g) for i, o, g, _ in results if o == label]
        if rows:
            print(f"\n  {label} ({len(rows)}):")
            for i, g in rows[: (len(rows) if show_all else 14)]:
                print(f"     [{i['ds']}/{i['area']}] {i['q'][:70]}  ->  {g[:100]}")

    if show_all:
        rows = [(i, g) for i, o, g, _ in results if o == "REFUSED"]
        print(f"\n  REFUSED ({len(rows)}), the roadmap:")
        for i, g in rows:
            print(f"     [{i['ds']}/{i['area']}/{i['level']}] {i['q'][:80]}")

    return bugs


def run_real(limit, out_path, only=None):
    """The real AI: a fair sample of every area, saved as it goes, safe to resume."""

    datasets = analyst_data.make_all()
    pool = []
    for name, (df, cols) in datasets.items():
        if only and name != only:
            continue
        for item in build_questions(name, df, cols):
            pool.append(item)

    by_area, chosen, rng = {}, [], random.Random(3)
    for item in pool:
        by_area.setdefault((item["area"]), []).append(item)
    while len(chosen) < min(limit, len(pool)):
        for area in sorted(by_area):
            if by_area[area] and len(chosen) < limit:
                chosen.append(by_area[area].pop(rng.randrange(len(by_area[area]))))
        if not any(by_area.values()):
            break

    done = set()
    if os.path.exists(out_path):
        with open(out_path, newline="", encoding="utf-8") as handle:
            done = {(r["dataset"], r["question"]) for r in csv.DictReader(handle)}

    print(f"{len(chosen)} questions chosen, {len(done)} already done. Getting the AI ready...", flush=True)

    engines = {}
    new_file = not os.path.exists(out_path)
    with open(out_path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["dataset", "area", "level", "question", "outcome", "seconds", "got", "ai_plan"])
        for number, item in enumerate(chosen, start=1):
            if (item["ds"], item["q"]) in done:
                continue
            if item["ds"] not in engines:
                df, cols = datasets[item["ds"]]
                engines[item["ds"]] = AskEngine(df)
                if len(engines) == 1:
                    engines[item["ds"]].warm_up()
            engine = engines[item["ds"]]
            started = time.time()
            try:
                if item["kind"] == "multi":
                    outcome, got = judge_multi(item, engine.ask_many(item["q"]), engine.df)
                else:
                    outcome, got = judge(item, engine.ask(item["q"]), engine.df)
            except Exception as error:
                outcome, got = "CRASH", repr(error)[:100]
            seconds = time.time() - started
            raw = getattr(engine.pipeline, "last_raw_plan", None)
            writer.writerow([item["ds"], item["area"], item["level"], item["q"], outcome, f"{seconds:.1f}", got, json.dumps(raw, default=str)])
            handle.flush()
            print(f"{number:4d}/{len(chosen)} {outcome:8s} {seconds:4.0f}s [{item['ds']}/{item['area']}] {item['q'][:60]}", flush=True)

    with open(out_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    counts = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    print("\nSUMMARY:", counts, "| WRONG, UNSAFE and CRASH must be 0")
    for row in rows:
        if row["outcome"] in ("WRONG", "UNSAFE", "CRASH", "TESTBUG"):
            print("   ", row["outcome"], "|", row["dataset"], "|", row["question"], "->", row["got"][:100])


def main():
    args = sys.argv[1:]
    show_all = "--all" in args
    words = [a for a in args if not a.startswith("--")]
    mode = next((w for w in words if w in ("noplan", "weak", "real")), "noplan")
    names = [w for w in words if w in analyst_data.BUILDERS]
    numbers = [w for w in words if w.isdigit()]

    if mode == "real":
        run_real(int(numbers[0]) if numbers else 400, "catalog_results.csv", names[0] if names else None)
        return

    datasets = analyst_data.make_all()
    results = []
    for name, (df, cols) in datasets.items():
        if names and name not in names:
            continue
        results += run_dataset(name, df, cols, mode)

    bugs = report(results, show_all)
    print(f"{len(results)} checks, {bugs} FAILED")


if __name__ == "__main__":
    main()