"""
Real files often store numbers as TEXT: "₹1,099", "64%", "24,269".
A program then sees no number columns at all. This module finds such
columns and turns them into real numbers, and says what it did.
"""

import re

import pandas as pd


CURRENCY_SYMBOLS = "₹$€£¥"

NUMBER_TEXT = re.compile(
    r"^\s*[₹$€£¥]?\s*-?\d[\d,]*(?:\.\d+)?\s*%?\s*$"
)

# A column of plain digits ("2020", "560001") may be a year or a code,
# not a quantity. Only convert when something shows it is a number.
HINT = re.compile(r"[₹$€£¥%,]|\.\d")


def convert_text_numbers(df):
    """
    Returns (new dataframe, notes).
    notes = {column: "text like ₹1,099 turned into numbers (₹)"}.
    """

    out = df.copy()
    notes = {}

    for column in out.columns:

        series = out[column]

        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):
            continue

        values = series.dropna().astype(str)

        if values.empty:
            continue

        looks_numeric = values.str.match(NUMBER_TEXT)

        # a few odd cells ("|", "N/A") are allowed
        if looks_numeric.mean() < 0.9:
            continue

        if not values.str.contains(HINT).any():
            continue

        cleaned = (
            series.astype("object")
            .astype(str)
            .str.replace(r"[₹$€£¥,%\s]", "", regex=True)
        )

        numbers = pd.to_numeric(cleaned, errors="coerce")

        # NaN stays NaN (it became the text "nan" above)
        numbers[series.isna()] = float("nan")

        unit = ""

        if values.str.contains("%").mean() > 0.5:
            unit = "%"
        else:
            for symbol in CURRENCY_SYMBOLS:
                if values.str.contains(re.escape(symbol)).any():
                    unit = symbol
                    break

        out[column] = numbers

        shown = f" ({unit})" if unit else ""
        notes[column] = f"text turned into numbers{shown}"

    return out, notes


def add_hierarchy_columns(df):
    """
    A column like "Electronics|Cables|HDMI" has hundreds of variants.
    Analysts mean its FIRST level ("Electronics"), so add that as a new
    column. Returns (new dataframe, notes, {original: new column}).
    """

    out = df.copy()
    notes = {}
    mapping = {}

    for column in list(out.columns):

        series = out[column]

        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):
            continue

        values = series.dropna().astype(str)

        # only columns that are too long to list, and look like paths
        if values.empty or values.nunique() <= 30:
            continue

        if values.str.contains(r"\|").mean() < 0.7:
            continue

        main = series.astype("object").where(
            series.isna(),
            series.astype(str).str.split("|").str[0].str.strip()
        )

        if not 2 <= main.nunique() <= 30:
            continue

        name = f"{column}_main"

        if name in out.columns:
            continue

        out.insert(out.columns.get_loc(column) + 1, name, main)

        notes[name] = f"new column: the first level of '{column}'"
        mapping[column] = name

    return out, notes, mapping


def strip_text(df):
    """
    'Production   ' and 'Production' are the same thing. Remove the extra
    spaces around text, so filters and groups match.
    Returns (new dataframe, notes).
    """

    out = df.copy()
    notes = {}

    for column in out.columns:

        series = out[column]

        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        ):
            continue

        texts = series.dropna()

        if texts.empty or not texts.map(lambda v: isinstance(v, str)).all():
            continue

        cleaned = series.where(series.isna(), series.str.strip())

        changed = int((texts != cleaned.dropna()).sum())

        if changed:
            out[column] = cleaned
            notes[column] = f"extra spaces removed from {changed:,} values"

    return out, notes
