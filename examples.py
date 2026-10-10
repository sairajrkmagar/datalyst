"""
WHAT CAN I ASK?

Example questions for the Ask AI page, written with the names in THIS file, grouped
by what they do. Every example here is checked by a test on many datasets: it
must give an answer, never a refusal.

    build(engine) -> [{"title": "Statistics", "items": [{"q": "What is the median revenue?", "plan": None}]}]

"plan" is only used by the tests (the plan a typical AI gives); the app ignores it.
"""

import re
import warnings

import pandas as pd

from dashboard import uses_total
from plan_repair import readable_label


def label(engine, column):
    alias = {m: o for o, m in engine.profile.get("main_columns", {}).items()}
    return re.sub(r" main$", "", readable_label(alias.get(column, column)))


def plural_word(engine, column):
    """'category' -> 'categories', 'job level' -> 'levels' (one word, as people write it)."""

    word = label(engine, column).split()[-1]

    if word.endswith("y") and word[-2:-1] not in "aeiou":
        return word[:-1] + "ies"

    return word + ("es" if word.endswith(("s", "x", "ch", "sh")) else "s")


def plan(intent=None, column=None, group=None, value=None, operation="sum", filter_value=None):
    return {
        "intent": intent, "column": column, "group_column": group,
        "value_column": value, "filter_value": filter_value, "operation": operation,
    }


def build(engine):

    df = engine.df
    under = engine.dataset_understanding
    profile = engine.profile

    measures = list(profile.get("measures", under["measures"]))
    ids = list(profile.get("identifier_columns", []))
    dates = list(under["date_columns"])
    noun = profile.get("count_noun") or "records"

    dims = [
        c for c, values in under["dimension_values"].items()
        if c not in ids and 2 <= len(values) <= 30
        and {str(v).strip().lower() for v in values} - {"yes", "no", "true", "false", "y", "n", "0", "1"}
    ]

    main = profile.get("revenue_column") if profile.get("revenue_column") in measures else (measures[0] if measures else None)
    groups = []

    def group(title, items):
        if items:
            groups.append({"title": title, "items": items[:4]})

    # ---------------- totals and counts
    items = [{"q": f"How many {noun} are there?", "plan": plan("count", operation="row_count")}]

    if main:
        name = label(engine, main)
        total = uses_total(main)
        items.append({
            "q": f"What is the {'total' if total else 'average'} {name}?",
            "plan": plan("total" if total else "average", main, None, main, "sum" if total else "average"),
        })
        if total:
            items.append({"q": f"What is the average {name}?", "plan": plan("average", main, None, main, "average")})

    group("Totals and counts", items)

    # ---------------- groups and rankings
    items = []

    if main and dims:
        name, dim = label(engine, main), dims[0]
        dim_name = label(engine, dim)
        total = uses_total(main)
        word = "total" if total else "average"
        op = "sum" if total else "average"
        items.append({"q": f"Show {word} {name} by {dim_name}", "plan": plan("breakdown", main, dim, main, op)})
        items.append({"q": f"Which {dim_name} has the highest {name}?", "plan": plan("top", main, dim, main, "group_sum" if total else "group_average")})
        items.append({"q": f"Which {dim_name} has the lowest {name}?", "plan": plan("bottom", main, dim, main, "group_sum" if total else "group_average")})

        if len(dims) > 1:
            other = label(engine, dims[1])
            items.append({"q": f"Show {name} by {dim_name} and {other}", "plan": None})

    group("Groups and rankings", items)

    # ---------------- shares
    items = []

    if main and dims and uses_total(main):
        values = df[dims[0]].astype(str).str.strip().value_counts()
        if len(values):
            items.append({"q": f"What share of {label(engine, main)} comes from {values.index[0]}?", "plan": None})

        items.append({"q": f"What are the top 3 {plural_word(engine, dims[0])} by number of {noun}?", "plan": None})
        items.append({"q": f"What share of {label(engine, main)} comes from the top 3 {plural_word(engine, dims[0])}?", "plan": None})

    group("Shares and concentration", items)

    # ---------------- time
    items = []

    if dates and main:

        name = label(engine, main)
        stamps = engine.df[dates[0]]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            years = sorted({int(y) for y in pd.to_datetime(stamps, errors="coerce").dt.year.dropna()})

        items.append({"q": f"Show me monthly {name}", "plan": plan("trend", main, dates[0], main, "time_series")})

        if len(years) >= 2 and uses_total(main):
            items.append({"q": f"Which year had the highest {name}?", "plan": None})
            items.append({"q": f"What is the year on year growth in {name} from {years[0]} to {years[1]}?", "plan": None})

        if uses_total(main):
            items.append({"q": f"Which day of the week has the highest {name}?", "plan": None})

    group("Time and growth", items)

    # ---------------- statistics
    items = []

    if main:
        name = label(engine, main)
        items.append({"q": f"What is the median {name}?", "plan": None})
        items.append({"q": f"How many {noun} are above the average {name}?", "plan": None})
        items.append({"q": f"Are there any outliers in {name}?", "plan": None})

        if len(measures) > 1:
            other = next(m for m in measures if m != main)
            items.append({"q": f"What is the correlation between {name} and {label(engine, other)}?", "plan": None})

    group("Statistics", items)

    # ---------------- business ratios (only when the columns exist)
    items = []
    tokens = {m: set(re.findall(r"[a-z0-9]+", label(engine, m).lower())) for m in measures}
    has = lambda word: any(word in t for t in tokens.values())

    if has("profit") and (profile.get("revenue_column") or has("revenue") or has("sales")):
        items.append({"q": "What is the overall profit margin?", "plan": None})

    if has("revenue") and has("spend"):
        items.append({"q": "What is the return on ad spend (ROAS)?", "plan": None})

    if has("clicks") and has("impressions"):
        items.append({"q": "What is the click through rate (CTR)?", "plan": None})

    group("Business ratios", items)

    # ---------------- customers (an ID that appears many times)
    items = []

    for column in ids:
        if 1 < df[column].nunique() < 0.9 * len(df):
            word = sorted(tokens_of(engine, column))[0] if tokens_of(engine, column) else "customer"
            if word in ("customer", "client", "user", "buyer", "account"):
                items.append({"q": f"How many {word}s placed more than one order?", "plan": None})
                items.append({"q": f"What is the repeat {word} rate?", "plan": None})
                if main and uses_total(main):
                    items.append({"q": f"Who is our best {word} by {label(engine, main)}?", "plan": None})
            break

    group("Customers", items)

    return groups


def tokens_of(engine, column):
    return set(re.findall(r"[a-z0-9]+", label(engine, column).lower())) & {"customer", "client", "user", "buyer", "account"}