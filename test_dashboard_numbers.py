"""
Checks every number on the Dashboard and Insights pages against an
independent calculation written directly in pandas (no AI, no app code
for the arithmetic). Run:  python test_dashboard_numbers.py <file.csv>
"""
import re
import sys
import warnings

import pandas as pd

warnings.filterwarnings("ignore")

from ask_engine import AskEngine
from dashboard import build_dashboard, main_measure, uses_total, groupable_dims
from insights import build_insights
from filters import to_dates

path = sys.argv[1]
engine = AskEngine(pd.read_csv(path))
typed = engine.df
dash = build_dashboard(engine)
items = build_insights(engine)

passed, failed = 0, []


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(f"{name}  {detail}")


close = lambda a, b: abs(float(a) - float(b)) <= 1e-6 * max(1, abs(float(b)))

measure = main_measure(engine)
kind = "sum" if measure and uses_total(measure) else "mean"

# ---- basic counts
check("rows", dash["rows"] == len(typed))
check("columns", dash["columns"] == len(typed.columns))
check("missing", dash["missing"] == int(typed.isnull().sum().sum()))
check("duplicates", dash["duplicates"] == int(typed.duplicated().sum()))
check("completeness", close(dash["completeness"], 100 * (1 - typed.isnull().sum().sum() / typed.size)))

# ---- headline KPI
if measure:
    values = typed[measure].dropna()
    expected = values.sum() if kind == "sum" else values.mean()
    shown = dash["kpis"][0]["full"].replace(",", "")
    check("headline KPI", close(shown, round(expected, 2)) or close(shown, expected), f"{shown} vs {expected}")

# ---- bar chart = independent groupby
if dash["bar"]:
    dim = dash["bar"]["dim"]
    if dash["bar"]["agg"] == "count":
        ref = typed.groupby(dim).size()
    elif dash["bar"]["agg"] == "sum":
        ref = typed.groupby(dim)[measure].sum()
    else:
        ref = typed.groupby(dim)[measure].mean()
    ref = ref.sort_values(ascending=False).head(8)
    got = dash["bar"]["values"]
    check("bar: same groups", set(map(str, ref.index)) == set(map(str, got)), f"{list(ref.index)} vs {list(got)}")
    for k, v in got.items():
        check(f"bar value {k}", close(v, ref[k] if k in ref.index else ref[[i for i in ref.index if str(i) == str(k)][0]]))

# ---- donut = independent counts, adds up to all rows
if dash["donut"]:
    dim = dash["donut"]["dim"]
    counts = typed[dim].value_counts()
    got = dash["donut"]["values"]
    check("donut: adds up to all rows", close(sum(got.values()), counts.sum()), f"{sum(got.values())} vs {counts.sum()}")
    for k, v in got.items():
        if k != "Other":
            check(f"donut value {k}", close(v, counts[k]))

# ---- trend: every month vs pandas resample; partly covered months excluded
if dash["trend"]:
    col = dash["trend"]["column"]
    stamps = to_dates(typed[col])
    frame = pd.DataFrame({"d": stamps, "v": typed[measure] if measure else 1}).dropna(subset=["d"])
    monthly = frame.set_index("d")["v"].resample("MS")
    ref = monthly.sum() if (kind == "sum" or not measure) else monthly.mean()
    for month, value in dash["trend"]["months"].items():
        check(f"trend {month}", close(value, ref[pd.Timestamp(month + "-01")]))
    check("trend left-out months are the first/last",
          all(m in (min(ref.index).strftime("%Y-%m"), max(ref.index).strftime("%Y-%m")) for m in dash["trend"]["left_out"]),
          str(dash["trend"]["left_out"]))

# ---- insights: re-derive the leader sentences
text_all = " ".join(i["text"] for i in items)
dims = groupable_dims(engine)
if dims and measure and kind == "sum":
    ref = typed.groupby(dims[0])[measure].sum().sort_values(ascending=False)
    top, share = ref.index[0], ref.iloc[0] / ref.sum() * 100
    check("insight: leader named", str(top) in text_all)
    check("insight: leader share", f"{share:.1f}%" in text_all, f"expected {share:.1f}%")
    low, lshare = ref.index[-1], ref.iloc[-1] / ref.sum() * 100
    check("insight: smallest share", f"{lshare:.1f}%" in text_all, f"expected {lshare:.1f}%")
miss = int(typed.isnull().sum().sum()); dup = int(typed.duplicated().sum())
if miss or dup:
    check("insight: missing/duplicates", f"{miss:,} missing" in text_all and f"{dup:,} duplicate" in text_all)

print(f"{path}: {passed} checks passed, {len(failed)} FAILED")
for f in failed:
    print("   FAIL:", f)
