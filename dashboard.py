"""
Everything the Dashboard and Insights pages show.
Plain pandas: no AI, no guessing. Every number is calculated here.
"""

from safe_numbers import is_whole
import re

import pandas as pd

from filters import to_dates
from metrics import group_values, partial_months
from plan_repair import pick_date_column

# Measures where a TOTAL makes sense (revenue, cost ...). Others
# (price, rating, age, score ...) are shown as AVERAGES.
SUM_WORDS = (
    "revenue", "sales", "amount", "total", "cost", "profit", "income",
    "quantity", "units", "spend",
)

YES_NO = {"yes", "no", "true", "false", "0", "1", "y", "n"}


def humanize(name):
    """'DepartmentType' / 'total_amount' -> 'department type' / 'total amount'."""

    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))

    return spaced.replace("_", " ").strip().lower()


def compact(value, decimals=1):
    """11846727 -> '11.8M',  34500 -> '34,500',  170.01 -> '170.01'."""

    number = float(value)

    if number != number or number in (float("inf"), float("-inf")):
        return "n/a"

    size = abs(number)

    if size >= 1e9:
        return f"{number / 1e9:.{decimals}f}B"

    if size >= 1e6:
        return f"{number / 1e6:.{decimals}f}M"

    if size >= 1e5:
        return f"{number / 1e3:.0f}K"

    if is_whole(number):
        return f"{int(number):,}"

    return f"{number:,.2f}"


def full_number(value):
    number = float(value)

    if number != number or number in (float("inf"), float("-inf")):
        return "n/a"

    if is_whole(number):
        return f"{int(number):,}"

    return f"{number:,.2f}"


def total_label(measure):
    """'total_amount' -> 'Total amount' (not 'Total total amount')."""

    text = humanize(measure)

    if text.startswith("total"):
        return text.capitalize()

    return f"Total {text}"


def ratio_words(high, low):
    """How much bigger: '39x' for big gaps, '+42%' for small ones."""

    if not low:
        return ""

    ratio = high / low

    if ratio >= 3:
        return f"{ratio:.0f}x"

    return f"{(ratio - 1) * 100:.0f}% higher"


def main_measure(engine):
    """The number column the Dashboard is about (revenue, cost ...)."""

    profile = engine.profile
    measures = engine.dataset_understanding["measures"]

    if profile.get("revenue_column"):
        return profile["revenue_column"]

    semantics = profile["column_semantics"]

    for measure in measures:
        if semantics.get(measure) == "monetary":
            return measure

    return measures[0] if measures else None


def uses_total(measure):
    return any(word in str(measure).lower() for word in SUM_WORDS)


def groupable_dims(engine):
    """Columns that make a good chart: 3 to 12 different values."""

    profile = engine.profile
    result = []

    for column, values in profile.get("dimension_values", {}).items():

        if column in profile.get("identifier_columns", []):
            continue

        lowered = {str(v).strip().lower() for v in values}

        if lowered <= YES_NO:
            continue

        if 3 <= len(values) <= 12:
            result.append(column)

    # a hand-made first-level column is the one people mean
    for original, main in profile.get("main_columns", {}).items():
        if main in result:
            result.remove(main)
            result.insert(0, main)

    return result


def yes_no_columns(engine):
    """Columns holding only Yes/No (returned, active ...)."""

    result = []

    for column, values in engine.profile.get("dimension_values", {}).items():

        lowered = {str(v).strip().lower() for v in values}

        if lowered and lowered <= YES_NO and not lowered <= {"0", "1"}:
            result.append(column)

    return result


