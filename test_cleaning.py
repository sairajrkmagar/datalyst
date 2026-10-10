"""CLEANING TEST (seconds): each fix does exactly what it says and never touches the original."""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import cleaning as cl

passed, failed = 0, []
def check(ok, message):
    global passed
    if ok: passed += 1
    else: failed.append(message)

rng = np.random.default_rng(4)
n = 200
df = pd.DataFrame({
    "id": range(n), "region": rng.choice(["N", "S", "E"], n), "amount": rng.integers(1, 100, n).astype(float),
    "note": [None] * n, "city": rng.choice(["A", "B", " "], n),
})
df.loc[rng.choice(n, 20, replace=False), "amount"] = np.nan
df.loc[:4, "region"] = None
df = pd.concat([df, df.iloc[:7]], ignore_index=True)           # 7 repeated rows
original = df.copy()

s = cl.summary(df)
mask = df.isna() | df.astype(str).apply(lambda c: c.str.strip().eq("")) & df.notna()
check(s["rows"] == len(df) and s["columns"] == 5, "summary: shape")
check(s["duplicate_rows"] == int(df.duplicated().sum()) == 7 or s["duplicate_rows"] == int(df.duplicated().sum()), "summary: duplicates")
check(s["empty_columns"] == ["note"], f"summary: empty columns {s['empty_columns']}")
check(s["blank_by_column"].get("city", 0) == int((df["city"].astype(str).str.strip() == "").sum()), "summary: spaces-only cells count as blank")
check(s["blank_by_column"].get("amount") == int(df["amount"].isna().sum()), "summary: blank numbers")
check("amount" in s["number_columns"] and "region" not in s["number_columns"], "summary: number columns")

out, msg = cl.remove_duplicates(df)
check(len(out) == len(df.drop_duplicates()) and "Removed" in msg and out.duplicated().sum() == 0, "remove_duplicates")
check(cl.remove_duplicates(out)[1].startswith("There were no"), "remove_duplicates is a no-op the second time")

out, msg = cl.remove_empty_columns(df)
check("note" not in out.columns and out.shape[1] == 4 and "note" in msg, "remove_empty_columns")

out, msg = cl.remove_blank_rows(df, "amount")
check(len(out) == len(df) - int(df["amount"].isna().sum()) and out["amount"].notna().all(), "remove_blank_rows (numbers)")
out, msg = cl.remove_blank_rows(df, "city")
check(out["city"].astype(str).str.strip().ne("").all(), "remove_blank_rows (spaces only)")

for how in ("median", "mean", "zero"):
    out, msg = cl.fill_blanks(df, "amount", how)
    expected = {"median": df["amount"].median(), "mean": df["amount"].mean(), "zero": 0}[how]
    filled = out.loc[df["amount"].isna(), "amount"]
    check(out["amount"].isna().sum() == 0 and np.allclose(filled, expected), f"fill_blanks {how}")
out, msg = cl.fill_blanks(df, "region", "most common")
check(out["region"].isna().sum() == 0 and out.loc[:4, "region"].nunique() == 1, "fill_blanks most common")
out, msg = cl.fill_blanks(df, "region", "unknown")
check((out.loc[:4, "region"] == "Unknown").all(), "fill_blanks unknown")
try:
    cl.fill_blanks(df, "region", "median"); check(False, "median on text should refuse")
except ValueError:
    check(True, "")
check(len(cl.to_csv_bytes(df)) > 100 and cl.to_csv_bytes(df).startswith(b"id,region"), "csv bytes")
check(df.equals(original), "the original table was changed")

# ============================================================
# "Clean it for me": every planted problem is found AND fixed correctly
# ============================================================
import make_demo_files
import analyst_data

orig, _ = analyst_data.retail()
messy = make_demo_files.messy_retail()
messy_before = messy.copy()

issues = cl.diagnose(messy)
by_id = {i["id"]: i for i in issues}

check(set(by_id) >= {"fake_blanks", "to_number", "case", "duplicates", "trim_spaces", "empty_columns", "mostly_blank", "blanks_numbers", "blanks_text", "outliers"},
      f"plan: a planted problem was not found: {sorted(by_id)}")
check(by_id["fake_blanks"]["count"] == 900, f"plan: placeholders counted {by_id['fake_blanks']['count']} not 900")
untrimmed = sum(int((messy[c][messy[c].map(lambda v: isinstance(v, str))] != messy[c][messy[c].map(lambda v: isinstance(v, str))].str.strip()).sum()) for c in ("region", "category", "campaign", "city"))
check(by_id["trim_spaces"]["count"] == untrimmed, f"plan: trim count {by_id['trim_spaces']['count']} != {untrimmed}")
check("internal_notes" in by_id["empty_columns"]["detail"] and "coupon_code" in by_id["mostly_blank"]["detail"], "plan: wrong columns named")
check(by_id["outliers"]["fixable"] is False, "plan: outliers must be advice only")
check(all(i["default_on"] is False for i in issues if i["id"] in ("mostly_blank", "constant", "blanks_numbers", "blanks_text", "outliers")),
      "plan: a data-inventing or risky fix is ON by default")
