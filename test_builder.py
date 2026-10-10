"""
Fuzz test for the dashboard builder.

For every dataset it makes hundreds of RANDOM filter + chart combinations,
and checks each answer against a separate calculation written with plain
Python loops (not the same code as builder.py).

    python test_builder.py                 (all files + a tricky synthetic one)
    python test_builder.py amazon.csv      (one file)
"""
import calendar
import datetime
import json
import math
import random
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import builder as b
from ask_engine import AskEngine

CONFIGS = 120
FILES = [
    "ecommerce_sales_34500.csv", "sample_sales.csv",
    "Cleaned_HR_Data_Analysis.csv", "amazon.csv",
]

failures = []
checks = 0


def check(ok, message):
    global checks
    checks += 1
    if not ok:
        failures.append(message)


def close(a, c):
    return abs(a - c) <= 1e-6 * max(1.0, abs(c))


def isnan(v):
    return v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT or v is pd.NA


# ------------------------------------------------------------
# Plain-Python reference calculation
# ------------------------------------------------------------

def ref_rows(info, filters):
    df = info["df"]
    months = filters.get("months")
    column = filters.get("date_column")
    stamps = info["stamps"][column] if months and column in info["stamps"] else None
    chosen = {
        c: {str(x).strip() for x in vals}
        for c, vals in (filters.get("values") or {}).items()
    }
    lists = {c: df[c].tolist() for c in chosen}

    rows = []
    for i in range(len(df)):
        if stamps is not None:
            s = stamps.iloc[i]
            if pd.isna(s):
                continue
            if not (months[0] <= f"{s.year:04d}-{s.month:02d}" <= months[1]):
                continue
        ok = True
        for c, allowed in chosen.items():
            v = lists[c][i]
            if isnan(v) or str(v).strip() not in allowed:
                ok = False
                break
        if ok:
            rows.append(i)
    return rows


def numbers(df, column, rows):
    out = []
    values = df[column].tolist()
    for i in rows:
        v = values[i]
        if isnan(v):
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def ref_agg(df, rows, measure, agg):
    """number or None"""
    if agg == "count":
        return float(len(rows))
    if agg == "distinct":
        values = df[measure].tolist()
        return float(len({values[i] for i in rows if not isnan(values[i])}))
    nums = numbers(df, measure, rows)
    if not nums:
        return None
    return {"sum": math.fsum(nums), "mean": math.fsum(nums) / len(nums),
            "max": max(nums), "min": min(nums)}[agg]


def ref_groups(df, rows, group, measure, agg):
    keys = df[group].tolist()
    buckets = {}
    left_out = 0
    for i in rows:
        if isnan(keys[i]):
            left_out += 1
            continue
        buckets.setdefault(str(keys[i]), []).append(i)
    result = {}
    for key, members in buckets.items():
        value = ref_agg(df, members, measure, agg)
        if agg == "sum" and value is None:
            value = 0.0
        if value is not None:
            result[key] = value
    return result, left_out


def ref_months(info, df, rows, column, measure, agg, grain="M"):
    """({label: number}, [partly covered labels])"""
    stamps = info["stamps"][column]
    buckets = {}
    for i in rows:
        s = stamps.iloc[i]
        if pd.isna(s):
            continue
        if grain == "M":
            key = f"{s.year:04d}-{s.month:02d}"
        elif grain == "Q":
            key = f"{s.year:04d}-Q{(s.month - 1) // 3 + 1}"
        else:
            key = f"{s.year:04d}"
        buckets.setdefault(key, []).append(i)

    valid = stamps.dropna()
    first = datetime.date(valid.min().year, valid.min().month, valid.min().day)
    last = datetime.date(valid.max().year, valid.max().month, valid.max().day)

    def span(key):
        if grain == "Q":
            year, q = int(key[:4]), int(key[-1])
            m1, m2 = 3 * (q - 1) + 1, 3 * q
            return datetime.date(year, m1, 1), datetime.date(year, m2, calendar.monthrange(year, m2)[1])
        year = int(key[:4])
        return datetime.date(year, 1, 1), datetime.date(year, 12, 31)

    partial_months = info["partial"].get(column, set())
    out, flagged = {}, []
    for key, members in buckets.items():
        if grain == "M" and key in partial_months:
            continue
        value = ref_agg(df, members, measure, agg)
        if agg == "sum" and value is None:
            value = 0.0
        if value is None:
            continue
        out[key] = value
        if grain != "M":
            start, end = span(key)
            if first > start or last < end:
                flagged.append(key)
    return out, flagged


