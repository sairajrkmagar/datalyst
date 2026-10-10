"""
The dashboard builder: filters, charts (called "tiles"), saving, loading.

No Streamlit in this file, so every number can be checked by tests.
A tile is a small dictionary, for example:

    {"id": "a1b2c3d4", "type": "bar", "title": "", "measure": "total_amount",
     "agg": "sum", "group": "category", "date": None, "top": 8,
     "sort": "desc", "width": "half"}

measure = None means "count the rows".
"""

from safe_numbers import is_whole
import json
import uuid

import pandas as pd

from dashboard import (
    dim_label, groupable_dims, humanize, main_measure, total_label,
    uses_total, yes_no_columns,
)
from filters import to_dates
from metrics import partial_months
from plan_repair import pick_date_column

TYPES = ["kpi", "bar", "column", "line", "donut", "table"]
TYPE_NAMES = {
    "kpi": "Number", "bar": "Bars", "column": "Columns",
    "line": "Line", "donut": "Donut", "table": "Table",
}

AGGS = ["sum", "mean", "max", "min", "count", "distinct"]
AGG_NAMES = {
    "sum": "Total", "mean": "Average", "max": "Highest", "min": "Lowest",
    "count": "Count", "distinct": "Different values",
}
NUMBER_AGGS = ["sum", "mean", "max", "min"]

WIDTHS = ["quarter", "half", "full"]
WIDTH_UNITS = {"quarter": 1, "half": 2, "full": 4}
WIDTH_NAMES = {"quarter": "Small", "half": "Medium", "full": "Wide"}
DEFAULT_WIDTH = {
    "kpi": "quarter", "bar": "half", "column": "half",
    "line": "full", "donut": "half", "table": "half",
}

MAX_TILES = 24
MAX_FILTER_VALUES = 30
MAX_FILTER_ATTRIBUTES = 15

# the time view of line charts
GRAINS = {"M": "Monthly", "Q": "Quarterly", "Y": "Yearly"}


# ============================================================
# What the builder knows about the file
# ============================================================

def dataset_info(engine):
    """Everything the builder needs, worked out once per file."""

    df = engine.df

    if not df.index.is_unique:
        df = df.reset_index(drop=True)

    understanding = engine.dataset_understanding
    profile = engine.profile

    measures = list(understanding["measures"])
    dates = list(understanding["date_columns"])
    identifiers = list(profile.get("identifier_columns", []))

    dims = [
        c for c in profile.get("dimension_values", {})
        if c not in identifiers and c in df.columns
    ]

    distinct_columns = [
        c for c in df.columns if c not in measures and c not in dates
    ]

    stamps = {column: to_dates(df[column]) for column in dates}

    main = main_measure(engine)
    filter_date = (
        pick_date_column(humanize(main) if main else "count", dates)
        if dates else None
    )

    info = {
        "df": df,
        "columns": list(df.columns),
        "measures": measures,
        "dims": dims,
        "dates": dates,
        "distinct_columns": distinct_columns,
        "stamps": stamps,
        "noun": profile.get("count_noun") or "records",
        "labels": {c: dim_label(engine, c) for c in df.columns},
        "filter_date": filter_date,
        "main_measure": main,
        "partial": {c: set(partial_months(df, c)) for c in dates},
    }

    # the first and last day of each date column (for quarters and years)
    info["date_span"] = {}

    for column, series in stamps.items():
        valid = series.dropna()

        if len(valid):
            info["date_span"][column] = (
                valid.min().normalize(), valid.max().normalize()
            )

    # new charts start from a few good columns (3-12 values, then yes/no)
    wanted = groupable_dims(engine)[:5]

    for column in yes_no_columns(engine):
        if column not in wanted and len(wanted) < 7:
            wanted.append(column)

    info["chart_dims"] = [c for c in wanted if c in dims]

    # the filter panel offers EVERY attribute: a column with 2 to 30
    # different values (the good chart columns first)
    usable = []

    for column in info["chart_dims"] + [c for c in dims if c not in info["chart_dims"]]:

        different = df[column].dropna().astype(str).str.strip().nunique()

        if 2 <= different <= MAX_FILTER_VALUES and column not in usable:
            usable.append(column)

    info["filter_dims"] = usable[:MAX_FILTER_ATTRIBUTES]

    return info


