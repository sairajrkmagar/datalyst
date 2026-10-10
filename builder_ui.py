"""
The Visualize page: build your own dashboard.

Layout (fixed, so every dashboard looks professional):
  left sidebar : Filters (date, time view, show top, one dropdown per attribute)
  top          : the dashboard title
  below        : a row of fixed-size KPI cards
  below        : fixed-size chart tiles in a grid

All numbers come from builder.py (which is tested); this file only draws.
"""

from compat import STRETCH
import hashlib
import json

import streamlit as st

import builder as bd
import dashboard as dash
import ui

STATE = "builder_state"
ACCENTS = ["blue", "purple", "teal", "green", "orange"]
GROUP_TYPES = ("bar", "column", "donut", "table")
CHART_HEIGHT = 300
KPI_PER_ROW = 4
TOP_CHOICES = ["Per chart", 3, 5, 10, 15, 20, "All"]
KPI_ICON = {
    "sum": "chart", "mean": "scale", "max": "zap", "min": "zap",
    "count": "layers", "distinct": "database",
}


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


def ekey():
    """A short text made from the current file (for widget keys)."""

    return hashlib.md5(st.session_state["engine_key"].encode()).hexdigest()[:8]


def ensure(key, value):
    """Give a widget its starting value (only when it has none yet)."""

    if key not in st.session_state:
        st.session_state[key] = value

    return key


# ============================================================
# State
# ============================================================

def get_info(engine):

    key = st.session_state["engine_key"]

    if st.session_state.get("builder_info_key") != key:

        with st.spinner("Preparing the builder..."):
            st.session_state["builder_info"] = bd.dataset_info(engine)

        st.session_state["builder_info_key"] = key

    return st.session_state["builder_info"]


def new_filter_state():
    return {"months": None, "grain": "M", "top": "Per chart", "off": {}}


def get_state(info):

    key = st.session_state["engine_key"]
    state = st.session_state.get(STATE)

    if not state or state["key"] != key:

        state = {
            "key": key,
            "tiles": bd.starter_tiles(info),
            "title": "",
            "editing": None,
            "editor_error": None,
            "draft": {},
            "f": new_filter_state(),
            "loaded_hash": None,
            "load_notes": [],
        }

        st.session_state[STATE] = state

    return state


def S():
    return st.session_state[STATE]


def INFO():
    return st.session_state["builder_info"]


# ============================================================
# Filters (in the left sidebar)
# ============================================================

def set_months(key):
    S()["f"]["months"] = tuple(st.session_state[key])


def set_grain(key):
    S()["f"]["grain"] = st.session_state[key] or "M"


def set_top(key):
    S()["f"]["top"] = st.session_state[key]


def toggle_value(dim, index, key):

    off = S()["f"]["off"].setdefault(dim, set())

    if st.session_state[key]:
        off.discard(index)
    else:
        off.add(index)


def set_attribute(dim, count, flag, prefix):
    """The 'All' / 'None' buttons of one attribute."""

    S()["f"]["off"][dim] = set() if flag else set(range(count))

    for i in range(count):
        st.session_state[f"{prefix}{dim}_{i}"] = flag


def reset_filters(prefix, months, options):

    f = S()["f"]
    f["months"] = None
    f["top"] = "Per chart"
    f["off"] = {}

    if months:
        st.session_state[prefix + "months"] = (months[0], months[-1])
    st.session_state[prefix + "grain"] = "M"
    f["grain"] = "M"

    st.session_state[prefix + "top"] = "Per chart"

    for dim, values in options["dims"].items():
        for i in range(len(values)):
            st.session_state[f"{prefix}{dim}_{i}"] = True


