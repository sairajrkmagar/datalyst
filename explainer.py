from safe_numbers import is_whole
import re

import pandas as pd

from filters import (
    effective_filters, plural_label, scope_text, subset_for, to_dates
)
from llm_client import LLMClient


# A small model is enough to put facts into words. Using a different
# model than the one that reads questions also keeps that model's
# memory of your data warm, so questions stay fast.
EXPLAINER_MODEL = "llama3.2:3b"

# Words that usually mean the AI is guessing a reason or a future
BANNED_PHRASES = [
    "because", "due to", "caused by", "probably", "likely", "perhaps",
    "seasonal", "holiday", "festival", "forecast", "predict",
    "expected to", "should",
]

NUMBER_PATTERN = re.compile(r"\d[\d,]*\.?\d*")


# ------------------------------------------------------------
# Number helpers
# ------------------------------------------------------------

def format_number(value):

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if number != number or number in (float("inf"), float("-inf")):
        return "n/a"

    if is_whole(number):
        return f"{int(number):,}"

    return f"{number:,.2f}"


def format_percent(value):
    return f"{float(value):.1f}%"


def label(name):
    return str(name).replace("_", " ")


def total_label(name):
    """'total amount' stays 'Total amount' (not 'Total total amount')."""

    text = label(name)

    if text.lower().startswith("total"):
        return text.capitalize()

    return f"Total {text}"


def number_tokens(text):
    """Every number written in a text, as (value, decimals)."""

    found = []

    for token in NUMBER_PATTERN.findall(str(text)):

        token = token.rstrip(".,")

        if not token:
            continue

        clean = token.replace(",", "")

        try:
            value = float(clean)
        except ValueError:
            continue

        decimals = len(clean.split(".")[1]) if "." in clean else 0

        found.append((value, decimals))

    return found


# ------------------------------------------------------------
# The facts the AI is allowed to talk about
# ------------------------------------------------------------

class Facts:

    def __init__(self):

        self.items = []     # (label, text shown to the AI)
        self.numbers = []   # numbers the AI may use
        self.names = []     # labels the AI may use (hidden when checking)

    def number(self, name, value, percent=False):

        text = format_percent(value) if percent else format_number(value)

        self.items.append((name, text))

        self.numbers.extend(v for v, _ in number_tokens(text))

    def text(self, name, value):

        value = str(value)

        self.items.append((name, value))
        self.names.append(value)

        self.numbers.extend(v for v, _ in number_tokens(value))

    def hide(self, *names):

        for name in names:
            if name is not None:
                self.names.append(str(name))