def monthly_series(engine, measure, kind):
    """Monthly numbers without the partly covered first/last month."""

    df = engine.df
    dates = engine.dataset_understanding["date_columns"]

    if not dates:
        return None

    label = humanize(measure) if measure else "count"
    date_column = pick_date_column(label, dates)

    stamps = to_dates(df[date_column])
    keep = stamps.notna()

    if keep.sum() < 30:
        return None

    frame = pd.DataFrame({"d": stamps[keep]})
    frame["m"] = frame["d"].dt.to_period("M")

    if measure:
        frame["v"] = df.loc[keep, measure].values
        grouped = frame.groupby("m")["v"]
        series = grouped.sum() if kind == "sum" else grouped.mean()
    else:
        series = frame.groupby("m").size()

    partial = partial_months(df, date_column)

    months = {str(k): float(v) for k, v in series.items()}
    full = {k: v for k, v in months.items() if k not in partial}

    if len(full) < 3:
        return None

    return {
        "column": date_column,
        "months": full,
        "left_out": sorted(k for k in months if k in partial),
    }


def build_dashboard(engine):
    """Returns a dict with everything the Dashboard page draws."""

    df = engine.df
    profile = engine.profile
    noun = profile.get("count_noun") or "records"

    rows, columns = len(df), len(df.columns)
    cells = rows * columns
    missing = int(df.isnull().sum().sum())
    duplicates = int(df.duplicated().sum())
    completeness = 100.0 * (1 - missing / cells) if cells else 100.0

    measure = main_measure(engine)
    kind = "sum" if measure and uses_total(measure) else "mean"

    out = {
        "noun": noun,
        "rows": rows,
        "columns": columns,
        "missing": missing,
        "duplicates": duplicates,
        "completeness": completeness,
        "measure": measure,
        "kind": kind,
        "measure_label": humanize(measure) if measure else None,
        "tidied": dict(engine.conversions),
    }

    # ---------------------------------------------------- KPI cards
    kpis = []

    if measure:

        series = df[measure].dropna()
        headline = series.sum() if kind == "sum" else series.mean()

        kpis.append({
            "label": (
                total_label(measure) if kind == "sum"
                else f"Average {humanize(measure)}"
            ),
            "value": compact(headline),
            "full": full_number(headline),
            "sub": (
                f"across {rows:,} {noun}" if kind == "sum"
                else f"from {len(series):,} {noun}"
            ),
            "accent": "blue",
            "icon": "chart",
        })

    kpis.append({
        "label": noun.capitalize(),
        "value": compact(rows),
        "full": f"{rows:,}",
        "sub": f"{columns} columns of data",
        "accent": "purple",
        "icon": "layers",
    })

    if measure:

        series = df[measure].dropna()

        if kind == "sum":
            kpis.append({
                "label": f"Average {humanize(measure)}",
                "value": compact(series.mean()),
                "full": full_number(series.mean()),
                "sub": f"per {noun[:-1] if noun.endswith('s') else noun}",
                "accent": "teal",
                "icon": "scale",
            })
        else:
            kpis.append({
                "label": f"Highest {humanize(measure)}",
                "value": compact(series.max()),
                "full": full_number(series.max()),
                "sub": f"lowest {compact(series.min())}",
                "accent": "teal",
                "icon": "scale",
            })

    if missing == 0:
        quality_value = "100%"
    elif completeness > 99.95:
        quality_value = "99.9%+"
    else:
        quality_value = f"{completeness:.1f}%"

    kpis.append({
        "label": "Data quality",
        "value": quality_value,
        "full": f"{completeness:.2f}%",
        "sub": f"{missing:,} missing · {duplicates:,} duplicate rows",
        "accent": "green" if completeness >= 98 and duplicates == 0 else "orange",
        "icon": "shield",
    })

    out["kpis"] = kpis[:4]

    # ---------------------------------------------------- trend
    out["trend"] = monthly_series(engine, measure, kind)

    if out["trend"]:

        months = list(out["trend"]["months"].items())

        if len(months) >= 2 and months[-2][1]:
            out["trend"]["change"] = (
                (months[-1][1] - months[-2][1]) / abs(months[-2][1]) * 100
            )
            out["trend"]["last"] = months[-1][0]
            out["trend"]["previous"] = months[-2][0]

    # ---------------------------------------------------- groups
    dims = groupable_dims(engine)
    out["dims"] = dims

    agg = "count" if not measure else ("sum" if kind == "sum" else "mean")

    out["bar"] = None
    out["donut"] = None

    if dims:

        first = dims[0]
        values = group_values(df, first, agg, measure)
        top = dict(list(values.items())[:8])

        out["bar"] = {
            "dim": first,
            "label": dim_label(engine, first),
            "agg": agg,
            "values": top,
            "total": sum(values.values()) if agg != "mean" else None,
        }

    if len(dims) >= 2:

        second = dims[1]
        counts = group_values(df, second, "count")
        items = list(counts.items())

        shown = items[:5]
        rest = sum(v for _, v in items[5:])

        if rest:
            # never reuse a name that is already a real value
            name = "Other" if "Other" not in counts else "All the rest"
            shown.append((name, rest))

        out["donut"] = {
            "dim": second,
            "label": dim_label(engine, second),
            "values": dict(shown),
        }

    # ---------------------------------------------------- highlights
    out["highlights"] = build_highlights(out, engine)

    return out