def _clean_value(value):
    return str(value).strip()


def filter_options(info):
    """What the filter panel offers: months and the values of each column."""

    df = info["df"]
    options = {"date_column": info["filter_date"], "months": [], "dims": {}}

    column = info["filter_date"]

    if column:
        stamps = info["stamps"][column].dropna()

        if len(stamps):
            options["months"] = [
                str(p) for p in pd.period_range(
                    stamps.min().to_period("M"), stamps.max().to_period("M"),
                    freq="M",
                )
            ]

    for dim in info["filter_dims"]:

        values = sorted({_clean_value(v) for v in df[dim].dropna().unique()})

        if 2 <= len(values) <= MAX_FILTER_VALUES:
            options["dims"][dim] = values

    return options


# ============================================================
# Filters
# ============================================================

def apply_filters(info, filters):
    """
    The rows that pass every filter.

    filters = {"months": ["2024-01", "2024-06"] or None,
               "date_column": "order_date",
               "values": {"category": ["Fashion", "Toys"]}}

    A month filter keeps only rows with a readable date in that range.
    A value filter keeps rows whose value is in the chosen list.
    """

    df = info["df"]
    filters = filters or {}

    keep = pd.Series(True, index=df.index)

    months = filters.get("months")
    column = filters.get("date_column")

    if months and column in info["stamps"]:

        start, end = months
        period = info["stamps"][column].dt.to_period("M")

        keep &= (
            period.notna()
            & (period >= pd.Period(start, freq="M"))
            & (period <= pd.Period(end, freq="M"))
        )

    for column_name, chosen in (filters.get("values") or {}).items():

        if column_name not in df.columns:
            continue

        allowed = {_clean_value(v) for v in chosen}

        keep &= (
            df[column_name].notna()
            & df[column_name].astype(str).str.strip().isin(allowed)
        )

    return df[keep]


# ============================================================
# Tiles
# ============================================================

def measure_kind(info, measure):
    """'count' (no column), 'number', 'distinct' or None (unknown)."""

    if measure is None:
        return "count"

    if measure in info["measures"]:
        return "number"

    if measure in info["distinct_columns"]:
        return "distinct"

    return None


def check_tile(tile, info):
    """A plain-words problem, or None when the tile is fine."""

    if not isinstance(tile, dict):
        return "This chart is not valid."

    kind_of_tile = tile.get("type")

    if kind_of_tile not in TYPES:
        return f"Unknown chart type: {kind_of_tile}."

    measure = tile.get("measure")
    agg = tile.get("agg")
    kind = measure_kind(info, measure)

    if kind is None:
        return f"The column '{measure}' is not in this file."

    if kind == "count" and agg != "count":
        return "Counting rows needs the 'count' method."

    if kind == "number" and agg not in NUMBER_AGGS:
        return f"'{measure}' can be totalled, averaged, or its highest or lowest value shown."

    if kind == "distinct" and agg != "distinct":
        return f"'{measure}' is text: it can only show how many different values it has."

    if kind_of_tile == "line":

        date = tile.get("date")

        if not info["dates"]:
            return "This file has no date column, so a line cannot be drawn."

        if date is not None and date not in info["dates"]:
            return f"'{date}' is not a date column."

    elif kind_of_tile != "kpi":

        if tile.get("group") not in info["dims"]:
            return "Pick a column to group by."

    if kind_of_tile == "donut" and agg not in ("sum", "count"):
        return "A donut shows a total or a count. Use bars for other methods."

    return None


