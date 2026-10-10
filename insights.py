"""
The Insights page: findings that code discovers in the data by itself.
Every sentence is built from numbers calculated here (no AI involved).
"""

from dashboard import (
    compact, groupable_dims, humanize, main_measure, monthly_series,
    ratio_words, uses_total, yes_no_columns,
)
from metrics import group_values


def build_insights(engine):
    """A ranked list of {tag, title, text}. Never raises."""

    df = engine.df
    noun = engine.profile.get("count_noun") or "records"
    measure = main_measure(engine)
    kind = "sum" if measure and uses_total(measure) else "mean"
    dims = groupable_dims(engine)
    agg = "count" if not measure else ("sum" if kind == "sum" else "mean")
    what = humanize(measure) if measure else noun

    found = []

    def add(tag, title, text):
        found.append({"tag": tag, "title": title, "text": text})

    # ------------------------------------------------ leaders and laggards
    for index, dim in enumerate(dims[:2]):

        try:
            values = group_values(df, dim, agg, measure)
            items = list(values.items())

            if len(items) < 2:
                continue

            (top, top_v), (second, second_v) = items[0], items[1]
            low, low_v = items[-1]
            total = sum(values.values())
            label = humanize(dim)

            if agg == "mean":
                text = f"{top} has the highest average {what} at {compact(top_v)}."

                if low_v:
                    text += (
                        f" That is {ratio_words(top_v, low_v)} than {low} "
                        f"({compact(low_v)})."
                    ).replace("x than", "x higher than")

                add("Opportunity" if index == 0 else "Fact",
                    f"Highest {label}", text)
            else:
                gap = (top_v - second_v) / abs(top_v) * 100 if top_v else None
                text = (
                    f"{top} is the largest {label}: {compact(top_v)} "
                    f"({top_v / total * 100:.1f}% of all {what})."
                )
                if gap is not None:
                    shown = f"{gap:.1f}" if gap < 10 else f"{gap:.0f}"
                    text += f" The next, {second}, is {shown}% lower."
                add("Opportunity" if index == 0 else "Fact",
                    f"Largest {label}", text)

                add("Watch" if index == 0 else "Fact",
                    f"Smallest {label}",
                    f"{low} is the smallest {label} at {compact(low_v)} "
                    f"({low_v / total * 100:.1f}% of all {what}).")

                if len(items) >= 5:
                    top3 = sum(v for _, v in items[:3]) / total * 100
                    add("Fact", f"Concentration by {label}",
                        f"The top 3 {label} values make up {top3:.1f}% of "
                        f"all {what}.")

        except Exception:
            continue

    # ------------------------------------------------ over time
    try:
        series = monthly_series(engine, measure, kind)

        if series:

            months = series["months"]
            keys = list(months)
            best = max(months, key=lambda k: months[k])
            weak = min(months, key=lambda k: months[k])

            add("Fact", "Best and weakest month",
                f"{best} was the strongest full month at {compact(months[best])}; "
                f"{weak} the weakest at {compact(months[weak])}.")

            if len(keys) >= 2 and months[keys[-2]]:

                change = (months[keys[-1]] - months[keys[-2]]) / abs(months[keys[-2]]) * 100
                average = sum(months.values()) / len(months)
                vs_avg = (months[keys[-1]] - average) / abs(average) * 100 if average else 0

                add("Opportunity" if change >= 0 else "Watch",
                    "Latest month",
                    f"{keys[-1]} is {'up' if change >= 0 else 'down'} "
                    f"{abs(change):.1f}% on {keys[-2]} and "
                    f"{abs(vs_avg):.1f}% {'above' if vs_avg >= 0 else 'below'} "
                    f"the monthly average.")

            if series["left_out"]:
                add("Fact", "Partly covered months",
                    f"{', '.join(series['left_out'])} only partly covered by "
                    f"the data, so they are left out of month comparisons.")

    except Exception:
        pass

    # ------------------------------------------------ unusual values
    try:
        if measure:

            values = df[measure].dropna()
            q1, q3 = values.quantile(0.25), values.quantile(0.75)
            spread = q3 - q1
            upper = q3 + 1.5 * spread

            if spread > 0:

                high = values[values > upper]

                if len(high):

                    median = values.median()
                    times = values.max() / median if median else None

                    text = (
                        f"{len(high):,} {noun} ({len(high) / len(values) * 100:.1f}%) "
                        f"have unusually high {what} (above {compact(upper)})."
                    )

                    if times:
                        text += (
                            f" The largest is {compact(values.max())}, "
                            f"{times:.1f}x the typical {noun[:-1] if noun.endswith('s') else noun}."
                        )

                    add("Watch", f"Unusual {what}", text)

    except Exception:
        pass

    # ------------------------------------------------ yes / no columns
    for column in yes_no_columns(engine)[:2]:

        try:
            values = df[column].astype(str).str.strip().str.lower()
            positive = values.isin({"yes", "true", "y", "1"}).sum()
            share = positive / len(df) * 100

            add("Watch" if share >= 3 else "Fact",
                f"{humanize(column).capitalize()}",
                f"{share:.1f}% of {noun} are marked {humanize(column)} "
                f"({positive:,} of {len(df):,}).")

        except Exception:
            continue

    # ------------------------------------------------ data quality
    try:
        missing = int(df.isnull().sum().sum())
        dup = int(df.duplicated().sum())
        cells = df.shape[0] * df.shape[1]

        if missing or dup:

            worst = df.isnull().sum().sort_values(ascending=False)
            text = (
                f"{missing:,} missing values ({missing / cells * 100:.2f}% of all "
                f"cells) and {dup:,} duplicate rows."
            )

            if missing and worst.iloc[0]:
                text += f" Most gaps are in '{worst.index[0]}' ({int(worst.iloc[0]):,})."

            add("Watch", "Data quality", text)

        else:
            add("Fact", "Data quality",
                "No missing values and no duplicate rows. The data is clean.")

        if engine.conversions:
            add("Fact", "Tidied automatically",
                f"{len(engine.conversions)} columns were tidied on load "
                f"(text turned into numbers, extra spaces removed or a "
                f"first-level column added).")

    except Exception:
        pass

    # the most useful first
    order = {"Opportunity": 0, "Watch": 1, "Fact": 2}
    found.sort(key=lambda item: order[item["tag"]])

    return found[:9]
