"""
PIN TEST (no AI, seconds): an answer pinned to the dashboard must show the SAME numbers.
Filtered answers, single numbers, duplicates and a full dashboard must be refused.

    python test_pin.py
"""
import warnings
warnings.filterwarnings("ignore")

import pandas as pd

import analyst_data
import builder as bd
from ask_engine import AskEngine
from question_understanding import QuestionUnderstanding

passed, failed = 0, []


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


def close(a, b):
    return abs(float(a) - float(b)) <= 1e-6 * max(1, abs(float(b)))


def run(name, df, measure, dim, date):
    e = AskEngine(df.copy())
    info = bd.dataset_info(e)
    view = info["df"]

    def ask(question, **plan):
        base = dict(intent="total", column=measure, group_column=None, value_column=measure, filter_value=None, operation="sum")
        base.update(plan)
        QuestionUnderstanding.understand = lambda self, q: dict(base)
        return e.ask(question)

    label = measure.replace("_", " ")

    # ---- breakdowns, rankings and trends become charts with the same numbers
    for kind, question, plan in [
        ("breakdown sum", f"Show {label} by {dim}", dict(intent="breakdown", group_column=dim, operation="sum")),
        ("breakdown mean", f"Show average {label} by {dim}", dict(intent="breakdown", group_column=dim, operation="average")),
        ("top", f"Which {dim} has the highest {label}?", dict(intent="top", group_column=dim, operation="group_sum")),
        ("bottom", f"Which {dim} has the lowest {label}?", dict(intent="bottom", group_column=dim, operation="group_sum")),
    ]:
        a = ask(question, **plan)
        tile, why = bd.tile_from_answer(a, info)
        check(tile is not None, f"{name}: {kind} could not be pinned: {why}")
        if tile is None:
            continue
        out = bd.compute_tile(view, dict(tile, top=50), info)
        check(out["kind"] == "groups", f"{name}: {kind} tile is not a group chart: {out['kind']}")
        if out["kind"] != "groups":
            continue
        truth = view.groupby(dim)[measure].agg("mean" if kind == "breakdown mean" else "sum")
        check(all(close(out["values"][str(k)], v) for k, v in truth.items() if str(k) in out["values"]) and len(out["values"]) == len(truth),
              f"{name}: {kind} pinned numbers differ from pandas")
        if kind in ("top", "bottom") and isinstance(a["result"], tuple):
            check(close(out["values"][str(a["result"][0])], a["result"][1]), f"{name}: {kind} pinned value differs from the answer")

    a = ask(f"Show me monthly {label}", intent="trend", group_column=date, operation="time_series")
    tile, why = bd.tile_from_answer(a, info)
    check(tile is not None and tile["type"] == "line", f"{name}: trend not pinned: {why}")
    if tile:
        out = bd.compute_tile(view, tile, info, {"grain": "M"})
        common = [k for k in a["result"] if k in out.get("months", {})]
        check(out["kind"] == "line" and len(common) >= 6 and all(close(out["months"][k], a["result"][k]) for k in common), f"{name}: trend pinned numbers differ from the answer")

    # ---- refused, with a reason
    first = list(view[dim].astype(str).value_counts().index)[0]
    a = ask(f"Show {label} by {dim} for {first}", intent="breakdown", group_column=dim, operation="sum", filter_value=first)
    if a["status"] == "success" and (a["plan"].get("filters") or a["plan"].get("filter_value")):
        t, why = bd.tile_from_answer(a, info)
        check(t is None and "filter" in why, f"{name}: a filtered answer was pinned")
    a = ask(f"What is the total {label}?")
    t, why = bd.tile_from_answer(a, info)
    check(t is None and "single number" in why or t is None, f"{name}: a single number was pinned")
    a = ask(f"Show {label} by {dim}", intent="breakdown", group_column=dim, operation="sum")
    t, _ = bd.tile_from_answer(a, info)
    t2, why = bd.tile_from_answer(a, info, existing=[t])
    check(t2 is None and "already" in why, f"{name}: a duplicate was pinned")
    t3, why = bd.tile_from_answer(a, info, existing=[dict(id=str(i), type="kpi") for i in range(bd.MAX_TILES)])
    check(t3 is None and "full" in why, f"{name}: pinned to a full dashboard")
    check(bd.tile_from_answer({"status": "error"}, info)[0] is None, f"{name}: pinned an error")


ecommerce = pd.read_csv("ecommerce_sales_34500.csv")
run("ecommerce", ecommerce, "total_amount", "category", "order_date")
for builder, measure, dim, date in [("retail", "revenue", "category", "order_date"), ("marketing", "revenue", "campaign", "date"), ("ops", "cost", "carrier", "ship_date")]:
    frame, _ = analyst_data.BUILDERS[builder]()
    run(builder, frame, measure, dim, date)

print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed[:12]:
    print("  FAIL:", f)
