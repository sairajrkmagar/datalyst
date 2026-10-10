"""
ADVANCED QUESTIONS, ANSWERED BY CODE (no AI needed)

Statistics (median, spread, percentiles, correlation, outliers), ratio KPIs
(margin, CTR, CPC, CPA, ROAS, cost per km, revenue per customer), growth and
comparisons (year on year, month on month, A versus B), customer questions
(repeat buyers), rankings (second best, rank of X, share of the top N, Pareto),
cross-tabs, filtered rankings, calendar patterns (weekday, month of the year,
per day), and questions about a yes/no event ("employees who left").

The AI is not used here: the question is read with patterns, the columns and
values are found in the data, and pandas does the arithmetic. A question that
belongs to one of these families but cannot be completed is REFUSED with a
reason, never answered with a nearby number.

    answer = try_answer(engine, "What is the median revenue?")   # a dict, or None
"""

from safe_numbers import is_whole
import re

import numpy as np
import pandas as pd

from filters import apply_filters, to_dates
from plan_repair import (
    REVENUE_WORDS, column_pattern, find_mentioned_values, parse_date_filter,
    pick_date_column, readable_label, unmapped_words_problem, word_forms,
)

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
]

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "fifty": 50,
    "hundred": 100,
}

ORDINALS = {
    "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4,
    "fifth": 5, "5th": 5,
}

HIGH_WORDS = r"(?:highest|best|top|most|largest|biggest|greatest|maximum|max|strongest)"
LOW_WORDS = r"(?:lowest|worst|bottom|least|smallest|fewest|minimum|min|weakest)"

# words people use for a number column that is not named like that in the file
MEASURE_SYNONYMS = {
    "payroll": ("salary", "pay", "wage", "compensation"),
    "compensation": ("salary", "pay", "wage", "compensation"),
    "salaries": ("salary", "pay", "wage"),
}

# "per kg", "per kilometre": the number column that is divided by
UNIT_COLUMNS = {
    "km": ("distance", "km"), "kilometre": ("distance", "km"), "kilometer": ("distance", "km"),
    "kilometres": ("distance", "km"), "kilometers": ("distance", "km"),
    "kg": ("weight", "kg"), "kilogram": ("weight", "kg"), "kilograms": ("weight", "kg"),
    "unit": ("quantity", "units", "items"), "units": ("quantity", "units", "items"),
    "item": ("quantity", "items", "units"), "items": ("quantity", "items", "units"),
    "click": ("clicks",), "clicks": ("clicks",),
    "impression": ("impressions",), "impressions": ("impressions",),
    "seat": ("seats",), "seats": ("seats",),
    "hour": ("hours",), "hours": ("hours",),
    "conversion": ("conversions",), "conversions": ("conversions",),
}

# yes/no events described by a verb: "employees who LEFT the company"
EVENT_VERBS = [
    (r"\b(left|leave|leaves|leaving|resigned|resign|quit|attrited)\b(?:\s+the\s+(?:company|organi[sz]ation|firm))?",
     ("attrition", "terminat", "exit", "resign", "churn", "left")),
    (r"\b(churned|cancel+ed)\b", ("churn", "cancel")),
]
LOSS_PATTERN = (
    r"\b(?:made|make|making|had|have|has)\s+(?:a\s+)?loss(?:es)?\b|\bloss[- ]making\b|"
    r"\bunprofitable\b|\bat\s+a\s+loss\b|\bnegative\s+profit\b|\bin\s+loss\b"
)
PROFIT_PATTERN = r"\bprofitable\b|\bmade\s+a\s+profit\b"

YES_NO = {"yes", "no", "true", "false", "y", "n", "0", "1"}


class Refuse(Exception):
    """A question of this family that cannot be answered: say why."""


# ------------------------------------------------------------
# What the question is about
# ------------------------------------------------------------

class Ctx:

    def __init__(self, engine, question):

        self.engine = engine
        self.df = engine.df
        self.q = str(question)
        self.t = self.q.lower().strip()

        profile, under = engine.profile, engine.dataset_understanding

        self.measures = list(profile.get("measures", under["measures"]))
        self.ids = list(profile.get("identifier_columns", []))
        self.dates = list(under["date_columns"])
        self.dim_values = dict(under["dimension_values"])
        self.dims = [c for c in self.dim_values if c not in self.ids]
        self.noun = profile.get("count_noun") or "records"
        self.revenue = profile.get("revenue_column")
        self.main_map = dict(profile.get("main_columns", {}))
        self.alias = {main: original for original, main in self.main_map.items()}

    # ---- names
    def label(self, column):
        text = readable_label(self.alias.get(column, column))
        return re.sub(r" main$", "", text)

    def tokens(self, column):
        return set(re.findall(r"[a-z0-9]+", readable_label(self.alias.get(column, column))))

    def named(self, pool):
        """Columns of `pool` written in the question, in the order of appearance."""

        text, found = self.t, []

        for column in sorted(pool, key=lambda c: -len(str(self.alias.get(c, c)))):
            match = re.search(column_pattern(self.alias.get(column, column)), text)
            if match:
                found.append((match.start(), column))
                text = text[:match.start()] + " " * (match.end() - match.start()) + text[match.end():]

        return [column for _, column in sorted(found, key=lambda x: x[0])]

    def by_words(self, words, pool=None):
        """The one column of `pool` whose name contains one of the words."""

        pool = self.measures if pool is None else pool
        wanted = {w for word in words for w in word_forms(word)}
        hits = [c for c in pool if self.tokens(c) & wanted]

        if len(hits) > 1:
            exact = [c for c in hits if self.tokens(c) <= wanted]
            hits = exact or hits

        if len(hits) > 1:
            fewest = min(len(self.tokens(c)) for c in hits)
            hits = [c for c in hits if len(self.tokens(c)) == fewest]

        return hits[0] if len(hits) == 1 else None

    def loose_measure(self, text):
        """A number column named by ONE of its words ("tenure" for "Tenure Years")."""

        generic = {"total", "average", "highest", "lowest", "number", "count", "amount", "value", "percentage", "percent", "share", "employees", "customers", "orders"}
        words = {w for w in re.findall(r"[a-z]{4,}", text) if w not in generic}
        wanted = {f for w in words for f in word_forms(w)}
        hits = [m for m in self.measures if self.tokens(m) & wanted]
        return hits[0] if len(hits) == 1 else None

    def measure(self):
        """The number column this question is about, or None."""

        named = self.named(self.measures)

        if len(named) == 1:
            return named[0]

        if len(named) > 1:
            return None

        for word, stems in MEASURE_SYNONYMS.items():
            if re.search(rf"\b{word}\b", self.t):
                found = self.by_words(stems)
                if found:
                    return found

        if REVENUE_WORDS.search(self.t) and self.revenue:
            return self.revenue

        return None

    def need_measure(self):
        measure = self.measure()
        if measure is None:
            raise Refuse(
                "Which number column do you mean? Please name it, for example "
                "'median revenue'."
            )
        return measure

    def years(self):
        return [int(y) for y in re.findall(r"\b((?:19|20)\d\d)\b", self.t)]

    def date_for(self, measure=None):
        if not self.dates:
            raise Refuse("This file has no date column, so I cannot answer that.")
        hint = self.label(measure) if measure else ""
        return pick_date_column(self.t + " " + hint, self.dates)

    def entity(self, word):
        """'customers' -> the customer id column (one value per customer)."""

        forms = word_forms(word.lower())

        for column in self.ids:
            if self.tokens(column) & forms:
                return column

        return None

    def dim_from_noun(self, word):
        """'categories' -> category, 'carriers' -> carrier."""

        forms = word_forms(word.lower())

        for column in self.dims:
            if self.tokens(column) & forms:
                return column

        return None

    def values_in_question(self):
        labels = [readable_label(c) for c in self.df.columns]
        phrase = r"standard deviation|annual recurring revenue|monthly recurring revenue|(?:annual|yearly|annualized|annualised)\s+(?:payroll|salary|revenue|total)"
        question = re.sub(phrase, lambda m: " " * len(m.group(0)), self.q, flags=re.IGNORECASE)
        found = find_mentioned_values(question, self.dim_values, labels)
        return {c: v for c, v in found.items() if v}

    def subset(self, use_values=True, skip=()):
        """The rows the question is about (value and single-period filters).
        `skip`: 5-letter word starts already used for something else."""

        filters = []

        if use_values:
            filters = [
                {"column": c, "value": v[0]} for c, v in self.values_in_question().items()
                if str(v[0]).lower()[:5] not in skip
            ]

        date_filter = None

        if self.dates and len(set(self.years())) == 1:
            date_filter, problem = parse_date_filter(
                self.q, self.dates, self.engine.profile.get("date_years", []), ""
            )
            if problem:
                raise Refuse(problem)

        data = apply_filters(self.df, filters, date_filter)

        if len(data) == 0:
            raise Refuse("No rows match that selection.")

        return data, filters, date_filter

    def chips(self, kind, measure=None, filters=(), extra=()):
        chips = [{"text": kind, "tone": "blue"}]
        if measure:
            chips.append({"text": self.label(measure), "tone": ""})
        for item in filters:
            chips.append({"text": f"{self.label(item['column'])} = {item['value']}", "tone": "green"})
        for text in extra:
            chips.append({"text": text, "tone": ""})
        return chips


