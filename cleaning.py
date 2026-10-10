"""
Fixing common data problems, one clear step at a time.

Every function returns (new table, message) and NEVER changes the table it is
given. "Blank" means an empty cell or a cell with only spaces.
"""

import numpy as np
import pandas as pd


def blank_mask(table):
    """True where a cell is empty or holds only spaces."""

    mask = table.isna()

    for column in table.columns:
        series = table[column]
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            spaces = [v for v in series.dropna().unique() if isinstance(v, str) and v.strip() == ""]
            if spaces:
                mask[column] = mask[column] | series.isin(spaces)

    return mask


def summary(table):
    """What is wrong with the table, in numbers."""

    mask = blank_mask(table)
    by_column = {c: int(n) for c, n in mask.sum().items() if n}

    return {
        "rows": len(table),
        "columns": table.shape[1],
        "blank_cells": int(mask.values.sum()),
        "blank_by_column": by_column,
        "duplicate_rows": int(table.duplicated().sum()),
        "empty_columns": [c for c in table.columns if mask[c].all()],
        "number_columns": [c for c in table.columns if pd.api.types.is_numeric_dtype(table[c]) and not pd.api.types.is_bool_dtype(table[c])],
    }


def remove_duplicates(table):
    count = int(table.duplicated().sum())
    if not count:
        return table.copy(), "There were no duplicate rows."
    cleaned = table.drop_duplicates().reset_index(drop=True)
    return cleaned, f"Removed {count:,} duplicate rows ({len(table):,} to {len(cleaned):,} rows)."


def remove_empty_columns(table):
    empty = summary(table)["empty_columns"]
    if not empty:
        return table.copy(), "There were no completely empty columns."
    return table.drop(columns=empty), f"Removed {len(empty)} empty column(s): {', '.join(map(str, empty[:6]))}."


def remove_blank_rows(table, column):
    mask = blank_mask(table)[column]
    count = int(mask.sum())
    if not count:
        return table.copy(), f"'{column}' has no blanks."
    cleaned = table[~mask].reset_index(drop=True)
    return cleaned, f"Removed {count:,} rows where '{column}' was blank ({len(table):,} to {len(cleaned):,} rows)."


def fill_blanks(table, column, how):
    """how: 'median', 'mean', 'zero' (numbers) or 'unknown', 'most common' (text)."""

    mask = blank_mask(table)[column]
    count = int(mask.sum())

    if not count:
        return table.copy(), f"'{column}' has no blanks."

    cleaned = table.copy()
    series = cleaned[column]
    numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)

    if how in ("median", "mean", "zero"):
        if not numeric:
            raise ValueError(f"'{column}' is not a number column.")
        value = {"median": series.median(), "mean": series.mean(), "zero": 0}[how]
        shown = f"{value:,.2f}" if how != "zero" else "0"
    elif how == "most common":
        counts = series[~mask].astype(str).str.strip().value_counts()
        if counts.empty:
            raise ValueError(f"'{column}' has no values to copy.")
        value = counts.index[0]
        shown = f"'{value}'"
    elif how == "unknown":
        value, shown = "Unknown", "'Unknown'"
    else:
        raise ValueError(f"Unknown way to fill: {how}")

    if numeric:
        cleaned[column] = series.where(~mask, value)
    else:
        cleaned[column] = series.astype(object).where(~mask, value)

    return cleaned, f"Filled {count:,} blank cells in '{column}' with {shown} ({how})."


def to_csv_bytes(table):
    return table.to_csv(index=False).encode("utf-8")


# ============================================================
# "Clean it for me": find the problems, suggest, apply what is ticked
# ============================================================

import re

# words that mean "missing" but are not real blanks
FAKE_BLANKS = {
    "n/a", "na", "n.a.", "#n/a", "null", "none", "nan", "nil", "-", "--", "---",
    "?", "??", "missing", "not available", "not applicable",
}
BLANKY = 0.6                 # a column this empty is "almost empty"
MAX_CATEGORY_VALUES = 200    # more distinct values than this is not a category
MONEY = re.compile(r"^[\u20b9$\u20ac\u00a3]?\s*-?\d[\d,]*(?:\.\d+)?$")
MONEY_MARK = re.compile(r"[\u20b9$\u20ac\u00a3,]")

