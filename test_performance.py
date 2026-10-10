"""
PERFORMANCE GATES: it must stay fast and light, not only correct.

Time and memory budgets for the things people do. The budgets are generous (a slow laptop passes);
a result that is 3x slower than it should be fails.

    python test_performance.py            (about 1 minute, 100,000 rows)
    python test_performance.py big        (500,000 rows, for a long final audit)
"""
import io
import resource
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import analyst_data
import cleaning as cl
import dashboard as dash
import file_reader as fr
import insights as ins
import make_demo_files
import question_understanding as qu
from ask_engine import AskEngine

BIG = len(sys.argv) > 1 and sys.argv[1] == "big"
ROWS = 500_000 if BIG else 100_000
SCALE = 3 if BIG else 1

failed, passed = [], 0
rows_out = []


def rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / (1024 * 1024) if sys.platform == "darwin" else usage / 1024


def gate(name, seconds, budget):
    global passed
    rows_out.append(f"  {name:44s} {seconds:6.2f}s  (budget {budget * SCALE:.0f}s)")
    if seconds <= budget * SCALE:
        passed += 1
    else:
        failed.append(f"{name}: {seconds:.1f}s is over the {budget * SCALE:.0f}s budget")


def timed(function):
    started = time.time()
    value = function()
    return value, time.time() - started


# a realistic table of the size we test: sales with dates, categories, numbers and some blanks
rng = np.random.default_rng(7)
retail = analyst_data.BUILDERS["retail"]()[0]
frame = pd.concat([retail] * (ROWS // len(retail) + 1), ignore_index=True).head(ROWS)
frame["order_id"] = np.arange(len(frame))
csv_bytes = frame.to_csv(index=False).encode()
print(f"{ROWS:,} rows x {frame.shape[1]} columns, {len(csv_bytes) / 1e6:.1f} MB as a CSV")
start_mb = rss_mb()

(table, info), t = timed(lambda: fr.read_table("big.csv", csv_bytes)); gate("read the CSV file", t, 6)
engine, t = timed(lambda: AskEngine(table)); gate("open the file (profile, types, dimensions)", t, 12)
_, t = timed(lambda: dash.build_dashboard(engine)); gate("build the dashboard", t, 6)
_, t = timed(lambda: ins.build_insights(engine)); gate("build the insights", t, 8)

measure = engine.profile.get("revenue_column") or list(engine.profile["measures"])[0]
label = measure.replace("_", " ")
questions = [f"What is the median {label}?", f"What is the 90th percentile of {label}?", f"What is the range of {label}?",
             f"How many orders are above the average {label}?", f"Which year had the highest {label}?",
             f"Which day of the week has the highest {label}?", f"What is the correlation between {label} and profit?"]
_, t = timed(lambda: [engine.ask(q) for q in questions]); gate(f"{len(questions)} advanced questions", t, 12)

qu.QuestionUnderstanding.understand = lambda self, q: dict(intent="breakdown", column=measure, group_column="category", value_column=measure, filter_value=None, operation="sum")
_, t = timed(lambda: [engine.ask("Show revenue by category") for _ in range(5)]); gate("5 breakdown questions (AI stand-in)", t, 6)

messy = pd.concat([make_demo_files.messy_retail()] * (ROWS // 12120 + 1), ignore_index=True).head(ROWS)
issues, t = timed(lambda: cl.diagnose(messy)); gate("find the cleaning problems", t, 12)
(cleaned, log), t = timed(lambda: cl.apply_plan(messy, [i["id"] for i in issues if i["default_on"]])); gate("apply the cleaning fixes", t, 20)
_, t = timed(lambda: cl.to_csv_bytes(cleaned)); gate("save the cleaned CSV", t, 8)

grown = rss_mb() - start_mb
rows_out.append(f"  {'memory added while doing all of the above':44s} {grown:6.0f} MB (budget {1800 * SCALE} MB)")
if grown <= 1800 * SCALE:
    passed += 1
else:
    failed.append(f"memory grew by {grown:.0f} MB")

print("\n".join(rows_out))
print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed:
    print("  FAIL:", f)
