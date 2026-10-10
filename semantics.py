"""
What a number column MEANS. Some columns can be added up (revenue, cost,
quantity). Others cannot: the sum of 1,465 discount percentages is a
number without a meaning. Only the average of those makes sense.
"""

import re

# words that tell us the column is a percentage, rate, rating or age
NON_ADDITIVE = {
    "percent": "a percentage", "percentage": "a percentage", "pct": "a percentage",
    "rate": "a rate", "ratio": "a ratio", "rating": "a rating",
    "score": "a score", "age": "an age",
}

# words that tell us it IS a quantity ("rating_count", "total_amount")
ADDITIVE_WORDS = {
    "count", "counts", "number", "num", "qty", "quantity", "total", "amount",
    "sum", "revenue", "sales", "cost", "price", "value",
}


def name_words(name):
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))

    return set(re.findall(r"[a-z]+", spaced.lower()))


def non_additive_reason(column, max_value=None):
    """'a percentage' / 'a rating' ... when a total would be meaningless, else None."""

    words = name_words(column)

    if words & ADDITIVE_WORDS:
        return None

    for word in sorted(words):
        if word in NON_ADDITIVE:
            return NON_ADDITIVE[word]

    # "discount" alone: a fraction like 0.15 (not an amount of money)
    if "discount" in words and max_value is not None and max_value <= 1:
        return "a discount rate"

    return None