def render_filters(info, slot):
    """
    Draws the filter panel in the sidebar slot.
    Returns (filters, opts, counter): the filters in builder.py's format,
    the dashboard-wide options, and a place to write the row count.
    """

    state = S()
    f = state["f"]
    options = bd.filter_options(info)
    months = options["months"]
    prefix = f"bf_{ekey()}_"

    filters = {"months": None, "date_column": options["date_column"], "values": {}}

    with slot:

        html('<div class="nav-label" style="padding-top:18px">Filters</div>')

        # ---------------- date
        if len(months) >= 2:

            html(f'<div class="flt-title">Date · {dash.humanize(options["date_column"])}</div>')

            key = prefix + "months"

            # a range slider takes its start from `value` (not from the state)
            chosen = st.select_slider(
                "Months", options=months, value=f["months"] or (months[0], months[-1]),
                key=key, label_visibility="collapsed",
                on_change=set_months, args=(key,),
            )

            chosen = tuple(chosen)

            if chosen != (months[0], months[-1]):
                filters["months"] = list(chosen)

            html('<div class="flt-title">View time by</div>')

            key = ensure(prefix + "grain", f["grain"])

            st.selectbox(
                "View time by", list(bd.GRAINS), key=key,
                format_func=lambda g: bd.GRAINS[g],
                label_visibility="collapsed", on_change=set_grain, args=(key,),
            )

        # ---------------- show top
        html('<div class="flt-title">Show top</div>')

        key = ensure(prefix + "top", f["top"])

        st.select_slider(
            "Show top", options=TOP_CHOICES, key=key, label_visibility="collapsed",
            on_change=set_top, args=(key,),
        )

        # ---------------- attributes
        if options["dims"]:
            html('<div class="flt-title" style="margin-top:14px">Attributes</div>')

        for dim, values in options["dims"].items():

            off = f["off"].setdefault(dim, set())
            label = info["labels"][dim].capitalize()

            with st.expander(label):

                on_count = len(values) - len(off)
                st.caption(f"{on_count} of {len(values)} selected")

                a, b = st.columns(2, gap="small")

                a.button(
                    "All", key=f"{prefix}all_{dim}", on_click=set_attribute,
                    args=(dim, len(values), True, prefix), **STRETCH,
                )
                b.button(
                    "None", key=f"{prefix}none_{dim}", on_click=set_attribute,
                    args=(dim, len(values), False, prefix), **STRETCH,
                )

                box = st.container(height=min(260, 35 * len(values) + 12), border=False)

                with box:
                    for i, value in enumerate(values):

                        key = ensure(f"{prefix}{dim}_{i}", i not in off)

                        st.checkbox(
                            value, key=key, on_change=toggle_value,
                            args=(dim, i, key),
                        )

            selected = [v for i, v in enumerate(values) if i not in off]

            if len(selected) != len(values):
                filters["values"][dim] = selected

        counter = st.empty()

        st.button(
            "Reset filters", key=prefix + "reset", on_click=reset_filters,
            args=(prefix, months, options), **STRETCH,
        )

    top = f["top"]
    opts = {
        "grain": f["grain"] if f["grain"] in bd.GRAINS else "M",
        "top": None if top == "Per chart" else (50 if top == "All" else int(top)),
    }

    return filters, opts, counter


def filters_from_state(info):
    """(filters, opts) from what the user chose, without drawing anything."""

    f = S()["f"]
    options = bd.filter_options(info)
    months = options["months"]

    filters = {"months": None, "date_column": options["date_column"], "values": {}}

    if f["months"] and len(months) >= 2 and tuple(f["months"]) != (months[0], months[-1]):
        filters["months"] = list(f["months"])

    for dim, values in options["dims"].items():

        off = f["off"].get(dim, set())
        selected = [v for i, v in enumerate(values) if i not in off]

        if len(selected) != len(values):
            filters["values"][dim] = selected

    top = f["top"]
    opts = {
        "grain": f["grain"] if f["grain"] in bd.GRAINS else "M",
        "top": None if top == "Per chart" else (50 if top == "All" else int(top)),
    }

    return filters, opts


# ============================================================
# The chart editor
# ============================================================

def measure_tokens(info):
    return (
        ["__count__"]
        + [f"n:{m}" for m in info["measures"]]
        + [f"d:{c}" for c in info["distinct_columns"]]
    )