def auto_title(tile, info, grain="M"):
    """'Total amount by category' and similar."""

    measure = tile.get("measure")
    agg = tile.get("agg")

    if agg == "count" or measure is None:
        base = f"Number of {info['noun']}"
    elif agg == "distinct":
        base = f"Unique {humanize(measure)}"
    elif agg == "sum":
        base = total_label(measure)
    elif agg == "mean":
        base = f"Average {humanize(measure)}"
    elif agg == "max":
        base = f"Highest {humanize(measure)}"
    else:
        base = f"Lowest {humanize(measure)}"

    if tile.get("type") == "line":
        return f"{base} by {({'M': 'month', 'Q': 'quarter', 'Y': 'year'}).get(grain, 'month')}"

    if tile.get("type") != "kpi" and tile.get("group"):
        group = info["labels"].get(tile["group"], humanize(tile["group"]))
        return f"{base} by {group}"

    return base


def new_tile(info, **values):
    """A complete tile (defaults filled in)."""

    tile_type = _name(values.get("type", "bar"))

    tile = {
        "id": uuid.uuid4().hex[:8],
        "type": tile_type,
        "title": "",
        "measure": None,
        "agg": "count",
        "group": None,
        "date": None,
        "top": 8,
        "sort": "desc",
        "width": DEFAULT_WIDTH.get(tile_type, "half"),
    }

    tile.update(values)
    tile["type"] = tile_type

    return clean_tile(tile)


def _name(value):
    """Settings from a file can be any junk: make them plain text or None."""

    if value is None or isinstance(value, str):
        return value

    return str(value)


def clean_tile(tile):
    """Safe values for every setting (never raises, whatever the input)."""

    tile = dict(tile)

    tile["id"] = str(tile.get("id") or uuid.uuid4().hex[:8])[:40]
    tile["title"] = str(tile.get("title") or "")[:80]

    for key in ("type", "measure", "agg", "group", "date", "sort", "width"):
        tile[key] = _name(tile.get(key))

    try:
        tile["top"] = max(1, min(50, int(tile.get("top", 8))))
    except (TypeError, ValueError):
        tile["top"] = 8

    if tile["sort"] not in ("asc", "desc"):
        tile["sort"] = "desc"

    if tile["width"] not in WIDTHS:
        tile["width"] = DEFAULT_WIDTH.get(tile["type"], "half")

    return tile


def _scalar(rows, measure, agg):
    if agg == "count":
        return len(rows)

    if agg == "distinct":
        return int(rows[measure].dropna().nunique())

    values = pd.to_numeric(rows[measure], errors="coerce").dropna()

    if values.empty:
        return None

    return float(getattr(values, agg)())


def _series_by(rows, keys, measure, agg):
    """One number per group (groups with no usable number are dropped)."""

    grouped = rows.groupby(keys)

    if agg == "count":
        series = grouped.size()

    elif agg == "distinct":
        series = grouped[measure].nunique()

    else:
        numbers = pd.to_numeric(rows[measure], errors="coerce")
        series = numbers.groupby(keys).agg(agg)

    return series.dropna()


def compute_tile(view, tile, info, opts=None):
    """
    The numbers for one tile, from the rows that passed the filters.

    opts = {"grain": "M" | "Q" | "Y",   (time view of line charts)
            "top": None | number}       (one limit for every group chart)

    Returns one of:
      {"kind": "kpi", "value": number or None, "rows": n}
      {"kind": "groups", "values": {name: number}, ...}
      {"kind": "line", "months": {"2024-01": number}, ...}
      {"kind": "empty" or "error", "message": "..."}
    """

    problem = check_tile(tile, info)

    if problem:
        return {"kind": "error", "message": problem}

    if len(view) == 0:
        return {"kind": "empty", "message": "No rows match the filters."}

    measure, agg = tile.get("measure"), tile["agg"]

    if tile["type"] == "kpi":
        return {
            "kind": "kpi",
            "value": _scalar(view, measure, agg),
            "rows": len(view),
        }

    if tile["type"] == "line":
        return _line(view, tile, info, opts)

    return _groups(view, tile, opts)