# ------------------------------------------------------------
# Random inputs
# ------------------------------------------------------------

def random_filters(opts, rng):
    f = {"months": None, "date_column": opts["date_column"], "values": {}}
    months = opts["months"]
    if months and rng.random() < 0.6:
        x, y = sorted((rng.randrange(len(months)), rng.randrange(len(months))))
        f["months"] = [months[x], months[y]]
    for dim, values in opts["dims"].items():
        if rng.random() < 0.35:
            k = rng.randint(0, len(values))
            f["values"][dim] = rng.sample(values, k)
    return f


def random_opts(rng):
    return {
        "grain": rng.choice(["M", "M", "Q", "Y"]),
        "top": rng.choice([None, None, None, 1, 3, 5, 10, 50]),
    }


def random_tile(info, rng):
    kinds = ["kpi", "bar", "column", "line", "donut", "table"]
    t = rng.choice(kinds)
    if t == "line" and not info["dates"]:
        t = "bar"
    if t not in ("kpi", "line") and not info["dims"]:
        t = "kpi"

    options = ["count"]
    if info["measures"]:
        options += ["number"] * 3
    if info["distinct_columns"]:
        options.append("distinct")
    kind = rng.choice(options)

    if kind == "count":
        measure, agg = None, "count"
    elif kind == "number":
        measure = rng.choice(info["measures"])
        agg = rng.choice(b.NUMBER_AGGS)
    else:
        measure, agg = rng.choice(info["distinct_columns"]), "distinct"

    if t == "donut" and agg not in ("sum", "count"):
        measure, agg = None, "count"

    tile = b.new_tile(
        info, type=t, measure=measure, agg=agg,
        group=rng.choice(info["dims"]) if info["dims"] else None,
        date=rng.choice(info["dates"]) if info["dates"] else None,
        top=rng.randint(1, 15), sort=rng.choice(["asc", "desc"]),
    )
    return tile


# ------------------------------------------------------------
# One comparison
# ------------------------------------------------------------