def token_label(token, info):

    if token == "__count__":
        return f"Number of {info['noun']}"

    kind, column = token.split(":", 1)

    return dash.humanize(column) if kind == "n" else f"Unique {dash.humanize(column)}"


def token_kind(token):

    if token == "__count__":
        return "count"

    return "number" if token.startswith("n:") else "distinct"


def tile_token(tile, info):

    measure = tile.get("measure")

    if measure is None:
        return "__count__"

    return ("n:" if measure in info["measures"] else "d:") + measure


def available_types(info):

    types = ["kpi"]

    if info["dims"]:
        types += ["bar", "column"]

    if info["dates"]:
        types.append("line")

    if info["dims"]:
        types += ["donut", "table"]

    return types


def open_editor(tile_id):

    info, state = INFO(), S()

    if tile_id == "new":

        main = info["main_measure"]
        total = bool(main) and dash.uses_total(main)

        tile = bd.new_tile(
            info,
            type="bar" if info["dims"] else "kpi",
            measure=main,
            agg=("sum" if total else "mean") if main else "count",
            group=info["chart_dims"][0] if info["chart_dims"] else (info["dims"][0] if info["dims"] else None),
        )

    else:
        tile = next(t for t in state["tiles"] if t["id"] == tile_id)

    state["editing"] = tile_id
    state["editor_error"] = None

    # the draft is the single source of truth: hidden fields keep their value
    state["draft"] = {
        "type": tile["type"],
        "title": tile["title"],
        "measure": tile_token(tile, info),
        "how": tile["agg"] if tile["agg"] in bd.NUMBER_AGGS else "sum",
        "group": tile["group"] if tile["group"] in info["dims"] else (info["dims"][0] if info["dims"] else None),
        "date": tile["date"] if tile["date"] in info["dates"] else (info["filter_date"] or (info["dates"][0] if info["dates"] else None)),
        "top": max(1, min(30, tile["top"])),
        "sort": tile["sort"],
        "width": tile["width"],
    }

    for key in [k for k in st.session_state if str(k).startswith("ed_w_")]:
        del st.session_state[key]


def sync(name):
    S()["draft"][name] = st.session_state["ed_w_" + name]


def on_type_change(*_):

    sync("type")

    draft = S()["draft"]
    draft["width"] = bd.DEFAULT_WIDTH.get(draft["type"], "half")
    st.session_state["ed_w_width"] = draft["width"]

    if draft["type"] == "donut":
        draft["how"] = "sum"
        st.session_state["ed_w_how"] = "sum"


def draft_widget(factory, label, name, *args, **kwargs):
    """A widget whose value lives in the draft (so it is never forgotten)."""

    key = ensure("ed_w_" + name, S()["draft"][name])

    return factory(
        label, *args, key=key, on_change=kwargs.pop("on_change", sync),
        args=kwargs.pop("cb_args", (name,)), **kwargs,
    )


def save_editor():

    info, state = INFO(), S()
    d = state["draft"]

    kind = token_kind(d["measure"])
    chart_type = d["type"]

    if kind == "count":
        measure, agg = None, "count"
    elif kind == "distinct":
        measure, agg = d["measure"].split(":", 1)[1], "distinct"
    else:
        measure, agg = d["measure"].split(":", 1)[1], d["how"]

    values = {
        "type": chart_type,
        "title": str(d["title"] or "").strip(),
        "measure": measure,
        "agg": agg,
        "group": d["group"] if chart_type in GROUP_TYPES else None,
        "date": d["date"] if chart_type == "line" else None,
        "top": d["top"],
        "sort": d["sort"],
        "width": d["width"],
    }

    if state["editing"] != "new":
        values["id"] = state["editing"]

    tile = bd.new_tile(info, **values)
    problem = bd.check_tile(tile, info)

    if problem:
        state["editor_error"] = problem
        return

    if state["editing"] == "new" and len(state["tiles"]) >= bd.MAX_TILES:
        state["editor_error"] = f"A dashboard can hold up to {bd.MAX_TILES} charts."
        return

    state["tiles"] = bd.upsert_tile(state["tiles"], tile)
    state["editing"] = None
    state["editor_error"] = None


