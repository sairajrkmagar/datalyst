"""
"I understood: ..." : the checked plan, written as short chips.

It is built from the FINAL plan (after the code repaired and checked it),
so it always matches the number that was calculated.
"""

from dashboard import humanize
from filters import effective_filters

CALCULATION = {
    "total": "Total",
    "average": "Average",
    "maximum": "Highest value",
    "minimum": "Lowest value",
    "unique": "Number of different values",
    "duplicate": "Duplicate rows",
    "missing": "Missing values",
    "trend": "Monthly trend",
    "breakdown": "Table by group",
    "share": "Share of the whole (%)",
}

RATIO_CALCULATION = "Ratio (%)"

PICK = {"max": "Best month", "min": "Weakest month", "mean": "Average month"}
RANK_BY = {"count": "by number of rows", "mean": "by average", "sum": "by total"}

MEASURE_INTENTS = (
    "total", "average", "maximum", "minimum", "trend", "top", "bottom",
    "breakdown", "month_pick",
)


def describe(plan, label=None):
    """A list of {"text": ..., "tone": ...} chips for this plan."""

    label = label or humanize
    intent = plan.get("intent")

    # answered by code (statistics, ratio KPIs, growth ...): it brings its own chips
    if intent == "advanced":
        return list(plan["advanced"]["chips"])
    agg = plan.get("agg")
    noun = plan.get("count_noun") or "rows"

    chips = []

    def add(text, tone=""):
        if text:
            chips.append({"text": str(text), "tone": tone})

    # ---- the calculation
    if intent == "count":
        add(f"Count of {noun}", "blue")

    elif intent in ("top", "bottom"):
        word = "Highest" if intent == "top" else "Lowest"
        add(f"{word} first {RANK_BY.get(agg, '')}".strip(), "blue")

    elif intent == "month_pick":
        add(PICK.get(plan.get("pick"), "Month"), "blue")

    elif intent == "share" and plan.get("ratio_denominator"):
        add(RATIO_CALCULATION, "blue")

    elif intent == "unique" and plan.get("want_list"):
        add("List of the different values", "blue")

    else:
        add(CALCULATION.get(intent, str(intent)), "blue")

    # ---- what it is calculated on
    value = plan.get("value_column")

    if intent in MEASURE_INTENTS and value and agg != "count":
        add(label(value))

    elif intent == "share" and plan.get("ratio_denominator"):
        add(f"{label(value)} ÷ {label(plan['ratio_denominator'])}")

    elif intent == "share":
        add(f"of {noun}" if agg == "count" else label(value) if value else "")

    elif intent == "unique":
        add(label(plan["column"]) if plan.get("column") else "")

    elif intent == "missing":
        add(label(plan["column"]) if plan.get("column") else "all columns")

    # ---- how it is grouped
    group = plan.get("group_column")

    if intent in ("top", "bottom", "breakdown") and group:
        add(f"by {label(group)}")

    elif intent == "share" and plan.get("share_group"):
        add(f"by {label(plan['share_group'])}")

    elif intent in ("trend", "month_pick"):
        add("by month")

    # ---- what it is limited to
    for item in effective_filters(plan):
        add(item.get("label") or f"{label(item['column'])} = {item['value']}", "green")

    for item in plan.get("conditions") or []:
        add(item.get("label"), "green")

    date_filter = plan.get("date_filter")

    if date_filter and date_filter.get("label"):

        text = f"in {date_filter['label']}"

        if date_filter.get("ambiguous") and date_filter.get("column"):
            text += f" (by {label(date_filter['column'])})"

        add(text, "green")

    return chips