def build_highlights(dash, engine):
    """Short sentences with numbers calculated by code."""

    lines = []
    noun = dash["noun"]
    measure_label = dash["measure_label"] or noun
    bar = dash["bar"]

    if bar and bar["values"]:

        name, value = next(iter(bar["values"].items()))
        total = bar["total"]

        if bar["agg"] == "mean":
            lines.append(
                f"{name} has the highest average {measure_label} "
                f"({compact(value)}) by {bar['label']}."
            )
        elif total:
            lines.append(
                f"{name} leads by {bar['label']} with "
                f"{value / total * 100:.1f}% of {measure_label if bar['agg'] == 'sum' else noun}."
            )

    trend = dash.get("trend")

    if trend:

        months = trend["months"]
        best = max(months, key=lambda k: months[k])

        lines.append(
            f"{best} is the strongest full month at {compact(months[best])}."
        )

        if "change" in trend:
            word = "up" if trend["change"] >= 0 else "down"
            lines.append(
                f"{trend['last']} is {word} {abs(trend['change']):.1f}% "
                f"on {trend['previous']}."
            )

    if dash["missing"] == 0 and dash["duplicates"] == 0:
        lines.append("No missing values or duplicate rows were found.")
    else:
        lines.append(
            f"{dash['missing']:,} missing values and "
            f"{dash['duplicates']:,} duplicate rows need a look."
        )

    return lines[:4]


def dim_label(engine, dim):
    """'category_main' is shown (and typed) as 'category'."""

    for original, main in engine.profile.get("main_columns", {}).items():
        if dim == main:
            return humanize(original)

    return humanize(dim)


def suggest_questions(engine, limit=6):
    """Questions that are good to try on THIS dataset."""

    df = engine.df
    noun = engine.profile.get("count_noun") or "records"
    measure = main_measure(engine)
    dims = groupable_dims(engine)
    dates = engine.dataset_understanding["date_columns"]

    questions = []

    if measure:

        label = humanize(measure)
        total = uses_total(measure)
        what = total_label(measure).lower() if total else f"average {label}"

        questions.append(f"What is the {what}?")

        if dims:

            dim = dim_label(engine, dims[0])

            adjective = "highest" if total else "highest average"
            questions.append(f"Which {dim} has the {adjective} {label}?")
            questions.append(
                f"Show {label} by {dim}" if total
                else f"Show average {label} by {dim}"
            )

            if total:
                top_value = df[dims[0]].value_counts().index[0]
                questions.append(f"What share of {label} comes from {top_value}?")

        if dates:
            questions.append(f"Show me monthly {label}")

    elif dims:
        questions.append(f"Show {noun} by {dim_label(engine, dims[0])}")

    questions.append(f"How many {noun} are there?")

    if dims and len(dims) >= 2:
        questions.append(f"Show {noun} by {dim_label(engine, dims[1])}")

    return questions[:limit]
