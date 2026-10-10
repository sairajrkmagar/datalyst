"""
Calculations for group tables, percentages and month questions.
Everything here is plain pandas: the AI never calculates.
"""


from filters import apply_filters, to_dates


def group_values(data, group, agg, value=None):
    """{group: number} sorted from the largest to the smallest."""

    if agg == "count":
        series = data.groupby(group).size()
    elif agg == "mean":
        series = data.groupby(group)[value].mean()
    else:
        series = data.groupby(group)[value].sum()

    series = series.sort_values(ascending=False)

    return {str(key): number for key, number in series.items()}


def share_values(df, plan):
    """
    Percent that the filtered rows make of the whole.

    The date filter applies to BOTH sides ("return rate in 2024").
    Value filters and number conditions describe the part only.
    Returns (percent or dict of percents, part, whole).
    """

    agg = plan.get("agg") or "count"
    value = plan.get("value_column")
    date_filter = plan.get("date_filter")

    # "profit as a percent of revenue": both sums use the SAME rows
    denominator = plan.get("ratio_denominator")

    if denominator:

        rows = apply_filters(
            df, plan.get("filters"), date_filter, plan.get("conditions")
        )

        top = float(rows[value].sum())
        bottom = float(rows[denominator].sum())

        if not bottom:
            return None, top, bottom

        return top / bottom * 100, top, bottom

    # "the churn rate for the Free plan": the Free plan is the POPULATION
    # (the whole) and "churned" is the part. A Yes/No flag is the part, the
    # other filters describe who we are looking at.
    yes_words = {"yes", "true", "y", "1"}
    all_words = yes_words | {"no", "false", "n", "0"}

    def is_flag(item):
        values = {str(v).strip().lower() for v in df[item["column"]].dropna().unique()}
        return bool(values) and values <= all_words and str(item["value"]).strip().lower() in yes_words

    rate_flag = plan.get("rate_flag")

    def is_rate_event(item):
        return bool(rate_flag) and item["column"] == rate_flag["column"] and str(item["value"]) == str(rate_flag["value"])

    flags = [f for f in plan.get("filters") or [] if is_flag(f) or is_rate_event(f)]
    population = [f for f in plan.get("filters") or [] if f not in flags]

    whole_rows = apply_filters(df, population if flags else [], date_filter)

    part_rows = apply_filters(
        df,
        plan.get("filters"),
        date_filter,
        plan.get("conditions")
    )

    def measure(rows):
        return len(rows) if agg == "count" else float(rows[value].sum())

    group = plan.get("share_group")

    if group:

        percents = {}

        for key, whole_group in whole_rows.groupby(group):

            whole = measure(whole_group)

            part_group = part_rows[part_rows[group] == key]

            if whole:
                percents[str(key)] = measure(part_group) / whole * 100

        return percents, measure(part_rows), measure(whole_rows)

    whole = measure(whole_rows)
    part = measure(part_rows)

    if not whole:
        return None, part, whole

    return part / whole * 100, part, whole


def partial_months(df, date_column):
    """Months only partly covered by the data (first and last month)."""

    stamps = to_dates(df[date_column]).dropna()

    if stamps.empty:
        return set()

    first, last = stamps.min(), stamps.max()

    partial = set()

    if first.day > 1:
        partial.add(first.strftime("%Y-%m"))

    if last.day < last.days_in_month:
        partial.add(last.strftime("%Y-%m"))

    return partial


def month_pick(monthly, pick, partial):
    """
    Best / weakest / average month. Partly covered months are left out,
    because they would unfairly look weak.
    Returns (result, months_used, months_left_out).
    """

    full = {m: v for m, v in monthly.items() if m not in partial}

    left_out = sorted(m for m in monthly if m in partial)

    if not full:
        full, left_out = dict(monthly), []

    if pick == "mean":
        return sum(full.values()) / len(full), len(full), left_out

    chooser = min if pick == "min" else max

    month = chooser(full, key=lambda key: full[key])

    return (month, full[month]), len(full), left_out