def fmt(value):
    number = float(value)
    if number != number:
        return "n/a"
    if is_whole(number) and abs(number) < 1e15:
        return f"{int(number):,}"
    return f"{number:,.2f}"


def py(value):
    """A plain Python number (not numpy)."""
    number = float(value)
    return int(number) if is_whole(number) and abs(number) < 1e15 else number


def answer(c, kind, result, response, chips=None, unit=""):
    plan = {
        "intent": "advanced", "column": None, "group_column": None,
        "value_column": None, "filter_value": None, "operation": "advanced",
        "advanced": {"kind": kind, "chips": chips or []}, "unit": unit,
        "filters": [], "conditions": [], "date_filter": None,
        "count_noun": c.noun,
    }
    return {
        "status": "success", "question": c.q, "plan": plan,
        "repairs": [f"answered by code: {kind}"], "result": result,
        "response": response,
    }


def groups(data, column, measure, how="sum"):
    series = data.groupby(column)[measure].agg(how)
    return {str(k): float(v) for k, v in series.items()}


# ------------------------------------------------------------
# 1. Statistics
# ------------------------------------------------------------

def h_stats(c):

    t = c.t

    if re.search(r"correlat\w*|relationship between|association between", t):

        pair = c.named(c.measures)

        if len(pair) != 2:
            raise Refuse(
                "Please name the two number columns, for example 'correlation "
                "between price and quantity'."
            )

        a, b = pair
        data, filters, _ = c.subset()
        value = float(data[a].corr(data[b]))
        return answer(
            c, "correlation", value,
            f"The correlation between {c.label(a)} and {c.label(b)} is {value:.3f}.",
            c.chips("Correlation", None, filters, [c.label(a), c.label(b)]),
        )

    above = re.search(
        r"(?:how many|number of).*?\b(above|below|over|under|more than|less than|"
        r"greater than|lower than|higher than)\s+(?:the\s+)?(average|mean|median)\b", t,
    )

    if above:
        measure = c.need_measure()
        data, filters, _ = c.subset()
        series = pd.to_numeric(data[measure], errors="coerce")
        limit = series.median() if above.group(2) == "median" else series.mean()
        up = above.group(1) in ("above", "over", "more than", "greater than", "higher than")
        count = int((series > limit).sum() if up else (series < limit).sum())
        return answer(
            c, "count vs average", count,
            f"{fmt(count)} {c.noun} have {c.label(measure)} {'above' if up else 'below'} the "
            f"{above.group(2)} ({fmt(limit)}).",
            c.chips("Count", measure, filters, [f"{'above' if up else 'below'} the {above.group(2)}"]),
        )

    checks = [
        ("median", r"\bmedian\b"),
        ("std", r"standard deviation|std\.? ?dev|\bstdev\b"),
        ("variance", r"\bvariance\b"),
        ("iqr", r"interquartile range|\biqr\b"),
        ("range", r"\brange of\b|\bwhat is the range\b"),
        ("outliers", r"\boutliers?\b"),
        ("percentile", r"\d{1,2}(?:\.\d+)?\s*(?:st|nd|rd|th)?\s+percentile"),
        ("q1", r"first quartile|lower quartile"),
        ("q3", r"third quartile|upper quartile"),
        ("mode", r"most common|most frequent|\bmode (?:of|value)\b|\bthe mode\b"),
    ]

    kind = next((name for name, pattern in checks if re.search(pattern, t)), None)

    if kind is None:
        return None

    if kind == "mode" and not c.named(c.measures):
        return None                       # "most common payment method": not a number

    measure = c.need_measure()
    data, filters, _ = c.subset()
    series = pd.to_numeric(data[measure], errors="coerce").dropna()
    name = c.label(measure)

    if kind == "median":
        value, text = series.median(), f"Median {name} is {{}}."
    elif kind == "std":
        value, text = series.std(), f"The standard deviation of {name} is {{}}."
    elif kind == "variance":
        value, text = series.var(), f"The variance of {name} is {{}}."
    elif kind == "iqr":
        value, text = series.quantile(0.75) - series.quantile(0.25), f"The interquartile range of {name} is {{}}."
    elif kind == "range":
        value, text = series.max() - series.min(), f"The range of {name} is {{}}."
    elif kind == "q1":
        value, text = series.quantile(0.25), f"The first quartile of {name} is {{}}."
    elif kind == "q3":
        value, text = series.quantile(0.75), f"The third quartile of {name} is {{}}."
    elif kind == "percentile":
        p = float(re.search(r"(\d{1,2}(?:\.\d+)?)\s*(?:st|nd|rd|th)?\s+percentile", t).group(1))
        value, text = series.quantile(p / 100), f"The {p:g}th percentile of {name} is {{}}."
    elif kind == "mode":
        value, text = series.mode().iloc[0], f"The most common value of {name} is {{}}."
    else:
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        spread = q3 - q1
        outside = (series > q3 + 1.5 * spread) | (series < q1 - 1.5 * spread)
        count = int(outside.sum())
        return answer(
            c, "outliers", count,
            f"{fmt(count)} {c.noun} have unusual {name} (more than 1.5 times the "
            f"interquartile range beyond the quartiles: below {fmt(q1 - 1.5 * spread)} "
            f"or above {fmt(q3 + 1.5 * spread)}).",
            c.chips("Outliers", measure, filters),
        )

    return answer(c, kind, py(value), text.format(fmt(value)), c.chips(kind.upper() if kind in ("std", "iqr") else kind.capitalize(), measure, filters))


# ------------------------------------------------------------
# 2. Ratio KPIs
# ------------------------------------------------------------

KPIS = [
    # name, question pattern, numerator words, denominator words, times, unit
    ("click through rate", r"click[- ]through rate|\bctr\b", ("clicks", "click"), ("impressions", "impression"), 100, "%"),
    ("cost per click", r"cost per click|\bcpc\b", ("spend", "cost"), ("clicks", "click"), 1, ""),
    ("cost per acquisition", r"cost per (?:acquisition|conversion|lead)|\bcpa\b", ("spend", "cost"), ("conversions", "conversion", "leads"), 1, ""),
    ("return on ad spend", r"return on ad spend|\broas\b", ("revenue", "sales"), ("spend", "cost"), 1, "x"),
    ("conversion rate", r"conversion rate", ("conversions", "conversion"), ("clicks", "click"), 100, "%"),
    ("loan to income ratio", r"loan[- ]to[- ]income", ("loan",), ("income",), 1, ""),
]