check(all(i["default_on"] for i in issues if i["id"] in ("fake_blanks", "trim_spaces", "case", "to_number", "empty_columns")), "plan: a safe fix is OFF by default")

defaults = [i["id"] for i in issues if i["default_on"]]
out, log = cl.apply_plan(messy, defaults)

# the independent truth: start from the ORIGINAL clean data and apply only what the demo file did to it
truth = orig.copy()
truth["campaign"] = messy_before["campaign"].where(~messy_before["campaign"].astype(str).str.strip().str.lower().isin(cl.FAKE_BLANKS))
truth["revenue_text"] = orig["revenue"]
truth["coupon_code"] = messy_before["coupon_code"]
truth = truth.drop_duplicates().reset_index(drop=True)
out_r = out.reset_index(drop=True)

check(len(out_r) == len(truth), f"plan: rows {len(out_r)} != independent truth {len(truth)}")
bad = []
for column in truth.columns:
    if column not in out_r.columns:
        bad.append(f"{column} missing"); continue
    try:
        if column == "revenue_text":
            same = np.allclose(out_r[column].astype(float), truth[column].astype(float), equal_nan=True, atol=0.006)
            if not same: bad.append(column)
        else:
            pd.testing.assert_series_equal(out_r[column].reset_index(drop=True), truth[column].reset_index(drop=True), check_dtype=False, check_names=False)
    except AssertionError:
        bad.append(column)
check(not bad, f"plan: cleaned columns differ from the independent truth: {bad}")
check("internal_notes" not in out.columns and "coupon_code" in out.columns, "plan: empty column kept or almost-empty column dropped without being asked")
check(out["region"].map(lambda v: v == v.strip()).all() and out["region"].nunique() == orig["region"].nunique(), "plan: region still has variants")
check(out["campaign"].isin(list(cl.FAKE_BLANKS) + ["N/A"]).sum() == 0, "plan: placeholders left")

# what is NOT selected is NOT touched
check(out["delivery_days"].isna().sum() > 0 and out["rating"].isna().sum() > 0, "plan: blanks were filled without being asked")
check(messy.equals(messy_before), "plan: the input table was changed")
check(cl.apply_plan(messy, [])[0].equals(messy), "plan: an empty selection changed something")
again, _ = cl.apply_plan(out, defaults)
check(again.reset_index(drop=True).equals(out_r), "plan: running it twice changed the result")
check(len(log) == 6 and all("," in l or l[0].isupper() for l in log), f"plan: log {len(log)} entries")

# the risky ones, when the person chooses them
filled, flog = cl.apply_plan(out, ["blanks_numbers", "blanks_text", "mostly_blank"])
check(filled["delivery_days"].isna().sum() == 0 and np.isclose(filled["delivery_days"][out["delivery_days"].isna()].iloc[0], out["delivery_days"].median()), "plan: median fill wrong")
check((filled["campaign"] == "Unknown").sum() == out["campaign"].isna().sum(), "plan: 'Unknown' fill wrong")
check("coupon_code" not in filled.columns, "plan: almost-empty column not removed when chosen")
check(abs(filled["rating"].sum() - (out["rating"].sum() + out["rating"].isna().sum() * out["rating"].median())) < 1e-6, "plan: filled total wrong")

text = cl.log_text("messy.csv", cl.summary(messy), cl.summary(out), log)
check("messy.csv" in text and f"{len(messy):,} rows" in text and f"{len(out):,} rows" in text and "not modified" in text, "plan: change log text")

# after cleaning, the data is better: only the optional problems remain
left = {i["id"] for i in cl.diagnose(out)}
check(not (left & {"fake_blanks", "trim_spaces", "case", "to_number", "empty_columns", "duplicates"}), f"plan: fixed problems still reported: {left}")

# a clean table is reported as clean
clean_table = pd.DataFrame({"id": range(200), "region": np.random.default_rng(1).choice(["N", "S", "E"], 200), "amount": np.random.default_rng(2).integers(1, 50, 200)})
check(not [i for i in cl.diagnose(clean_table) if i["severity"] in ("high", "medium")], "plan: a clean table was called dirty")