def _groups(view, tile, opts=None):

    group, measure, agg = tile["group"], tile.get("measure"), tile["agg"]

    rows = view[view[group].notna()]
    left_out = len(view) - len(rows)

    if rows.empty:
        return {"kind": "empty", "message": "No rows have a value in this column."}

    series = _series_by(rows, rows[group], measure, agg)

    if series.empty:
        return {"kind": "empty", "message": "There is no usable number to show."}

    # biggest first (ties: by name, so the order is always the same)
    items = [(str(key), float(number)) for key, number in series.items()]
    descending = tile["sort"] == "desc"
    items.sort(key=lambda kv: (-kv[1] if descending else kv[1], kv[0]))

    top = tile["top"]
    other_label = None

    override = (opts or {}).get("top")

    if override:
        try:
            top = max(1, min(50, int(override)))
        except (TypeError, ValueError):
            pass

    shown = items[:top]
    additive = agg in ("sum", "count")
    total = sum(number for _, number in items)

    if tile["type"] == "donut":

        if any(number < 0 for _, number in items):
            return {
                "kind": "error",
                "message": "A donut cannot show negative values. Use bars instead.",
            }

        rest = items[top:]

        if rest:

            # a real group may already be called "Other": never reuse its name
            taken = {name for name, _ in items}
            other_label = "Other groups"

            while other_label in taken:
                other_label += " "

            shown = shown + [(other_label, sum(number for _, number in rest))]

    result = {
        "kind": "groups",
        "other_label": other_label,
        "values": dict(shown),
        "n_groups": len(items),
        "left_out": left_out,
        "agg": agg,
        "total": total if additive else None,
    }

    if tile["type"] == "table":

        frame = pd.DataFrame(
            {"Group": [k for k, _ in shown], "Value": [v for _, v in shown]}
        )

        if additive and total > 0 and all(v >= 0 for _, v in items):
            frame["Share %"] = [round(v / total * 100, 1) for _, v in shown]

        result["frame"] = frame

    return result


def _line(view, tile, info, opts=None):

    column = tile.get("date") or info["dates"][0]
    measure, agg = tile.get("measure"), tile["agg"]

    grain = (opts or {}).get("grain") or "M"

    if grain not in GRAINS:
        grain = "M"

    stamps = info["stamps"][column].loc[view.index]
    usable = stamps.notna()

    rows = view[usable]

    if rows.empty:
        return {"kind": "empty", "message": "No rows have a readable date."}

    periods = stamps[usable].dt.to_period(grain)

    series = _series_by(rows, periods, measure, agg).sort_index()

    if grain == "M":

        # months only partly covered by the data are left out
        partial = info["partial"].get(column, set())

        values = {
            str(period): float(number)
            for period, number in series.items()
            if str(period) not in partial
        }

        left_out = sorted(str(p) for p in series.index if str(p) in partial)
        flagged = []

    else:

        # quarters and years are few, so partly covered ones are KEPT and flagged
        first, last = info["date_span"][column]

        def label(period):
            if grain == "Q":
                return f"{period.year}-Q{period.quarter}"
            return str(period.year)

        values = {label(p): float(number) for p, number in series.items()}
        left_out = []
        flagged = [
            label(p) for p in series.index
            if first > p.start_time.normalize() or last < p.end_time.normalize()
        ]

    if len(values) < 2:
        return {
            "kind": "empty",
            "message": (
                "Not enough full months to draw a line." if grain == "M"
                else "Not enough periods to draw a line. Try a finer time view."
            ),
        }

    return {
        "kind": "line", "months": values, "left_out": left_out,
        "partial": flagged, "agg": agg, "grain": grain,
    }


# ============================================================
# Layout helpers
# ============================================================

def pack_rows(tiles):
    """Tiles grouped into rows that add up to at most 4 units wide."""

    rows, current, used = [], [], 0

    for tile in tiles:

        units = WIDTH_UNITS[tile["width"]]

        if current and used + units > 4:
            rows.append(current)
            current, used = [], 0

        current.append(tile)
        used += units

    if current:
        rows.append(current)

    return rows