def ratio_parts(c, numerator_words, denominator_words):
    top = c.by_words(numerator_words)
    bottom = c.by_words(denominator_words)

    if top is None or bottom is None:
        raise Refuse(
            "I need two number columns for that ratio "
            f"({' / '.join(numerator_words[:1])} and {' / '.join(denominator_words[:1])}), "
            "and I could not find both in your data."
        )
    return top, bottom


def group_ratio(c, data, top, bottom, times, how, label):
    """The ratio per group, when the question says 'by <column>' or 'which <column> has the highest'."""

    dims = c.named(c.dims)

    if len(dims) != 1:
        return None

    dim = dims[0]
    sums = data.groupby(dim)[[top, bottom]].sum() if how == "sum" else None
    values = (sums[top] / sums[bottom] * times).replace([np.inf, -np.inf], np.nan).dropna()

    if values.empty:
        raise Refuse("No groups have a value to divide by.")

    if re.search(rf"\b(?:which|what)\b.*\b{HIGH_WORDS}\b|\b{HIGH_WORDS}\b", c.t) and re.search(r"\bwhich\b|\bwho\b", c.t):
        best = values.idxmax()
        return answer(c, label, (str(best), float(values.max())), f"{best} has the highest {label} ({fmt(values.max())}).", c.chips(label, None, (), [c.label(dim)]))

    if re.search(r"\bwhich\b", c.t) and re.search(rf"\b{LOW_WORDS}\b", c.t):
        worst = values.idxmin()
        return answer(c, label, (str(worst), float(values.min())), f"{worst} has the lowest {label} ({fmt(values.min())}).", c.chips(label, None, (), [c.label(dim)]))

    table = {str(k): float(v) for k, v in values.items()}
    return answer(c, label, table, f"{label.capitalize()} by {c.label(dim)}: " + ", ".join(f"{k} ({fmt(v)})" for k, v in list(table.items())[:8]) + ".", c.chips(label, None, (), [f"by {c.label(dim)}"]))


def h_ratio(c):

    t = c.t

    # ---- average order value: each row is an order
    if re.search(r"\baverage order value\b|\baov\b|\baverage basket\b", t) and not c.named(c.measures) and not c.named(c.dims) and not re.search(r"\b(?:by|per|for each|in each)\b", t):
        revenue = c.revenue
        if revenue is None:
            raise Refuse("Which number is the value of an order? Please name it, for example 'average total amount'.")
        data, filters, _ = c.subset()
        value = float(data[revenue].mean())
        return answer(c, "average order value", py(value), f"The average order value is {fmt(value)} (average {c.label(revenue)} per {c.noun[:-1] if c.noun.endswith('s') else c.noun}).", c.chips("Average", revenue, filters))

    # ---- named KPIs
    for label, pattern, num_words, den_words, times, unit in KPIS:
        if re.search(pattern, t):
            top, bottom = ratio_parts(c, num_words, den_words)
            data, filters, _ = c.subset()
            grouped = group_ratio(c, data, top, bottom, times, "sum", label)
            if grouped:
                return grouped
            value = float(data[top].sum() / data[bottom].sum() * times)
            return answer(
                c, label, py(value), f"{label.capitalize()} is {fmt(value)}{'%' if unit == '%' else 'x' if unit == 'x' else ''}.",
                c.chips(label.capitalize(), None, filters), unit=unit,
            )

    if re.search(r"\broi\b|return on investment", t):
        revenue = c.by_words(("revenue", "sales"))
        spend = c.by_words(("spend", "cost"))
        if revenue is None or spend is None:
            raise Refuse("I need a revenue column and a spend column to calculate ROI.")
        data, filters, _ = c.subset()
        value = float((data[revenue].sum() - data[spend].sum()) / data[spend].sum() * 100)
        return answer(c, "roi", py(value), f"ROI is {fmt(value)}%.", c.chips("ROI", None, filters), unit="%")

    # ---- margin: profit as a percent of revenue (unless the file has a margin column)
    if re.search(r"\bmargin\b", t):
        if any("margin" in c.tokens(m) for m in c.measures):
            return None
        profit = c.by_words(("profit",))
        revenue = c.revenue or c.by_words(("revenue", "sales"))
        if profit is None or revenue is None:
            raise Refuse("I need a profit column and a revenue column to calculate a margin.")
        data, filters, _ = c.subset()
        grouped = group_ratio(c, data, profit, revenue, 100, "sum", "profit margin")
        if grouped:
            return grouped
        value = float(data[profit].sum() / data[revenue].sum() * 100)
        return answer(c, "profit margin", py(value), f"The profit margin is {fmt(value)}%.", c.chips("Profit margin", None, filters), unit="%")

    # ---- weighted average
    weighted = re.search(r"weighted average", t)
    if weighted:
        pair = c.named(c.measures)
        if len(pair) != 2:
            raise Refuse("Please name the two number columns, for example 'weighted average interest rate by loan amount'.")
        x, w = pair
        data, filters, _ = c.subset()
        value = float((data[x] * data[w]).sum() / data[w].sum())
        return answer(c, "weighted average", py(value), f"The average {c.label(x)} weighted by {c.label(w)} is {fmt(value)}.", c.chips("Weighted average", x, filters, [f"by {c.label(w)}"]))

    # ---- annualised: ARR, annual payroll
    if re.search(r"\barr\b|annual recurring revenue", t):
        mrr = c.by_words(("mrr",)) or c.by_words(("recurring",))
        if mrr is None:
            raise Refuse("I need a monthly recurring revenue column (mrr) for ARR.")
        data, filters, _ = c.subset()
        value = float(data[mrr].sum() * 12)
        return answer(c, "arr", py(value), f"The annual recurring revenue is {fmt(value)} (monthly total x 12).", c.chips("ARR", mrr, filters))

    if re.search(r"\b(annual|yearly|annualized|annualised)\b", t):
        measure = c.measure()
        if measure is not None and "monthly" in c.tokens(measure) | {"monthly"} and ("monthly" in c.tokens(measure)):
            data, filters, _ = c.subset()
            value = float(data[measure].sum() * 12)
            return answer(c, "annualised", py(value), f"The annual {c.label(measure)} is {fmt(value)} (monthly total x 12).", c.chips("Annual total", measure, filters))

    # ---- average time between two dates: transit time, customer lifetime
    lifespan = re.search(r"\b(?:average|mean)\s+(?:customer\s+)?(lifetime|transit time|delivery time|lead time|processing time|turnaround time|duration|time to)\b", t)
    if lifespan and len(c.dates) >= 2:
        start_words = ("ship", "order", "signup", "start", "hire", "open", "creat", "origin", "join", "sign")
        end_words = ("deliver", "arriv", "end", "close", "churn", "terminat", "exit", "complet", "cancel")
        starts = [d for d in c.dates if any(w in readable_label(d).replace(" ", "") for w in start_words)]
        ends = [d for d in c.dates if any(w in readable_label(d).replace(" ", "") for w in end_words)]
        if len(starts) == 1 and len(ends) == 1 and starts != ends:
            data, filters, _ = c.subset()
            both = pd.DataFrame({"a": to_dates(data[starts[0]]), "b": to_dates(data[ends[0]])}).dropna()
            if both.empty:
                raise Refuse("No rows have both dates.")
            days = float((both["b"] - both["a"]).dt.days.mean())
            return answer(c, "duration", py(days), f"The average time from {c.label(starts[0])} to {c.label(ends[0])} is {fmt(days)} days.", c.chips("Average days", None, filters, [f"{c.label(starts[0])} to {c.label(ends[0])}"]))

    # ---- "revenue per kg", "cost per kilometre"
    unit = re.search(r"\bper\s+(kilometres?|kilometers?|km|kilograms?|kg|units?|items?|clicks?|impressions?|seats?|hours?|conversions?)\b", t)
    if unit:
        words = UNIT_COLUMNS[unit.group(1)]
        bottom = c.by_words(words)
        before = t[:unit.start()]
        tops = [m for m in c.named(c.measures) if m != bottom]
        top = tops[0] if tops else None
        if top is None and REVENUE_WORDS.search(before) and c.revenue:
            top = c.revenue
        if top is None or bottom is None:
            raise Refuse(f"I need two number columns for 'per {unit.group(1)}', and I could not find both.")
        data, filters, _ = c.subset()
        value = float(data[top].sum() / data[bottom].sum())
        return answer(c, "ratio", py(value), f"{c.label(top).capitalize()} per {unit.group(1)} is {fmt(value)} ({c.label(top)} total divided by {c.label(bottom)} total).", c.chips("Ratio", top, filters, [f"per {unit.group(1)}"]))

    # ---- per customer, per employee ...
    entity_word = re.search(r"\bper\s+(?:paying\s+)?(customer|client|buyer|user|employee|patient|student|account|product|shipment|loan)s?\b", t)
    if entity_word:
        return per_entity(c, entity_word)

    return None


