"""
CLARIFICATION: turn a refusal into a conversation.

When the app cannot answer, it knows WHY (a word it could not match, a value in
two columns, a missing number column). This module turns that reason into a few
one-click choices. Each choice is the person's own question with ONE thing made
explicit, so the normal checked path answers it. Nothing is guessed silently:
the person picks.

    option = suggest(engine, "total wages", "I could not match 'wages' ...")
    -> {"prompt": "I could not find 'wages'. Did you mean:",
        "options": [{"label": "Monthly Salary", "question": "total monthly salary"}]}

Returns None when there is no honest choice to offer.
"""

import difflib
import re

from plan_repair import readable_label

MAX_OPTIONS = 4

# words people use for a column that is called something else
SYNONYMS = {
    "wages": ("salary", "pay"), "wage": ("salary", "pay"), "pay": ("salary",),
    "salaries": ("salary",), "payroll": ("salary", "pay", "wage"), "compensation": ("salary", "pay"),
    "earnings": ("salary", "revenue", "profit"),
    "turnover": ("revenue", "sales"), "income": ("revenue", "income", "salary"),
    "expense": ("cost",), "expenses": ("cost",), "spending": ("spend", "cost"),
    "price": ("price", "amount"), "worth": ("amount", "value"),
    "clients": ("customer",), "client": ("customer",), "buyers": ("customer",),
    "staff": ("employee",), "workers": ("employee",), "headcount": ("employee",),
    "area": ("region", "zone"), "location": ("region", "city", "location"),
    "type": ("category", "type"), "kind": ("category", "type"),
}

# words for "money earned" that a file of prices or costs may not have as a column
MONEY_WORDS = {
    "revenue", "revenues", "sales", "income", "turnover", "earnings", "money", "amount", "amounts",
    "spend", "spending", "cost", "costs", "profit", "profits", "price", "prices",
}
MONEY_COLUMN_WORDS = {
    "price", "cost", "amount", "value", "revenue", "sales", "salary", "pay", "spend", "fee",
    "fare", "charge", "income", "profit", "mrr", "total",
}

STAT_WORDS = (
    r"standard deviation|interquartile range|most common value|most common|"
    r"\d{1,2}(?:st|nd|rd|th) percentile|median|variance|range|mode"
)


def measures_of(engine):
    """Number columns, the main one first."""

    columns = list(engine.profile.get("measures", engine.dataset_understanding["measures"]))
    main = engine.profile.get("revenue_column")

    return ([main] if main in columns else []) + [c for c in columns if c != main]


def label(engine, column):
    alias = {m: o for o, m in engine.profile.get("main_columns", {}).items()}
    return re.sub(r" main$", "", readable_label(alias.get(column, column)))


def replace_word(question, word, new):
    """The question with one word (any capital letters) swapped for another."""

    return re.sub(rf"\b{re.escape(word)}\b", new, question, count=1, flags=re.IGNORECASE)


def candidates_for(engine, word):
    """[(kind, shown name, text to put in the question)] closest to an unknown word."""

    word = word.lower().strip()
    found, seen = [], set()

    def add(kind, shown, text):
        key = (kind, str(shown).lower())
        if key not in seen:
            seen.add(key)
            found.append((kind, str(shown), str(text)))

    columns = list(engine.df.columns)
    labels = {c: label(engine, c) for c in columns}

    # 1. a value with a typo: "Electonics" -> Electronics
    values = {}
    for column, items in engine.dataset_understanding["dimension_values"].items():
        for item in items:
            values.setdefault(str(item).strip().lower(), str(item).strip())

    for hit in difflib.get_close_matches(word, list(values), n=2, cutoff=0.78):
        add("value", values[hit], values[hit])

    # 2. a column with a typo or a synonym
    for hit in difflib.get_close_matches(word, [l.lower() for l in labels.values()], n=2, cutoff=0.72):
        column = next(c for c, l in labels.items() if l.lower() == hit)
        add("column", labels[column], labels[column])

    # a misspelt word of a column name: "revnue" -> revenue
    for column, text in labels.items():
        tokens = [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 4]
        if difflib.get_close_matches(word, tokens, n=1, cutoff=0.78):
            add("column", text, text)

    stems = SYNONYMS.get(word, ()) + (word,)

    for column, text in labels.items():
        tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
        for stem in stems:
            if len(stem) >= 4 and any(t.startswith(stem[:5]) or stem.startswith(t[:5]) for t in tokens if len(t) >= 4):
                add("column", text, text)
                break

    return found


