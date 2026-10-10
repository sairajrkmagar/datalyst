import difflib
import re

from semantics import name_words, non_additive_reason

from filters import MONTH_NAMES, OPERATOR_WORDS, RANKING_INTENTS


ALL_KEYS = [
    "intent",
    "column",
    "group_column",
    "value_column",
    "filter_value",
    "operation",
]

VALID_INTENTS = [
    "total", "average", "maximum", "minimum", "count", "unique",
    "top", "bottom", "trend", "duplicate", "missing",
]

# If the AI forgot the intent, the operation tells us what it meant
OPERATION_TO_INTENT = {
    "sum": "total",
    "average": "average",
    "max": "maximum",
    "min": "minimum",
    "count": "count",
    "row_count": "count",
    "unique": "unique",
    "time_series": "trend",
    "duplicate_count": "duplicate",
    "missing_count": "missing",
}

# Intents that calculate on a number column
NUMBER_INTENTS = [
    "total", "average", "maximum", "minimum", "top", "bottom", "trend",
]

BOTTOM_WORDS = [
    "lowest", "least", "smallest", "worst", "fewest", "minimum", "bottom",
]

# Text values that really mean "nothing"
EMPTY_TEXT = ["null", "none", "nan", ""]

YES_WORDS = {"yes", "true", "y", "1"}
NO_WORDS = {"no", "false", "n", "0"}
YES_NO = YES_WORDS | NO_WORDS

# Values that are also everyday words: never treat them as a filter
GENERIC_VALUES = {
    "other", "others", "unknown", "none", "all", "any", "na", "n/a",
}

# Words the app itself uses to read a question. A category value that is one
# of them ("Total", "Average", "Top" ...) is a HAZARD: the word "total" in
# "what is the total revenue" must never become a filter "tier = Total".
VOCABULARY_VALUES = {
    "total", "sum", "average", "avg", "mean", "median", "count", "number",
    "overall", "combined", "altogether", "highest", "lowest", "maximum",
    "minimum", "max", "min", "top", "bottom", "best", "worst", "most",
    "least", "fewest", "first", "last", "each", "every", "per", "monthly",
    "yearly", "daily", "weekly", "quarterly", "trend", "rate", "share",
    "percent", "percentage", "ratio", "general", "misc",
    "miscellaneous", "rest", "remaining", "normal", "regular",
}

HAZARD_VALUES = GENERIC_VALUES | VOCABULARY_VALUES

# a hazard value counts only after a linking word: "for Total", "from Other"
CONNECTORS = (
    r"(?:for|from|in|of|by|with|among|where|is|are|within|only|than|not|"
    r"excluding|equals?|=)"
)

# "for Other", "for the Other", "for gender Other", "where payment method is Other"
BETWEEN_WORDS = r"(?:the\s+)?(?:[\w'&/-]+\s+){0,3}"

# what may follow a value that ENDS its phrase ("for other?", "for total in 2024")
PHRASE_END = r"(?=\s*(?:$|[?.!,;]|\b(?:in|during|and|or|from|with|by|across|between|where|for)\b))"


def ambiguous_hazard(question, filters, dimension_values):
    """
    "...for total" in a file where "Total" is a category: the lowercase word
    could be the category or just a word of the sentence. The filter must
    never be dropped silently, so ask for the exact spelling.
    """

    applied = {(f["column"], str(f["value"]).lower()) for f in filters or []}

    for column, values in dimension_values.items():

        for value in values:

            clean = str(value).strip().lower()

            if clean not in HAZARD_VALUES or (column, clean) in applied:
                continue

            pattern = (
                r"\b" + CONNECTORS + r"\s+" + BETWEEN_WORDS + re.escape(clean)
                + r"\b" + PHRASE_END
            )

            if re.search(pattern, question.lower()):
                return (
                    f"'{value}' is a value of the column '{column}', but it is "
                    f"also an ordinary word, so I am not sure you mean the "
                    f"value. Please type it exactly as it appears in the data, "
                    f"with the same capital letters, for example 'for {value}'."
                )

    return None

# Short values that are also ordinary English words (state codes IN, OR,
# ME, OK, HI ...). They count as a filter ONLY when typed exactly like that.
SHORT_WORDS = {
    "in", "on", "or", "me", "us", "to", "it", "is", "as", "at", "be", "by",
    "do", "go", "he", "hi", "if", "my", "no", "of", "so", "up", "we", "an",
    "am", "ok", "oh",
}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3,
    "mar": 3, "april": 4, "apr": 4, "june": 6, "jun": 6, "july": 7,
    "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9,
    "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

RANK_WORDS = (
    r"(?:top|best|highest|biggest|largest|bottom|lowest|worst|"
    r"smallest|least|fewest)"
)

BOTTOM_PATTERN = re.compile(
    r"\b(bottom|lowest|worst|least|fewest|smallest|fastest|quickest|"
    r"shortest|cheapest)\b"
)
TOP_PATTERN = re.compile(
    r"\b(top|best|highest|most|biggest|largest|greatest|slowest|longest|"
    r"priciest)\b"
)
AVG_WORDS = re.compile(r"\b(average|avg|mean)\b")
COUNT_RANK_WORDS = re.compile(
    r"\b(popular|popularity|frequent|frequently|common|commonly|busiest)\b|"
    r"\b(most|fewest|least)\s+(orders|transactions|purchases|records|rows|"
    r"customers|products)\b|\bhighest\s+(number|count)\s+of\b"
)
MONTH_AVG_PATTERN = re.compile(
    r"\b(average|avg|mean)\b[^?.]*\b(per month|monthly|a month|each month)\b|"
    r"\b(monthly|per month)\s+(average|avg|mean)\b"
)
BY_WORDS = r"(?:by|per|each|every|across)"
RANK_CUE = re.compile(
    r"\b(rank|ranking|ranked|who|which|top|bottom|best|worst|highest|"
    r"lowest|most|least|biggest|smallest|largest|fastest|slowest|"
    r"cheapest|popular|popularity|busiest)\b"
)
NEGATION_PATTERN = re.compile(
    r"\b(not|non|never|without|didn't|did not|weren't|were not|"
    r"wasn't|was not|isn't|aren't)\b"
)
REVENUE_WORDS = re.compile(
    r"\b(revenue|sales|income|turnover|earn\w*|money|spend|spent|spending|"
    r"order value|order amount|basket value|aov)\b"
)
BASE_ROW_NOUNS = [
    "orders", "records", "rows", "transactions", "purchases", "entries",
    "deliveries",
]


def row_patterns(extra_nouns):
    """Patterns for 'how many orders / employees ...' (words from the data)."""

    nouns = sorted(set(BASE_ROW_NOUNS + list(extra_nouns)), key=len, reverse=True)

    options = "|".join(re.escape(noun) for noun in nouns)

    count_pattern = re.compile(
        rf"\b(?:how many|number of|count of|total number of)\b[^?.]*?"
        rf"\b(?:{options})\b"
    )
    noun_pattern = re.compile(rf"\b(?:{options})\b")

    # "most orders", "fewest employees": ranking by how many rows
    rank_pattern = re.compile(
        rf"\b(?:most|fewest|least)\s+(?:{options}|customers|products)\b"
    )

    return count_pattern, noun_pattern, rank_pattern
NOT_ROW_COUNT = re.compile(
    r"\b(unique|distinct|different|duplicate|duplicates|missing|null|"
    r"nulls|blank|empty)\b"
)
NUMERIC_TEXT = re.compile(r"\s*[$]?\d[\d,.]*\s*(?:%|k|percent)?\s*")
RELATIVE_DATE_PATTERN = re.compile(
    r"\b(last|this|previous|next|current|past)\s+"
    r"(month|year|quarter|week|day)s?\b|"
    r"\b(last|past|previous|next|coming)\s+(?:\d+|few|couple of|several)\s+"
    r"(?:day|week|month|quarter|year)s?\b|"
    r"\byesterday\b|\btoday\b|\btomorrow\b|\bytd\b|\bmtd\b|"
    r"\byear[- ]to[- ]date\b|\bmonth[- ]to[- ]date\b|\bso far this\b|"
    r"\brecent(?:ly)?\b|\bmost recent\b|\blatest (?:month|year|quarter|week)\b"
)


# ------------------------------------------------------------
# Reading the question with plain code
# ------------------------------------------------------------

def label_of(name):
    return str(name).replace("_", " ")


def column_pattern(name):
    """A pattern that finds a column name written in a question."""

    # DepartmentType -> "department type"  (people type it with a space)
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))

    label = label_of(spaced).lower()

    forms = {re.escape(label), re.escape(str(name).lower())}

    # returned -> return / returns / returning
    if label.endswith("ed") and len(label) > 5:
        forms.add(re.escape(label[:-2]) + r"(?:s|ed|ing)?")

    # category -> categories, country -> countries
    if len(label) > 3 and label.endswith("y") and label[-2] not in "aeiou":
        forms.add(re.escape(label[:-1]) + "ie")

    return (
        r"(?<![a-z0-9])(?:" + "|".join(sorted(forms, key=len, reverse=True))
        + r")(?:s|es)?(?![a-z0-9])"
    )


def mentioned_columns(question, columns):
    """Columns named in the question, in the order they appear."""

    text = question.lower()
    found = []

    for column in sorted(columns, key=lambda c: -len(str(c))):

        match = re.search(column_pattern(column), text)

        if match:
            found.append((match.start(), column))
            blank = " " * (match.end() - match.start())
            text = text[:match.start()] + blank + text[match.end():]

    return [column for _, column in sorted(found, key=lambda x: x[0])]


def find_mentioned_values(question, dimension_values, column_labels=()):
    """
    Real column values named in the question.
    Returns {column: [values]}.  ("Fashion" -> {"category": ["Fashion"]})
    """

    original = question
    text = question.lower()

    # words inside a multi-word COLUMN name ("sales value", "customer rating")
    # are not values ("Sales" is also a department): blank them first
    for label in sorted(column_labels, key=len, reverse=True):

        if " " not in label:
            continue

        spot = r"(?<![A-Za-z0-9])" + re.escape(label) + r"(?![A-Za-z0-9])"
        text = re.sub(spot, lambda m: " " * len(m.group(0)), text)
        original = re.sub(spot, lambda m: " " * len(m.group(0)), original, flags=re.IGNORECASE)

    candidates = []

    for column, values in dimension_values.items():

        for value in values:

            clean = str(value).strip().lower()

            if len(clean) < 2 or clean in YES_NO:
                continue

            # "IN" must be typed "IN", never found inside "in February".
            # "Other" / "Total" / "Average" are words of the sentence AND real
            # values in some data: they count only when typed EXACTLY like the
            # data and after a linking word ("for Total"), never as a plain
            # lowercase "total".
            hazard = clean in HAZARD_VALUES
            strict = (len(clean) <= 3 and clean in SHORT_WORDS) or hazard

            candidates.append((clean, column, value, strict, hazard))

    found = {}

    original_start, text_start = original, text

    def hits(candidate, original_text, lower_text):
        """Does this value appear in the question (with its own strictness)?"""

        clean, column, value, strict, hazard = candidate

        if strict:
            pattern = (
                r"(?<![A-Za-z0-9])" + re.escape(str(value).strip())
                + r"(?![A-Za-z0-9])"
            )

            if hazard:
                pattern = (
                    r"(?<![A-Za-z0-9])(?i:" + CONNECTORS + r"\s+" + BETWEEN_WORDS + r")"
                    + r"(?P<value>" + re.escape(str(value).strip()) + r")(?![A-Za-z0-9])"
                )

            return re.search(pattern, original_text)

        pattern = r"(?<![a-z0-9])" + re.escape(clean) + r"(?![a-z0-9])"

        return re.search(pattern, lower_text)

    # Longest first, so "Credit Card" wins over "Card"
    for candidate in sorted(candidates, key=lambda c: -len(c[0])):

        clean, column, value, strict, hazard = candidate

        match = hits(candidate, original, text)

        if match:

            found.setdefault(column, []).append(value)

            # the same word may ALSO be a value of another column
            # ("Other" in channel and in gender): report every owner
            for other in candidates:
                if other[0] == clean and other[1] != column and hits(
                    other, original_start, text_start
                ):
                    if other[2] not in found.get(other[1], []):
                        found.setdefault(other[1], []).append(other[2])

            # blank ONLY the value (not the words that led up to it)
            start, end = (
                match.span("value") if "value" in match.re.groupindex
                else match.span()
            )
            blank = " " * (end - start)

            text = text[:start] + blank + text[end:]
            original = original[:start] + blank + original[end:]

    # "defaulted loans", "returns": a word that is a FORM of a value
    # ("Default", "Return") names that value
    single = {}
    for candidate in candidates:
        clean, column, value, strict, hazard = candidate
        if not hazard and not strict and " " not in clean and len(clean) >= 4:
            single.setdefault(clean, []).append((column, value))

    for token in re.findall(r"[a-z]{5,}", text):
        for form in word_forms(token) - {token}:
            for column, value in single.get(form, []):
                if value not in found.get(column, []):
                    found.setdefault(column, []).append(value)

    return found