def per_entity(c, match):

    word = match.group(1)
    paying = "paying" in match.group(0)
    data, filters, _ = c.subset()
    before = c.t[:match.start()]
    entity = c.entity(word)
    rows_per = re.search(rf"\b(?:orders|purchases|transactions|records|rows|{re.escape(c.noun)})\b", before) and not c.named(c.measures)

    if rows_per:
        if entity is None or entity == c.ids[0] and data[entity].is_unique:
            raise Refuse(f"I cannot tell how many {c.noun} there are per {word}.")
        value = len(data) / data[entity].nunique()
        return answer(c, "per entity", py(value), f"There are {fmt(value)} {c.noun} per {word} on average.", c.chips("Per " + word, None, filters))

    measure = c.measure()

    if measure is None:
        raise Refuse(f"Which number should I divide per {word}? Please name it, for example 'revenue per {word}'.")

    if paying:
        value = float(data[data[measure] > 0][measure].mean())
        return answer(c, "per entity", py(value), f"The average {c.label(measure)} per paying {word} is {fmt(value)}.", c.chips("Average", measure, filters, [f"paying {word}s"]))

    # rows ARE the entity ("customers" in a subscription table): an average
    if entity is None or data[entity].is_unique or word_forms(word) & word_forms(c.noun):
        value = float(data[measure].mean())
        return answer(c, "per entity", py(value), f"The average {c.label(measure)} per {word} is {fmt(value)}.", c.chips("Average", measure, filters, [f"per {word}"]))

    value = float(data[measure].sum() / data[entity].nunique())
    return answer(c, "per entity", py(value), f"The average {c.label(measure)} per {word} is {fmt(value)} ({fmt(data[measure].sum())} across {fmt(data[entity].nunique())} {word}s).", c.chips("Average", measure, filters, [f"per {word}"]))


# ------------------------------------------------------------
# 3. Growth and comparisons
# ------------------------------------------------------------

def yearly(c, measure, date):
    stamps = to_dates(c.df[date])
    series = c.df.groupby(stamps.dt.year)[measure].sum()
    return {int(k): float(v) for k, v in series.items() if k == k}


def partial_note(c, date, *years):
    """'(2025 only has data for 9 months)' when a compared year is not complete."""

    stamps = to_dates(c.df[date]).dropna()
    notes = []

    for year in years:
        months = stamps[stamps.dt.year == year].dt.month.nunique()
        if 0 < months < 12:
            notes.append(f"{year} only has data for {months} month{'s' if months != 1 else ''}")

    return f" Note: {'; '.join(notes)}, so the comparison is not like for like." if notes else ""


def h_growth(c):

    t = c.t
    years = c.years()

    # ---- which year had the highest ...
    if re.search(r"\bwhich year\b", t) and re.search(rf"\b(?:{HIGH_WORDS}|{LOW_WORDS})\b", t):
        measure = c.need_measure()
        by_year = yearly(c, measure, c.date_for(measure))
        low = bool(re.search(rf"\b{LOW_WORDS}\b", t)) and not re.search(rf"\b{HIGH_WORDS}\b", t)
        year = (min if low else max)(by_year, key=by_year.get)
        return answer(c, "best year", (str(year), by_year[year]), f"{year} has the {'lowest' if low else 'highest'} {c.label(measure)} ({fmt(by_year[year])}).", c.chips("Year", measure))

    # ---- month on month
    if re.search(r"month on month|month-on-month|month over month|\bmom\b", t):
        found = re.search(rf"\b({'|'.join(MONTH_NAMES)})\s+((?:19|20)\d\d)\b", t)
        if not found:
            raise Refuse("Which month do you mean? Please write it like 'March 2025'.")
        measure = c.need_measure()
        date = c.date_for(measure)
        month = pd.Period(f"{found.group(2)}-{MONTH_NAMES.index(found.group(1)) + 1:02d}")
        stamps = to_dates(c.df[date])
        monthly = c.df.groupby(stamps.dt.to_period("M"))[measure].sum()
        if month not in monthly.index or (month - 1) not in monthly.index:
            raise Refuse(f"I need the data of both {month - 1} and {month} for that.")
        now, before = float(monthly[month]), float(monthly[month - 1])
        if before == 0:
            raise Refuse("The earlier month is zero, so a percentage change is not defined.")
        change = (now - before) / before * 100
        return answer(c, "month on month", py(change), f"{c.label(measure).capitalize()} in {month} is {fmt(now)} against {fmt(before)} in {month - 1}: {change:+.1f}%.", c.chips("Month on month", measure), unit="%")

    # ---- two years: change, growth, up or down
    if len(set(years)) >= 2 and re.search(r"grow|growth|increase|decrease|drop|fall|fell|rise|rose|change|up or down|higher or lower|year on year|yoy|year-over-year|compared|versus", t):
        measure = c.need_measure()
        by_year = yearly(c, measure, c.date_for(measure))
        newest_first = re.search(r"compared (?:with|to)|versus|\bvs\b|relative to", t)
        base, now = (years[1], years[0]) if newest_first else (years[0], years[1])
        if base not in by_year or now not in by_year:
            raise Refuse(f"I do not have data for both {base} and {now}.")
        before, after = by_year[base], by_year[now]
        name = c.label(measure)
        if re.search(r"how much did|by how much|how much has|difference", t) and not re.search(r"percent|%|growth rate|year on year|yoy", t):
            diff = after - before
            note = partial_note(c, c.date_for(measure), base, now)
            return answer(c, "change", py(diff), f"{name.capitalize()} changed by {diff:+,.2f} from {base} ({fmt(before)}) to {now} ({fmt(after)}).{note}", c.chips("Change", measure, (), [f"{base} to {now}"]))
        if before == 0:
            raise Refuse(f"{name} in {base} is zero, so a percentage change is not defined.")
        change = (after - before) / before * 100
        word = "up" if change >= 0 else "down"
        note = partial_note(c, c.date_for(measure), base, now)
        return answer(c, "growth", py(change), f"{name.capitalize()} went {word} {abs(change):.1f}% from {base} ({fmt(before)}) to {now} ({fmt(after)}).{note}", c.chips("Growth", measure, (), [f"{base} to {now}"]), unit="%")

    # ---- compare A and B, difference, how many times bigger
    compare = re.search(r"\bcompare\b|\bdifference (?:in|between)\b|\bhow many times (?:bigger|larger|more|higher|greater)\b", t)
    if compare:
        mentions = c.values_in_question()
        pairs = [(col, v) for col, vals in mentions.items() for v in vals]
        if len(pairs) != 2 or pairs[0][0] != pairs[1][0]:
            raise Refuse("Please name two values of the same column to compare, for example 'compare Fashion and Beauty by revenue'.")
        col = pairs[0][0]
        a, b = sorted((pairs[0][1], pairs[1][1]), key=lambda v: t.find(str(v).lower()))
        named = c.named(c.measures)
        measure = c.measure() if len(named) <= 1 else None
        data = c.df

        def part(value):
            rows = data[data[col].astype(str).str.strip().str.lower() == str(value).lower()]
            return float(rows[measure].sum()) if measure else float(len(rows))

        sa, sb = part(a), part(b)
        what = c.label(measure) if measure else c.noun
        if re.search(r"how many times", t):
            if sb == 0:
                raise Refuse(f"{b} is zero, so I cannot divide by it.")
            return answer(c, "ratio", py(sa / sb), f"{a} is {sa / sb:.2f} times {b} by {what} ({fmt(sa)} against {fmt(sb)}).", c.chips("Times", measure, (), [str(a), str(b)]))
        if re.search(r"difference", t):
            return answer(c, "difference", py(sa - sb), f"The difference in {what} between {a} and {b} is {sa - sb:+,.2f} ({fmt(sa)} against {fmt(sb)}).", c.chips("Difference", measure, (), [str(a), str(b)]))
        return answer(c, "compare", {str(a): sa, str(b): sb}, f"{what.capitalize()}: {a} {fmt(sa)}, {b} {fmt(sb)}.", c.chips("Compare", measure, (), [str(a), str(b)]))

    return None