# the order matters: placeholders first, so everything after sees real blanks
STEPS = [
    "fake_blanks", "trim_spaces", "to_number", "case", "empty_columns",
    "mostly_blank", "constant", "blanks_numbers", "blanks_text", "duplicates",
]


def text_columns(table):
    return [
        c for c in table.columns
        if pd.api.types.is_object_dtype(table[c]) or pd.api.types.is_string_dtype(table[c])
    ]


def text_counts(series):
    """{text: number of cells} for the TEXT cells of a column (a Series indexed by the text)."""

    clean = series.dropna()

    if pd.api.types.is_string_dtype(series) or pd.api.types.infer_dtype(clean, skipna=True) == "string":
        counts = clean.value_counts()
    else:
        counts = clean[clean.map(lambda v: isinstance(v, str))].value_counts()

    return counts


def collapse(index):
    """Text without spaces at the ends and with single spaces inside."""
    return index.str.strip().str.replace(r"\s+", " ", regex=True)


def find_fake_blanks(table):
    found = {}
    for column in text_columns(table):
        counts = text_counts(table[column])
        hit = counts.index.str.strip().str.lower().isin(FAKE_BLANKS)
        n = int(counts[hit].sum())
        if n:
            found[column] = n
    return found


def find_untrimmed(table):
    found = {}
    for column in text_columns(table):
        counts = text_counts(table[column])
        n = int(counts[counts.index != counts.index.str.strip()].sum())
        if n:
            found[column] = n
    return found


def grouped_counts(counts):
    """Counts by collapsed text: {'north': 5, 'North': 90, ...} (blank texts removed)."""

    if counts.empty:
        return counts
    merged = pd.Series(counts.values, index=collapse(counts.index)).groupby(level=0).sum()
    return merged[merged.index != ""].sort_values(ascending=False)


def category_columns(table):
    """Text columns that behave like categories (few distinct values, short words)."""
    found = []
    for column in text_columns(table):
        grouped = grouped_counts(text_counts(table[column]))
        if grouped.empty:
            continue
        distinct, total = len(grouped), int(grouped.sum())
        average = float((np.asarray(grouped.index.str.len()) * grouped.values).sum() / total)
        if 1 < distinct <= MAX_CATEGORY_VALUES and distinct <= 0.5 * total and average <= 40:
            found.append(column)
    return found


def case_map(series):
    """{variant: most common spelling} for values that differ only by capitals or spaces."""
    grouped = grouped_counts(text_counts(series))
    groups = {}
    for value in grouped.index:                       # sorted: the most common first
        groups.setdefault(value.lower(), []).append(value)
    mapping = {}
    for variants in groups.values():
        if len(variants) > 1:
            for v in variants[1:]:
                mapping[v] = variants[0]
    return mapping


def find_case_problems(table):
    found = {}
    for column in category_columns(table):
        mapping = case_map(table[column])
        if mapping:
            grouped = grouped_counts(text_counts(table[column]))
            found[column] = {"variants": mapping, "rows": int(grouped[grouped.index.isin(list(mapping))].sum())}
    return found


def money_columns(table):
    """Text columns that really hold amounts such as '\u20b91,299.00'."""
    found = {}
    for column in text_columns(table):
        counts = text_counts(table[column])
        counts = counts[(counts.index.str.strip() != "") & ~counts.index.str.strip().str.lower().isin(FAKE_BLANKS)]
        total = int(counts.sum())
        if total < 3:
            continue
        values = pd.Series(counts.index.str.strip(), index=counts.index)
        fits = values.map(lambda v: bool(MONEY.match(v)))
        marked = values.map(lambda v: bool(MONEY_MARK.search(v)))
        if counts[fits].sum() / total >= 0.95 and counts[marked].sum() / total >= 0.05:
            found[column] = str(values[marked].iloc[0])
    return found