def parse_top_n(question):
    """'top 3', '5 best', 'bottom five' -> 3, 5, 5.  None if not asked."""

    text = question.lower()

    number = r"(\d+|" + "|".join(NUMBER_WORDS) + r")"

    for pattern in [
        rf"\b{RANK_WORDS}\s+{number}\b",
        rf"\b{number}\s+{RANK_WORDS}\b",
    ]:

        match = re.search(pattern, text)

        if match:

            raw = match.group(1)
            value = int(raw) if raw.isdigit() else NUMBER_WORDS[raw]

            if 2 <= value <= 20:
                return value

    return None


CONDITION_WORDS = {
    "above", "over", "below", "under", "more", "less", "than", "greater",
    "higher", "lower", "fewer", "least", "most", "between", "and", "to",
    "days", "day", "units", "unit", "percent", "k",
}


def looks_like_condition(value):
    """'7', '10%', 'above 10%', 'more than 7 days' -> a number condition."""

    text = str(value).lower()

    if not re.search(r"\d", text):
        return False

    return all(word in CONDITION_WORDS for word in re.findall(r"[a-z]+", text))


def date_tokens(date_filter):
    """The ways a date from the question may be written as a 'filter'."""

    tokens = {date_filter["label"].lower()}

    if date_filter.get("year"):
        tokens.add(str(date_filter["year"]))

    if date_filter.get("month"):
        tokens.add(MONTH_NAMES[date_filter["month"] - 1].lower())

    if date_filter.get("quarter"):
        tokens.add(f"q{date_filter['quarter']}")

    return tokens


def parse_date_filter(question, date_columns, years, hint_text=""):
    """
    'in September 2024' / 'in 2024' / 'Q1 2024' -> a date filter.
    Returns (date_filter or None, problem message or None).
    """

    if not date_columns:
        return None, None

    text = question.lower()

    if RELATIVE_DATE_PATTERN.search(text):

        return None, (
            "Relative dates like 'last month' or 'this year' are not "
            "supported yet. Please name the month and year, for example "
            "'September 2024'."
        )

    year = None
    month = None
    quarter = None

    # A year only counts if it is close to the years in the data
    # (so "orders above 2000" is not read as the year 2000)
    for match in re.finditer(r"\b((?:19|20)\d{2})\b", text):

        candidate = int(match.group(1))

        if not years or min(years) - 3 <= candidate <= max(years) + 3:
            year = candidate
            break

    for name, number in MONTHS.items():

        if re.search(rf"\b{name}\b", text):
            month = number
            break

    # "may" is also an everyday word
    if month is None and re.search(
        r"\b(?:in|during|for|of|since|from)\s+may\b|\bmay\s+(?:19|20)\d{2}\b",
        text
    ):
        month = 5

    match = re.search(r"\bq([1-4])\b", text)

    if match:
        quarter = int(match.group(1))

    else:

        ordinal = {"first": 1, "second": 2, "third": 3, "fourth": 4}

        match = re.search(r"\b(first|second|third|fourth)\s+quarter\b", text)

        if match:
            quarter = ordinal[match.group(1)]

    # "March 2031" / "in 2031": an explicit year, even outside the data
    if year is None:

        match = re.search(
            r"\b(?:in|during|for|of|year)\s+((?:19|20)\d{2})\b", text
        )

        if match is None and (month or quarter):
            match = re.search(r"\b((?:19|20)\d{2})\b", text)

        if match:
            year = int(match.group(1))

    if year is None and month is None and quarter is None:
        return None, None

    parts = []

    if month:
        parts.append(MONTH_NAMES[month - 1])

    if quarter:
        parts.append(f"Q{quarter}")

    if year:
        parts.append(str(year))

    needs_year = (month or quarter) and year is None and len(years) > 1

    return {
        "column": pick_date_column(question + " " + hint_text, date_columns),
        "year": year,
        "month": month,
        "quarter": quarter,
        "label": " ".join(parts),
        "needs_year": bool(needs_year),
    }, None


COMPARATORS = [
    (r"(?:greater than or equal to|more than or equal to|equal to or more than|"
     r"equal to or greater than|at least|not less than|no less than|"
     r"not below|not under)", ">="),
    (r"(?:less than or equal to|equal to or less than|equal to or smaller than|"
     r"at most|not more than|no more than|not above|not over|not exceeding|"
     r"up to)", "<="),
    (r"(?<!not )(?<!no )(?:above|over|greater than|more than|higher than|"
     r"bigger than|larger than|exceeding|exceeds)", ">"),
    (r"(?<!not )(?<!no )(?:below|under|less than|lower than|fewer than|"
     r"smaller than)", "<"),
]

# a number as people write it: -44, $1,200, ₹5,00,000, 12.5%, 3k, 5 lakh, 2 crore
CURRENCY = "$₹€£"
MINUS = "-−"
NUMBER = (
    rf"[{CURRENCY}]?\s?([{MINUS}]?\s?[{CURRENCY}]?\d[\d,]*(?:\.\d+)?)"
    r"(?:\s?(%|k\b|percent\b|per cent\b|thousand\b|lakhs?\b|lacs?\b|crores?\b|"
    r"cr\b|million\b|mn\b|billion\b|bn\b)|(?![a-z0-9]))"
)


def valid_number_text(raw):
    """'5,00,000' and '1,200,000' are numbers; '1,0' is not (never guess)."""

    core = re.sub(rf"[{CURRENCY}{MINUS}\s]", "", str(raw))

    if "," not in core:
        return True

    return bool(
        re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", core)
        or re.fullmatch(r"\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d+)?", core)
    )

MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5,
    "lacs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7, "million": 1e6,
    "mn": 1e6, "billion": 1e9, "bn": 1e9,
}

NUMBER_WORD_PATTERN = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    r"thousand|million|billion|lakh|crore)"
)


def column_positions(question, columns):
    """(start position, column) for every column named in the question."""

    text = question.lower()
    found = []

    for column in sorted(columns, key=lambda c: -len(str(c))):

        match = re.search(column_pattern(column), text)

        if match:
            found.append((match.start(), column))
            blank = " " * (match.end() - match.start())
            text = text[:match.start()] + blank + text[match.end():]

    return sorted(found, key=lambda x: x[0])


STEM_STOP = {
    "what", "many", "orders", "order", "took", "more", "than", "with",
    "have", "from", "that", "this", "were", "there", "above", "below",
    "over", "under", "least", "most", "into", "does", "each", "total",
    "average", "number", "count", "show", "give", "which", "where",
    "when", "made", "placed", "received", "highest", "lowest", "about",
}


def word_stems(text):
    return {
        word[:5]
        for word in re.findall(r"[a-z]+", text.lower())
        if len(word) >= 4 and word not in STEM_STOP
    }


DATE_SYNONYMS = {
    "left": "termination exit", "leave": "termination exit", "leaving": "termination exit",
    "resigned": "termination exit", "quit": "termination exit", "fired": "termination",
    "terminated": "termination", "exited": "exit termination", "attrited": "termination",
    "hired": "hire", "recruited": "hire", "joined": "join hire signup start",
    "joining": "join hire start", "started": "start hire", "onboarded": "hire join",
    "signed": "signup", "registered": "signup register", "subscribed": "signup",
    "churned": "churn cancel", "cancelled": "cancel churn", "canceled": "cancel churn",
    "delivered": "delivery deliver", "arrived": "delivery arrival", "received": "delivery received",
    "shipped": "ship dispatch", "dispatched": "ship dispatch", "sent": "ship",
    "ordered": "order", "purchased": "order purchase", "bought": "order purchase",
    "originated": "origination", "disbursed": "origination", "issued": "issue origination",
    "approved": "approval", "closed": "close end", "ended": "end termination",
    "paid": "payment paid", "due": "due",
}


# ------------------------------------------------------------
# Never silently ignore a word: if part of the question cannot be mapped to
# the data, say so instead of answering a simpler question
# ------------------------------------------------------------

FILLER_WORDS = set("""
a about above across after again against all also am an and any are as at be because been before
being below between both but by can could did do does doing done down during each either else ever
every few for from further get gets give given go goes going got had has have having he her here
hers him his how i if in into is it its just let like many may me might more most much must my no
nor not now of off on once one only or other our out over own per please same shall she should
since so some such than that the their them then there these they this those through to too under
until up upon us very was we were what when where which while who whom whose why will with within
without would yet you your yours
tell show list display see find know want need calculate compute work provide report check look
overall total sum combined altogether average mean avg maximum minimum max min highest lowest
biggest smallest largest greatest top bottom best worst first last rank ranked
ranking number count counts amount amounts value values figure figures
percent percentage share rate ratio proportion fraction
month months monthly year years yearly quarter quarters week weeks day days date dates time period
different distinct unique separate
made make makes making brought bring brings generate generated
generates placed received recorded created processed completed shipped delivered ordered sold
purchased bought booked handled taken
group groups category categories type types kind kinds each
performing performance performed perform performs
data dataset file table column columns row rows record records entry entries
good high low big small large
split breakdown broken
average avg mean typical usual
overall entire whole altogether full
people persons person items item things thing stuff
active inactive current currently
id ids identifier identifiers
sell sells selling seller sellers buy buys buyer buyers place places took take takes
deliver delivers receive receives receiving single performer performers
use used using need needed
""".split())

def cue_patterns():
    """The engine's own vocabulary (looked up when needed: they are defined further down)."""

    return (
        ASKS_ENTITY, AVG_CUE, AVG_WORDS, BOTTOM_PATTERN, COUNT_CUE, COUNT_RANK_WORDS,
        DISTINCT_CUE, DUPLICATE_CUE, LIST_WORDS, MAX_CUE, MIN_CUE,
        MISSING_CUE, QUANTITY_WORDS, RANK_ANY, RANK_CUE, TOP_PATTERN,
        TOTAL_CUE, TREND_CUE, UNIQUE_EVIDENCE_WORDS,
    )

# quantities that are NOT the thing counted: "cost per kg" is a ratio
UNIT_WORDS = {
    "unit", "units", "kg", "kilogram", "kilograms", "km", "kilometre", "kilometer",
    "mile", "miles", "hour", "hours", "click", "clicks", "impression", "impressions",
    "seat", "seats", "user", "users", "item", "items", "sqft", "square", "litre", "liter",
}