def close_editor():
    S()["editing"] = None
    S()["editor_error"] = None


def render_editor(info):

    state = S()
    d = state["draft"]
    creating = state["editing"] == "new"

    with st.container(key="glass-editor"):

        html(ui.card_title(
            "Add a chart" if creating else "Edit chart",
            "Pick what to show. Every number is calculated from your data.",
        ))

        types = available_types(info)

        if d["type"] not in types:
            d["type"] = types[0]

        draft_widget(
            st.radio, "Chart type", "type", types, horizontal=True,
            format_func=lambda t: bd.TYPE_NAMES[t], on_change=on_type_change,
        )

        chart_type = d["type"]
        tokens = measure_tokens(info)

        if d["measure"] not in tokens:
            d["measure"] = "__count__"

        c1, c2, c3 = st.columns(3, gap="medium")

        with c1:
            draft_widget(
                st.selectbox, "What to measure", "measure", tokens,
                format_func=lambda t: token_label(t, info),
            )

        kind = token_kind(d["measure"])

        with c2:

            if kind == "number":

                how_options = ["sum"] if chart_type == "donut" else bd.NUMBER_AGGS

                if d["how"] not in how_options:
                    d["how"] = how_options[0]
                    st.session_state["ed_w_how"] = d["how"]

                draft_widget(
                    st.selectbox, "How", "how", how_options,
                    format_func=lambda a: bd.AGG_NAMES[a],
                )

            else:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                st.caption(
                    "Counts the rows." if kind == "count"
                    else "Counts how many different values there are."
                )

        with c3:

            if chart_type in GROUP_TYPES:
                draft_widget(
                    st.selectbox, "Group by", "group", info["dims"],
                    format_func=lambda c: info["labels"][c],
                )

            elif chart_type == "line" and len(info["dates"]) > 1:
                draft_widget(st.selectbox, "Date column", "date", info["dates"])

        d1, d2, d3 = st.columns([1, 1, 1.25], gap="medium")

        with d1:
            if chart_type in GROUP_TYPES:
                draft_widget(st.slider, "Show top", "top", 1, 30)

        with d2:
            if chart_type in ("bar", "column", "table"):
                draft_widget(
                    st.radio, "Order", "sort", ["desc", "asc"], horizontal=True,
                    format_func=lambda s: "Highest" if s == "desc" else "Lowest",
                )

        with d3:
            draft_widget(
                st.radio, "Size", "width", bd.WIDTHS, horizontal=True,
                format_func=lambda w: bd.WIDTH_NAMES[w],
            )

        preview = bd.new_tile(
            info, type=chart_type,
            measure=None if kind == "count" else d["measure"].split(":", 1)[1],
            agg="count" if kind == "count" else ("distinct" if kind == "distinct" else d["how"]),
            group=d["group"] if chart_type in GROUP_TYPES else None,
        )

        draft_widget(
            st.text_input, "Title (optional)", "title",
            placeholder=bd.auto_title(preview, info),
        )

        if state["editor_error"]:
            st.warning(state["editor_error"])

        b1, b2, _ = st.columns([1, 1, 3], gap="small")

        b1.button("Save chart", type="primary", on_click=save_editor, **STRETCH)
        b2.button("Cancel", on_click=close_editor, **STRETCH)


# ============================================================
# Buttons on a chart
# ============================================================

def do_move(tile_id, step):
    S()["tiles"] = bd.move_tile(S()["tiles"], tile_id, step)


def do_duplicate(tile_id):
    S()["tiles"] = bd.duplicate_tile(S()["tiles"], tile_id)


def do_delete(tile_id):

    S()["tiles"] = bd.delete_tile(S()["tiles"], tile_id)

    if S()["editing"] == tile_id:
        close_editor()