def to_amount(value):
    if not isinstance(value, str):
        return value
    text = MONEY_MARK.sub("", value.strip())
    try:
        return float(text)
    except ValueError:
        return float("nan")


def map_values(series, mapping):
    """Replace cells by looking the DISTINCT values up (fast), leaving other cells alone."""
    return series.map(lambda v: mapping.get(v, v)) if mapping else series


def share_blank(table):
    return blank_mask(table).mean()


def issue(id_, title, detail, severity, default_on, fixable=True, count=0):
    return {"id": id_, "title": title, "detail": detail, "severity": severity,
            "default_on": default_on, "fixable": fixable, "count": int(count)}


def names(columns, limit=4):
    columns = list(columns)
    shown = ", ".join(f"'{c}'" for c in columns[:limit])
    return shown + (f" and {len(columns) - limit} more" if len(columns) > limit else "")


def diagnose(table):
    """The problems of a table, most serious first, each with a plain-words explanation."""

    issues = []
    blanks = blank_mask(table)
    share = blanks.mean()

    fake = find_fake_blanks(table)
    if fake:
        n = sum(fake.values())
        issues.append(issue(
            "fake_blanks", "Placeholders that mean \u201cmissing\u201d",
            f"{n:,} cells say things like N/A, null or - in {names(fake)}. They are not real blanks, "
            "so counts and averages treat them as values.", "high", True, count=n))

    empty = [c for c in table.columns if blanks[c].all()]
    if empty:
        issues.append(issue(
            "empty_columns", "Empty columns", f"{names(empty)} {'has' if len(empty) == 1 else 'have'} no data at all.",
            "medium", True, count=len(empty)))

    # count duplicates the way they will be AFTER the text is tidied: tidying can make rows identical
    dup_now = int(table.duplicated().sum())
    tidy_needed = bool(find_fake_blanks(table) or find_untrimmed(table) or find_case_problems(table) or money_columns(table))
    dup = dup_now

    if tidy_needed:
        tidied, _ = apply_plan(table, ["fake_blanks", "trim_spaces", "to_number", "case"])
        dup = int(tidied.duplicated().sum())

    if dup:
        when = f" once the text is tidied ({dup_now:,} right now)" if dup != dup_now else ""
        issues.append(issue(
            "duplicates", "Duplicate rows",
            f"{dup:,} rows are exact copies of another row{when}. "
            "They could be real repeated records, so look first.",
            "high", True, count=dup))

    case = find_case_problems(table)
    if case:
        n = sum(v["rows"] for v in case.values())
        examples = []
        for column, info in list(case.items())[:2]:
            variant, best = next(iter(info["variants"].items()))
            examples.append(f"{column}: \u2018{variant}\u2019 \u2192 \u2018{best}\u2019")
        issues.append(issue(
            "case", "Same value written in different ways",
            f"{n:,} cells differ only by capitals or spaces ({'; '.join(examples)}). They would be counted as different groups.",
            "high", True, count=n))

    trimmed = find_untrimmed(table)
    if trimmed:
        n = sum(trimmed.values())
        issues.append(issue(
            "trim_spaces", "Extra spaces around text",
            f"{n:,} cells have spaces at the start or end, in {names(trimmed)}. 'North ' and 'North' look different to a computer.",
            "medium", True, count=n))

    money = money_columns(table)
    if money:
        shown = ", ".join(f"'{c}' (like {v})" for c, v in list(money.items())[:3])
        issues.append(issue(
            "to_number", "Numbers stored as text",
            f"{shown}. They cannot be added up until they become real numbers.", "high", True, count=len(money)))

    almost = [c for c in table.columns if BLANKY <= share[c] < 1]
    if almost:
        issues.append(issue(
            "mostly_blank", "Columns that are almost empty",
            f"{names(almost)} {'is' if len(almost) == 1 else 'are'} {int(BLANKY * 100)}% or more blank. They rarely help an analysis. Off by default.",
            "medium", False, count=len(almost)))

    constant = []
    for column in table.columns:
        values = table[column][~blanks[column]]
        if len(values) and share[column] < 1:
            distinct = values.unique()
            if len(distinct) == 1 or (len(distinct) <= 50 and len({str(v).strip() for v in distinct}) == 1):
                constant.append(column)
    if constant:
        issues.append(issue(
            "constant", "Columns with a single value",
            f"{names(constant)} never changes, so it tells you nothing. Off by default.", "info", False, count=len(constant)))

    numeric_blank = [c for c in table.columns if pd.api.types.is_numeric_dtype(table[c])
                     and not pd.api.types.is_bool_dtype(table[c]) and 0 < share[c] < BLANKY]
    if numeric_blank:
        n = int(blanks[numeric_blank].values.sum())
        issues.append(issue(
            "blanks_numbers", "Blank numbers",
            f"{n:,} blank cells in {names(numeric_blank)}. Filling them with the middle value (median) means INVENTING data, "
            "and it can make some rows identical. Off by default.", "medium", False, count=n))

    text_blank = [c for c in text_columns(table) if 0 < share[c] < BLANKY and c not in empty]
    if text_blank:
        n = int(blanks[text_blank].values.sum())
        issues.append(issue(
            "blanks_text", "Blank text",
            f"{n:,} blank cells in {names(text_blank)}. They can be labelled 'Unknown' so they show up in groups. Off by default.",
            "info", False, count=n))

    unusual = []
    for column in table.columns:
        series = table[column]
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series) and series.nunique() > 20:
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            spread = q3 - q1
            if spread > 0:
                n = int(((series < q1 - 3 * spread) | (series > q3 + 3 * spread)).sum())
                if n:
                    unusual.append((column, n))
    if unusual:
        unusual.sort(key=lambda x: -x[1])
        issues.append(issue(
            "outliers", "Unusual numbers to review",
            "Very high or low values in " + ", ".join(f"'{c}' ({n:,})" for c, n in unusual[:3])
            + ". They are NOT changed: they may be real, so check them yourself.", "info", False, fixable=False, count=sum(n for _, n in unusual)))

    order = {"high": 0, "medium": 1, "info": 2}
    return sorted(issues, key=lambda i: (order[i["severity"]], STEPS.index(i["id"]) if i["id"] in STEPS else 99))


