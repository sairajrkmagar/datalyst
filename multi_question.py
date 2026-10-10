"""
Several questions in one sentence: "how many orders and what is the
total revenue". They are split and answered one by one.
Only a clear case is split: every part must be a real question or command.
"""

import re

LEAD = (
    r"(?:how|what|which|who|where|when|show|list|give|tell|compare|total|"
    r"average|avg|highest|lowest|count|number)"
)

SPLIT = re.compile(
    r"\s*[?;]\s*|\s+(?:and then|and also|and|also|then|plus|&)\s+(?=" + LEAD + r"\b)",
    re.IGNORECASE,
)


def split_question(question, max_parts=3):
    """A list of 2 or 3 questions, or None when it is one question."""

    text = " ".join(str(question).strip().split())

    parts = [p.strip(" ,.?") for p in SPLIT.split(text) if p and p.strip(" ,.?")]

    if len(parts) < 2 or len(parts) > max_parts:
        return None

    if any(len(p.split()) < 3 for p in parts):
        return None

    return parts