def verify(info, filters, tile, label, opts=None):
    opts = opts or {}
    df = info["df"]
    view = b.apply_filters(info, filters)
    rows = ref_rows(info, filters)

    check(len(view) == len(rows), f"{label}: filter kept {len(view)} rows, expected {len(rows)}")
    check(list(view.index) == [df.index[i] for i in rows], f"{label}: filter kept different rows")

    got = b.compute_tile(view, tile, info, opts)

    if not rows:
        check(got["kind"] == "empty", f"{label}: no rows but result is {got['kind']}")
        return

    if tile["type"] == "kpi":
        expected = ref_agg(df, rows, tile["measure"], tile["agg"])
        check(got["kind"] == "kpi", f"{label}: kpi gave {got}")
        if got["kind"] == "kpi":
            same = (expected is None and got["value"] is None) or (
                expected is not None and got["value"] is not None and close(got["value"], expected))
            check(same, f"{label}: kpi {got['value']} vs {expected}")
            check(got["rows"] == len(rows), f"{label}: kpi rows")
        return

    if tile["type"] == "line":
        grain = opts.get("grain") or "M"
        expected, flagged = ref_months(info, df, rows, tile.get("date") or info["dates"][0], tile["measure"], tile["agg"], grain)
        if len(expected) < 2:
            check(got["kind"] == "empty", f"{label}: line expected empty, got {got['kind']}")
            return
        check(got["kind"] == "line", f"{label}: line gave {got['kind']}")
        if got["kind"] == "line":
            check(set(got["months"]) == set(expected), f"{label}: line periods differ {sorted(got['months'])[:4]} vs {sorted(expected)[:4]}")
            check(list(got["months"]) == sorted(got["months"]), f"{label}: line not in time order")
            check(set(got["partial"]) == set(flagged), f"{label}: partial flags {got['partial']} vs {flagged}")
            check(got["grain"] == grain, f"{label}: grain")
            for m, v in got["months"].items():
                check(m in expected and close(v, expected[m]), f"{label}: line {m} {v} vs {expected.get(m)}")
        return

    # groups
    ref, left_out = ref_groups(df, rows, tile["group"], tile["measure"], tile["agg"])
    if not ref:
        check(got["kind"] in ("empty", "error"), f"{label}: groups expected empty, got {got['kind']}")
        return

    donut = tile["type"] == "donut"
    if donut and any(v < 0 for v in ref.values()):
        check(got["kind"] == "error", f"{label}: donut with negatives should be an error")
        return

    check(got["kind"] == "groups", f"{label}: groups gave {got}")
    if got["kind"] != "groups":
        return

    values = dict(got["values"])
    top = opts.get("top") or tile["top"]
    other = values.pop(got.get("other_label"), None) if donut and len(ref) > top else None
    check((got.get("other_label") is not None) == (donut and len(ref) > top), f"{label}: other_label {got.get('other_label')!r}")

    top = opts.get("top") or tile["top"]
    check(len(values) == min(top, len(ref)), f"{label}: showed {len(values)} groups, expected {min(top, len(ref))}")
    for k, v in values.items():
        check(k in ref and close(v, ref[k]), f"{label}: group {k}: {v} vs {ref.get(k)}")

    ordered = list(values.values())
    want = sorted(ordered, reverse=(tile["sort"] == "desc"))
    check(all(close(x, y) for x, y in zip(ordered, want)), f"{label}: not in {tile['sort']} order")

    best = sorted(ref.values(), reverse=(tile["sort"] == "desc"))[:top]
    check(all(close(x, y) for x, y in zip(sorted(ordered), sorted(best))), f"{label}: wrong top groups")

    if donut and len(ref) > top:
        check(other is not None and close(other, sum(ref.values()) - sum(values.values())), f"{label}: 'Other' {other}")

    check(got["n_groups"] == len(ref), f"{label}: n_groups")
    check(got["left_out"] == left_out, f"{label}: left_out {got['left_out']} vs {left_out}")

    if tile["type"] == "table":
        frame = got["frame"]
        check(list(frame["Group"]) == list(got["values"]), f"{label}: table groups")
        if "Share %" in frame:
            check(frame["Share %"].sum() <= 100.5, f"{label}: shares add to {frame['Share %'].sum()}")


# ------------------------------------------------------------
# Tests that do not need the reference calculation
# ------------------------------------------------------------