def go_report():
    st.session_state["navigation_page"] = "Report"


def use_starter():
    S()["tiles"] = bd.starter_tiles(INFO())
    close_editor()


def clear_all():
    S()["tiles"] = []
    close_editor()


def render_tile_menu(tile):

    with st.popover("⋯"):

        st.button("Edit", key=f"m_edit_{tile['id']}", on_click=open_editor, args=(tile["id"],), **STRETCH)
        st.button("Move earlier", key=f"m_up_{tile['id']}", on_click=do_move, args=(tile["id"], -1), **STRETCH)
        st.button("Move later", key=f"m_dn_{tile['id']}", on_click=do_move, args=(tile["id"], 1), **STRETCH)
        st.button("Duplicate", key=f"m_cp_{tile['id']}", on_click=do_duplicate, args=(tile["id"],), **STRETCH)
        st.button("Delete", key=f"m_rm_{tile['id']}", on_click=do_delete, args=(tile["id"],), **STRETCH)


# ============================================================
# The KPI cards (fixed size)
# ============================================================

def render_kpi(tile, result, info, position):

    title = tile["title"] or bd.auto_title(tile, info)

    with st.container(key=f"glass-kpi-{tile['id']}"):

        render_tile_menu(tile)

        if result["kind"] == "kpi" and result["value"] is not None:
            value = bd.kpi_number(result["value"])
            full = dash.full_number(result["value"])
            sub = f"{result['rows']:,} {info['noun']} in view"

        elif result["kind"] == "kpi":
            value, full, sub = "—", "", "No numbers to calculate"

        else:
            value, full, sub = "—", "", result.get("message", "")

        html(ui.kpi_fixed_html(
            title, value, full, sub, ACCENTS[position % len(ACCENTS)],
            KPI_ICON.get(tile["agg"], "chart"),
        ))


# ============================================================
# The charts (fixed height)
# ============================================================

def chart_key(tile, payload, opts):

    raw = json.dumps(tile, sort_keys=True) + repr(payload) + repr(opts)

    return f"tc_{tile['id']}_{hashlib.md5(raw.encode()).hexdigest()[:8]}"


def render_chart(tile, result, info, opts):

    title = tile["title"] or bd.auto_title(tile, info, opts["grain"])
    kind = result["kind"]

    with st.container(key=f"glass-tile-{tile['id']}"):

        render_tile_menu(tile)

        html(ui.card_title(title, bd.tile_subtitle(tile, result)))

        if kind in ("empty", "error"):
            html(ui.tile_message_html(result["message"], error=(kind == "error")))
            return

        if kind == "line":

            marked = {
                (f"{k}*" if k in result["partial"] else k): v
                for k, v in result["months"].items()
            }

            st.altair_chart(
                ui.line_chart(marked, height=CHART_HEIGHT),
                **STRETCH, theme=None,
                key=chart_key(tile, list(marked.items()), opts),
            )
            return

        values = result["values"]
        key = chart_key(tile, list(values.items()), opts)

        if tile["type"] == "table":

            st.dataframe(
                result["frame"], hide_index=True, **STRETCH,
                height=CHART_HEIGHT,
            )

        elif tile["type"] == "donut":
            st.altair_chart(ui.donut_chart(values, height=CHART_HEIGHT), **STRETCH, theme=None, key=key)

        elif tile["type"] == "column":
            st.altair_chart(ui.column_chart(values, height=CHART_HEIGHT), **STRETCH, theme=None, key=key)

        else:

            # many bars scroll inside the tile, so every tile keeps its size
            with st.container(height=CHART_HEIGHT, border=False):
                st.altair_chart(
                    ui.bar_chart(values, height=max(CHART_HEIGHT - 16, 34 * len(values) + 40)),
                    **STRETCH, theme=None, key=key,
                )