# ------------------------------------------------------------
# 4. Customers (an entity that appears in many rows)
# ------------------------------------------------------------

def count_word(text):
    text = text.lower()
    return int(text) if text.isdigit() else NUMBER_WORDS.get(text)


def h_entity(c):

    t = c.t
    word = re.search(r"\b(customers?|clients?|buyers?|users?|accounts?)\b", t)

    if not word:
        return None

    entity = c.entity(word.group(1).rstrip("s"))

    interesting = re.search(
        r"repeat|returning|loyal|only once|bought once|ordered once|one[- ]time|single purchase|"
        r"more than (?:one|1|once|two|\d+) (?:order|purchase|transaction)|at least (?:one|two|\d+) (?:order|purchase)|"
        r"(?:highest|maximum|max|most|largest) number of (?:orders|purchases)|"
        r"(?:spent|paid|bought for|ordered for|generated) (?:more|less) than|"
        r"(?:ordered|bought|purchased|active|shopped) in both|"
        r"(?:bought|purchased|ordered) from (?:more than|at least|over)", t,
    )

    if not interesting:
        return None

    if entity is None:
        raise Refuse(f"I could not find a column that identifies each {word.group(1).rstrip('s')} (like a customer id).")

    data, filters, _ = c.subset()
    per = data.groupby(entity).size()

    rate_words = r"(?:percentage|percent|share|proportion|rate|%)"
    wants_rate = re.search(rate_words, t) is not None and not re.search(r"\bhow many\b", t)

    if re.search(r"only once|bought once|ordered once|one[- ]time|single purchase", t) and wants_rate:
        value = float((per == 1).mean() * 100)
        return answer(c, "one-time rate", py(value), f"{value:.1f}% of {word.group(1).rstrip('s')}s ordered only once.", c.chips("One-time rate", None, filters), unit="%")

    if re.search(r"(?:repeat|returning|loyal)", t) and wants_rate:
        value = float((per > 1).mean() * 100)
        return answer(c, "repeat rate", py(value), f"{value:.1f}% of {word.group(1).rstrip('s')}s ordered more than once ({fmt((per > 1).sum())} of {fmt(len(per))}).", c.chips("Repeat rate", None, filters), unit="%")

    if re.search(r"(?:highest|maximum|max|most|largest) number of (?:orders|purchases)", t):
        top = int(per.max())
        return answer(c, "max orders", top, f"The most orders placed by one {word.group(1).rstrip('s')} is {top}.", c.chips("Highest", None, filters, ["orders per " + word.group(1).rstrip('s')]))

    both = re.search(r"in both\s+((?:19|20)\d\d)\s+and\s+((?:19|20)\d\d)", t)
    if both:
        date = c.date_for()
        stamps = to_dates(data[date])
        one = set(data[stamps.dt.year == int(both.group(1))][entity])
        two = set(data[stamps.dt.year == int(both.group(2))][entity])
        return answer(c, "both years", len(one & two), f"{fmt(len(one & two))} {word.group(1).rstrip('s')}s ordered in both {both.group(1)} and {both.group(2)}.", c.chips("Count", None, filters, [both.group(1), both.group(2)]))

    cats = re.search(r"(?:bought|purchased|ordered) from (more than|at least|over) (\w+) (\w+)", t)
    if cats:
        limit = count_word(cats.group(2))
        dim = c.dim_from_noun(cats.group(3))
        if limit is None or dim is None:
            raise Refuse("Which column do you mean? For example 'customers who bought from more than 3 categories'.")
        spread = data.groupby(entity)[dim].nunique()
        count = int((spread >= limit).sum() if cats.group(1) == "at least" else (spread > limit).sum())
        return answer(c, "entity spread", count, f"{fmt(count)} {word.group(1).rstrip('s')}s bought from {cats.group(1)} {limit} {c.label(dim)} values.", c.chips("Count", None, filters, [f"{cats.group(1)} {limit} {c.label(dim)}"]))

    spent = re.search(r"(?:spent|paid|bought for|ordered for|generated)\s+(more|less)\s+than\s+([\d,]+(?:\.\d+)?)", t)
    if spent:
        measure = c.measure() or c.revenue
        if measure is None:
            raise Refuse("Which number should I add up per customer? Please name it, for example 'spent more than 5000 in revenue'.")
        limit = float(spent.group(2).replace(",", ""))
        totals = data.groupby(entity)[measure].sum()
        count = int((totals > limit).sum() if spent.group(1) == "more" else (totals < limit).sum())
        return answer(c, "entity total", count, f"{fmt(count)} {word.group(1).rstrip('s')}s have a total {c.label(measure)} {'above' if spent.group(1) == 'more' else 'below'} {fmt(limit)}.", c.chips("Count", measure, filters, [f"total {'above' if spent.group(1) == 'more' else 'below'} {fmt(limit)}"]))

    if re.search(r"only once|bought once|ordered once|one[- ]time|single purchase|only one (?:order|purchase)", t):
        count = int((per == 1).sum())
        return answer(c, "one-time", count, f"{fmt(count)} {word.group(1).rstrip('s')}s ordered only once.", c.chips("Count", None, filters, ["ordered once"]))

    more = re.search(r"(more than|over|at least)\s+(one|1|once|two|2|twice|\d+)\s+(?:order|purchase|transaction)", t)
    if more or re.search(r"repeat (?:customers|buyers)", t):
        limit = count_word({"once": "1", "twice": "2"}.get(more.group(2), more.group(2))) if more else 1
        at_least = bool(more and more.group(1) == "at least")
        count = int((per >= limit).sum() if at_least else (per > limit).sum())
        return answer(c, "repeat count", count, f"{fmt(count)} {word.group(1).rstrip('s')}s placed {'at least' if at_least else 'more than'} {limit} order(s).", c.chips("Count", None, filters, [f"{'at least' if at_least else 'more than'} {limit} orders"]))

    return None


# ------------------------------------------------------------
# 5. Rankings, concentration, cross-tabs
# ------------------------------------------------------------

def group_noun(c, word):
    """'categories' / 'customers' -> the column that makes the groups."""
    return c.entity(word) or c.dim_from_noun(word)


def numeric_word(text):
    text = text.lower()
    return int(text) if text.isdigit() else NUMBER_WORDS.get(text)