def build_facts(plan, result, df):
    """
    Work out the facts with plain Python.
    Returns (facts, fallback_text).
    The fallback text is written by code, never by the AI.
    """

    facts = Facts()

    intent = plan["intent"]
    v = plan["value_column"]
    g = plan["group_column"]
    col = plan["column"] or v

    # The rows this question is about (after any filters)
    sub = subset_for(plan, df)
    scope = scope_text(plan)
    scoped = bool(
        effective_filters(plan)
        or plan.get("date_filter")
        or plan.get("conditions")
    )
    scope_phrase = f" {scope}" if scope else ""

    rows = len(sub)

    facts.hide(v, g, col)

    for item in effective_filters(plan):
        facts.hide(item["value"], item["column"])

    date_filter = plan.get("date_filter")

    if date_filter:
        facts.text("Period asked about", date_filter["label"])

    fallback = ""

    # ---------------------------------------------------- TOTAL
    if intent == "total":

        if not scoped:

            average = df[v].mean()

            facts.number(total_label(v), result)
            facts.number("Number of rows", rows)
            facts.number(f"Average {label(v)} per row", average)

            fallback = (
                f"{total_label(v)} is {format_number(result)} across "
                f"{format_number(rows)} rows, an average of "
                f"{format_number(average)} per row."
            )

        else:

            overall = float(df[v].sum())

            facts.number(f"{total_label(v)} {scope}", result)
            facts.number(f"Overall total {label(v)}", overall)
            facts.number("Rows matching this filter", rows)

            fallback = (
                f"{total_label(v)} {scope} is {format_number(result)}"
            )

            if overall:
                share = float(result) / overall * 100
                facts.number("Share of the overall total", share, True)
                fallback += (
                    f", which is {format_percent(share)} of the overall "
                    f"total of {format_number(overall)}"
                )

            fallback += f", from {format_number(rows)} rows."

    # -------------------------------------------------- AVERAGE
    elif intent == "average":

        if not scoped:

            low, high = df[v].min(), df[v].max()

            facts.number(f"Average {label(v)}", result)
            facts.number("Lowest value", low)
            facts.number("Highest value", high)
            facts.number("Number of rows", rows)

            fallback = (
                f"The average {label(v)} is {format_number(result)}, "
                f"ranging from {format_number(low)} to "
                f"{format_number(high)} across {format_number(rows)} rows."
            )

        else:

            overall = df[v].mean()

            facts.number(f"Average {label(v)} {scope}", result)
            facts.number(f"Overall average {label(v)}", overall)
            facts.number("Rows matching this filter", rows)

            fallback = (
                f"The average {label(v)} {scope} is "
                f"{format_number(result)}, compared with an overall "
                f"average of {format_number(overall)}."
            )

            if overall:
                difference = (float(result) - overall) / overall * 100
                direction = "above" if difference >= 0 else "below"

                facts.number(
                    "Difference from overall average",
                    abs(difference),
                    True
                )
                facts.text("Direction of difference", direction)

                fallback = (
                    f"The average {label(v)} {scope} is "
                    f"{format_number(result)}, which is "
                    f"{format_percent(abs(difference))} {direction} the "
                    f"overall average of {format_number(overall)}."
                )

    # ----------------------------------------- MAXIMUM / MINIMUM
    elif intent in ("maximum", "minimum"):

        word = "highest" if intent == "maximum" else "lowest"
        average = sub[v].mean()

        facts.number(f"The {word} {label(v)}{scope_phrase}", result)
        facts.number(f"Average {label(v)}{scope_phrase}", average)

        fallback = (
            f"The {word} {label(v)}{scope_phrase} is "
            f"{format_number(result)}, compared with an average of "
            f"{format_number(average)}."
        )

        if average:
            times = float(result) / average
            facts.number("Times the average", times)

        matches = sub[sub[v] == result]

        if len(matches) > 0:

            first = matches.iloc[0]
            details = []

            for name in sub.columns:

                if name == v:
                    continue

                if pd.api.types.is_numeric_dtype(sub[name]):
                    continue

                if pd.isna(first[name]):
                    continue

                facts.text(label(name) + " on that row", first[name])
                details.append(f"{label(name)} {first[name]}")

                if len(details) == 3:
                    break

            if details:
                fallback += " It is on the row with " + ", ".join(details) + "."

    # ------------------------------------------------ TOP / BOTTOM
    elif intent in ("top", "bottom"):

        agg = plan.get("agg") or "sum"

        noun = plan.get("count_noun") or "orders"

        if agg == "count":
            sums = sub.groupby(g).size()
            vlabel = f"number of {noun}"
        elif agg == "mean":
            sums = sub.groupby(g)[v].mean()
            vlabel = f"average {label(v)}"
        else:
            sums = sub.groupby(g)[v].sum()
            vlabel = label(v)

        sums = sums.sort_values(ascending=False)

        # a share of the total only makes sense for sums and counts
        total = float(sums.sum()) if agg != "mean" else 0.0
        count = len(sums)
        word = "highest" if intent == "top" else "lowest"

        # "top 3": a list of (name, value)
        if isinstance(result, list):

            names = [name for name, _ in result]
            facts.hide(*names)

            for position, (name, value) in enumerate(result, start=1):
                facts.text(f"Number {position} {label(g)}", name)
                facts.number(f"Number {position} {vlabel}", value)

            facts.number(f"Number of {label(g)} values", count)

            listing = ", ".join(
                f"{name} ({format_number(value)})" for name, value in result
            )

            kind = "top" if intent == "top" else "bottom"

            fallback = (
                f"The {kind} {len(result)} {plural_label(label(g))} by "
                f"{vlabel}{scope_phrase} are {listing}"
            )

            combined = sum(float(value) for _, value in result)

            if total:
                share = combined / total * 100
                facts.number(
                    "Combined share of the overall total", share, True
                )
                fallback += (
                    f", together {format_percent(share)} of the total"
                )

            fallback += "."

        else:

            name, value = result

            facts.hide(name)

            facts.text(f"{label(g)} with the {word} {vlabel}", name)
            facts.number(f"Its {vlabel}", value)
            facts.number(f"Number of {label(g)} values", count)

            fallback = (
                f"{name} has the {word} {vlabel}{scope_phrase} at "
                f"{format_number(value)}"
            )

            if total:
                share = float(value) / total * 100
                facts.number("Its share of the overall total", share, True)
                fallback += f", which is {format_percent(share)} of the total"

            if count > 1:

                neighbour_name = (
                    sums.index[1] if intent == "top" else sums.index[-2]
                )
                neighbour_value = (
                    sums.iloc[1] if intent == "top" else sums.iloc[-2]
                )

                facts.hide(neighbour_name)
                facts.text("Next one in the ranking", neighbour_name)
                facts.number("Its value", neighbour_value)

                fallback += (
                    f". Next is {neighbour_name} at "
                    f"{format_number(neighbour_value)}"
                )

                if neighbour_value:
                    gap = abs(float(value) - float(neighbour_value)) / abs(
                        float(neighbour_value)
                    ) * 100
                    facts.number("Gap between them", gap, True)
                    fallback += f", a gap of {format_percent(gap)}"

            fallback += "."

    # ---------------------------------------------------- GROUP TABLE
    elif intent == "breakdown":

        agg = plan.get("agg") or "sum"
        noun = plan.get("count_noun") or "orders"

        if agg == "count":
            vlabel = f"number of {noun}"
        elif agg == "mean":
            vlabel = f"average {label(v)}"
        else:
            vlabel = label(v)

        items = list(result.items())
        facts.hide(*[name for name, _ in items])

        top_name, top_value = items[0]
        low_name, low_value = items[-1]

        as_percent = bool(plan.get("as_percent"))
        show = format_percent if as_percent else format_number

        facts.number(f"Number of {label(g)} values", len(items))
        facts.text(f"{label(g)} with the highest {vlabel}", top_name)
        facts.number("Highest value", top_value, as_percent)
        facts.text(f"{label(g)} with the lowest {vlabel}", low_name)
        facts.number("Lowest value", low_value, as_percent)

        fallback = (
            f"Across {len(items)} {plural_label(label(g))}, {top_name} has "
            f"the highest {vlabel}{scope_phrase} at "
            f"{show(top_value)} and {low_name} the lowest at "
            f"{show(low_value)}."
        )

        if as_percent:
            pass

        elif agg != "mean":

            total = sum(float(number) for _, number in items)

            if total:
                share = float(top_value) / total * 100
                facts.number("Highest one's share of the total", share, True)
                fallback += (
                    f" {top_name} makes up {format_percent(share)} of the "
                    f"total."
                )

        if len(items) > 1 and low_value and not as_percent:
            ratio_times = float(top_value) / float(low_value)
            facts.number("Highest is this many times the lowest", ratio_times)

    # ---------------------------------------------------- PERCENTAGE
    elif intent == "share":

        agg = plan.get("agg") or "count"
        detail = plan.get("share_detail") or {}
        part, whole = detail.get("part"), detail.get("whole")

        noun = plan.get("count_noun") or "orders"
        phrase = noun if agg == "count" else label(v)

        if isinstance(result, dict):

            ordered = sorted(result.items(), key=lambda x: -x[1])
            facts.hide(*[name for name, _ in ordered])

            high_name, high_value = ordered[0]
            low_name, low_value = ordered[-1]

            facts.text(f"Highest {label(plan['share_group'])}", high_name)
            facts.number("Its share", high_value, True)
            facts.text(f"Lowest {label(plan['share_group'])}", low_name)
            facts.number("Its share", low_value, True)

            if whole:
                facts.number("Overall share", float(part) / float(whole) * 100, True)

            fallback = (
                f"Share of {phrase}{scope_phrase} by "
                f"{label(plan['share_group'])} is highest for {high_name} "
                f"at {format_percent(high_value)} and lowest for "
                f"{low_name} at {format_percent(low_value)}."
            )

        else:

            facts.number("Share", result, True)
            facts.number("Part", part)
            facts.number("Whole", whole)

            if plan.get("ratio_denominator"):
                fallback = (
                    f"{label(v).capitalize()} is {format_percent(result)} of "
                    f"{label(plan['ratio_denominator'])}{scope_phrase} "
                    f"({format_number(part)} of {format_number(whole)})."
                )
            elif agg == "count":
                fallback = (
                    f"{noun.capitalize()}{scope_phrase} are "
                    f"{format_percent(result)} of all {noun} "
                    f"({format_number(part)} of {format_number(whole)})."
                )
            else:
                fallback = (
                    f"{label(v).capitalize()}{scope_phrase} is "
                    f"{format_percent(result)} of the overall {label(v)} "
                    f"({format_number(part)} of {format_number(whole)})."
                )

    # ---------------------------------------------------- BEST MONTH
    elif intent == "month_pick":

        detail = plan.get("month_detail") or {}
        left_out = detail.get("left_out") or []

        facts.number("Months compared", detail.get("months_used", 0))

        for month in left_out:
            facts.text("Month left out (partly covered)", month)

        note = (
            f" Partly covered months left out: {', '.join(left_out)}."
            if left_out else ""
        )

        if plan["pick"] == "mean":

            facts.number(f"Average monthly {label(v)}", result)

            fallback = (
                f"Average monthly {label(v)}{scope_phrase} is "
                f"{format_number(result)} over "
                f"{detail.get('months_used', 0)} full months.{note}"
            )

        else:

            month, value = result
            word = "weakest" if plan["pick"] == "min" else "best"

            facts.hide(month)
            facts.text(f"The {word} month", month)
            facts.number(f"{label(v)} in that month", value)

            fallback = (
                f"The {word} month for {label(v)}{scope_phrase} is "
                f"{month} at {format_number(value)}.{note}"
            )

    # ------------------------------------------------------ TREND
    elif intent == "trend":

        months = list(result.items())

        facts.hide(*[key for key, _ in months])

        first_month, first_value = months[0]
        last_month, last_value = months[-1]
        best_month, best_value = max(months, key=lambda x: x[1])
        worst_month, worst_value = min(months, key=lambda x: x[1])
        average = sum(value for _, value in months) / len(months)

        facts.number("Number of months", len(months))
        facts.text("Best month", best_month)
        facts.number("Best month value", best_value)
        facts.text("Weakest month", worst_month)
        facts.number("Weakest month value", worst_value)
        facts.number("Average per month", average)

        fallback = (
            f"{label(v).capitalize()}{scope_phrase} covers "
            f"{len(months)} months. "
            f"The best month is {best_month} at {format_number(best_value)} "
            f"and the weakest is {worst_month} at "
            f"{format_number(worst_value)}."
        )

        if len(months) > 1:

            facts.text("Latest month", last_month)
            facts.number("Latest month value", last_value)

            previous_value = months[-2][1]

            if previous_value:
                change = (float(last_value) - previous_value) / abs(
                    previous_value
                ) * 100
                direction = "up" if change >= 0 else "down"

                facts.number(
                    "Change from the previous month",
                    abs(change),
                    True
                )
                facts.text("Direction of that change", direction)

                fallback += (
                    f" The latest month, {last_month}, is {direction} "
                    f"{format_percent(abs(change))} on the month before."
                )

        # Is the last month only partly covered by the data?
        dates = to_dates(sub[g])
        last_date = dates.max()

        if pd.notna(last_date) and last_date.day < last_date.days_in_month:

            end = last_date.strftime("%Y-%m-%d")

            facts.text("The latest month is incomplete, data ends on", end)

            fallback += (
                f" Note that the latest month is incomplete "
                f"(data ends on {end})."
            )

    # ------------------------------------------------------ UNIQUE
    elif intent == "unique":

        facts.number(f"Distinct {label(col)} values{scope_phrase}", result)
        facts.number("Number of rows", rows)

        fallback = (
            f"There are {format_number(result)} distinct {label(col)} "
            f"values{scope_phrase} across {format_number(rows)} rows"
        )

        if result:
            per = rows / float(result)
            facts.number(f"Average rows per {label(col)}", per)
            fallback += f", about {format_number(round(per, 1))} rows each"

        fallback += "."

    # ------------------------------------------------------- COUNT
    elif intent == "count":

        if scoped:

            total_rows = len(df)

            facts.number(f"Rows {scope}", result)
            facts.number("Rows in the whole dataset", total_rows)

            fallback = (
                f"There are {format_number(result)} rows {scope}"
            )

            if total_rows:
                share = float(result) / total_rows * 100
                facts.number("Share of all rows", share, True)
                fallback += (
                    f", which is {format_percent(share)} of all "
                    f"{format_number(total_rows)} rows"
                )

            fallback += "."

        else:

            facts.number("Number of rows", rows)
            facts.number("Number of columns", len(df.columns))

            fallback = (
                f"The dataset has {format_number(rows)} rows and "
                f"{format_number(len(df.columns))} columns."
            )

    # ---------------------------------------------------- DUPLICATE
    elif intent == "duplicate":

        facts.number(f"Duplicate rows{scope_phrase}", result)
        facts.number("Number of rows", rows)
        facts.number("Rows left after removing duplicates", rows - result)

        fallback = (
            f"There are {format_number(result)} duplicate rows"
            f"{scope_phrase} out of {format_number(rows)}"
        )

        if rows:
            share = result / rows * 100
            facts.number("Duplicates as a share of all rows", share, True)
            fallback += f" ({format_percent(share)})"

        fallback += "."

    # ------------------------------------------------------ MISSING
    elif intent == "missing":

        cells = rows * len(sub.columns)

        facts.number(f"Missing values{scope_phrase}", result)
        facts.number("Total cells in the dataset", cells)

        if result == 0:

            fallback = f"There are no missing values{scope_phrase}."

        else:

            share = result / cells * 100 if cells else 0
            facts.number("Missing values as a share of all cells", share, True)

            missing = sub.isnull().sum()
            worst = missing.idxmax()

            facts.text("Column with the most missing values", worst)
            facts.number("Missing values in that column", missing.max())

            fallback = (
                f"There are {format_number(result)} missing values"
                f"{scope_phrase} ({format_percent(share)} of all cells). "
                f"The column with the most is {worst} with "
                f"{format_number(missing.max())}."
            )

    return facts, fallback