def apply_plan(table, selected):
    """(cleaned table, log). `selected` = ids of the issues to fix. The input is never changed."""

    data = table.copy()
    selected = set(selected)
    log = []

    for step in STEPS:

        if step not in selected:
            continue

        if step == "fake_blanks":
            total, cols = 0, 0
            for column in text_columns(data):
                counts = text_counts(data[column])
                fake = list(counts.index[counts.index.str.strip().str.lower().isin(FAKE_BLANKS)])
                if fake:
                    total += int(counts[fake].sum()); cols += 1
                    data[column] = data[column].astype(object).where(~data[column].isin(fake))
            if total:
                log.append(f"Replaced {total:,} placeholders (N/A, null, -) with real blanks in {cols} column(s).")

        elif step == "trim_spaces":
            total = 0
            for column in text_columns(data):
                counts = text_counts(data[column])
                loose = counts[counts.index != counts.index.str.strip()]
                if len(loose):
                    total += int(loose.sum())
                    data[column] = map_values(data[column], {v: v.strip() for v in loose.index})
            if total:
                log.append(f"Removed spaces around the text in {total:,} cells.")

        elif step == "to_number":
            for column in money_columns(data):
                counts = text_counts(data[column])
                data[column] = data[column].map(lambda v, m={u: to_amount(u) for u in counts.index}: m.get(v, v))
                log.append(f"Turned the text amounts in '{column}' into real numbers.")

        elif step == "case":
            total = 0
            for column in category_columns(data):
                mapping = case_map(data[column])
                if mapping:
                    counts = text_counts(data[column])
                    spaced = pd.Series(collapse(counts.index), index=counts.index)
                    change = {raw: mapping[norm] for raw, norm in spaced.items() if norm in mapping}
                    total += int(counts[list(change)].sum())
                    data[column] = map_values(data[column], change)
            if total:
                log.append(f"Made {total:,} cells use the most common spelling (for example 'north' and 'NORTH' became 'North').")

        elif step == "empty_columns":
            blanks_now = blank_mask(data)
            empty = [c for c in data.columns if blanks_now[c].all()]
            if empty:
                data = data.drop(columns=empty)
                log.append(f"Removed {len(empty)} empty column(s): {names(empty)}.")

        elif step == "mostly_blank":
            share = share_blank(data)
            almost = [c for c in data.columns if share[c] >= BLANKY]
            if almost:
                data = data.drop(columns=almost)
                log.append(f"Removed {len(almost)} almost-empty column(s): {names(almost)}.")

        elif step == "constant":
            blanks = blank_mask(data)
            constant = [c for c in data.columns if (~blanks[c]).any()
                        and data[c][~blanks[c]].astype(str).str.strip().nunique() == 1]
            if constant:
                data = data.drop(columns=constant)
                log.append(f"Removed {len(constant)} column(s) with only one value: {names(constant)}.")

        elif step == "blanks_numbers":
            share = share_blank(data)
            filled = 0
            for column in data.columns:
                s = data[column]
                if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s) and 0 < share[column] < BLANKY:
                    n = int(s.isna().sum())
                    data[column] = s.fillna(s.median())
                    filled += n
            if filled:
                log.append(f"Filled {filled:,} blank numbers with the median of their column.")

        elif step == "blanks_text":
            blanks = blank_mask(data)
            share = blanks.mean()
            filled = 0
            for column in text_columns(data):
                if 0 < share[column] < BLANKY:
                    mask = blanks[column]
                    data[column] = data[column].astype(object)
                    data.loc[mask, column] = "Unknown"
                    filled += int(mask.sum())
            if filled:
                log.append(f"Labelled {filled:,} blank text cells 'Unknown'.")

        elif step == "duplicates":
            before = len(data)
            data = data.drop_duplicates().reset_index(drop=True)
            if len(data) < before:
                log.append(f"Removed {before - len(data):,} duplicate rows ({before:,} to {len(data):,} rows).")

    return data, log