def word_forms(word):
    """'returned' / 'returns' / 'returning' -> {'return', ...}."""

    forms = {word}

    for suffix in ("ing", "ed", "es", "s", "ly"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            forms.add(word[:-len(suffix)])

    if word.endswith("ies") and len(word) > 4:
        forms.add(word[:-3] + "y")

    if word.endswith("ied") and len(word) > 4:
        forms.add(word[:-3] + "y")

    return forms


def unmapped_words_problem(plan, question, profile, columns, dimension_values):
    """
    Words of the question that map to nothing in the data and to no known
    analytic word ("left the company", "made a loss", "profit margin") would
    be dropped silently, and the answer would be for a SIMPLER question.
    """

    known = set(FILLER_WORDS)

    for column in columns:
        for word in re.findall(r"[a-z0-9]+", readable_label(column)):
            known |= word_forms(word)

        # ...and the name exactly as written in the file ("BusinessUnit")
        for word in re.findall(r"[a-z0-9]+", str(column).lower()):
            known |= word_forms(word)

    for values in dimension_values.values():
        for value in values:
            for word in re.findall(r"[a-z0-9]+", str(value).lower()):
                known |= word_forms(word)

    for noun in list(profile.get("row_nouns", [])) + list(BASE_ROW_NOUNS):
        known |= word_forms(noun)

    for name in MONTHS:
        known.add(name)

    text_lower = question.lower()

    # "hired in 2019", "signed up in March": the verb names a DATE column
    if re.search(r"\b(?:19|20)\d\d\b|\bq[1-4]\b", text_lower) or any(
        re.search(rf"\b{m}\b", text_lower) for m in MONTHS
    ):
        known |= set(DATE_SYNONYMS)

    known |= {"come", "comes", "came", "coming"}

    has_revenue = bool(profile.get("revenue_column"))

    row_nouns = {n for noun in list(profile.get("row_nouns", [])) + list(BASE_ROW_NOUNS) for n in word_forms(noun)}

    text = question.lower()

    # "paid with COD", "paid by credit card": a payment method, not a status
    text = re.sub(r"\b(?:paid|pay|payed)\s+(?:with|by|using|via|through)\b", " ", text)

    # "cost per kg", "revenue per unit": a ratio between two quantities
    measure_words = {
        w for measure in profile.get("measures", [])
        for w in re.findall(r"[a-z0-9]+", readable_label(measure))
    }

    for match in re.finditer(r"\bper\s+([a-z]+)", text):

        word = match.group(1)

        if (word in UNIT_WORDS or word in measure_words) and not (word_forms(word) & row_nouns):
            return (
                f"'per {word}' is a ratio between two quantities (like cost per "
                f"{word}), which I do not calculate yet. You can ask for the "
                f"two totals separately."
            )

    # "the share of X that CAME FROM Y" with a Yes/No flag: which is the whole?
    if re.search(r"\b(?:came|come|comes|coming)\s+from\b", text) and any(
        {str(v).strip().lower() for v in dimension_values.get(f["column"], [])} <= {"yes", "no", "true", "false", "y", "n", "0", "1"}
        for f in plan.get("filters") or []
    ):
        return (
            "That could mean two different percentages (the share of one "
            "group within the other, or the other way round). Please ask "
            "for one, for example 'what percentage of Electronics orders "
            "were returned'."
        )

    leftover = []

    for token in re.findall(r"[a-z]+", text):

        if len(token) < 3 or token in leftover:
            continue

        if word_forms(token) & known:
            continue

        if any(pattern.search(token) for pattern in cue_patterns()):
            continue

        # money words ("revenue", "sales", "cost", "profit") mean something
        # only if the data has such a number column
        if has_revenue and (REVENUE_WORDS.search(token) or MEASURE_WORDS.search(token)):
            continue

        # "growth", "change": a trend question may use them, nothing else
        if plan.get("intent") == "trend" and TREND_WORDS.search(token):
            continue

        leftover.append(token)

    if leftover:
        shown = "', '".join(leftover[:3])
        return (
            f"I could not match '{shown}' to anything in your data, so I would "
            f"be answering a different question than the one you asked. "
            f"Please rephrase using the column names or values of your data."
        )

    return None


def date_scores(text, dates):
    """How well each date column's name fits the words of the question."""

    words = word_stems(text)

    # the verb names the date: "left in 2024" -> the termination date
    extra = " ".join(DATE_SYNONYMS.get(w, "") for w in re.findall(r"[a-z]+", text.lower()))
    words = words | word_stems(extra)

    return {
        column: len(
            words
            & word_stems(re.sub(r"([a-z])([A-Z])", r"\1 \2", label_of(column)))
        )
        for column in dates
    }


def pick_date_column(text, dates):
    """'Training Cost in 2023' -> the Training Date column."""

    if not dates:
        return None

    scores = date_scores(text, dates)

    return max(dates, key=lambda column: scores[column])


def guess_measure(words_text, measures):
    """The one number column whose name shares a word with the text."""

    words = word_stems(words_text)

    best, best_score, tie = None, 0, False

    for measure in measures:

        score = len(words & word_stems(label_of(measure)))

        if score > best_score:
            best, best_score, tie = measure, score, False

        elif score == best_score and score > 0:
            tie = True

    return best if best_score > 0 and not tie else None


def parse_conditions(question, measures, numeric_max, fallback_column):
    """
    'above 2000', 'at least 5', 'between 10 and 50' -> number conditions.
    Returns (conditions, problem message or None).
    """

    text = question.lower()

    if re.search(
        r"\b(?:above|below|over|under|more than|less than|greater than|"
        r"higher than|lower than)\s+(?:the\s+)?(?:average|mean|median)\b",
        text
    ):
        return [], (
            "Comparisons with the average (like 'above average') are not "
            "supported yet. Please give a number, for example 'above 500'."
        )

    comparators = "|".join(pattern for pattern, _ in COMPARATORS)

    # a comparison followed by a number written in WORDS: never guess
    if re.search(rf"\b(?:{comparators})\s+{NUMBER_WORD_PATTERN}\b", text):
        return [], (
            "Please write the number with digits, for example 'above 500', "
            "so that I do not have to guess."
        )

    found = []   # (position, operator, number, suffix, number2, end)

    for match in re.finditer(
        rf"\bbetween\s+{NUMBER}\s+and\s+{NUMBER}", text
    ):
        found.append((match.start(), "between", match.group(1),
                      match.group(2), match.group(3), match.end()))

    for pattern, operator in COMPARATORS:

        for match in re.finditer(rf"\b{pattern}\s+{NUMBER}", text):

            found.append((match.start(), operator, match.group(1),
                          match.group(2), None, match.end()))

    # a comparison with a number-like text that could NOT be read is never
    # ignored silently (that would answer a different question)
    comparisons_seen = len(re.findall(
        rf"\b(?:{comparators})\s+[{MINUS}{CURRENCY}]?\s?\d", text
    )) + len(re.findall(rf"\bbetween\s+[{MINUS}{CURRENCY}]?\s?\d", text))

    leftover = re.sub(rf"\b(?:{comparators})\s+{NUMBER}", " ", text)
    leftover = re.sub(rf"\bbetween\s+{NUMBER}\s+and\s+{NUMBER}", " ", leftover)

    if re.search(
        rf"\b(?:exactly|equals?|equal to|equal)\s+[{MINUS}{CURRENCY}]?\s?\d", leftover
    ):
        return [], (
            "Exact matches (like 'exactly 5') are not supported yet. Please "
            "ask with above, below, at least or at most."
        )

    for _, _, number, _, number2, _ in found:
        for raw in (number, number2):
            if raw and not valid_number_text(raw):
                return [], (
                    f"I could not read '{raw.strip()}' as a number. Please "
                    f"write it plainly, for example 'above 500' or "
                    f"'above 5,00,000'."
                )

    if comparisons_seen > len(found):
        return [], (
            "I found a comparison with a number in your question but could "
            "not read the number safely. Please write it plainly, for "
            "example 'above 500' or 'below -20'."
        )

    if not found:
        return [], None

    positions = column_positions(question, measures)

    conditions = []

    for start, operator, number, suffix, number2, end in sorted(found):

        # "10 percent" means the same as "10%"
        if suffix and suffix.startswith("per"):
            suffix = "%"

        number = number.replace("−", "-").replace(" ", "")
        number2 = number2.replace("−", "-").replace(" ", "") if number2 else number2

        # 1. The unit word after the number: "more than 7 days"
        unit_match = re.match(r"\s*([a-z]+)", text[end:])
        unit = unit_match.group(1) if unit_match else ""

        column = None

        if unit:
            column = guess_measure(unit, measures)

        # 2. The number column named just before the comparison
        if column is None:

            before = [col for pos, col in positions if pos < start]

            if before:
                column = before[-1]
            elif positions:
                column = positions[0][1]

        # 3. The column the AI chose, or a word match in the question
        if column is None:
            column = fallback_column or guess_measure(text, measures)

        if column is None:
            return [], (
                f"I could not tell which number column to compare with "
                f"{number}. Please name the column, for example "
                f"'total amount above {number}'."
            )

        space = " " if suffix and suffix[0].isalpha() else ""
        shown_one = number.lstrip(CURRENCY) + space + (suffix or "")
        shown_two = (number2 or "").lstrip(CURRENCY) + space + (suffix or "")

        def scaled(raw, mark, column=column):

            cleaned = raw.replace(",", "")

            for symbol in CURRENCY:
                cleaned = cleaned.replace(symbol, "")

            value = float(cleaned)

            if mark in MULTIPLIERS:
                value *= MULTIPLIERS[mark]

            # "10%" on a column that holds fractions (0.10)
            if mark == "%" and numeric_max.get(column, 100) <= 1:
                value /= 100

            return value

        if operator == "between":

            conditions.append({
                "column": column, "op": ">=",
                "value": scaled(number, suffix),
                "label": (
                    f"where {label_of(column)} is between "
                    f"{shown_one} and {shown_two}"
                ),
            })
            conditions.append({
                "column": column, "op": "<=",
                "value": scaled(number2, suffix),
                "label": "",
            })

        else:

            conditions.append({
                "column": column, "op": operator,
                "value": scaled(number, suffix),
                "label": (
                    f"where {label_of(column)} is "
                    f"{OPERATOR_WORDS[operator]} {shown_one}"
                ),
            })

    return conditions, None


def closest_column(name, columns):
    """Find the real column that a wrong/near name was meant to be."""

    lowered = {column.lower(): column for column in columns}

    key = str(name).strip().lower().replace(" ", "_")

    if key in lowered:
        return lowered[key]

    # A whole word of exactly ONE column name
    # ("customer" -> "customer_name", "category" -> "product_category")
    singular = key[:-1] if key.endswith("s") else key

    word_matches = [
        column
        for lowered_name, column in lowered.items()
        if key in lowered_name.split("_")
        or singular in lowered_name.split("_")
    ]

    if len(word_matches) == 1:
        return word_matches[0]

    matches = difflib.get_close_matches(
        key, list(lowered), n=1, cutoff=0.75
    )

    if matches:
        return lowered[matches[0]]

    return None


# ------------------------------------------------------------
# Questions the app cannot answer correctly YET
# (it must say so, never answer with a nearby number)
# ------------------------------------------------------------

RATIO_WORDS = r"\b(percentage|percent|per cent|share|proportion|ratio|fraction|rate)\b"
EXTREME_WORDS = (
    r"\b(highest|lowest|best|worst|top|bottom|most|least|peak|"
    r"strongest|weakest|biggest|smallest)\b"
)


def readable_label(column):
    """'DiscountPercent (₹)' / 'discount_percent' -> 'discount percent'."""

    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", str(column))
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    spaced = re.sub(r"[^A-Za-z0-9 ]+", " ", spaced.replace("_", " "))

    return re.sub(r"\s+", " ", spaced).lower().strip()


def without_values(text, filters):
    """The question without the filter values it names: 'Sales' (a department)
    is a value there, not the word for revenue."""

    for item in filters or []:

        value = str(item.get("value", "")).strip().lower()

        if len(value) >= 2:
            text = re.sub(
                r"(?<![a-z0-9])" + re.escape(value) + r"(?![a-z0-9])", " ", text
            )

    return text


def ratio_names_column(text, word, labels):
    """
    Is the word 'percentage' part of a COLUMN NAME that is written in the
    question ("discount percentage")? Only then it is not a ratio request.
    """

    if isinstance(labels, str):
        return word in labels

    return any(
        word in label.split()
        and re.search(r"(?<![a-z0-9])" + re.escape(label) + r"(?![a-z0-9])", text)
        for label in labels
    )


TIME_WORDS = re.compile(
    r"\b(?:in|during|for|of|since|from|before|after|year)\s+(?:19|20)\d{2}\b|"
    r"\b(?:january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\s+(?:19|20)\d{2}\b|\bq[1-4]\s+(?:19|20)\d{2}\b"
)


def asks_ratio(question, column_labels):
    """True for 'what percentage / share / rate ...' questions."""

    ratio_text = re.sub(
        r"\d[\d,.]*\s*(?:%|percent|per cent)", " ", question.lower()
    )

    ratio = re.search(RATIO_WORDS, ratio_text) or re.search(
        r"\bwhat\s*%", ratio_text
    )

    if not ratio:
        return False

    word = ratio.group(1) if ratio.groups() else "%"

    return not ratio_names_column(ratio_text, word, column_labels)


def find_unsupported_phrase(question, plan, column_labels, label_list=()):
    """Returns a helpful 'not supported yet' message, or None."""

    text = question.lower()

    # words that are PART OF A COLUMN NAME ("annual income", "Monthly Salary",
    # "weekly sales") are not time words
    time_free = text
    for label in sorted(label_list, key=len, reverse=True):
        if label:
            time_free = time_free.replace(label, " ")

    if re.search(
        r"\b(forecast\w*|predict\w*|projection\w*|projected|what\s+if|"
        r"what\s+would|what\s+will|will\s+be|going\s+to\s+be|expected\s+to|"
        r"estimate[sd]?|simulat\w*|scenarios?|"
        r"if\s+(?:we|i|you)\s+(?:increase|decrease|raise|cut|reduce|add|remove|"
        r"double|halve|stop|start|change|drop|lower)|"
        r"next\s+(?:month|quarter|year|week)|(?:in|over)\s+the\s+(?:next|coming)|"
        r"project\s+\w+\s+for)\b", text
    ):
        return (
            "I can only calculate from the data you have. I cannot predict "
            "the future or run what-if scenarios."
        )

    if re.search(
        r"\b(month|months)\s+of\s+the\s+year\b|"
        r"\bacross\s+(?:all\s+)?(?:the\s+)?years\b|\bcalendar\s+(?:month|year)\b|"
        r"\b(?:per|each|every|a)\s+(?:day|week)\b|\bdaily\b|\bweekly\b", time_free
    ):
        return (
            "Calendar patterns (month of the year, per day, per week) are not "
            "supported yet. You can ask for the monthly totals instead."
        )

    if re.search(
        r"\b(median|standard deviation|stdev|variance|percentiles?|"
        r"quartiles?|correlat\w*|outliers?|anomal\w*)\b", text
    ):
        return (
            "Statistics like median, standard deviation, correlation or "
            "outliers are not supported yet. You can ask for the "
            "average, minimum or maximum instead."
        )

    if re.search(
        r"\b(weekday|weekdays|day of the week|days of the week|weekend|"
        r"weekends|hour of the day|time of day)\b", text
    ):
        return (
            "Patterns by weekday or hour are not supported yet. You can "
            "ask for monthly totals instead."
        )

    if re.search(
        r"\b(repeat|returning|loyal)\s+(customers?|buyers?|users?)\b|"
        r"\bmore than once\b|\bmultiple orders\b|\btwice\b|"
        r"\b(more than|over|at least)\s+(one|1|two|2|a single)\s+"
        r"(order|orders|purchase|purchases|time|times)\b", text
    ):
        return (
            "Repeat-customer questions are not supported yet. You can ask "
            "how many unique customers there are, or who spent the most."
        )

    def per_entity():
        """'revenue per customer' (a ratio), but not 'in each customer gender'."""

        for match in re.finditer(
            r"\b(per|for each|each)\s+(customer|client|buyer|user|product)\b"
            r"(?!\s*(?:id|name)s?\b)(?:\s+([a-z]+))?", text
        ):
            entity, following = match.group(2), match.group(3)

            if following and f"{entity} {following}" in column_labels.lower():
                continue

            return True

        return False

    if per_entity() and not re.search(r"\b(by|per|each|every|across)\s+(customer|product)\s+(id|name)", text):
        return (
            "Ratios like 'revenue per customer' are not supported yet. "
            "Ask for the total revenue and the number of customers "
            "separately."
        )

    if re.search(
        r"\b(average|avg|mean)\s+(daily|weekly|quarterly|yearly|annual)\b",
        time_free
    ):
        return (
            "Averages per day, week, quarter or year are not supported yet. "
            "Ask for the monthly totals and read the average from them."
        )

    return None


# ------------------------------------------------------------
# New question types, recognised by code
# ------------------------------------------------------------

GROUP_PHRASE = re.compile(
    rf"\b{BY_WORDS}\s+(?:the\s+)?([a-z][a-z]+(?:\s+[a-z]+){{0,2}})"
)

NOT_A_GROUP = {
    "month", "year", "quarter", "week", "day", "date", "time", "hour",
    "order", "item", "unit", "row", "record", "transaction", "purchase",
    "entry", "total", "average", "number", "count", "sale", "customer",
    "client", "product", "monthly", "weekly", "daily", "yearly",
}


def find_group_columns(text, ctx):
    """
    The columns the question groups by.
    "by category" and also loosely typed "by department"
    (DepartmentType) are both understood.
    """

    main_map = ctx["main_map"]

    exact = []

    for column in ctx["named_dims_raw"]:

        if re.search(rf"\b{BY_WORDS}\s+(?:the\s+)?{column_pattern(column)}", text):
            exact.append(main_map.get(column, column))

    exact = list(dict.fromkeys(exact))

    if exact:
        return exact

    # loosely typed: match the words after "by" to a column's name
    candidates = [
        c for c in ctx["profile"].get("dimension_values", {})
        if c not in ctx["profile"].get("identifier_columns", [])
    ]

    for match in GROUP_PHRASE.finditer(text):

        words = [w for w in match.group(1).split() if w not in NOT_A_GROUP]

        stems = word_stems(" ".join(words))

        if not stems:
            continue

        fits = [
            c for c in candidates
            if stems <= word_stems(re.sub(r"([a-z])([A-Z])", r"\1 \2", label_of(c)))
        ]

        # a column and its first-level twin are the same thing here
        fits = list(dict.fromkeys(main_map.get(c, c) for c in fits))

        if len(fits) == 1:
            ctx["notes"].append(f"'by {match.group(1)}' read as {fits[0]!r}")
            return fits

    return []

LIST_START = re.compile(
    r"^\s*(?:please\s+|can you\s+|could you\s+)?"
    r"(?:list|name|enumerate|show(?:\s+me)?|give(?:\s+me)?|tell\s+me|what|which)\b"
)
LIST_WORDS = re.compile(
    r"\b(list|name|enumerate|all|every|different|distinct|unique|are there|"
    r"do we have|have we got|exist|available|kinds?|types?|what are the|"
    r"which are the)\b"
)
LIST_BLOCK = re.compile(
    r"\b(by|per|each|average|avg|mean|total|sum|share|percent\w*|rate|top|"
    r"best|worst|highest|lowest|most|least|biggest|smallest|trend|monthly|"
    r"how many|number of|count|compare|versus|vs)\b"
)


def detect_ratio(text, ctx, by_dims):
    """
    "profit as a percent of revenue" or "profit percent":
    (numerator, denominator), "by_group", or None.
    """

    used = {item["column"] for item in ctx["conditions"]}
    named = [c for c in ctx["named_measures"] if c not in used]

    explicit = re.search(
        r"\b(?:as|of)\s+(?:a\s+|an\s+)?(?:percent|percentage|share|proportion|"
        r"fraction|ratio)\s+(?:of|to)\b|\bdivided by\b|\bper\s*cent\s+of\b",
        text,
    )

    pair = None

    if len(named) >= 2 and explicit:
        pair = (named[0], named[1])

    else:

        profit_columns = [m for m in ctx["measures"] if "profit" in str(m).lower()]
        revenue = ctx["profile"].get("revenue_column")

        alias = re.search(
            r"\bprofit\s+(?:margin\s+)?(?:percent|percentage|per cent|%|ratio)|"
            r"\b(?:percent|percentage|%)\s+profit\b|"
            r"\bprofit\s+margin\s+(?:overall|in total)",
            text,
        )

        if (
            alias and len(profit_columns) == 1 and revenue
            and revenue != profit_columns[0]
            and not (set(named) - {profit_columns[0], revenue})
        ):
            pair = (profit_columns[0], revenue)

    if pair is None:
        return None

    return "by_group" if by_dims else pair


def detect_metrics(plan, question, ctx):
    """
    Turns the plan into a group table, a share (percent), a ranking by
    count/average, or a best/average month when the WORDS of the question
    ask for it. Returns a problem message, or None.
    """

    text = question.lower()
    intent = plan["intent"]
    notes = ctx["notes"]
    measures = ctx["measures"]
    dates = ctx["dates"]
    named_dims = ctx["named_dims"]
    revenue_column = ctx["profile"].get("revenue_column")
    used = {item["column"] for item in ctx["conditions"]}

    # "Sales" in "employees in Sales" is a value, not the word for revenue
    value_free = without_values(text, ctx["filters"])

    # "average Monthly Salary" / "mrr for Monthly": a column or value NAMED
    # monthly is not a request for months
    time_text = text
    for named_column in ctx["named_all"]:
        time_text = re.sub(column_pattern(named_column), " ", time_text)
    time_text = without_values(time_text, ctx["filters"])

    def pick_value():
        """The number column this question is about."""

        value = plan["value_column"]

        asked = [c for c in ctx["named_measures"] if c not in used]

        if asked:
            return asked[0]

        if REVENUE_WORDS.search(value_free) and revenue_column:
            return revenue_column

        return value if value in measures else None

    asks_extreme = bool(TOP_PATTERN.search(text) or BOTTOM_PATTERN.search(text))
    measure_asked = bool(
        REVENUE_WORDS.search(value_free)
        or [c for c in ctx["named_measures"] if c not in used]
    )

    # ---------------- "which categories are there?": the different values
    if (
        len(named_dims) == 1 and not measure_asked and not asks_extreme
        and LIST_START.search(text) and LIST_WORDS.search(text)
        and not LIST_BLOCK.search(text) and not ctx["conditions"]
    ):

        plan.update(
            intent="unique", operation="unique", column=named_dims[0],
            value_column=named_dims[0], group_column=None, agg=None,
        )
        notes.append(f"question asks which {named_dims[0]} values exist")
        return None

    # ---------------- best month / average month
    month_extreme = (
        re.search(r"\b(which|what)\s+month\b", time_text)
        and re.search(EXTREME_WORDS, time_text)
    )
    month_average = MONTH_AVG_PATTERN.search(time_text)

    if dates and (month_extreme or month_average):

        value = pick_value()

        if value is None:
            return (
                "Which number should I use per month? Please name it, for "
                "example 'highest total amount per month'."
            )

        if month_average and not month_extreme:
            pick = "mean"
        elif BOTTOM_PATTERN.search(text) and not TOP_PATTERN.search(text):
            pick = "min"
        else:
            pick = "max"

        plan.update(
            intent="month_pick", pick=pick, value_column=value,
            column=value, agg="sum",
            group_column=pick_date_column(text + " " + value, dates),
        )
        notes.append(f"month question: {pick} of monthly {value}")
        return None

    # ---------------- "monthly revenue", "revenue by month", "over time"
    trend_cue = re.search(
        r"\b(monthly|by month|per month|each month|month by month|"
        r"month over month|over time|trend)\b", time_text
    )

    if dates and trend_cue and intent in [
        "total", "average", "maximum", "minimum"
    ]:

        if intent != "total":
            return (
                "Monthly averages, highest or lowest values are not "
                "supported yet. Ask for the monthly totals instead, for "
                "example 'show me monthly total amount'."
            )

        value = pick_value()

        if value is None:
            return (
                "Which number should I show per month? Please name it, "
                "for example 'monthly total amount'."
            )

        plan.update(
            intent="trend", operation="time_series", value_column=value,
            column=value,
            group_column=pick_date_column(text + " " + value, dates),
        )
        notes.append("monthly question -> trend over time")
        return None

    # ---------------- percentages and shares
    ratio_text = re.sub(r"\d[\d,.]*\s*(?:%|percent|per cent)", " ", text)
    ratio = re.search(RATIO_WORDS, ratio_text) or re.search(
        r"\bwhat\s*%", ratio_text
    )

    ratio_word = ratio.group(1) if ratio and ratio.groups() else "%"

    by_dims = find_group_columns(text, ctx)

    if ratio and not ratio_names_column(
        ratio_text, ratio_word, ctx.get("column_label_list") or ctx["column_labels"]
    ):

        pair = detect_ratio(text, ctx, by_dims)

        if pair == "by_group":
            return (
                "A percentage of one number column over another, split by "
                "group, is not supported yet. Ask for the overall ratio, or "
                "the two numbers by group separately."
            )

        if pair:
            plan.update(
                intent="share", agg="sum", value_column=pair[0], column=pair[0],
                ratio_denominator=pair[1], share_group=None, group_column=None,
            )
            notes.append(f"ratio: {pair[0]} as a percent of {pair[1]}")
            return None

        if not ctx["filters"] and not ctx["conditions"]:

            # a yes/no column named without a filter ("return rate"):
            # never turn it into "share of everything"
            yes_no_named = [
                c for c, values in ctx["profile"].get("dimension_values", {}).items()
                if c in ctx["named_all"]
                and {str(v).strip().lower() for v in values} <= YES_NO
            ]

            if yes_no_named:
                return (
                    "I could not tell which rows to take the percentage of "
                    f"for '{label_of(yes_no_named[0])}'. Please rephrase, "
                    "for example 'what percentage of orders were returned'."
                )

            # "revenue share by category": each group's percent of the total
            if len(by_dims) == 1:

                agg = "sum" if measure_asked else "count"
                value = pick_value() if agg == "sum" else None

                if agg == "sum" and value is None:
                    return (
                        "Which number should I take the share of? Please "
                        "name it, for example 'share of total amount by "
                        "category'."
                    )

                plan.update(
                    intent="breakdown", agg=agg, as_percent=True,
                    group_column=by_dims[0], value_column=value,
                    column=value,
                )
                notes.append(f"each {by_dims[0]} as a percent of the total")
                return None

            return (
                "Percent of what? Name what you want the share of, for "
                "example 'share of revenue from Electronics' or 'what "
                "percentage of orders were returned'."
            )

        if len(by_dims) > 1:
            return (
                "I can calculate a percentage for one grouping at a time. "
                "Please name just one."
            )

        agg = "sum" if measure_asked else "count"
        value = pick_value() if agg == "sum" else None

        if agg == "sum" and value is None:
            return (
                "Which number should I take the share of? Please name it, "
                "for example 'share of total amount from Electronics'."
            )

        plan.update(
            intent="share", agg=agg, value_column=value,
            column=value, share_group=by_dims[0] if by_dims else None,
            group_column=None,
        )
        notes.append(f"percentage of {'revenue' if agg == 'sum' else 'rows'}")
        return None

    # ---------------- group table: "revenue by category"
    ranking_same = (
        intent in ["top", "bottom"]
        and asks_extreme
        and len(by_dims) == 1
        and by_dims[0] == plan["group_column"]
    )

    if by_dims and not ranking_same:

        if len(by_dims) > 1:
            return (
                "I can show a table for one grouping at a time. Please "
                "name just one, for example 'revenue by category'."
            )

        group = by_dims[0]

        # "which category ... by region": a ranking inside each group
        if intent in ["top", "bottom"] and asks_extreme:
            return (
                "Ranking inside each group (like 'which category is best "
                f"in each {label_of(group)}') is not supported yet. Ask "
                "for one at a time."
            )

        # "by category and region": a second grouping that would be ignored
        filtered_columns = {item["column"] for item in ctx["filters"]}
        extra = [
            c for c in named_dims
            if c != group and c not in filtered_columns
        ]

        if extra:
            return (
                "I can show a table for one grouping at a time. Your "
                f"question also names {label_of(extra[0])}. Please ask "
                "about one at a time."
            )

        if ctx["count_re"].search(text):
            agg = "count"
        elif measure_asked:
            agg = "mean" if AVG_WORDS.search(text) else "sum"
        elif ctx["noun_re"].search(text) or intent == "count":
            agg = "count"
        else:
            agg = "mean" if AVG_WORDS.search(text) else "sum"

        value = pick_value() if agg != "count" else None

        if agg != "count" and value is None:
            return (
                "Which number should I show by "
                f"{label_of(group)}? Please name it, for example "
                f"'total amount by {label_of(group)}'."
            )

        plan.update(
            intent="breakdown", agg=agg, group_column=group,
            value_column=value, column=value,
        )
        notes.append(f"table by {group} ({agg})")
        return None

    # ---------------- "Which region ...?" with a single number as plan
    which_dim = next(
        (
            ctx["main_map"].get(c, c) for c in ctx["named_dims_raw"]
            if re.search(rf"\b(?:which|what)\s+{column_pattern(c)}", text)
        ),
        None,
    )

    if which_dim and intent in [
        "average", "total", "maximum", "minimum", "count"
    ]:

        bottom = BOTTOM_PATTERN.search(text) and not TOP_PATTERN.search(text)

        plan["intent"] = "bottom" if bottom else "top"
        plan["group_column"] = which_dim
        intent = plan["intent"]

        notes.append(f"'which {which_dim}' needs a ranking -> {intent}")

    # ---------------- the AI invented a ranking nobody asked for
    if (
        intent in ["top", "bottom"]
        and not RANK_CUE.search(text)
        and not parse_top_n(question)
    ):

        value = pick_value()

        if AVG_WORDS.search(text) and value:

            plan.update(
                intent="average", operation="average", group_column=None,
                value_column=value, column=value,
            )
            notes.append("no ranking was asked for -> plain average")
            return None

        return (
            "I could not tell whether you want a ranking or a single "
            "number. Please rephrase, for example 'which category has the "
            "highest total amount' or 'what is the total amount'."
        )

    # ---------------- rankings by count or by average
    if intent in ["top", "bottom"]:

        if COUNT_RANK_WORDS.search(time_text) or ctx["rank_re"].search(time_text):
            plan["agg"] = "count"

        elif AVG_WORDS.search(text):

            plan["agg"] = "mean"

            if plan["value_column"] is None:
                plan["value_column"] = pick_value()

        else:
            plan["agg"] = "sum"

        if plan["agg"] != "count" and plan["value_column"] is None:
            return (
                "Which number should I rank by? Please name it, for "
                "example 'highest total amount'."
            )

        if plan["agg"] != "sum":
            notes.append(f"ranking by {plan['agg']}")

    return None



# ------------------------------------------------------------
# The intent guard: do the WORDS of the question agree with the plan?
# ------------------------------------------------------------

AVG_CUE = re.compile(r"\b(average|avg|mean|typical)\b")
MAX_CUE = re.compile(r"\b(highest|largest|biggest|maximum|max|greatest|peak)\b")
MIN_CUE = re.compile(r"\b(lowest|smallest|minimum|min|least|cheapest|fewest)\b")
TOTAL_CUE = re.compile(r"\b(total|sum|overall|combined|altogether|how much)\b")
COUNT_CUE = re.compile(r"\b(how many|number of|count|how often)\b")
DISTINCT_CUE = re.compile(r"\b(different|distinct|unique)\b")
DUPLICATE_CUE = re.compile(r"\bduplicat\w*")
MISSING_CUE = re.compile(r"\b(missing|null|nulls|blank|empty|n/a)\b")
ASKS_ENTITY = re.compile(r"\b(which|who|rank\w*)\b")
TREND_WORDS = re.compile(
    r"\b(change[sd]?|growth|grow(?:ing|n)?|evolv\w*|progress\w*|history|"
    r"timeline|by (?:year|quarter|week|day)|per (?:year|quarter|week|day)|"
    r"each (?:year|quarter|week|day)|over the (?:year|years|months|period)|"
    r"across (?:months|years|time))\b"
)
UNIQUE_EVIDENCE_WORDS = re.compile(
    r"\b(list|names?|what are|which|show (?:me )?(?:all|every)|all the|"
    r"every|available|types? of|kinds? of)\b"
)
TREND_CUE = re.compile(
    r"\b(monthly|by month|per month|each month|month by month|"
    r"month over month|over time|trend)\b"
)
QUANTITY_WORDS = re.compile(r"\b(units?|items?|pieces?|sold|quantity|quantities)\b")
MEASURE_WORDS = re.compile(
    r"\b(value|amount|worth|revenue|sales|income|turnover|cost|costs|price|"
    r"prices|spend|spent|spending|profit|earnings)\b"
)

SCALAR_INTENTS = ("total", "average", "maximum", "minimum", "count")
SCALAR_OPERATION = {
    "total": "sum", "average": "average", "maximum": "max", "minimum": "min",
}

RANKING_OR_SINGLE = (
    "I could not tell whether you want a ranking or a single "
    "number. Please rephrase, for example 'which category has the "
    "highest total amount' or 'what is the total amount'."
)


def drop_hidden_filters(plan, notes):
    """
    "which returned has ..." / "how many different returned values": the
    yes/no column is what the question is ABOUT. A hidden 'returned = Yes'
    filter (made from the column name alone) would give a wrong answer.
    """

    about = set()

    if plan.get("intent") in ("top", "bottom", "breakdown", "month_pick"):
        about.add(plan.get("group_column"))

    if plan.get("intent") in ("unique", "missing"):
        about.add(plan.get("column"))

    kept = []

    for item in plan.get("filters") or []:

        hidden = str(item.get("label") or "").startswith("where ")

        if hidden and item["column"] in about:
            notes.append(
                f"dropped the filter on '{item['column']}': the question is "
                f"about that column"
            )
            continue

        kept.append(item)

    plan["filters"] = kept


def _guard_core(plan, question, ctx):
    """
    The last safety net. The AI may have picked the wrong calculation
    (total instead of average, a count instead of a total ...). The WORDS
    of the question are checked against the final plan. If they clash:
    repair when the fix is obvious, otherwise refuse. Never guess.
    Returns a problem message or None.
    """

    intent = plan["intent"]

    # "missing values" and "duplicate rows" must be asked for in words
    # ("quantity BELOW 2" is not a question about missing values)
    if intent in ("missing", "duplicate"):

        lowered = question.lower()
        asked = MISSING_CUE if intent == "missing" else DUPLICATE_CUE

        if asked.search(lowered):
            return None

        # the AI picked the wrong one of the two: does the question ask for the other?
        other_cue = DUPLICATE_CUE if intent == "missing" else MISSING_CUE
        other = "duplicate" if intent == "missing" else "missing"

        if other_cue.search(lowered) and (
            COUNT_CUE.search(lowered)
            or re.search(r"\b(any|are there|is there|exist)\b", lowered)
        ):
            plan.update(
                intent=other,
                operation="duplicate_count" if other == "duplicate" else "missing_count",
                column=ctx["named_all"][0] if (other == "missing" and ctx["named_all"]) else None,
                value_column=None, group_column=None,
            )
            ctx["notes"].append(f"the question asks about {other} values, not {intent}")
            return None

        if COUNT_CUE.search(lowered) and (
            ctx["conditions"] or ctx["filters"] or ctx["noun_re"].search(lowered)
        ):
            plan.update(
                intent="count", operation="row_count", column=None,
                value_column=None, group_column=None,
            )
            ctx["notes"].append(
                f"the question does not ask about {intent} values: counting rows"
            )
            return None

        return (
            f"I was not sure what to calculate: the AI chose '{intent}' but "
            "the question does not mention it. Please rephrase, for example "
            "'how many orders have quantity below 2'."
        )

    if intent not in SCALAR_INTENTS + ("unique", "top", "bottom", "trend"):
        return None

    notes = ctx["notes"]
    measures = ctx["measures"]

    # the words of the question, without the column names (so that
    # "total_amount" is not read as the word "total")
    text = question.lower()

    for column in ctx["named_all"]:
        text = re.sub(column_pattern(column), " ", text)

    # "Sales" (a department) is a value, not the word for revenue
    text = without_values(text, ctx["filters"])

    # "at least 3" / "at most 3" are number conditions, not "lowest"/"highest"
    text = re.sub(r"\bat\s+(?:least|most)\b", " ", text)
    plain_question = re.sub(r"\bat\s+(?:least|most)\b", " ", question.lower())

    cue = {
        "avg": bool(AVG_CUE.search(text)),
        "max": bool(MAX_CUE.search(text)),
        "min": bool(MIN_CUE.search(text)),
        "count": bool(COUNT_CUE.search(text)),
        "distinct": bool(DISTINCT_CUE.search(text)),
        "dup": bool(DUPLICATE_CUE.search(text)),
        "missing": bool(MISSING_CUE.search(text)),
        "total": bool(TOTAL_CUE.search(text) or REVENUE_WORDS.search(text)),
    }

    used = {item["column"] for item in ctx["conditions"]}

    def value_column():
        """The number column this question is about, or None."""

        for candidate in (plan["value_column"], plan["column"]):
            if candidate in measures:
                return candidate

        asked = [c for c in ctx["named_measures"] if c not in used]

        if asked:
            return asked[0]

        revenue = ctx["profile"].get("revenue_column")

        if REVENUE_WORDS.search(text) and revenue:
            return revenue

        return None

    def to_scalar(new_intent, why):

        value = value_column()

        if value is None:
            return (
                "Which number should I use? Please name it, for example "
                "'average total amount'."
            )

        plan.update(
            intent=new_intent, operation=SCALAR_OPERATION[new_intent],
            value_column=value, column=value, group_column=None,
        )
        notes.append(why)

        return None

    # ---- the AI chose a RANKING, a TREND or a DISTINCT COUNT: the WORDS of
    # the question must ask for it (the AI may have picked the wrong one)
    if intent in ("top", "bottom", "trend", "unique"):

        top_words = bool(TOP_PATTERN.search(text))
        bottom_words = bool(BOTTOM_PATTERN.search(text))
        asks_ranking = bool(
            parse_top_n(plain_question) or COUNT_RANK_WORDS.search(text)
            or ASKS_ENTITY.search(text)
        )

        if intent in ("top", "bottom"):

            if top_words and bottom_words:
                return (
                    "That asks for the highest AND the lowest at once. Please "
                    "ask them one at a time."
                )

            # the right calculation, the wrong direction: flip it
            if intent == "top" and bottom_words:
                plan["intent"] = "bottom"
                notes.append("the question says lowest, not highest")
                return None

            if intent == "bottom" and top_words:
                plan["intent"] = "top"
                notes.append("the question says highest, not lowest")
                return None

            evidence = top_words or bottom_words or (intent == "top" and asks_ranking)

        elif intent == "trend":
            evidence = bool(TREND_CUE.search(text) or TREND_WORDS.search(text))

        else:
            # "which category has the HIGHEST ..." is a ranking, not a list
            evidence = bool(
                cue["count"] or cue["distinct"]
                or (UNIQUE_EVIDENCE_WORDS.search(text) and not (top_words or bottom_words))
            )

        if not evidence:

            # a ranking question must never be flattened into one number
            if asks_ranking:
                return RANKING_OR_SINGLE

            kinds = [name for name in ("avg", "max", "min") if cue[name]]

            if len(kinds) >= 2:
                return (
                    "That asks for more than one calculation. Please ask "
                    "them one at a time."
                )

            expected = (
                "average" if cue["avg"] else "maximum" if cue["max"]
                else "minimum" if cue["min"] else "total" if cue["total"]
                else None
            )

            if expected:
                return to_scalar(
                    expected,
                    f"the question asks for the {expected}, not the {intent}",
                )

            return (
                f"I was not sure what to calculate: the AI chose '{intent}' "
                "but the question does not ask for it. Please say whether "
                "you want a total, an average, a highest or lowest value, a "
                "ranking, or a trend."
            )

    if intent in ("top", "bottom"):

        # the question says WHAT to rank ("which payment method ..."): the
        # AI may have grouped by another column
        entities = [c for c in ctx["named_all"] if c not in measures]

        # "category" and its clean first-level column are the same thing here
        main_map = ctx["profile"].get("main_columns", {})
        allowed = set(entities) | {main_map.get(c, c) for c in entities}

        if entities and plan["group_column"] not in allowed:

            if len(entities) == 1:
                notes.append(
                    f"the question groups by {entities[0]}, not "
                    f"{plan['group_column']}"
                )
                plan["group_column"] = main_map.get(entities[0], entities[0])
            else:
                return (
                    "I could not tell which column to rank by. Please name "
                    "one column, for example 'which region has the highest "
                    "total amount'."
                )

        return None

    if intent == "trend":
        return None

    # ---- duplicates, missing values, different values
    if cue["dup"] and not (intent == "unique" and cue["distinct"]) and (
        cue["count"] or re.search(r"\b(any|are there|is there|exist)\b", text)
    ):
        plan.update(
            intent="duplicate", operation="duplicate_count", column=None,
            value_column=None, group_column=None,
        )
        notes.append("question asks about duplicate rows")
        return None

    if cue["missing"] and not cue["avg"] and (
        cue["count"] or re.search(r"\b(any|are there|is there)\b", text)
    ):
        column = ctx["named_all"][0] if ctx["named_all"] else None
        plan.update(
            intent="missing", operation="missing_count", column=column,
            value_column=None, group_column=None,
        )
        notes.append("question asks about missing values")
        return None

    if cue["distinct"] and cue["count"] and intent != "unique":

        if not ctx["named_all"]:
            return (
                "Which column should I count the different values of? "
                "Please name it, for example 'how many different regions "
                "are there'."
            )

        plan.update(
            intent="unique", operation="unique", column=ctx["named_all"][0],
            value_column=None, group_column=None,
        )
        notes.append("question asks for different values")
        return None

    if intent == "unique":
        return None

    # ---- "monthly ...", "over time": a single number is never the answer
    if TREND_CUE.search(text):
        return (
            "Monthly or over-time questions are answered as the monthly "
            "total. Please ask for it directly, for example 'show me "
            "monthly total amount'."
        )

    # ---- "Best category by revenue?": a ranking in few words. The AI said
    #      "total", the words say best/worst of ONE named column
    if (
        bool(TOP_PATTERN.search(text)) != bool(BOTTOM_PATTERN.search(text))
        and len(ctx["named_dims"]) == 1
        and not cue["count"]
        and not parse_top_n(plain_question)
    ):
        value = value_column()

        if value:
            plan.update(
                intent="top" if TOP_PATTERN.search(text) else "bottom",
                operation="group_sum", group_column=ctx["named_dims"][0],
                value_column=value, column=value, filter_value=None,
                agg="mean" if cue["avg"] else "sum",
            )
            notes.append(
                f"the words ask for the best/worst {ctx['named_dims'][0]}, not one total"
            )
            return None

    # ---- a ranking ("top 3 ...", "which product ...", "most popular ...")
    #      cannot be answered with a single number
    if (
        parse_top_n(plain_question) or COUNT_RANK_WORDS.search(text)
        or ASKS_ENTITY.search(text)
    ):
        return RANKING_OR_SINGLE

    # ---- two different calculations at once
    asked = [name for name in ("avg", "max", "min") if cue[name]]

    if len(asked) >= 2:
        return (
            "That asks for more than one calculation (for example the "
            "average and the highest value). Please ask them one at a time."
        )

    # ---- what do the words ask for?
    if cue["avg"]:
        expected = "average"
    elif cue["max"]:
        expected = "maximum"
    elif cue["min"]:
        expected = "minimum"
    elif cue["count"]:
        expected = "count"
    elif cue["total"]:
        expected = "total"
    else:
        expected = None

    # the question names a number column but the plan only counts rows
    asked_measure = [c for c in ctx["named_measures"] if c not in used]

    if (
        intent == "count" and not cue["count"] and asked_measure
        and not (cue["avg"] or cue["max"] or cue["min"])
    ):

        if re.search(r"\b(total|sum)\b", question.lower()):
            return to_scalar("total", "the question asks for a total of a number column, not a count")

        return (
            "I was not sure whether you want to count the rows or "
            "calculate on a number column. Please say 'how many ...' or "
            "'total / average / highest ...'."
        )

    # "how many units were sold": rows or a total quantity? do not guess
    if (
        intent == "count" and cue["count"] and QUANTITY_WORDS.search(text)
        and not ctx["noun_re"].search(text)
    ):
        return (
            "I was not sure whether to count the rows or add up a "
            "quantity. Please rephrase, for example 'how many orders "
            "are there' or 'what is the total quantity'."
        )

    if expected is None or expected == intent:

        # the AI chose a calculation the words do not mention at all
        if intent in ("average", "maximum", "minimum") and expected is None:

            supported = {
                "average": AVG_CUE.search(text),
                "maximum": MAX_CUE.search(text) or TOP_PATTERN.search(text),
                "minimum": MIN_CUE.search(text) or BOTTOM_PATTERN.search(text),
            }[intent]

            if not supported:
                return (
                    "I was not sure which calculation you meant. Please say "
                    "whether you want the total, average, highest or lowest "
                    "value."
                )

        return None

    # words and plan disagree
    if expected == "count":

        quantity_like = bool(
            QUANTITY_WORDS.search(text)
            or re.search(
                r"quant|unit|qty|item|piece", str(plan["value_column"]).lower()
            )
        )

        # "how many units were sold" = the total of the quantity column
        if intent == "total" and quantity_like:
            return None

        # a count question answered with a calculation on a number column
        # is not guessed
        if intent in ("average", "maximum", "minimum", "total"):
            return (
                "I was not sure whether you want a count or a calculation "
                "on a number column. Please rephrase, for example 'how many "
                "orders are there' or 'what is the total quantity'."
            )

        return None

    # "total orders in 2024" is still a count; "total value of orders" is not
    if (
        intent == "count" and ctx["noun_re"].search(text)
        and not (cue["avg"] or cue["max"] or cue["min"])
        and not MEASURE_WORDS.search(text) and not asked_measure
    ):
        return None

    return to_scalar(
        expected, f"the question asks for the {expected}, not the {intent}"
    )


LIST_CUE = re.compile(
    r"\blist\b|\bname\b|\benumerate\b|\b(?:what|which)\s+(?:are|were)\b|"
    r"\b(?:what|which)\s+(?:\w+\s+){0,5}(?:do we|are there|exist|did we|are available)\b|"
    r"\bshow\s+(?:me\s+)?(?:all|every|the\s+(?:different|unique|distinct))\b|"
    r"\b(?:different|distinct|unique)\b"
)
RANK_ANY = re.compile(
    r"\b(top|bottom|best|worst|highest|lowest|most|least|biggest|smallest|"
    r"largest|fastest|slowest|cheapest|popular|common|frequent)\b"
)


def detect_list(plan, question, ctx):
    """
    "what are the categories", "list all regions", "which are those
    categories": the VALUES of one column, as words. Returns True if so.
    """

    text = question.lower()
    used = {item["column"] for item in ctx["conditions"]}
    measures_named = [c for c in ctx["named_measures"] if c not in used]

    if len(ctx["named_dims"]) != 1 or measures_named or ctx["conditions"]:
        return False

    if (
        REVENUE_WORDS.search(text) or RANK_ANY.search(text)
        or AVG_CUE.search(text) or MAX_CUE.search(text) or MIN_CUE.search(text)
        or TOTAL_CUE.search(text) or re.search(r"\bby\b|\bper\b|\beach\b|\d", text)
    ):
        return False

    # "how many different regions" keeps its number (the names are added)
    if COUNT_CUE.search(text) and not re.search(r"\b(list|name)\b", text):
        return False

    if not LIST_CUE.search(text):
        return False

    column = ctx["named_dims"][0]

    plan.update(
        intent="unique", operation="unique", column=column,
        value_column=column, group_column=None, want_list=True,
    )
    ctx["notes"].append(f"question asks for the different values of {column}")

    return True


MEASURE_INTENTS = (
    "total", "average", "maximum", "minimum", "top", "bottom", "trend",
    "breakdown", "month_pick",
)

# everyday words that mean a number column
SYNONYM_WORDS = {
    "units": {"quantity", "qty", "units", "items", "pieces"},
    "items": {"quantity", "qty", "units", "items", "pieces"},
    "pieces": {"quantity", "qty", "units", "items", "pieces"},
    "sold": {"quantity", "qty", "units"},
    "old": {"age"}, "older": {"age"}, "oldest": {"age"},
    "young": {"age"}, "younger": {"age"}, "youngest": {"age"},
    "expensive": {"price", "cost"}, "cheap": {"price", "cost"},
    "rated": {"rating", "score"},
}


def related_words(question):
    """The question's words, with simple plurals and everyday synonyms."""

    words = set(re.findall(r"[a-z]+", question.lower()))
    related = set(words)

    for word in words:

        if word.endswith("s") and len(word) > 3:
            related.add(word[:-1])

        related |= SYNONYM_WORDS.get(word, set())

    return related


def fix_measure(plan, question, ctx):
    """
    The plan must calculate on the column the QUESTION is about, whatever
    the AI chose. Returns a problem message, or None.
    """

    if plan["intent"] not in MEASURE_INTENTS or plan.get("agg") == "count":
        return None

    current = plan["value_column"] or plan["column"]

    if current is None:
        return None

    used = {item["column"] for item in ctx["conditions"]}
    asked = [c for c in ctx["named_measures"] if c not in used]
    revenue = ctx["profile"].get("revenue_column")
    revenue_words = bool(REVENUE_WORDS.search(question.lower()))

    related = related_words(question)

    # words like "customer" or "order" also name ID / category columns, so
    # they cannot identify a NUMBER column
    generic = set()

    for column in ctx["profile"].get("column_semantics", {}):
        if column not in ctx["measures"]:
            generic |= name_words(column)

    supported = bool((name_words(current) - generic) & related) or (
        revenue_words and current == revenue
    )

    target = None

    if len(asked) == 1:
        target = asked[0]

    elif not asked and not supported:

        # the AI's column shares no word with the question: is there exactly
        # one number column that does? (words win over the "revenue" guess)
        candidates = [
            m for m in ctx["measures"] if (name_words(m) - generic) & related
        ]

        if len(candidates) == 1:
            target = candidates[0]

        elif not candidates:

            if revenue and revenue_words and current != revenue:
                target = revenue

        elif revenue_words and revenue in candidates:
            target = revenue

        else:
            return (
                "I was not sure which number column you mean. Did you "
                "mean one of: "
                + ", ".join(label_of(c) for c in candidates[:4])
                + "? Please name the column."
            )

    if target and target != current:
        plan.update(value_column=target, column=target)
        ctx["notes"].append(
            f"the question is about '{target}', not '{current}'"
        )

    return None


def guard_intent(plan, question, ctx):
    """
    0. the calculation uses the column the question names
    1. a question about the VALUES of a column is a list
    2. the words must agree with the calculation (the core guard)
    3. a total of a percentage / rating / age is meaningless: use the average
    """

    if detect_list(plan, question, ctx):
        return None

    wrong_column = fix_measure(plan, question, ctx)

    if wrong_column:
        return wrong_column

    problem = _guard_core(plan, question, ctx)

    if problem:
        return problem

    if plan["intent"] == "total" and plan.get("value_column"):

        value = plan["value_column"]
        biggest = (ctx["profile"].get("numeric_max") or {}).get(value)
        reason = non_additive_reason(value, biggest)

        if reason:
            plan.update(intent="average", operation="average")
            plan["notice"] = (
                f"A total of '{label_of(value)}' is not meaningful because "
                f"it is {reason}, so the average is shown instead."
            )
            ctx["notes"].append(f"total of {value} ({reason}) -> average")

    return None


# ------------------------------------------------------------
# The repair
# ------------------------------------------------------------

def repair_plan(plan, question, profile):
    """
    Fix small, obvious mistakes in the AI's plan, and add what code
    can read from the question itself (filters, dates, top N).

    Returns: (repaired_plan, notes)
    notes = a list of text lines saying what was repaired.
    """

    if not isinstance(plan, dict):
        return plan, []

    plan = dict(plan)
    notes = []

    columns = profile["basic_info"]["column_names"]
    semantics = profile.get("column_semantics", {})

    identifiers = profile.get("identifier_columns", [])

    # ONE list of number columns for the whole engine (codes like ZONE 101..105
    # were already taken out of it when the file was read)
    measures = [
        column
        for column in (
            profile["measures"] if "measures" in profile
            else profile.get("numeric_columns", [])
        )
        if column not in identifiers
    ]
    dates = profile.get("datetime_columns", [])
    dimension_values = profile.get("dimension_values", {})
    years = profile.get("date_years", [])
    numeric_max = profile.get("numeric_max", {})

    # ---- 1. Make sure every key exists, and turn 'null' text into None
    for key in ALL_KEYS:

        value = plan.get(key)

        if isinstance(value, str) and value.strip().lower() in EMPTY_TEXT:
            plan[key] = None
        else:
            plan.setdefault(key, None)

    # ---- 2. Missing / invented intent: work it out from the operation
    if plan["intent"] not in VALID_INTENTS:

        operation = plan["operation"]
        derived = None

        if operation == "group_sum":

            words = question.lower()

            if any(word in words for word in BOTTOM_WORDS):
                derived = "bottom"
            else:
                derived = "top"

        elif operation in OPERATION_TO_INTENT:
            derived = OPERATION_TO_INTENT[operation]

        if derived:
            notes.append(f"intent {plan['intent']!r} -> {derived!r}")
            plan["intent"] = derived

    # ---- 2b. "How many orders ...?" always means: count the rows.
    # (The filters in the question are added further down, by code.)
    lowered_question = question.lower()

    count_re, noun_re, rank_re = row_patterns(profile.get("row_nouns", []))

    # a "count" that names no column can only mean: count the rows
    if (
        plan["intent"] == "count" and plan["operation"] != "row_count"
        and plan["column"] is None
        and re.search(r"\b(how many|number of|count of)\b", lowered_question)
        and not NOT_ROW_COUNT.search(lowered_question)
    ):
        plan["operation"] = "row_count"
        notes.append("a count with no column: counting rows")

    if (
        count_re.search(lowered_question)
        and not NOT_ROW_COUNT.search(lowered_question)
        and (
            plan["intent"] not in VALID_INTENTS
            or plan["intent"] in [
                "count", "unique", "total", "average", "maximum", "minimum"
            ]
        )
    ):

        if plan["intent"] != "count" or plan["operation"] != "row_count":
            notes.append("counting rows (question says 'how many orders')")

        plan["intent"] = "count"
        plan["operation"] = "row_count"
        plan["column"] = None
        plan["value_column"] = None

    # ---- 3. Column names that are wrong but close (revenue -> sales)
    for key in ["column", "group_column", "value_column"]:

        name = plan[key]

        if name is None or name in columns:
            continue

        match = closest_column(name, columns)

        # Number columns: if the dataset has only ONE real measure,
        # a made-up name like "revenue" must mean that measure.
        allow_measure_fallback = (
            key in ["column", "value_column"]
            and plan["intent"] in NUMBER_INTENTS
        )

        if match is None and allow_measure_fallback and len(measures) == 1:
            match = measures[0]

        if match is not None:
            notes.append(f"{key} {name!r} -> {match!r}")
            plan[key] = match

    # ---- 3b. A column the AI forgot, but the question names it
    named = mentioned_columns(question, columns)
    named_dims = [c for c in named if c not in measures and c not in dates]
    named_measures = [c for c in named if c in measures]

    # "category" with 211 path variants really means its first level
    main_map = profile.get("main_columns", {})
    named_dims_raw = list(named_dims)

    if main_map:

        named_dims = list(dict.fromkeys(main_map.get(c, c) for c in named_dims))

        for key in ["group_column"]:
            if plan[key] in main_map:
                notes.append(f"{key} {plan[key]!r} -> {main_map[plan[key]]!r}")
                plan[key] = main_map[plan[key]]

    # a distinct count of "category" means its first level, like the lists do
    if main_map and plan["intent"] == "unique":

        for key in ("column", "value_column"):

            if plan[key] in main_map:
                original = plan[key]
                notes.append(f"{key} {original!r} -> {main_map[original]!r}")
                plan[key] = main_map[original]
                plan["notice"] = (
                    f"'{label_of(original)}' holds long path-like values, so "
                    f"its first level is used (the same as in the lists)."
                )

    lowered = question.lower()

    # ---- 3c. "How many different categories?" is a distinct count, whatever
    # the AI said (it was a ranking, nothing at all ...)
    if (
        plan["intent"] != "unique"
        and DISTINCT_CUE.search(lowered) and COUNT_CUE.search(lowered)
        and len(named_dims) == 1 and not named_measures
        and not re.search(r"\bby\b|\bper\b|\beach\b", lowered)
    ):
        plan.update(
            intent="unique", operation="unique", column=named_dims[0],
            value_column=named_dims[0], group_column=None,
        )
        notes.append(f"question asks how many different {named_dims[0]} values")

    # ---- 3d. The AI gave no usable calculation, but the WORDS are clear
    # ("how much profit we have done"): use the one number column the
    # question names or shares a word with
    if plan["intent"] not in VALID_INTENTS:

        value = (
            named_measures[0] if len(named_measures) == 1
            else guess_measure(lowered, measures)
        )

        kind = (
            "average" if AVG_CUE.search(lowered)
            else "maximum" if MAX_CUE.search(lowered)
            else "minimum" if MIN_CUE.search(lowered)
            else "total" if TOTAL_CUE.search(lowered)
            else None
        )

        if DUPLICATE_CUE.search(lowered) and (
            COUNT_CUE.search(lowered) or re.search(r"\b(any|are there|is there|exist)\b", lowered)
        ):
            plan.update(
                intent="duplicate", operation="duplicate_count", column=None,
                value_column=None, group_column=None,
            )
            notes.append("no calculation from the AI: the question asks about duplicate rows")

        elif MISSING_CUE.search(lowered) and not AVG_CUE.search(lowered) and (
            COUNT_CUE.search(lowered) or re.search(r"\b(any|are there|is there)\b", lowered)
        ):
            plan.update(
                intent="missing", operation="missing_count",
                column=named[0] if named else None,
                value_column=None, group_column=None,
            )
            notes.append("no calculation from the AI: the question asks about missing values")

        elif value and kind and not DISTINCT_CUE.search(lowered):
            plan.update(
                intent=kind, operation=SCALAR_OPERATION[kind],
                value_column=value, column=value, group_column=None,
            )
            notes.append(
                f"no calculation from the AI: the words say '{kind}' of {value}"
            )

    # "how many missing values in delivery days": the column is in the question
    if plan["intent"] == "missing" and plan["column"] not in columns:
        wanted = [c for c in named if c not in dates]
        plan["column"] = wanted[0] if len(wanted) == 1 else None

    intent = plan["intent"]

    if intent == "unique" and plan["column"] is None and named_dims:
        plan["column"] = named_dims[0]
        notes.append(f"column None -> {named_dims[0]!r} (named in question)")

    if intent in NUMBER_INTENTS:

        if plan["value_column"] is None and plan["column"] in measures:
            plan["value_column"] = plan["column"]
            notes.append(f"value_column None -> {plan['column']!r}")

    if intent in ["top", "bottom"] and plan["group_column"] is None:

        if named_dims:
            plan["group_column"] = named_dims[0]
            notes.append(f"group_column None -> {named_dims[0]!r}")

    if intent == "trend" and dates:

        hint = question + " " + str(plan["value_column"] or "")
        best = pick_date_column(hint, dates)
        scores = date_scores(hint, dates)
        current = plan["group_column"]

        if current is None:
            plan["group_column"] = best
            notes.append(f"group_column None -> {best!r}")

        elif current in dates and scores[best] > scores[current]:
            notes.append(f"date column {current!r} -> {best!r}")
            plan["group_column"] = best

    # ---- 4. "WHO ..." questions must group by the person column
    if plan["intent"] in ["top", "bottom"] and re.search(
        r"\bwho\b", question.lower()
    ):

        people = [
            column
            for column in columns
            if semantics.get(column) == "customer"
        ]

        # If both customer_id and customer_name exist, prefer the name
        if len(people) > 1:
            named_people = [
                column for column in people if column not in identifiers
            ]
            if len(named_people) == 1:
                people = named_people

        if len(people) == 1 and plan["group_column"] != people[0]:
            notes.append(
                f"group_column {plan['group_column']!r} -> {people[0]!r}"
            )
            plan["group_column"] = people[0]

    # ---- 5. Highest vs lowest: trust the words in the question
    if plan["intent"] in ["top", "bottom"]:

        wants_bottom = bool(BOTTOM_PATTERN.search(question.lower()))
        wants_top = bool(TOP_PATTERN.search(question.lower()))

        if wants_bottom and not wants_top and plan["intent"] == "top":
            plan["intent"] = "bottom"
            notes.append("intent 'top' -> 'bottom' (question says lowest)")

        elif wants_top and not wants_bottom and plan["intent"] == "bottom":
            plan["intent"] = "top"
            notes.append("intent 'bottom' -> 'top' (question says highest)")

    # ---- 6. "top 3" / "5 best"
    if plan["intent"] in ["top", "bottom"]:

        top_n = parse_top_n(question)

        if top_n:
            plan["top_n"] = top_n
            notes.append(f"top_n = {top_n}")

    # ---- 7. Dates, read from the question by code
    unsupported = None

    date_filter, date_problem = parse_date_filter(
        question, dates, years, str(plan["value_column"] or "")
    )

    if date_problem:
        unsupported = date_problem

    # "from 2023 to 2024", "between 2023 and 2024": a comparison of periods
    if not unsupported and len(set(re.findall(r"\b(19\d\d|20\d\d)\b", question))) >= 2:
        unsupported = (
            "Comparing two years or periods in one question (like 'from 2023 "
            "to 2024', growth or change) is not supported yet. Please ask "
            "about each year separately."
        )

    # a file with no date column cannot answer "last month" or "in 2024":
    # never ignore the time part silently
    if not dates and not unsupported and (
        RELATIVE_DATE_PATTERN.search(question.lower()) or TIME_WORDS.search(question.lower())
    ):

        year_values = {
            str(v).strip()
            for values in profile.get("dimension_values", {}).values() for v in values
        }

        if not any(y in year_values for y in re.findall(r"(?:19|20)\d{2}", question)):
            unsupported = (
                "This file has no date column, so I cannot answer questions "
                "about a time period like 'last month' or 'in 2024'. Please "
                "ask without the time part."
            )

    if date_filter:

        # several date columns: say which one was used
        if len(dates) > 1:
            date_filter["ambiguous"] = True

        plan["date_filter"] = date_filter
        notes.append(f"date filter {date_filter['label']}")

    # The AI sometimes tries to filter the date column like a value
    ai_date_filter = (
        plan["group_column"] in dates
        and plan["filter_value"] is not None
        and plan["intent"] != "trend"
    )

    if ai_date_filter:

        if date_filter:
            plan["group_column"] = None
            plan["filter_value"] = None

        else:
            unsupported = (
                "I could not read the date in your question. Please "
                "write it like 'September 2024' or '2024'."
            )

    # ---- 7b. Number conditions: "above 2000", "at least 5"
    conditions, condition_problem = parse_conditions(
        question,
        measures,
        numeric_max,
        plan["value_column"] if plan["intent"] in NUMBER_INTENTS else None
    )

    if condition_problem:
        unsupported = condition_problem

    if conditions:

        plan["conditions"] = conditions

        for item in conditions:
            if item["label"]:
                notes.append(item["label"])

    # ---- 7b1. A number column the AI forgot. Never use the column that
    # only appears inside a condition ("orders with discount above 10%")
    if plan["intent"] in NUMBER_INTENTS and plan["value_column"] is None:

        used = {item["column"] for item in conditions}
        options = [c for c in named_measures if c not in used]

        revenue_column = profile.get("revenue_column")

        if options:
            fill = options[0]
        elif (
            REVENUE_WORDS.search(question.lower())
            and revenue_column
            and revenue_column not in used
        ):
            fill = revenue_column
        elif named_measures:
            fill = named_measures[0]
        else:
            fill = None   # a wrong guess is worse than a clear refusal

        if fill:
            plan["value_column"] = fill
            notes.append(f"value_column None -> {fill!r}")

    if plan["intent"] in NUMBER_INTENTS:
        if plan["column"] is None and plan["value_column"] is not None:
            plan["column"] = plan["value_column"]

    # ---- 7b2. Question types the app cannot answer correctly yet
    if not unsupported:

        column_labels = " ".join(label_of(c).lower() for c in columns)

        guard_plan = dict(plan, _date_columns=dates, _named_dims=named_dims)

        phrase_problem = find_unsupported_phrase(
            question, guard_plan, column_labels,
            [readable_label(c) for c in columns],
        )

        if phrase_problem:
            unsupported = phrase_problem

    # ---- 8. Filters, read from the question by code
    filters = []

    def add_filter(column, value, label=None):

        for item in filters:
            if (
                item["column"] == column
                and str(item["value"]).lower() == str(value).lower()
            ):
                return

        item = {"column": column, "value": value}

        if label:
            item["label"] = label

        filters.append(item)

    llm_column = plan["group_column"]
    llm_value = plan["filter_value"]
    ranking = plan["intent"] in RANKING_INTENTS

    # ---- Check the filter the AI proposed against the question
    # and the real data. Move it, drop it, or leave it for the checks.
    if llm_value is not None:

        text_value = str(llm_value).strip().lower()
        boolean_named = any(
            column in named
            and {str(v).strip().lower() for v in values} <= YES_NO
            for column, values in dimension_values.items()
        )

        drop_reason = None

        if conditions and looks_like_condition(text_value):
            drop_reason = "a number condition, which code handles"

        elif date_filter and text_value in date_tokens(date_filter):
            drop_reason = "a date, which code handles"

        elif text_value in YES_NO and not boolean_named:
            drop_reason = "a yes/no value the question never mentions"

        if drop_reason:

            notes.append(f"dropped AI filter {llm_value!r}: {drop_reason}")

            plan["filter_value"] = None
            llm_value = None

            if not ranking:
                plan["group_column"] = None
                llm_column = None

    # The AI put a real value on the wrong column ("Yes" on category)
    if llm_value is not None and llm_column is not None and not ranking:

        text_value = str(llm_value).strip().lower()

        known_here = {
            str(v).strip().lower() for v in dimension_values.get(llm_column, [])
        }

        if llm_column in dimension_values and text_value not in known_here:

            owners = [
                column
                for column, values in dimension_values.items()
                if column != llm_column
                and text_value in {str(v).strip().lower() for v in values}
                # a yes/no value belongs to a yes/no column only if the
                # question actually names that column
                and (text_value not in YES_NO or column in named)
            ]

            if len(owners) == 1:

                actual = next(
                    v for v in dimension_values[owners[0]]
                    if str(v).strip().lower() == text_value
                )

                notes.append(
                    f"filter value {llm_value!r} moved from "
                    f"{llm_column!r} to {owners[0]!r}"
                )

                plan["group_column"] = owners[0]
                plan["filter_value"] = actual
                llm_column = owners[0]
                llm_value = actual

    # 7a. A filter the AI found itself (for non-ranking questions)
    if (
        llm_value is not None
        and llm_column is not None
        and llm_column not in dates
        and not ranking
    ):
        add_filter(llm_column, llm_value)

    # 7b. Real column values named in the question ("Fashion")
    mentions = find_mentioned_values(
        question, dimension_values, [readable_label(c) for c in columns]
    )

    # the SAME word is a value of several columns ("Other" in channel AND
    # gender): use the column the question names, otherwise ask
    by_word = {}

    for column, values in mentions.items():
        for value in values:
            by_word.setdefault(str(value).strip().lower(), []).append(column)

    for word, owners in by_word.items():

        if len(owners) < 2:
            continue

        chosen = [c for c in owners if c in named]

        if len(chosen) == 1:
            for owner in owners:
                if owner != chosen[0]:
                    mentions[owner] = [
                        v for v in mentions[owner]
                        if str(v).strip().lower() != word
                    ]
        elif not unsupported:
            unsupported = (
                f"'{word}' is a value in more than one column "
                f"({', '.join(label_of(c) for c in owners)}). Please say "
                f"which one, for example '{label_of(owners[0])} {word}'."
            )

    mentions = {c: v for c, v in mentions.items() if v}

    for column, values in mentions.items():

        if len(values) > 1:

            unsupported = (
                f"Your question names more than one {label_of(column)} "
                f"value ({', '.join(str(v) for v in values)}). I can use "
                f"one at a time for now. Please ask about each separately."
            )
            continue

        # Grouping by a column and filtering on the same column: skip
        if ranking and column == plan["group_column"]:
            continue

        # The question is ABOUT this column (not a filter on it) --
        # except for percentage questions ("what share are female?")
        if column in [plan["column"], plan["value_column"]] and (
            plan["intent"] in ["unique", "count"]
        ) and not asks_ratio(
            question, [readable_label(c) for c in columns]
        ) and (
            # ...but only when the WORDS ask about the column itself ("how many
            # different ...", "list the ..."): "total cost for NEL" is a filter
            DISTINCT_CUE.search(question.lower())
            or COUNT_CUE.search(question.lower())
            or UNIQUE_EVIDENCE_WORDS.search(question.lower())
        ):
            continue

        before = len(filters)
        add_filter(column, values[0])

        if len(filters) > before:
            notes.append(f"filter {column} = {values[0]!r} (from question)")

    # 7c. Yes/No columns: "How many orders were returned?"
    for column, values in dimension_values.items():

        lowered = {str(v).strip().lower(): v for v in values}

        if not set(lowered) <= YES_NO:
            continue

        if column not in named:
            continue

        # the question is ABOUT the column ("how many different returned...",
        # or "which returned ..." when ranking by it)
        if plan["intent"] == "unique":
            continue

        if column == plan["group_column"] and plan["intent"] in [
            "top", "bottom", "trend"
        ]:
            continue

        if any(item["column"] == column for item in filters):
            continue

        negative = bool(NEGATION_PATTERN.search(question.lower()))

        wanted = NO_WORDS if negative else YES_WORDS

        value = next((lowered[k] for k in lowered if k in wanted), None)

        if value is None:
            continue

        if (
            plan["intent"] in ["top", "bottom"]
            and not named_measures
            and not asks_ratio(
                question, [readable_label(c) for c in columns]
            )
        ):

            unsupported = (
                f"Ranking by the number of '{label_of(column)}' rows is not "
                f"supported yet. You can ask for a total or average of a "
                f"number column instead."
            )
            continue

        add_filter(column, value, f"where {label_of(column)} is {value}")
        notes.append(f"filter {column} = {value!r} (from question)")

    # 7d. A filter the AI found for a ranking question: not trusted
    if ranking and llm_value is not None:

        known = any(
            str(item["value"]).lower() == str(llm_value).lower()
            for item in filters
        )

        if not known:
            unsupported = (
                "I could not safely apply the filter in your question "
                "to this kind of question yet, so I will not guess."
            )

    # A filter value but no column to apply it to: do not guess
    if llm_value is not None and not ranking and llm_column is None:

        known = any(
            str(item["value"]).lower() == str(llm_value).lower()
            for item in filters
        )

        if not known and not date_filter:
            unsupported = (
                "I understood that you want to filter, but I could not "
                "tell which column to filter. Please mention the column "
                "name."
            )

    plan["filters"] = filters

    # "the default rate for business loans": the word before "rate" names
    # the event (the part); the other filters say WHO we look at
    rate_word = re.search(r"\b([a-z]+)\s+rate\b", question.lower())

    if rate_word:
        forms = word_forms(rate_word.group(1))
        for item in filters:
            value = str(item["value"]).strip().lower()
            if value in forms or (word_forms(value) & forms):
                plan["rate_flag"] = {"column": item["column"], "value": item["value"]}

    if not unsupported:
        unsupported = ambiguous_hazard(
            question, filters, profile.get("dimension_values", {})
        )

    # ---- 9. Group tables, percentages, rankings by count/average,
    # best month: decided by code from the words of the question
    if not unsupported:

        metric_ctx = {
            "named_dims": named_dims,
            "named_dims_raw": named_dims_raw,
            "main_map": main_map,
            "named_measures": named_measures,
            "named_all": named,
            "measures": measures,
            "dates": dates,
            "profile": profile,
            "conditions": conditions,
            "filters": filters,
            "column_labels": " ".join(readable_label(c) for c in columns),
            "column_label_list": [readable_label(c) for c in columns],
            "count_re": count_re,
            "noun_re": noun_re,
            "rank_re": rank_re,
            "notes": notes,
        }

        unsupported = detect_metrics(plan, question, metric_ctx)

        # the last safety net: do the words agree with the plan?
        if not unsupported:
            unsupported = guard_intent(plan, question, metric_ctx)

        # ...and does every meaningful word of the question map to something?
        if not unsupported:
            unsupported = unmapped_words_problem(
                plan, question, profile, columns, dimension_values
            )

        drop_hidden_filters(plan, notes)

    plan["count_noun"] = profile.get("count_noun", "orders")

    if unsupported:
        plan["unsupported"] = unsupported

    return plan, notes