def move_tile(tiles, tile_id, step):
    """Move a tile earlier (-1) or later (+1)."""

    tiles = list(tiles)
    ids = [t["id"] for t in tiles]

    if tile_id not in ids:
        return tiles

    position = ids.index(tile_id)
    target = position + step

    if 0 <= target < len(tiles):
        tiles[position], tiles[target] = tiles[target], tiles[position]

    return tiles


def duplicate_tile(tiles, tile_id):

    tiles = list(tiles)

    if len(tiles) >= MAX_TILES:
        return tiles

    for position, tile in enumerate(tiles):
        if tile["id"] == tile_id:
            copy = dict(tile, id=uuid.uuid4().hex[:8])
            tiles.insert(position + 1, copy)
            break

    return tiles


def delete_tile(tiles, tile_id):
    return [t for t in tiles if t["id"] != tile_id]


def upsert_tile(tiles, tile):
    """Replace the tile with the same id, or add it at the end."""

    tiles = list(tiles)

    for position, existing in enumerate(tiles):
        if existing["id"] == tile["id"]:
            tiles[position] = tile
            return tiles

    if len(tiles) < MAX_TILES:
        tiles.append(tile)

    return tiles


# ============================================================
# A ready-made dashboard
# ============================================================

def starter_tiles(info):
    """A good first dashboard for this file."""

    measure = info["main_measure"]
    total = bool(measure) and uses_total(measure)
    dims = [d for d in info["chart_dims"] if d in info["dims"]]

    tiles = []

    def add(**values):
        tiles.append(new_tile(info, **values))

    if measure:
        add(type="kpi", measure=measure, agg="sum" if total else "mean")

    add(type="kpi", measure=None, agg="count")

    if measure:
        add(type="kpi", measure=measure, agg="mean" if total else "max")

    # a column that repeats (customers, products) makes a nice number
    repeat = next(
        (
            c for c in info["distinct_columns"]
            if 1 < info["df"][c].nunique() < 0.9 * len(info["df"])
            and c not in info["dims"]
        ),
        None,
    )

    if repeat:
        add(type="kpi", measure=repeat, agg="distinct")

    if info["dates"]:
        add(type="line", measure=measure, agg=(
            "count" if not measure else ("sum" if total else "mean")
        ), date=info["filter_date"])

    agg = "count" if not measure else ("sum" if total else "mean")

    if dims:
        add(type="bar", measure=measure, agg=agg, group=dims[0])

    if len(dims) >= 2:
        add(type="donut", measure=None, agg="count", group=dims[1])

    return tiles[:MAX_TILES]


# ============================================================
# Saving and loading
# ============================================================

def dump(tiles, title=""):
    return json.dumps(
        {
            "app": "datalyst", "version": 2,
            "title": str(title or "")[:80], "tiles": tiles,
        },
        indent=2,
    )


def load_dashboard(text, info):
    """{"tiles": [...], "title": "...", "problems": [...]}. Never raises."""

    problems = []

    try:
        data = json.loads(text)
        raw = data.get("tiles") if isinstance(data, dict) else None
    except Exception:
        return {"tiles": [], "title": "", "problems": ["This is not a dashboard file."]}

    if not isinstance(raw, list):
        return {"tiles": [], "title": "", "problems": ["This file has no charts in it."]}

    title = data.get("title", "")
    title = title[:80] if isinstance(title, str) else ""

    tiles = []
    used_ids = set()

    for item in raw[:MAX_TILES]:

        if not isinstance(item, dict):
            problems.append("A chart in the file was not readable and was skipped.")
            continue

        tile = clean_tile(item)

        # two charts with the same id would crash the page: give a new one
        while tile["id"] in used_ids:
            tile["id"] = uuid.uuid4().hex[:8]

        used_ids.add(tile["id"])

        problem = check_tile(tile, info)

        if problem:
            name = tile["title"] or tile.get("type") or "chart"
            problems.append(f"'{name}' was skipped: {problem}")
            continue

        tiles.append(tile)

    return {"tiles": tiles, "title": title, "problems": problems}


def load(text, info):
    """(tiles, problems)."""

    result = load_dashboard(text, info)

    return result["tiles"], result["problems"]