# ------------------------------------------------------------
# Checking what the AI wrote
# ------------------------------------------------------------

def verify(text, facts):
    """Returns (is_ok, reason). Every number must come from the facts."""

    if text is None or not str(text).strip():
        return False, "empty answer"

    cleaned = str(text).strip()

    if len(cleaned) > 700:
        return False, "too long"

    lowered = cleaned.lower()

    for phrase in BANNED_PHRASES:

        if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
            return False, f"guessing word: '{phrase}'"

    # Hide names and labels (like "2026-03" or "ORD-1380")
    hidden = cleaned

    for name in sorted(set(facts.names), key=len, reverse=True):

        if name:
            hidden = re.sub(re.escape(name), " ", hidden, flags=re.IGNORECASE)

    for value, decimals in number_tokens(hidden):

        allowed = any(
            abs(round(number, decimals) - value) < 10 ** -(decimals + 3)
            for number in facts.numbers
        )

        if not allowed:
            return False, f"number not in the facts: {value:g}"

    return True, ""


def tidy(text):

    cleaned = str(text).strip().replace("**", "").replace("__", "")

    # We do not know the currency, so never show a currency symbol.
    # (A "$" would also break the page: Streamlit reads $...$ as math.)
    cleaned = re.sub(r"[$€£₹]", "", cleaned)

    return re.sub(r"\s+", " ", cleaned)