def h_rank(c):

    t = c.t

    # ---- second best X by M
    nth = re.search(rf"\b(second|2nd|third|3rd|fourth|4th|fifth|5th)\s+({HIGH_WORDS}|{LOW_WORDS})\b", t)
    if nth:
        dims = c.named(c.dims + c.ids)
        if len(dims) != 1:
            raise Refuse("Which column do you want to rank? For example 'the second best category by revenue'.")
        measure = c.need_measure()
        data, filters, _ = c.subset()
        sums = data.groupby(dims[0])[measure].sum().sort_values(ascending=not re.search(HIGH_WORDS, nth.group(2)))
        place = ORDINALS[nth.group(1)]
        if len(sums) < place:
            raise Refuse(f"There are only {len(sums)} groups.")
        name = sums.index[place - 1]
        return answer(c, "nth", (str(name), float(sums.iloc[place - 1])), f"The {nth.group(1)} {'best' if re.search(HIGH_WORDS, nth.group(2)) else 'lowest'} {c.label(dims[0])} by {c.label(measure)} is {name} ({fmt(sums.iloc[place - 1])}).", c.chips(nth.group(1).capitalize(), measure, filters, [f"by {c.label(dims[0])}"]))

    # ---- what rank is V by M
    if re.search(r"\brank\b", t) and re.search(r"what(?:'s| is)?(?: the)? rank|what rank|rank of|where does .* rank", t):
        mentions = c.values_in_question()
        pairs = [(col, v) for col, vals in mentions.items() for v in vals]
        if len(pairs) != 1:
            raise Refuse("Which value do you want the rank of? For example 'what rank is Electronics by revenue'.")
        col, value = pairs[0]
        measure = c.need_measure()
        sums = c.df.groupby(c.df[col].astype(str).str.strip())[measure].sum()
        mine = float(sums[str(value).strip()])
        rank = int((sums > mine).sum() + 1)
        return answer(c, "rank", rank, f"{value} ranks number {rank} of {len(sums)} {c.label(col)} values by {c.label(measure)} ({fmt(mine)}).", c.chips("Rank", measure, (), [str(value)]))

    # ---- what share comes from the top N
    top_share = re.search(r"\bshare of (.+?) (?:comes from|from|by|made up by|contributed by|generated by)\s+the top\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)(\s+percent|\s*%)?\s+(?:of\s+)?(\w+)", t)
    if top_share:
        n = numeric_word(top_share.group(2))
        percent = bool(top_share.group(3))
        column = group_noun(c, top_share.group(4))
        measure = c.need_measure()
        if column is None or n is None:
            raise Refuse("Which groups do you mean? For example 'share of revenue from the top 3 categories'.")
        data, filters, _ = c.subset()
        sums = data.groupby(column)[measure].sum().sort_values(ascending=False)
        take = max(1, int(len(sums) * n / 100)) if percent else n
        share = float(sums.iloc[:take].sum() / sums.sum() * 100)
        where = f"{n} percent" if percent else f"{n}"
        return answer(c, "top share", py(share), f"The top {where} {c.label(column)} values ({take} of {len(sums)}) make up {share:.1f}% of {c.label(measure)}.", c.chips("Share of top", measure, filters, [f"top {where} {c.label(column)}"]), unit="%")

    # ---- top N by number of rows
    top_count = re.search(r"\btop\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(\w+)\s+by\s+(?:the\s+)?(?:number|count)\s+of\b", t)
    if top_count:
        n = numeric_word(top_count.group(1))
        column = group_noun(c, top_count.group(2))
        if column is None:
            raise Refuse(f"I could not find a column for '{top_count.group(2)}'.")
        data, filters, _ = c.subset()
        counts = data.groupby(column).size().sort_values(ascending=False).iloc[:n]
        pairs = [(str(k), int(v)) for k, v in counts.items()]
        return answer(c, "top by count", pairs, f"Top {len(pairs)} {c.label(column)} values by number of {c.noun}: " + ", ".join(f"{k} ({fmt(v)})" for k, v in pairs) + ".", c.chips("Top", None, filters, [f"{len(pairs)} by number of {c.noun}"]))

    # ---- Pareto: how many X make up 80 percent of Y
    pareto = re.search(r"how many (\w+) (?:make up|account for|generate|contribute|are needed for|produce)\s+(\d+)\s*(?:percent|%)\s+of\s+", t)
    if pareto:
        column = group_noun(c, pareto.group(1))
        measure = c.need_measure()
        if column is None:
            raise Refuse(f"I could not find a column for '{pareto.group(1)}'.")
        data, filters, _ = c.subset()
        sums = data.groupby(column)[measure].sum().sort_values(ascending=False)
        share = sums.cumsum() / sums.sum()
        needed = int((share < int(pareto.group(2)) / 100).sum() + 1)
        return answer(c, "pareto", needed, f"{fmt(needed)} {c.label(column)} values make up {pareto.group(2)}% of {c.label(measure)} (out of {fmt(len(sums))}).", c.chips("Pareto", measure, filters, [f"{pareto.group(2)}%"]))

    return None


ENTITY_NOUNS = r"(customers?|clients?|buyers?|users?|accounts?|employees?|patients?|students?|products?|vendors?|suppliers?|shipments?)"


def h_entity_rank(c):
    """'Who is our best customer?', 'top 5 customers by revenue' (the ID column, not a segment)."""

    t = c.t
    noun = re.search(rf"\b{ENTITY_NOUNS}\b", t)
    extreme = re.search(rf"\b({HIGH_WORDS}|{LOW_WORDS})\b", t)

    if not noun or not extreme or re.search(r"\bhow many\b|\bnumber of (?:customers|clients)\b", t):
        return None

    entity = c.entity(noun.group(1).rstrip("s"))

    # a segment, channel or region in the question is the thing to rank: the normal path
    if entity is None or c.named(c.dims):
        return None

    # "highest customer age": the noun is part of a COLUMN name
    noun_forms = word_forms(noun.group(1).rstrip("s"))
    if any(c.tokens(m) & noun_forms for m in c.named(c.measures)):
        return None

    count = re.search(r"\bby\s+(?:the\s+)?(?:number|count)\s+of\b", t)
    top_n = re.search(r"\b(?:top|bottom|best|worst|highest|lowest)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b|\b(\d+)\s+(?:best|worst|highest|lowest|top)\b", t)

    measure = None if count else c.measure() or c.revenue

    if measure is None and not count:
        raise Refuse("Which number should I rank by? For example 'top 5 customers by revenue'.")

    data, filters, _ = c.subset()
    series = data.groupby(entity).size() if count else data.groupby(entity)[measure].sum()
    low = bool(re.search(LOW_WORDS, extreme.group(1)))
    ordered = series.sort_values(ascending=low)
    what = f"number of {c.noun}" if count else c.label(measure)

    if top_n:
        n = numeric_word(top_n.group(1) or top_n.group(2))
        pairs = [(str(k), float(v)) for k, v in ordered.iloc[:n].items()]
        return answer(c, "entity top", pairs, f"{'Bottom' if low else 'Top'} {len(pairs)} {c.label(entity)} values by {what}: " + ", ".join(f"{k} ({fmt(v)})" for k, v in pairs) + ".", c.chips("Bottom" if low else "Top", measure, filters, [f"{len(pairs)} {c.label(entity)}"]))

    name = ordered.index[0]
    return answer(c, "entity best", (str(name), float(ordered.iloc[0])), f"The {'lowest' if low else 'top'} {c.label(entity)} by {what} is {name} ({fmt(ordered.iloc[0])}).", c.chips("Lowest" if low else "Top", measure, filters, [c.label(entity)]))