def log_text(file_name, before, after, log):
    """The change log people can keep: what was found and what was done."""

    lines = [
        f"Datalyst cleaning log for {file_name}", "",
        f"Before: {before['rows']:,} rows, {before['columns']} columns, {before['blank_cells']:,} blank cells, "
        f"{before['duplicate_rows']:,} duplicate rows",
        f"After:  {after['rows']:,} rows, {after['columns']} columns, {after['blank_cells']:,} blank cells, "
        f"{after['duplicate_rows']:,} duplicate rows", "", "What was changed:",
    ]
    lines += [f"  - {item}" for item in log] or ["  - nothing was changed"]
    lines += ["", "Your original file was not modified."]
    return "\n".join(lines)


def history_text(file_name, original, steps):
    """The change log across ALL cleaning steps, from the original file to now.

    original: summary() of the original table. steps: [{"log": [...], "after": summary()}, ...]
    """

    now = steps[-1]["after"] if steps else original

    lines = [
        f"Datalyst cleaning log for {file_name}", "",
        f"Original file: {original['rows']:,} rows, {original['columns']} columns, {original['blank_cells']:,} blank cells, "
        f"{original['duplicate_rows']:,} duplicate rows",
        f"Now:           {now['rows']:,} rows, {now['columns']} columns, {now['blank_cells']:,} blank cells, "
        f"{now['duplicate_rows']:,} duplicate rows", "",
    ]

    for number, step in enumerate(steps, start=1):
        lines.append(f"Step {number}:")
        lines += [f"  - {item}" for item in step["log"]] or ["  - nothing was changed"]

    lines += ["", "Your original file was not modified."]
    return "\n".join(lines)