# ------------------------------------------------------------
# The explainer
# ------------------------------------------------------------

class Explainer:

    def __init__(self, model=EXPLAINER_MODEL):

        self.llm = LLMClient(model=model, timeout=90)

    def create_prompt(self, question, response, facts):

        lines = "\n".join(f"- {name}: {text}" for name, text in facts.items)

        return f"""You are a business data analyst explaining a result to a manager who is not technical.

QUESTION: {question}

ANSWER (already calculated): {response}

FACTS (calculated by code, the only numbers you may use):
{lines}

Write 2 or 3 short sentences that explain what this means for the business.

Rules:
- Use ONLY numbers that appear in FACTS. Copy them exactly as written: same digits, same commas, same % sign.
- Do not round, convert, abbreviate, or calculate any new number.
- Do not give reasons, causes, or predictions. Describe only what the FACTS show.
- No bullet points, no headings, no markdown.
- Do not add currency symbols. The currency is unknown.
- Do not start with "Based on".
"""

    def explain(self, answer, df):
        """
        Returns a dict:
          text    - the explanation to show
          source  - "ai" (AI wrote it and passed the number check)
                    or "template" (written by code)
          reason  - why the AI text was rejected (if it was)
          facts   - the facts behind the explanation
        """

        facts, fallback = build_facts(answer["plan"], answer["result"], df)

        text = None
        source = "template"
        reason = ""

        try:

            prompt = self.create_prompt(
                answer["question"], answer["response"], facts
            )

            raw = self.llm.generate(
                prompt, json_mode=False, max_tokens=220
            )

            ok, reason = verify(raw, facts)

            if ok:
                text = tidy(raw)
                source = "ai"

        except RuntimeError as error:

            reason = str(error)

        if text is None:
            text = fallback

        return {
            "text": text,
            "source": source,
            "reason": reason,
            "facts": facts.items
        }