def test_structure(info, rng, name):
    tiles = b.starter_tiles(info)

    # save and load gives the same charts back
    loaded, problems = b.load(b.dump(tiles), info)
    check(loaded == tiles and not problems, f"{name}: save/load changed the dashboard {problems}")

    # the dashboard title survives save / load
    reloaded = b.load_dashboard(b.dump(tiles, "My Sales Overview"), info)
    check(reloaded["title"] == "My Sales Overview" and reloaded["tiles"] == tiles, f"{name}: title lost")
    check(b.load_dashboard(b.dump(tiles, 12345), info)["title"] in ("", "12345"), f"{name}: junk title")
    check(b.load_dashboard('{"tiles": [], "title": ["x"]}', info)["title"] == "", f"{name}: list title accepted")

    # a hand-edited file with the SAME chart id twice must still load (unique ids)
    twin = [dict(tiles[0]), dict(tiles[0]), dict(tiles[0], id="")]
    twin_load = b.load_dashboard(json.dumps({"tiles": twin}), info)
    twin_ids = [x["id"] for x in twin_load["tiles"]]
    check(len(twin_ids) == 3 and len(set(twin_ids)) == 3, f"{name}: duplicate chart ids were kept {twin_ids}")

    # the chart limit is respected when loading
    flood = json.dumps({"tiles": [dict(tiles[0], id=f"x{i}") for i in range(b.MAX_TILES + 10)]})
    check(len(b.load_dashboard(flood, info)["tiles"]) == b.MAX_TILES, f"{name}: loaded more than {b.MAX_TILES} charts")

    # nothing in the starter dashboard is invalid
    for t in tiles:
        check(b.check_tile(t, info) is None, f"{name}: starter tile invalid: {t}")

    # layout: rows never exceed 4 units and keep the order
    many = [b.new_tile(info, type="kpi", measure=None, agg="count") for _ in range(11)]
    for _ in range(40):
        for t in many:
            t["width"] = rng.choice(b.WIDTHS)
        rows = b.pack_rows(many)
        check(all(sum(b.WIDTH_UNITS[t["width"]] for t in r) <= 4 for r in rows), f"{name}: row too wide")
        check([t["id"] for r in rows for t in r] == [t["id"] for t in many], f"{name}: pack_rows changed order")

    # moving, copying, deleting
    ids = [t["id"] for t in tiles]
    moved = b.move_tile(tiles, ids[0], +1)
    check(sorted(t["id"] for t in moved) == sorted(ids), f"{name}: move lost tiles")
    check(b.move_tile(tiles, ids[0], -1) == tiles, f"{name}: moving the first tile up changed something")
    check(len(b.duplicate_tile(tiles, ids[0])) == len(tiles) + 1, f"{name}: duplicate")
    check(len(b.delete_tile(tiles, ids[0])) == len(tiles) - 1, f"{name}: delete")
    full = [dict(tiles[0], id=f"x{i}") for i in range(b.MAX_TILES)]
    check(len(b.upsert_tile(full, b.new_tile(info, type="kpi", measure=None, agg="count"))) == b.MAX_TILES, f"{name}: too many tiles allowed")

    # empty filters keep every row
    check(len(b.apply_filters(info, {})) == len(info["df"]), f"{name}: empty filter dropped rows")

    # junk never crashes
    junk_values = [None, 0, -5, "abc", [], {}, [1, 2], 3.5, True, "sum", "bar", "zzz"]
    keys = ["type", "measure", "agg", "group", "date", "top", "sort", "width", "title", "id"]
    view = b.apply_filters(info, {})
    for _ in range(300):
        t = {k: rng.choice(junk_values) for k in keys if rng.random() < 0.8}
        try:
            r = b.compute_tile(view, b.clean_tile(t), info)
            check(r["kind"] in ("kpi", "groups", "line", "empty", "error"), f"{name}: junk gave {r}")
        except Exception as error:
            check(False, f"{name}: junk tile crashed: {t} -> {error!r}")

    # bad files never crash
    for text in ["", "{", "[]", "null", '{"tiles": 5}', '{"tiles": [1, "a", null, {"type": "bar", "group": "zzz"}]}', "\x00\x01"]:
        try:
            result, notes = b.load(text, info)
            check(result == [], f"{name}: bad file {text!r} gave tiles")
        except Exception as error:
            check(False, f"{name}: bad file {text!r} crashed {error!r}")


# ------------------------------------------------------------
# A tricky file: negatives, empty cells, broken dates
# ------------------------------------------------------------

