"""
Filters that are applied by CODE (never by the AI):
  - value filters   (category = Fashion)
  - date filters    (September 2024, 2024, Q1 2024)
Every question type can then run on the filtered rows.
"""

import warnings

import pandas as pd


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]

RANKING_INTENTS = ["top", "bottom", "trend"]


def plural_label(text):
    """'category' -> 'categories', 'payment method' -> 'payment methods'."""

    text = str(text)

    if text.endswith("s"):
        return text

    if text.endswith("y") and text[-2:-1] not in "aeiou":
        return text[:-1] + "ies"

    return text + "s"


def guess_day_first(series):
    """
    14-01-2023 can only be day-first. Look for a value that proves it.
    Returns True (day first), False (month first) or None (cannot tell).
    """

    sample = series.dropna().astype(str).head(3000)

    parts = sample.str.extract(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}")

    if parts.isna().all().all():
        return None

    first_big = (pd.to_numeric(parts[0], errors="coerce") > 12).sum()
    second_big = (pd.to_numeric(parts[1], errors="coerce") > 12).sum()

    if first_big > 0 and second_big == 0:
        return True

    if second_big > 0 and first_big == 0:
        return False

    return None


def to_dates(series):
    """Turn a column into dates (fast for ISO dates, safe for mixed)."""

    day_first = guess_day_first(series)

    with warnings.catch_warnings():

        warnings.simplefilter("ignore")

        if day_first is None:
            dates = pd.to_datetime(series, errors="coerce")
        else:
            dates = pd.to_datetime(series, errors="coerce", dayfirst=day_first)

        if len(series) > 0 and dates.notna().mean() < 0.9:

            if day_first is None:
                dates = pd.to_datetime(series, errors="coerce", format="mixed")
            else:
                dates = pd.to_datetime(
                    series, errors="coerce", format="mixed", dayfirst=day_first
                )

    return dates


OPERATOR_WORDS = {">": "above", ">=": "at least", "<": "below", "<=": "at most"}


def apply_filters(df, filters, date_filter, conditions=None):

    data = df

    for item in filters or []:

        column = item["column"]
        value = str(item["value"]).lower()

        data = data[data[column].astype(str).str.lower() == value]

    if date_filter:

        stamps = to_dates(data[date_filter["column"]])

        keep = pd.Series(True, index=data.index)

        if date_filter.get("year"):
            keep &= stamps.dt.year == date_filter["year"]

        if date_filter.get("month"):
            keep &= stamps.dt.month == date_filter["month"]

        if date_filter.get("quarter"):
            keep &= stamps.dt.quarter == date_filter["quarter"]

        data = data[keep]

    for item in conditions or []:

        numbers = pd.to_numeric(data[item["column"]], errors="coerce")
        limit = item["value"]
        operator = item["op"]

        if operator == ">":
            keep = numbers > limit
        elif operator == ">=":
            keep = numbers >= limit
        elif operator == "<":
            keep = numbers < limit
        else:
            keep = numbers <= limit

        data = data[keep]

    return data


def effective_filters(plan):
    """The filters of a plan (also understands older, simpler plans)."""

    if plan.get("filters") is not None:
        return plan["filters"]

    value = plan.get("filter_value")
    column = plan.get("group_column")

    if (
        value is not None
        and column is not None
        and plan.get("intent") not in RANKING_INTENTS
    ):
        return [{"column": column, "value": value}]

    return []


def subset_for(plan, df):
    return apply_filters(
        df,
        effective_filters(plan),
        plan.get("date_filter"),
        plan.get("conditions")
    )


def scope_text(plan):
    """'for Fashion in September 2024' (empty if there is no filter)."""

    values = []
    labelled = []

    for item in effective_filters(plan):

        if item.get("label"):
            labelled.append(item["label"])
        else:
            values.append(str(item["value"]))

    pieces = []

    if values:
        pieces.append("for " + " and ".join(values))

    pieces.extend(labelled)

    for item in plan.get("conditions") or []:
        pieces.append(item["label"])

    date_filter = plan.get("date_filter")

    if date_filter and date_filter.get("label"):

        text = "in " + date_filter["label"]

        # a file with several date columns: say which one counted
        if date_filter.get("ambiguous") and date_filter.get("column"):
            text += f" (by {str(date_filter['column']).replace('_', ' ')})"

        pieces.append(text)

    return " ".join(pieces)