def h_share_of(c):
    """'What share of revenue comes from Fashion?' (a value of a column)."""

    t = c.t
    found = re.search(r"\b(?:share|percentage|percent|proportion)\s+of\s+(.+?)\s+(?:comes?\s+from|is\s+from|are\s+from|from|made\s+by)\s+(.+?)\s*\??$", t)

    if not found or re.search(r"\btop\b|\bby\s+(?:each|every)\b", t):
        return None

    measure = None
    named = c.named(c.measures)
    if len(named) == 1:
        measure = named[0]
    elif not named and REVENUE_WORDS.search(found.group(1)) and c.revenue:
        measure = c.revenue

    mentions = [(col, v) for col, vals in c.values_in_question().items() for v in vals]

    if measure is None or len(mentions) != 1:
        return None

    column, value = mentions[0]
    data = c.df
    part = data[data[column].astype(str).str.strip().str.lower() == str(value).lower()][measure].sum()
    whole = data[measure].sum()

    if whole == 0:
        raise Refuse(f"The total {c.label(measure)} is zero, so a share is not defined.")

    share = float(part / whole * 100)
    return answer(c, "share", py(share), f"{value} is {share:.1f}% of {c.label(measure)} ({fmt(part)} of {fmt(whole)}).", c.chips("Share", measure, [{"column": column, "value": value}]), unit="%")


def h_cross(c):

    t = c.t

    # ---- top N X by M for V
    filtered = re.search(r"\btop\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(\w+)\s+by\s+(.+?)\s+(?:for|in|within|among|of)\s+(.+?)\s*\??$", t)
    if filtered:
        n = numeric_word(filtered.group(1))
        column = group_noun(c, filtered.group(2))
        measure = c.need_measure()
        mentions = c.values_in_question()
        pairs = [(col, v) for col, vals in mentions.items() for v in vals if col != column]
        if column is None or len(pairs) != 1:
            raise Refuse("Please name one value to look inside, for example 'top 3 categories by revenue for North'.")
        col, value = pairs[0]
        rows = c.df[c.df[col].astype(str).str.strip().str.lower() == str(value).lower()]
        sums = rows.groupby(column)[measure].sum().sort_values(ascending=False).iloc[:n]
        result = [(str(k), float(v)) for k, v in sums.items()]
        return answer(c, "filtered top", result, f"Top {len(result)} {c.label(column)} values by {c.label(measure)} for {value}: " + ", ".join(f"{k} ({fmt(v)})" for k, v in result) + ".", c.chips("Top", measure, [{"column": col, "value": value}], [f"{len(result)} {c.label(column)}"]))

    # ---- which X has the highest M in V
    within = re.search(rf"\bwhich\s+(\w+(?: \w+)?)\s+(?:has|have|had|is|are|generates?|makes?|brings?)\s+(?:the\s+)?({HIGH_WORDS}|{LOW_WORDS})\b.*\b(?:in|for|within|among)\s+(.+?)\s*\??$", t)
    if within:
        dims = [d for d in c.named(c.dims + c.ids)]
        mentions = c.values_in_question()
        pairs = [(col, v) for col, vals in mentions.items() for v in vals if col not in dims]
        if len(dims) == 1 and len(pairs) == 1 and c.named(c.measures):
            measure = c.need_measure()
            col, value = pairs[0]
            rows = c.df[c.df[col].astype(str).str.strip().str.lower() == str(value).lower()]
            sums = rows.groupby(dims[0])[measure].sum()
            high = bool(re.search(HIGH_WORDS, within.group(2)))
            name = sums.idxmax() if high else sums.idxmin()
            return answer(c, "filtered best", (str(name), float(sums[name])), f"Within {value}, {name} has the {'highest' if high else 'lowest'} {c.label(measure)} ({fmt(sums[name])}).", c.chips("Top" if high else "Lowest", measure, [{"column": col, "value": value}], [f"by {c.label(dims[0])}"]))

    # ---- show M by A and B
    two = re.search(r"\bby\s+(.+?)\s+and\s+(.+?)\s*\??$", t)
    if two:
        dims = c.named(c.dims)
        if len(dims) == 2 and re.search(r"\bby\b", t):
            measure = c.measure()
            data, filters, _ = c.subset(use_values=False)
            if measure is None:
                table = data.groupby(dims).size()
                what = f"number of {c.noun}"
            else:
                table = data.groupby(dims)[measure].sum()
                what = c.label(measure)
            result = {f"{a} | {b}": float(v) for (a, b), v in table.items()}
            return answer(c, "cross-tab", result, f"{what.capitalize()} by {c.label(dims[0])} and {c.label(dims[1])}: {len(result)} combinations.", c.chips("Table", measure, (), [c.label(dims[0]), c.label(dims[1])]))

    return None


# ------------------------------------------------------------
# 6. Calendar patterns
# ------------------------------------------------------------

def h_calendar(c):

    t = c.t

    weekday = re.search(r"\b(day of the week|days of the week|weekday|which day)\b", t) and re.search(rf"\b(?:{HIGH_WORDS}|{LOW_WORDS})\b", t)
    month_of_year = re.search(r"\bmonth of the year\b|\bacross all years\b|\bwhich month\b.*\bacross\b", t)
    daily = re.search(r"\b(average daily|daily average|per day|a day|each day)\b", t)
    weekend = re.search(r"\bweekends?\b", t)
    per_month = re.search(r"\baverage number of\b.*\bper month\b", t)

    if not (weekday or month_of_year or daily or weekend or per_month):
        return None

    measure = c.measure()
    date = c.date_for(measure)
    data, filters, _ = c.subset()
    stamps = to_dates(data[date])
    low = bool(re.search(rf"\b{LOW_WORDS}\b", t)) and not re.search(rf"\b{HIGH_WORDS}\b", t)

    def numbers():
        return data[measure] if measure else pd.Series(1, index=data.index)

    what = c.label(measure) if measure else c.noun

    if weekday or month_of_year:
        key = stamps.dt.day_name() if weekday else stamps.dt.month
        sums = numbers().groupby(key).sum()
        pick = sums.idxmin() if low else sums.idxmax()
        name = pick if weekday else MONTH_NAMES[int(pick) - 1].capitalize()
        return answer(c, "calendar", (str(name), float(sums[pick])), f"{name} has the {'lowest' if low else 'highest'} {what} across the data ({fmt(sums[pick])}).", c.chips("Weekday" if weekday else "Month of the year", measure, filters))

    if weekend:
        mask = stamps.dt.dayofweek >= 5
        value = float(numbers()[mask].sum())
        return answer(c, "weekends", py(value), f"On weekends there {'are' if not measure else 'is a total of'} {fmt(value)} {what}.", c.chips("Weekends", measure, filters))

    if per_month:
        months = stamps.dt.to_period("M").nunique()
        value = len(data) / months
        return answer(c, "per month", py(value), f"There are {fmt(value)} {c.noun} per month on average ({fmt(len(data))} over {months} months).", c.chips("Per month", None, filters))

    days = stamps.dt.normalize().nunique()
    value = float(numbers().sum() / days)
    return answer(c, "per day", py(value), f"The average daily {what} is {fmt(value)} ({fmt(numbers().sum())} over {fmt(days)} days with data).", c.chips("Per day", measure, filters))


# ------------------------------------------------------------
# 7. A yes/no EVENT said with a verb ("employees who left the company")
# ------------------------------------------------------------

def positive_value(c, column):
    """The 'yes' of a yes/no column: Yes, True, Y or 1."""

    by_lower = {str(v).strip().lower(): str(v).strip() for v in c.dim_values.get(column, [])}

    for word in ("yes", "true", "y", "1"):
        if word in by_lower:
            return by_lower[word]

    return "Yes"


def flag_columns(c):
    return [col for col, values in c.dim_values.items()
            if values and {str(v).strip().lower() for v in values} <= YES_NO]