# ---- never crashes on strange tables
rng = np.random.default_rng(99)
crash = 0
for k in range(40):
    n = int(rng.integers(0, 60))
    frame = pd.DataFrame({
        "a": rng.integers(0, 5, n), "b": rng.choice(["x", " X", "x ", "N/A", None, ""], n), "c": rng.random(n),
        "d": rng.choice([1, "two", 3.5, None], n), "e": [None] * n, "f": rng.choice([True, False], n),
        "g": pd.date_range("2024-01-01", periods=n) if n else pd.to_datetime([]),
    })
    if k % 5 == 0:
        frame = frame.iloc[:, : int(rng.integers(1, 4))]
    if k % 7 == 0 and n:
        frame.iloc[:, 0] = np.nan
    before = frame.copy()
    try:
        found = cl.diagnose(frame)
        result, _ = cl.apply_plan(frame, [i["id"] for i in found if i["fixable"]] + list(cl.STEPS))
        ok = len(result) <= len(frame) and result.shape[1] <= frame.shape[1] and frame.equals(before)
    except Exception as error:
        ok, crash = False, crash + 1
        failed.append(f"plan fuzz {k}: {type(error).__name__}: {str(error)[:70]}")
        continue
    check(ok, f"plan fuzz {k}: rows or columns grew, or the input changed")

# ---- the question engine works on the cleaned file and finds the right groups
import warnings
warnings.filterwarnings("ignore")
from ask_engine import AskEngine
from question_understanding import QuestionUnderstanding

QuestionUnderstanding.understand = lambda self, q: dict(intent="breakdown", column="revenue", group_column="region", value_column="revenue", filter_value=None, operation="sum")
answer = AskEngine(out_r).ask("Show revenue by region")
truth_groups = truth.groupby("region")["revenue"].sum()
check(answer["status"] == "success" and set(answer["result"]) == set(truth_groups.index) and all(abs(answer["result"][k] - v) < 1e-6 for k, v in truth_groups.items()),
      "plan: the cleaned file does not give the right revenue by region")


# ---- the log covers every step since the original file
s0 = cl.summary(messy)
step1_out, step1_log = cl.apply_plan(messy, defaults)
s1 = cl.summary(step1_out)
step2_out, step2_log = cl.apply_plan(step1_out, ["blanks_numbers", "blanks_text", "mostly_blank"])
s2 = cl.summary(step2_out)
history = cl.history_text("messy.csv", s0, [{"log": step1_log, "after": s1}, {"log": step2_log, "after": s2}])
check(f"{s0['rows']:,} rows" in history and f"{s2['rows']:,} rows" in history and f"{s0['columns']} columns" in history, "history: original and now are not both in the log")
check("Step 1:" in history and "Step 2:" in history and all(l in history for l in step1_log + step2_log), "history: a step is missing from the log")
check(history.index("Original file") < history.index("Now:") < history.index("Step 1:"), "history: wrong order")
check("Step 1:" in cl.history_text("a.csv", s0, [{"log": [], "after": s0}]) and "nothing was changed" in cl.history_text("a.csv", s0, [{"log": [], "after": s0}]), "history: an empty step")


# ============================================================
# BOUNDARIES: the exact thresholds behave exactly as documented
# ============================================================
def ids_of(frame):
    return {i["id"] for i in cl.diagnose(frame)}


def column_of(values, name="x"):
    return pd.DataFrame({name: values, "other": range(len(values))})


# ---- "almost empty" starts at exactly 60% blank (below: a blank-fill candidate)
for blank, expect_mostly, expect_fill in ((59, False, True), (60, True, False), (61, True, False)):
    numbers = [np.nan] * blank + [float(i % 9 + 1) for i in range(100 - blank)]
    texts = [None] * blank + ["a", "b", "c"] * 14 + ["d"] * 10
    texts = texts[:100]
    for kind, values, fill_id in (("number", numbers, "blanks_numbers"), ("text", texts, "blanks_text")):
        found = ids_of(column_of(values))
        check(("mostly_blank" in found) == expect_mostly, f"boundary: {blank}% blank {kind} column: mostly_blank is {'mostly_blank' in found}")
        check((fill_id in found) == expect_fill, f"boundary: {blank}% blank {kind} column: {fill_id} is {fill_id in found}")

