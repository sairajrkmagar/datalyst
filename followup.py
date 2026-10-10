"""
FOLLOW-UP QUESTIONS

"and for 2024?", "what about Home?", "same for North", "now by region" refer to
the question before them. This module rewrites such a short question into a
complete one, using only the words of the earlier question, so the normal
(checked) path answers it. The person is shown the rewritten question, so
nothing is hidden.

    rewrite(engine, "and for 2024?", "What is the total revenue in 2023?")
    -> "What is the total revenue in 2024?"        (or None: not a follow-up)
"""

import re

from plan_repair import find_mentioned_values, readable_label

START = re.compile(
    r"^\s*(?:and|but|ok|okay|now|then|also)?[\s,]*"
    r"(?:what about|how about|and for|and in|and what about|same for|same but|"
    r"and|now for|now by|now|only for|only|just|for|in|by|instead for|instead)\b[\s,:]*",
    re.IGNORECASE,
)

FILLERS = {
    "the", "same", "only", "just", "too", "also", "one", "please", "instead", "for", "in", "by",
    "what", "about", "how", "and", "but", "now", "then", "ok", "okay", "per", "on", "of", "it",
    "that", "this", "year", "month", "is", "was", "are", "were", "to", "a", "an", "with", "at",
}


def nothing_else(text, *removed):
    """True when the text holds only the removed words plus filler words."""

    text = text.lower()

    for item in removed:
        text = re.sub(rf"\b{re.escape(str(item).lower())}\b", " ", text)

    return not (set(re.findall(r"[a-z0-9&']+", text)) - FILLERS)


YEAR = re.compile(r"\b((?:19|20)\d\d)\b")
MONTHS = ("january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december")


def is_followup(question):
    """A short question that begins like a follow-up and is not complete by itself."""

    text = str(question).strip()
    words = re.findall(r"[A-Za-z0-9&']+", text)

    return bool(START.match(text)) and 0 < len(words) <= 7


def values_of(engine, text):
    """{column: [values]} named in the text."""

    labels = [readable_label(c) for c in engine.df.columns]
    found = find_mentioned_values(text, engine.dataset_understanding["dimension_values"], labels)

    return {c: v for c, v in found.items() if v}


def dimension_named(engine, text):
    """A dimension column named in the text ('by region'), or None."""

    text = text.lower()

    for column in engine.dataset_understanding["dimension_values"]:
        if re.search(rf"\b{re.escape(readable_label(column))}s?\b", text):
            return column

    return None


def rewrite(engine, question, previous):
    """The complete question, or None when this is not a follow-up we can resolve."""

    if not previous or not is_followup(question):
        return None

    short = START.sub("", str(question).strip()).strip(" ?.!")
    prev = str(previous).strip().rstrip("?.! ")

    if not short:
        return None

    # ---- a different year: "and for 2024?"
    new_years = YEAR.findall(short)
    old_years = YEAR.findall(prev)

    if len(new_years) == 1 and len(old_years) == 1 and nothing_else(short, new_years[0]):
        return YEAR.sub(new_years[0], prev, count=1) + "?"

    # ---- a different month: "and for March?"
    month = next((m for m in MONTHS if re.search(rf"\b{m}\b", short.lower())), None)
    old_month = next((m for m in MONTHS if re.search(rf"\b{m}\b", prev.lower())), None)

    if month and old_month and nothing_else(short, month):
        return re.sub(old_month, month, prev, count=1, flags=re.IGNORECASE) + "?"

    # ---- a different value of the same column: "what about Home?"
    mentioned = values_of(engine, short)
    earlier = values_of(engine, prev)

    for column, values in mentioned.items():

        if not nothing_else(short, *[str(v) for v in values]):
            continue

        old = [v for v in earlier.get(column, [])]

        if old:
            new = str(values[0])
            pattern = re.compile(rf"\b{re.escape(str(old[0]))}\b", re.IGNORECASE)
            if pattern.search(prev):
                return pattern.sub(new, prev, count=1) + "?"

        # the earlier question had no value of this column: add it
        if not old:
            return f"{prev} for {values[0]}?"

    # ---- a different split: "now by region", "by channel instead"
    by = dimension_named(engine, short)

    if by and re.search(r"\bby\b|\binstead\b|\bper\b|^now\b", str(question).lower()) \
            and nothing_else(short, readable_label(by), readable_label(by) + "s"):

        label = readable_label(by)

        if re.search(r"\bby\s+[a-z ]+$", prev, re.IGNORECASE):
            return re.sub(r"\bby\s+[a-z ]+$", f"by {label}", prev, flags=re.IGNORECASE) + "?"

        return f"{prev} by {label}?"

    return None