def h_events(c):

    t = c.t
    text = t
    conditions, label_bits = [], []                     # (mask function, chip text)
    used_stems = set()
    flags = flag_columns(c)

    # "left the company", "churned"
    for pattern, stems in EVENT_VERBS:
        found = re.search(pattern, text)
        if not found:
            continue
        column = next((f for f in flags if any(s in readable_label(f).replace(" ", "") for s in stems)), None)
        if column is None:
            return None
        conditions.append((column, positive_value(c, column)))
        label_bits.append(f"{c.label(column)} = {positive_value(c, column)}")
        text = text[:found.start()] + " " + text[found.end():]

    # "made a loss", "profitable"
    profit = c.by_words(("profit",))
    loss = re.search(LOSS_PATTERN, text)
    gain = re.search(PROFIT_PATTERN, text)
    numeric_rule = None

    if (loss or gain) and profit is not None:
        found = loss or gain
        numeric_rule = (profit, "<" if loss else ">")
        label_bits.append(f"{c.label(profit)} {'below' if loss else 'above'} 0")
        text = text[:found.start()] + " " + text[found.end():]

    # "earn more than 100000 per month"
    earn = re.search(r"\b(?:earn|earns|earning|make|makes|paid)\s+(more than|over|above|less than|under|below|at least|at most)\s+([\d,]+(?:\.\d+)?)(?:\s*(?:per|a)\s+month)?", text)
    pay_measure = c.by_words(("salary", "pay", "wage", "compensation")) if earn else None
    earn_rule = None

    if earn and pay_measure is not None:
        op = {"more than": ">", "over": ">", "above": ">", "less than": "<", "under": "<", "below": "<", "at least": ">=", "at most": "<="}[earn.group(1)]
        earn_rule = (pay_measure, op, float(earn.group(2).replace(",", "")))
        label_bits.append(f"{c.label(pay_measure)} {earn.group(1)} {earn.group(2)}")
        text = text[:earn.start()] + " " + text[earn.end():]

    # "total payroll", "average payroll"
    payroll = re.search(r"\b(total|average|mean|highest|lowest|maximum|minimum)\s+(payroll|compensation)\b", text)

    if payroll:
        text = text[:payroll.start()] + " " + payroll.group(1) + " " + text[payroll.end():]

    # a yes/no column named by words of the question ("work remotely" ~ Remote Work)
    if not conditions and not (numeric_rule or earn_rule or payroll) and not re.search(r"\b(?:different|distinct|unique|which|who|highest|lowest|best|worst|top|bottom)\b", t):
        # a word that EXACTLY equals a value of some column ("Active") is that value,
        # not a flag ("remotely" only resembles the value "Remote": the flag wins)
        value_words = {
            token for values in c.dim_values.values() for v in values
            for token in re.findall(r"[a-z]{5,}", str(v).lower())
        }
        words = {w[:5] for w in re.findall(r"[a-z]{5,}", text) if w not in value_words}
        generic = {"work", "type", "statu", "flag"}
        matches = [f for f in flags if {tok[:5] for tok in c.tokens(f) if len(tok) >= 5 and tok[:5] not in generic} & words]
        if len(matches) == 1 and re.search(r"\b(?:how many|percentage|percent|share|proportion)\b", t):
            conditions.append((matches[0], positive_value(c, matches[0])))
            label_bits.append(f"{c.label(matches[0])} = {positive_value(c, matches[0])}")
            used_stems = {tok[:5] for tok in c.tokens(matches[0]) if len(tok) >= 5} & words

    if not (conditions or numeric_rule or earn_rule or payroll):
        return None

    # ---- the words that are left must all be understood
    check_plan = {"intent": "count", "filters": []}
    problem = unmapped_words_problem(
        check_plan, text, c.engine.profile, list(c.df.columns), c.dim_values,
    )

    if problem:
        raise Refuse(problem)

    data, filters, _ = c.subset(skip=used_stems)

    def apply(frame):
        for column, value in conditions:
            frame = frame[frame[column].astype(str).str.strip().str.lower() == value.lower()]
        if numeric_rule:
            frame = frame[frame[numeric_rule[0]] < 0] if numeric_rule[1] == "<" else frame[frame[numeric_rule[0]] > 0]
        if earn_rule:
            column, op, limit = earn_rule
            frame = frame[{">": frame[column] > limit, "<": frame[column] < limit, ">=": frame[column] >= limit, "<=": frame[column] <= limit}[op]]
        return frame

    chips = c.chips("Count", None, filters, label_bits)
    subset = apply(data)

    # ---- total / average of a number column for the subset
    agg = re.search(r"\b(total|sum|average|mean|highest|lowest|maximum|minimum)\b", t)
    measure = None if payroll is None else c.by_words(("salary", "pay", "wage", "compensation"))
    named = c.named(c.measures)
    measure = measure or (named[0] if len(named) == 1 else None)

    if measure is None and agg and not re.search(r"^\s*(?:how many|what (?:percentage|percent|share))", t):
        measure = c.loose_measure(re.sub(r"\b(?:left|leave|churned)\b", " ", text))

    if measure and agg and not re.search(r"^\s*(?:how many|what (?:percentage|percent|share))", t):
        if subset.empty:
            raise Refuse("No rows match that selection.")
        how = {"total": "sum", "sum": "sum", "average": "mean", "mean": "mean", "highest": "max", "maximum": "max", "lowest": "min", "minimum": "min"}[agg.group(1)]
        value = float(getattr(subset[measure], how)())
        return answer(c, "event aggregate", py(value), f"{agg.group(1).capitalize()} {c.label(measure)}: {fmt(value)} (for {fmt(len(subset))} {c.noun}).", c.chips(agg.group(1).capitalize(), measure, filters, label_bits))

    # ---- percentage, optionally in each group
    if re.search(r"\b(?:percentage|percent|share|proportion|%)\b", t):
        by = re.search(r"\b(?:in|by|for|per) each\s+(\w+(?: \w+)?)|\bby\s+(\w+(?: \w+)?)\s*\??$", t)
        used = {column for column, _ in conditions}
        dims = [d for d in c.named(c.dims) if d not in used]
        if by and dims:
            column = dims[0]
            flagged = apply(data).groupby(column).size()
            whole = data.groupby(column).size()
            rates = (flagged.reindex(whole.index).fillna(0) / whole * 100)
            result = {str(k): float(v) for k, v in rates.items()}
            return answer(c, "event rate by group", result, f"Share of {c.noun} ({', '.join(label_bits)}) by {c.label(column)}: " + ", ".join(f"{k} {v:.1f}%" for k, v in list(result.items())[:8]) + ".", c.chips("Share", None, filters, label_bits + [f"by {c.label(column)}"]), unit="%")
        value = len(subset) / len(data) * 100
        return answer(c, "event share", py(value), f"{value:.1f}% of {c.noun} ({fmt(len(subset))} of {fmt(len(data))}).", c.chips("Share", None, filters, label_bits), unit="%")

    if re.search(r"\bhow many\b|\bnumber of\b|\bcount\b", t):
        return answer(c, "event count", len(subset), f"There are {fmt(len(subset))} {c.noun} ({', '.join(label_bits)}).", chips)

    return None


# ------------------------------------------------------------
# The entry point
# ------------------------------------------------------------

HANDLERS = (
    h_stats, h_ratio, h_growth, h_entity, h_rank, h_entity_rank, h_share_of,
    h_cross, h_calendar, h_events,
)


def try_answer(engine, question):
    """An answer dict, or None when the question is not an advanced one."""

    try:
        ctx = Ctx(engine, question)

        for handler in HANDLERS:
            result = handler(ctx)
            if result is not None:
                return result

        return None

    except Refuse as problem:
        return {"status": "error", "message": str(problem)}

    except Exception:
        # a bug here must never produce a wrong number: fall back to the normal path
        import os
        if os.environ.get("ADVANCED_DEBUG"):
            raise
        return None
