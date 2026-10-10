"""
CLEANING FUZZ TEST: 150 random messy tables, and rules that must ALWAYS hold.

  - the table you give is never changed
  - cleaning never adds rows or columns
  - cleaning twice gives the same result as cleaning once
  - every problem it fixes is really gone afterwards
  - number columns are untouched (same values) unless you ask to fill blanks
  - a cleaned file saved and re-read is still clean

    python test_cleaning_fuzz.py            (about 40 seconds)
    python test_cleaning_fuzz.py 400 7      (tables, random seed)
"""
import io
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import cleaning as cl
import file_reader as fr

TABLES = int(sys.argv[1]) if len(sys.argv) > 1 else 150
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1

passed, failed = 0, []


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


WORDS = ["North", "South", "East", "West", "Central", "Alpha", "Beta", "Gamma", "Delta"]
PLACEHOLDERS = ["N/A", "-", "null", "missing", "n/a", "--", "?"]
SAFE_ON = {"fake_blanks", "trim_spaces", "case", "to_number", "empty_columns", "duplicates"}


def random_table(rng):
    n = int(rng.integers(8, 500))
    data = {}
    for i in range(int(rng.integers(2, 10))):
        kind = rng.choice(["cat", "num", "money", "date", "id", "text", "bool", "mixed", "empty", "const", "float"])
        name = f"{kind}_{i}" if rng.random() < 0.7 else f"Col {i} ({kind})"
        if kind == "cat":
            values = rng.choice(WORDS[: int(rng.integers(2, 7))], n).astype(object)
            for j in rng.choice(n, int(n * rng.random() * 0.4), replace=False):
                values[j] = [values[j].lower(), values[j].upper(), f" {values[j]} ", values[j] + "  "][int(rng.integers(4))]
            for j in rng.choice(n, int(n * rng.random() * 0.15), replace=False):
                values[j] = PLACEHOLDERS[int(rng.integers(len(PLACEHOLDERS)))]
            for j in rng.choice(n, int(n * rng.random() * 0.1), replace=False):
                values[j] = None
        elif kind == "num":
            values = rng.integers(0, 500, n).astype(float)
            values[rng.choice(n, int(n * rng.random() * 0.3), replace=False)] = np.nan
        elif kind == "float":
            values = rng.normal(100, 30, n)
        elif kind == "money":
            values = np.array(["\u20b9" + format(v, ",.2f") for v in rng.random(n) * 5000], dtype=object)
            values[rng.choice(n, int(n * 0.05), replace=False)] = ""
        elif kind == "date":
            values = pd.date_range("2024-01-01", periods=n).astype(str).values.astype(object)
        elif kind == "id":
            values = np.array([f"ID{i:05d}" for i in range(n)], dtype=object)
        elif kind == "text":
            values = rng.choice(["a long free text comment number " + str(k) for k in range(n)], n)
        elif kind == "bool":
            values = rng.choice(["Yes", "No", "yes", " NO "], n).astype(object)
        elif kind == "mixed":
            values = rng.choice([1, "two", 3.5, None, "N/A"], n).astype(object)
        elif kind == "empty":
            values = np.full(n, np.nan)
        else:
            values = np.full(n, "same")
        data[name] = values
    frame = pd.DataFrame(data)
    if rng.random() < 0.5 and n > 3:
        frame = pd.concat([frame, frame.iloc[rng.choice(n, int(rng.integers(1, max(2, n // 6))))]], ignore_index=True)
    return frame


def same(a, b):
    return a.reset_index(drop=True).astype(object).where(a.reset_index(drop=True).notna(), None).equals(
        b.reset_index(drop=True).astype(object).where(b.reset_index(drop=True).notna(), None))


for k in range(TABLES):
    rng = np.random.default_rng(SEED * 10_007 + k)
    table = random_table(rng)
    before = table.copy(deep=True)
    tag = f"table {k} {table.shape}"

    try:
        issues = cl.diagnose(table)
        ids = [i["id"] for i in issues if i["default_on"]]
        out, log = cl.apply_plan(table, ids)
    except Exception as error:
        check(False, f"{tag}: crashed: {type(error).__name__}: {str(error)[:90]}")
        continue

    check(same(table, before) and list(table.columns) == list(before.columns), f"{tag}: the input table was changed")
    check(len(out) <= len(table) and out.shape[1] <= table.shape[1], f"{tag}: rows or columns grew")
    check(all(isinstance(line, str) and line for line in log), f"{tag}: bad log lines")

    again, _ = cl.apply_plan(out, ids)
    check(same(out, again), f"{tag}: cleaning twice is not the same as cleaning once")

    left = {i["id"] for i in cl.diagnose(out)}
    check(not (left & SAFE_ON), f"{tag}: problems still reported after fixing them: {sorted(left & SAFE_ON)}")

    # number columns that were already numbers are untouched when nothing asks to fill them (and no row is dropped)
    keep = [i for i in ids if i != "duplicates"]
    kept, _ = cl.apply_plan(table, keep)
    check(len(kept) == len(table), f"{tag}: rows changed without the duplicates fix")
    for column in table.columns:
        if column in kept.columns and pd.api.types.is_numeric_dtype(table[column]) and not pd.api.types.is_bool_dtype(table[column]):
            ok = np.array_equal(table[column].to_numpy(dtype=float, na_value=np.nan), kept[column].to_numpy(dtype=float, na_value=np.nan), equal_nan=True)
            check(ok, f"{tag}: the number column '{column}' was changed")

    # categories: after cleaning no two spellings of the same word remain
    for column in out.columns:
        if column in cl.category_columns(out):
            values = out[column].dropna().astype(str)
            check(values.str.strip().str.lower().nunique() == values.nunique() or values.str.strip().str.lower().nunique() >= values.nunique() - 0, f"{tag}: '{column}' still has spellings of the same word")
            check((values == values.str.strip()).all(), f"{tag}: '{column}' still has spaces at the ends")

    # save, re-read, and it is still clean
    if len(out) and out.shape[1]:
        try:
            reread, _ = fr.read_table("cleaned.csv", cl.to_csv_bytes(out))
            left = {i["id"] for i in cl.diagnose(reread)}
            check(not (left & {"fake_blanks", "trim_spaces", "case", "empty_columns"}), f"{tag}: not clean after saving and re-reading: {sorted(left)}")
        except fr.FileProblem:
            pass                                    # an all-empty result is allowed to be refused as a file

print(f"{passed + len(failed)} checks, {len(failed)} FAILED  ({TABLES} random tables)")
for f in failed[:12]:
    print("  FAIL:", f[:230])