def render_dashboard(view, info, opts):

    state = S()
    tiles = state["tiles"]

    if not tiles:

        html(ui.empty_state_html(
            "Your dashboard is empty",
            "Add a chart, or start from a ready-made dashboard and change it.",
        ))
        return

    kpis = [t for t in tiles if t["type"] == "kpi"]
    charts = [t for t in tiles if t["type"] != "kpi"]

    # ---------------- the KPI row: same size cards, 4 per row
    for start in range(0, len(kpis), KPI_PER_ROW):

        row = kpis[start:start + KPI_PER_ROW]
        columns = st.columns(KPI_PER_ROW, gap="medium")

        for offset, (column, tile) in enumerate(zip(columns, row)):
            with column:
                render_kpi(tile, bd.compute_tile(view, tile, info, opts), info, start + offset)

    # ---------------- the charts, in a grid
    for row in bd.pack_rows(charts):

        widths = [bd.WIDTH_UNITS[t["width"]] for t in row]

        if sum(widths) < 4:
            widths.append(4 - sum(widths))

        columns = st.columns(widths, gap="medium")

        for column, tile in zip(columns, row):
            with column:
                render_chart(tile, bd.compute_tile(view, tile, info, opts), info, opts)


# ============================================================
# Save and load
# ============================================================

def handle_upload(info):
    """Loads a dashboard file (before the title box is drawn)."""

    state = S()
    uploaded = st.session_state.get(f"bload_{ekey()}")

    if uploaded is None:
        return

    raw = uploaded.getvalue()
    digest = hashlib.md5(raw).hexdigest()

    if digest == state["loaded_hash"]:
        return

    result = bd.load_dashboard(raw.decode("utf-8", errors="replace"), info)

    if result["tiles"]:
        state["tiles"] = result["tiles"]
        state["title"] = result["title"]
        st.session_state[f"bt_{ekey()}"] = result["title"]
        close_editor()

    state["loaded_hash"] = digest
    state["load_notes"] = result["problems"] or (
        [] if result["tiles"] else ["No charts could be loaded."]
    )


def render_save_load():

    state = S()

    with st.expander("Save or load a dashboard"):

        st.download_button(
            "Download this dashboard", bd.dump(state["tiles"], state["title"]),
            file_name="dashboard.json", mime="application/json",
        )

        st.file_uploader(
            "Load a dashboard file", type=["json"], key=f"bload_{ekey()}",
        )

        st.caption("The file keeps the title and the charts. Filters are not saved.")


# ============================================================
# The page
# ============================================================

def set_title(key):
    S()["title"] = st.session_state[key]


def render(engine, name, filter_slot):

    info = get_info(engine)
    state = get_state(info)

    handle_upload(info)

    filters, opts, counter = render_filters(info, filter_slot)

    view = bd.apply_filters(info, filters)

    counter.markdown(
        f'<div class="filter-count">Showing {len(view):,} of {len(info["df"]):,} {info["noun"]}</div>',
        unsafe_allow_html=True,
    )

    # ---------------- title
    html('<div class="eyebrow-line">Visualize</div>')

    title_key = ensure(f"bt_{ekey()}", state["title"])

    with st.container(key="title-box"):
        st.text_input(
            "Dashboard name", key=title_key, label_visibility="collapsed",
            placeholder="Enter your dashboard name here",
            on_change=set_title, args=(title_key,), max_chars=80,
        )

    html('<div class="title-hint">For example: Sales Overview · Profit Analysis · Customer Insights</div>')

    # ---------------- toolbar
    with st.container(key="glass-toolbar"):

        a, b, c, d, _ = st.columns([1.2, 1.7, 1.1, 1.6, 0.9], gap="small")

        a.button("＋ Add chart", type="primary", on_click=open_editor, args=("new",), **STRETCH)
        b.button("Starter dashboard", on_click=use_starter, **STRETCH)
        c.button("Clear all", on_click=clear_all, **STRETCH)
        d.button("Export report", on_click=go_report, **STRETCH)

        render_save_load()

    for note in state["load_notes"]:
        st.warning(note)

    state["load_notes"] = []

    if state["editing"] is not None:
        render_editor(info)

    render_dashboard(view, info, opts)