# ============================================================
# Short texts used by the page AND by the report exports
# ============================================================

def kpi_number(value):
    """Short numbers for the fixed-size cards (the full number is the tooltip)."""

    size = abs(float(value))

    if size >= 1e9:
        return f"{value / 1e9:.1f}B"

    if size >= 1e6:
        return f"{value / 1e6:.1f}M"

    if size >= 1e4:
        return f"{value / 1e3:.1f}K"

    if is_whole(float(value)):
        return f"{int(value):,}"

    if size >= 1:
        return f"{value:,.2f}"

    return f"{value:.3g}"


def tile_subtitle(tile, result):

    kind = result["kind"]

    if kind == "line":

        text = GRAINS[result["grain"]]

        if result["grain"] == "M":
            text += " · full months only"

            if result["left_out"]:
                text += f" (left out: {', '.join(result['left_out'])})"

        elif result["partial"]:
            text += " · * partly covered by the data"

        return text

    if kind == "groups":

        shown = len(result["values"]) - (1 if result.get("other_label") else 0)
        word = "Top" if tile["sort"] == "desc" or tile["type"] == "donut" else "Lowest"

        text = (
            f"All {result['n_groups']}" if result["n_groups"] <= shown
            else f"{word} {shown} of {result['n_groups']}"
        )

        if result["left_out"]:
            text += f" · {result['left_out']:,} rows with no value here are not counted"

        return text

    return ""


# ============================================================
# Pin an answer from Ask AI to the dashboard
# ============================================================

PIN_AGGS = {
    "sum": "sum", "total": "sum", "mean": "mean", "average": "mean", "avg": "mean",
    "max": "max", "min": "min", "count": "count", "row_count": "count",
}


def tile_from_answer(answer, info, existing=()):
    """
    (tile, None) when an answer can become a chart on the dashboard, or
    (None, reason in plain words). The chart shows the same numbers as the
    answer. An answer with a filter is NOT pinned: the chart would silently
    show more rows than the answer did.
    """

    if not isinstance(answer, dict) or answer.get("status") != "success":
        return None, "Only a finished answer can be pinned."

    plan = answer.get("plan") or {}
    intent = plan.get("intent")

    if any(plan.get(key) for key in ("filters", "conditions", "date_filter", "filter_value")):
        return None, (
            "This answer uses a filter, so a chart would show different numbers. "
            "Use the filters on this page instead."
        )

    if intent not in ("breakdown", "top", "bottom", "trend"):
        return None, (
            "Only tables, rankings and trends can be pinned. A single number "
            "is already part of the key numbers."
        )

    group = plan.get("group_column")
    value = plan.get("value_column") or plan.get("column")
    word = str(plan.get("agg") or plan.get("operation") or "").lower().replace("group_", "")
    agg = PIN_AGGS.get(word, "sum")

    measure = value if value in info["measures"] else None

    if str(plan.get("operation")).lower() in ("count", "row_count") or agg == "count":
        measure, agg = None, "count"
    elif measure is None:
        agg = "count"
    elif agg not in ("sum", "mean", "max", "min"):
        agg = "sum"

    if intent == "trend":

        if group not in info["dates"]:
            return None, "This trend uses a date column the dashboard cannot draw."

        tile = new_tile(info, type="line", measure=measure, agg=agg, date=group)

    else:

        if group not in info["dims"]:
            return None, f"'{group}' cannot be used to group a chart on the dashboard."

        tile = new_tile(
            info, type="bar", measure=measure, agg=agg, group=group,
            sort="asc" if intent == "bottom" else "desc",
        )

    problem = check_tile(tile, info)

    if problem:
        return None, problem

    keys = ("type", "measure", "agg", "group", "date")

    if any(all(t.get(k) == tile.get(k) for k in keys) for t in existing):
        return None, "This chart is already on your dashboard."

    if len(existing) >= MAX_TILES:
        return None, f"Your dashboard is full ({MAX_TILES} items). Delete one first."

    return tile, None