def synthetic():
    r = np.random.default_rng(7)
    n = 3000
    dates = pd.to_datetime("2024-01-15") + pd.to_timedelta(r.integers(0, 420, n), unit="D")
    df = pd.DataFrame({
        "order_id": [f"O{i}" for i in range(n)],
        "order_date": dates.strftime("%Y-%m-%d"),
        "region": r.choice(["North", "South", "East", "West", None], n, p=[.25, .25, .2, .25, .05]),
        "category": r.choice(list("ABCDEF"), n),
        "customer_id": [f"C{x}" for x in r.integers(0, 300, n)],
        "profit": r.normal(20, 80, n).round(2),
        "sales": r.gamma(2, 100, n).round(2),
        "returned": r.choice(["Yes", "No"], n, p=[.1, .9]),
    })
    df.loc[r.random(n) < 0.03, "profit"] = np.nan
    df.loc[::97, "order_date"] = None
    df.loc[5::211, "order_date"] = "not a date"
    return df


# ------------------------------------------------------------
# Every chart type x every method (no luck involved)
# ------------------------------------------------------------

def grid_tiles(info):
    tiles = []
    measure_choices = [(None, "count")]
    for m in info["measures"][:2]:
        measure_choices += [(m, a) for a in b.NUMBER_AGGS]
    if info["distinct_columns"]:
        measure_choices.append((info["distinct_columns"][0], "distinct"))

    for t in b.TYPES:
        if t == "line" and not info["dates"]:
            continue
        for measure, agg in measure_choices:
            if t == "donut" and agg not in ("sum", "count"):
                continue
            groups = [None] if t in ("kpi", "line") else info["dims"][:2]
            for group in groups:
                if t not in ("kpi", "line") and group is None:
                    continue
                for sort in (["desc", "asc"] if t in ("bar", "column", "table") else ["desc"]):
                    tiles.append(b.new_tile(
                        info, type=t, measure=measure, agg=agg, group=group,
                        date=info["dates"][0] if info["dates"] else None,
                        top=4, sort=sort,
                    ))
    return tiles


def run_grid(info, opts, rng, name):
    tiles = grid_tiles(info)
    filter_sets = [{}, random_filters(opts, rng), random_filters(opts, rng)]
    option_sets = [{}, {"grain": "Q", "top": 3}, {"grain": "Y", "top": 50}]
    for n, tile in enumerate(tiles):
        for k, (filters, chosen) in enumerate(zip(filter_sets, option_sets)):
            verify(info, filters, tile, f"{name} GRID#{n}.{k} {json.dumps(tile)} {json.dumps(filters)} {chosen}"[:420], chosen)
            # the same tile with the OTHER options too
            verify(info, filters, tile, f"{name} GRID2#{n}.{k} {json.dumps(tile)} {chosen}"[:420], option_sets[(k + 1) % 3])
    return len(tiles) * len(filter_sets) * 2


# ------------------------------------------------------------

def run(name, df, seed):
    global failures
    before = len(failures)
    engine = AskEngine(df)
    info = b.dataset_info(engine)
    opts = b.filter_options(info)
    rng = random.Random(seed)

    for n in range(CONFIGS):
        filters = random_filters(opts, rng)
        tile = random_tile(info, rng)
        chosen = random_opts(rng)
        verify(info, filters, tile, f"{name} #{n} {json.dumps(tile)} {json.dumps(filters)} {chosen}"[:420], chosen)

    grid = run_grid(info, opts, rng, name)
    test_structure(info, rng, name)
    print(f"  {name:38s} {CONFIGS} random + {grid} systematic dashboards | failures: {len(failures) - before}")


if __name__ == "__main__":
    files = sys.argv[1:] or FILES
    print("Dashboard builder fuzz test")
    for i, f in enumerate(files):
        run(f, pd.read_csv(f), 100 + i)
    if len(sys.argv) == 1:
        run("synthetic (negatives, gaps, bad dates)", synthetic(), 999)

    print(f"\n{checks} checks, {len(failures)} FAILED")
    seen = {}
    for f in failures:
        kind = f.split("}: ")[-1].split(":")[0][:60] if "}: " in f else f[:60]
        seen.setdefault(kind, []).append(f)
    for kind, items in seen.items():
        print(f"  [{len(items)}x] {items[0][:330]}")