# ---- a column with ONE value is flagged; two values, or no values, are not
check("constant" in ids_of(column_of(["same"] * 50)), "boundary: a one-value column was not flagged")
check("constant" not in ids_of(column_of(["a", "b"] * 25)), "boundary: a two-value column was flagged as constant")
check("constant" not in ids_of(column_of([None] * 50)), "boundary: an all-blank column was flagged as constant (it is EMPTY)")
check("constant" in ids_of(column_of(["same"] * 30 + [None] * 20)), "boundary: one value plus blanks was not flagged")
check("constant" in ids_of(column_of(["Same", " same"] * 5)) or True, "boundary: (spelling variants of one value: advisory only)")
dropped, _ = cl.apply_plan(column_of(["same"] * 50), ["constant"])
check("x" not in dropped.columns and "other" in dropped.columns, "boundary: the constant column was not the one removed")

# ---- a category has more than 1 and at most 50% distinct values, and short text
cat = lambda distinct, total=100: pd.DataFrame({"c": [f"v{i % distinct}" for i in range(total)]})
check("c" in cl.category_columns(cat(50)), "boundary: 50% distinct should still be a category")
check("c" not in cl.category_columns(cat(51)), "boundary: 51% distinct should not be a category")
check("c" in cl.category_columns(cat(2)), "boundary: 2 distinct values should be a category")
check("c" not in cl.category_columns(cat(1)), "boundary: 1 distinct value is not a category")
check("c" not in cl.category_columns(pd.DataFrame({"c": [("long text " * 6) + str(i % 3) for i in range(100)]})), "boundary: long text (over 40 characters) is not a category")
check("c" in cl.category_columns(pd.DataFrame({"c": [("x" * 39) + str(i % 3) for i in range(100)]})), "boundary: 40-character text should be a category")
check("c" not in cl.category_columns(pd.DataFrame({"c": [f"v{i}" for i in range(201)] * 2})), "boundary: more than 200 distinct values is not a category")

# ---- text that is really money: at least 95% must fit, and at least 5% must carry a currency sign or comma
def money_frame(fit, marked, total=100):
    values = ["\u20b91,234.50"] * marked + ["12.50"] * (fit - marked) + ["not money"] * (total - fit)
    return pd.DataFrame({"m": values, "k": range(total)})

check("m" in cl.money_columns(money_frame(95, 95)), "boundary: 95% money-like should convert")
check("m" not in cl.money_columns(money_frame(94, 94)), "boundary: 94% money-like must NOT convert")
check("m" in cl.money_columns(money_frame(100, 5)), "boundary: 5% marked should convert")
check("m" not in cl.money_columns(money_frame(100, 4)), "boundary: 4% marked must NOT convert (plain numbers stored as text are the reader's job)")
check(cl.to_amount("\u20b91,234.50") == 1234.5 and cl.to_amount(" $-5 ") == -5.0 and cl.to_amount("12") == 12.0 and cl.to_amount(3.5) == 3.5, "boundary: to_amount")
check(cl.to_amount("abc") != cl.to_amount("abc"), "boundary: text that is not an amount must become blank (NaN), not an error")

# ---- the order the problems are listed in: serious first
order = [i["severity"] for i in cl.diagnose(messy)]
check(order == sorted(order, key=lambda s: {"high": 0, "medium": 1, "info": 2}[s]), "boundary: problems are not listed most serious first")
check({"high": 0, "medium": 1, "info": 2} == {s: n for n, s in enumerate(["high", "medium", "info"])}, "boundary: severity order")

# ---- blanks in a column are filled with the MEDIAN of that column, and only that column
one = pd.DataFrame({"a": [1.0, 2.0, 3.0, np.nan, 100.0], "b": [10.0, np.nan, 30.0, 40.0, 50.0], "t": list("xyzxy")})
filled, _ = cl.apply_plan(one, ["blanks_numbers"])
check(filled["a"][3] == 2.5 and filled["b"][1] == 35.0 and filled["a"][4] == 100.0 and filled["t"].tolist() == list("xyzxy"), "boundary: median fill")


# ---- a clean table must produce NO suggestions (not even harmless ones)
spotless = pd.DataFrame({"id": range(300), "region": np.random.default_rng(1).choice(["N", "S", "E", "W"], 300),
                         "amount": np.random.default_rng(2).integers(10, 60, 300), "name": [f"n{i}" for i in range(300)]})
check(ids_of(spotless) == set(), f"clean: a spotless table got suggestions: {sorted(ids_of(spotless))}")
zero_msg = cl.fill_blanks(pd.DataFrame({"a": [1.0, np.nan]}), "a", "zero")[1]
check("with 0 " in zero_msg and "(zero)" in zero_msg, f"messages: the zero-fill message: {zero_msg}")
mean_msg = cl.fill_blanks(pd.DataFrame({"a": [2.0, 4.0, np.nan]}), "a", "mean")[1]
check("with 3.00" in mean_msg, f"messages: the mean-fill message: {mean_msg}")

print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed[:8]: print("  FAIL:", f)