def unmatched_words(message):
    found = re.search(r"could not match '([^']+(?:', '[^']+)*)'", message)
    return found.group(1).split("', '") if found else []


def suggest(engine, question, message):
    """{"prompt", "options": [{"label", "question"}]} or None."""

    question, message = str(question), str(message)

    # ---- 1. a word that matches nothing: a typo, or another name for a column
    words = unmatched_words(message)

    for word in words:

        # "revenue" on a file of prices: offer the real amount columns, say what the file is
        if word.lower() in MONEY_WORDS:
            money = [
                c for c in measures_of(engine)
                if set(re.findall(r"[a-z0-9]+", label(engine, c).lower())) & MONEY_COLUMN_WORDS
            ][:MAX_OPTIONS]

            if money:
                return {
                    "prompt": (
                        f"This file has no \u201c{word}\u201d column (it holds amounts like prices, "
                        f"not sales). Did you mean one of these?"
                    ),
                    "options": [
                        {"label": label(engine, c), "question": replace_word(question, word, label(engine, c)), "kind": "column"}
                        for c in money
                    ],
                }

        options = [
            {"label": text, "question": replace_word(question, word, text), "kind": kind}
            for kind, shown, text in candidates_for(engine, word)
        ][:MAX_OPTIONS]

        if options:
            return {"prompt": f"I could not find \u201c{word}\u201d in your data. Did you mean:", "options": options}

    # ---- 2. a value that lives in two columns
    ambiguous = re.search(r"'([^']+)' is a value in more than one column \(([^)]+)\)", message)

    if ambiguous:

        value, owners = ambiguous.group(1), [o.strip() for o in ambiguous.group(2).split(",")]

        options = [
            {"label": f"{owner}: {value}", "question": replace_word(question, value, f"{owner} {value}")}
            for owner in owners[:MAX_OPTIONS]
        ]

        return {"prompt": f"\u201c{value}\u201d appears in more than one column. Which do you mean?", "options": options}

    # ---- 3. a number column is missing from the question
    if re.search(r"Which number (?:column )?(?:should I|do you)", message) or "Percent of what" in message:

        text = question.strip().rstrip("?.! ")
        options = []

        for column in measures_of(engine)[:MAX_OPTIONS]:

            name = label(engine, column)
            new = None

            if re.search(rf"\b(?:{STAT_WORDS})\b", text, re.IGNORECASE):
                new = re.sub(rf"\b({STAT_WORDS})\b(?!\s+of\b)", rf"\1 of {name}", text, count=1, flags=re.IGNORECASE) + "?"
            elif re.search(r"\bshare\b(?!\s+of\b)", text, re.IGNORECASE):
                new = re.sub(r"\bshare\b", f"share of {name}", text, count=1, flags=re.IGNORECASE) + "?"
            elif re.search(r"^(?:show|give|list|display)\b", text, re.IGNORECASE) and re.search(r"\bby\b", text, re.IGNORECASE):
                new = re.sub(r"^(show|give|list|display)( me)?\b", rf"\1\2 {name}", text, count=1, flags=re.IGNORECASE) + "?"
            elif re.search(r"\b(?:best|worst|top|highest|lowest|most|least)\b", text, re.IGNORECASE) and not re.search(r"\bby\b", text, re.IGNORECASE):
                new = f"{text} by {name}?"

            if new:
                options.append({"label": name, "question": new})

        if options:
            return {"prompt": "Which number do you mean?", "options": options}

    return None
