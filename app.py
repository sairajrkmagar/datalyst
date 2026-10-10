import hashlib
import json
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import builder as bd
import builder_ui
import clarify
from compat import STRETCH
import cleaning
import dashboard as dash
import examples
import feedback
import file_reader
import insights as ins
import report
import ui
import understanding
from ask_engine import AskEngine
from llm_client import ollama_status

SAMPLE_FILE = "sample_sales.csv"
DEMO_ENV = "DATALYST_DEMO_FILE"   # a file to open automatically (for testing)

st.set_page_config(
    page_title="Datalyst · AI Data Analyst",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="auto",          # open on a computer, closed on a phone
)


def safe(text):
    """Streamlit reads $...$ as maths, which garbles text. Escape it."""
    return str(text).replace("$", "\\$")


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_table(file_name, file_bytes, sheet=None):
    """(table, info): the file read once, safely (not again on every click)."""

    return file_reader.read_table(file_name, file_bytes, sheet)


def load_data(file_name, file_bytes):
    table, _ = load_table(file_name, file_bytes, st.session_state.get("sheet"))
    return table


def file_info():
    name, data = st.session_state["source"]
    return load_table(name, data, st.session_state.get("sheet"))[1]


def is_new_upload(uploaded, memory_key):
    """
    True once per uploaded file. An uploader keeps holding its file on every
    rerun; without this, the app would re-open that file again and again and
    undo anything done since (like cleaning).
    """

    signature = (getattr(uploaded, "file_id", None), uploaded.name, uploaded.size)

    if st.session_state.get(memory_key) == signature:
        return False

    st.session_state[memory_key] = signature
    return True


def accept_upload(name, data):
    """
    Check a file BEFORE using it. Returns True when it can be used; otherwise
    remembers a plain-words reason to show, and returns False.
    """

    try:
        load_table(name, data, None)

    except file_reader.FileProblem as problem:
        st.session_state["file_problem"] = {
            "name": name, "message": problem.message, "steps": problem.steps,
        }
        return False

    except Exception:
        st.session_state["file_problem"] = {
            "name": name, "steps": ["Try saving it again as CSV or XLSX."],
            "message": "Something unexpected happened while reading this file.",
        }
        return False

    st.session_state.pop("file_problem", None)
    forget_cleaning()
    set_source(name, data)
    return True


def show_file_notes():
    """What was decided when the file was opened (encoding, separator, sheet ...)."""

    if "source" not in st.session_state:
        return

    for note in file_info().get("notes", []):
        html(ui.notice_html(note))


@st.cache_data(ttl=8, show_spinner=False)
def ai_state():
    return ollama_status()


# ============================================================
# Which file are we working on?
# ============================================================

def set_source(name, data):
    st.session_state["source"] = (name, data)

    # a new file: forget everything about the old one
    for key in ["last", "history", "dash", "engine_key", "warm_key", "builder_state", "builder_info_key", "sheet", "file_problem"]:
        st.session_state.pop(key, None)


def get_engine():
    """The engine for the current file (built once, reused on every click)."""

    name, data = st.session_state["source"]
    key = f"{name}-{len(data)}-{st.session_state.get('sheet')}"

    if st.session_state.get("engine_key") != key:

        raw = load_data(name, data)

        with st.spinner("Reading your data..."):
            st.session_state["engine"] = AskEngine(raw)

        st.session_state["engine_key"] = key
        st.session_state.pop("dash", None)

    return st.session_state["engine"]


# ============================================================
# The pages
# ============================================================

def page_landing():

    html(ui.hero_html(
        "Ask your data anything.",
        "Upload a spreadsheet and ask questions in plain English. Every "
        "number is calculated by code and double-checked. The AI explains, "
        "it never guesses.",
        eyebrow="Datalyst · AI Data Analyst",
    ))

    uploaded = st.file_uploader(
        "Upload your CSV or Excel file",
        type=["csv", "tsv", "txt", "xlsx", "xls"],
        key="uploader_main",
    )

    if uploaded is not None and is_new_upload(uploaded, "main_seen"):
        if accept_upload(uploaded.name, uploaded.getvalue()):
            st.rerun()

    problem = st.session_state.get("file_problem")

    if problem:
        html(ui.problem_card_html(
            None, f"We could not read \u201c{problem['name']}\u201d",
            problem["message"], problem["steps"],
        ))

    st.caption(
        "Your file stays on your computer. The AI model runs locally (Ollama) "
        "and only sees your question, the column names and the names of your "
        "categories. Every number is calculated by code."
    )

    if os.path.exists(SAMPLE_FILE):

        if st.button("Try it with sample sales data", key="try_sample"):

            with open(SAMPLE_FILE, "rb") as handle:
                accept_upload(SAMPLE_FILE, handle.read())

            st.rerun()

    html(ui.how_it_works_html())


def page_dashboard(engine, name):

    if "dash" not in st.session_state:
        st.session_state["dash"] = dash.build_dashboard(engine)

    d = st.session_state["dash"]

    chips = [
        {"text": f"{d['rows']:,} {d['noun']}"},
        {"text": f"{d['columns']} columns"},
    ]

    trend = d.get("trend")

    if trend:
        months = list(trend["months"])
        chips.append({"text": f"{months[0]} to {months[-1]}"})

    show_file_notes()
    show_tour()

    chips.append({
        "text": f"Data quality {d['kpis'][-1]['value']}",
        "tone": "green" if d["completeness"] >= 98 and d["duplicates"] == 0 else "orange",
    })

    html(ui.hero_html(
        "Dashboard",
        f"A live overview of {name}.",
        eyebrow="Overview",
        chips=chips,
    ))

    html(ui.kpi_row_html(d["kpis"]))

    # ---------------- the charts (drawn by small helpers)
    def draw_trend(height):

        label = d["measure_label"] or d["noun"]
        title_text = (
            dash.total_label(d["measure"]) if d["kind"] == "sum" and d["measure"]
            else f"Average {label}"
        )
        note = (
            f"Full months only. Left out: {', '.join(trend['left_out'])}"
            if trend["left_out"] else "Full months"
        )

        with st.container(key="glass-trend"):
            html(ui.card_title(f"{title_text} by month", note))
            st.altair_chart(
                ui.line_chart(trend["months"], height=height),
                **STRETCH, theme=None,
                key=f"dash_trend_{st.session_state['engine_key']}",
            )

    bar, donut = d.get("bar"), d.get("donut")

    def draw_bars(height):

        what = {
            "sum": f"{d['measure_label']}",
            "mean": f"average {d['measure_label']}",
            "count": f"number of {d['noun']}",
        }[bar["agg"]]

        with st.container(key="glass-bars"):
            html(ui.card_title(f"{what.capitalize()} by {bar['label']}", "Top 8"))
            st.altair_chart(
                ui.bar_chart(bar["values"], height=height),
                **STRETCH, theme=None,
                key=f"dash_bars_{st.session_state['engine_key']}",
            )

    def draw_donut(height):

        with st.container(key="glass-donut"):
            html(ui.card_title(f"{d['noun'].capitalize()} by {donut['label']}", "Share of rows"))
            st.altair_chart(
                ui.donut_chart(donut["values"], height=height),
                **STRETCH, theme=None,
                key=f"dash_donut_{st.session_state['engine_key']}",
            )

    charts = []

    if trend:
        charts.append(draw_trend)

    if bar:
        charts.append(draw_bars)

    if donut:
        charts.append(draw_donut)

    # ---------------- the first chart is big, next to the side cards
    left, right = st.columns([2, 1], gap="medium")

    with left:

        if charts:
            charts[0](345)
        else:
            with st.container(key="glass-empty"):
                html(ui.card_title("No chart yet"))
                st.caption("This file has no date or category column to draw.")

    with right:

        with st.container(key="glass-highlights"):

            html(ui.card_title("Highlights", "Calculated from your data"))
            html(ui.highlights_html(d["highlights"]))

        with st.container(key="glass-ask-cta"):

            html(ui.card_title("Ask your data", "Tap a question to try it"))

            for index, text in enumerate(dash.suggest_questions(engine)[1:4]):
                st.button(
                    text, key=f"cta_{index}", on_click=go_ask, args=(text,),
                    **STRETCH,
                )

    # ---------------- the other charts, below
    rest = charts[1:]

    if len(rest) == 2:

        first, second = st.columns(2, gap="medium")

        with first:
            rest[0](300)

        with second:
            rest[1](300)

    elif len(rest) == 1:
        rest[0](300)

    if d["tidied"]:

        with st.expander("What was tidied up automatically"):
            for column_name, note in d["tidied"].items():
                st.write(safe(f"- {column_name}: {note}"))


# ---------------------------------------------------------------- Ask AI

def pick_question(text):
    st.session_state["ask_q"] = text
    st.session_state["run_now"] = True


def pin_answer(engine, answer, base):
    """Put an answer (a table, ranking or trend) on the Visualize dashboard."""

    info = builder_ui.get_info(engine)
    state = builder_ui.get_state(info)
    tile, why = bd.tile_from_answer(answer, info, state["tiles"])

    if tile is None:
        st.session_state[f"pin_{base}"] = ("warn", why)
        return

    state["tiles"] = bd.upsert_tile(state["tiles"], tile)
    st.session_state[f"pin_{base}"] = ("ok", "Pinned. Open Visualize to see it on your dashboard.")


def save_feedback(engine, question, answer, rating, base, comment=""):
    """One reaction, saved on this computer (see feedback_report.py)."""

    feedback.record(
        question, answer, rating,
        dataset=st.session_state["source"][0], columns=list(engine.df.columns),
        comment=comment,
    )
    st.session_state[f"fb_{base}"] = rating


def open_note(base):
    st.session_state[f"fbopen_{base}"] = True


def go_page(name):
    st.session_state["navigation_page"] = name


def finish_tour():
    st.session_state["tour_done"] = True


def accessibility_labels():
    """Names for two controls Streamlit draws without one (for screen readers)."""

    try:
        _inject_accessibility_labels()
    except Exception:
        pass                      # only names for screen readers: never worth a crash


def _inject_accessibility_labels():
    components.html(
        """<script>
        const w = window.parent;
        if (!w.__datalystLabels) {
          w.__datalystLabels = true;
          const fix = () => {
            const d = w.document;
            d.querySelectorAll('[data-testid="stBaseButton-headerNoPadding"]').forEach(b => {
              if (!b.getAttribute('aria-label')) b.setAttribute('aria-label', 'Show or hide the menu');
            });
            // an attribute that is not allowed on these containers (it only confuses screen readers)
            d.querySelectorAll('section[data-testid="stSidebar"], #MainMenu').forEach(e => e.removeAttribute('aria-expanded'));
            d.querySelectorAll('summary').forEach(s => {
              if (!s.innerText.trim() && !s.getAttribute('aria-label')) s.setAttribute('aria-label', 'Chart options');
            });
          };
          fix();
          new MutationObserver(fix).observe(w.document.body, {childList: true, subtree: true});
        }
        </script>""",
        height=0,
    )


def show_tour():
    """Three steps for a first visit (hidden for good once dismissed)."""

    if st.session_state.get("tour_done"):
        return

    with st.container(key="glass-tour"):

        html(ui.card_title("Welcome to Datalyst", "Three things to try with your file"))

        a, b, c = st.columns(3, gap="small")

        a.markdown("**1. Ask**  \nType a question in plain English and get an exact answer.")
        a.button("Open Ask AI", key="tour_ask", on_click=go_page, args=("Ask AI",), **STRETCH)

        b.markdown("**2. Discover**  \nSee what is worth knowing about your data, found for you.")
        b.button("Open Insights", key="tour_insights", on_click=go_page, args=("Insights",), **STRETCH)

        c.markdown("**3. Build and share**  \nMake a dashboard and download it as a report.")
        c.button("Open Visualize", key="tour_viz", on_click=go_page, args=("Visualize",), **STRETCH)

        st.button("Got it, hide this", key="tour_done_btn", on_click=finish_tour)


def go_ask(text):
    """Jump to the Ask AI page and run a question."""

    st.session_state["navigation_page"] = "Ask AI"
    st.session_state["ask_q"] = text
    st.session_state["run_now"] = True


def draw_result_chart(answer, result_id=0):
    """A chart for answers that are tables, rankings or trends."""

    plan = answer["plan"]
    result = answer["result"]
    intent = plan["intent"]

    if intent == "trend" and isinstance(result, dict):
        chart = ui.line_chart(result, height=290)
        title = "Over time"

    elif isinstance(result, dict):
        percent = intent == "share" or bool(plan.get("as_percent"))
        chart = ui.bar_chart(result, height=max(220, 44 * len(result)), percent=percent)
        title = "Breakdown"

    elif isinstance(result, list):
        chart = ui.bar_chart(dict(result), height=max(200, 52 * len(result)))
        title = "Ranking"

    else:
        return

    with st.container(key="glass-result-chart"):
        html(ui.card_title(title))
        st.altair_chart(
            chart, **STRETCH, theme=None,
            key=f"result_chart_{result_id}",
        )


def render_one(engine, last, sub_q, answer, index, single):
    """One question and its answer."""

    if answer["status"] != "success":

        kind = answer.get("kind")

        if kind == "ai_offline":
            html(ui.problem_card_html(
                sub_q, "The AI is not running",
                "This question needs the AI to read it. Statistics, growth, "
                "ratio and ranking questions work without it.",
                ["Open the Ollama app (or run: ollama serve)", "Ask the question again"],
            ))
            return

        if kind in ("ai_slow", "ai_error"):
            html(ui.problem_card_html(
                sub_q, "The AI had a problem", safe(answer["message"]),
                ["Wait a moment and ask again"],
            ))
            return

        html(ui.refusal_card_html(sub_q, safe(answer["message"])))

        base = f"{last['id']}_{index}"
        choice = clarify.suggest(engine, sub_q, answer["message"])

        if choice:
            st.caption(safe(choice["prompt"]))
            columns = st.columns(min(len(choice["options"]), 4), gap="small")

            for n, (column, option) in enumerate(zip(columns, choice["options"])):
                column.button(
                    option["label"], key=f"clar_{base}_{n}",
                    on_click=pick_question, args=(option["question"],),
                    **STRETCH,
                )

        if st.session_state.get(f"fb_{base}"):
            st.caption("Thanks. Saved on this computer so it can be fixed.")
        else:
            st.button(
                "This should have worked", key=f"fbx_{base}",
                on_click=save_feedback, args=(engine, sub_q, answer, "down", base),
            )
        return

    html(ui.answer_card_html(sub_q, answer))

    if answer.get("rewritten_from"):
        html(ui.notice_html(
            f"I read \u201c{answer['rewritten_from']}\u201d as: {answer.get('question', '')}"
        ))

    if answer["plan"].get("notice"):
        html(ui.notice_html(answer["plan"]["notice"]))

    html(ui.understood_html(
        understanding.describe(answer["plan"], lambda c: dash.dim_label(engine, c))
    ))

    if answer.get("values"):
        html(ui.values_chips_html(answer["values"], answer.get("values_total")))

    draw_result_chart(answer, f"{last['id']}_{index}")

    explanation = {"text": "", "source": "template", "facts": []}

    if single:

        # the exact answer is on screen; now write the insight
        slot = st.empty()

        if last["explanation"] is None:

            slot.markdown(
                '<div class="glass insight"><div class="ico">'
                + ui.icon_svg("sparkle", 19)
                + '</div><div><div class="head">Insight</div>'
                '<div class="body" style="color:#86868b">Writing the insight...</div></div></div>',
                unsafe_allow_html=True,
            )

            last["explanation"] = engine.explain(answer) or {
                "text": "", "source": "template", "facts": []
            }

        explanation = last["explanation"]

        if explanation["text"]:
            slot.markdown(
                ui.insight_card_html(explanation["text"], explanation["source"] == "ai"),
                unsafe_allow_html=True,
            )
        else:
            slot.empty()

    base = f"{last['id']}_{index}"
    pinned = st.session_state.get(f"pin_{base}")
    reaction = st.session_state.get(f"fb_{base}")

    a, b, c, _ = st.columns([1.4, 1, 1, 3], gap="small")

    a.button(
        "Pin to dashboard", key=f"pin_btn_{base}",
        on_click=pin_answer, args=(engine, answer, base), **STRETCH,
    )
    b.button(
        "Helpful", key=f"up_{base}", disabled=bool(reaction),
        on_click=save_feedback, args=(engine, sub_q, answer, "up", base),
        **STRETCH,
    )
    c.button(
        "Not right", key=f"down_{base}", disabled=bool(reaction),
        on_click=open_note, args=(base,), **STRETCH,
    )

    if pinned:
        (st.success if pinned[0] == "ok" else st.warning)(safe(pinned[1]))

    if st.session_state.get(f"fbopen_{base}") and not reaction:
        st.text_input("What was wrong? (optional)", key=f"fbnote_{base}")
        st.button(
            "Save", key=f"fbsave_{base}", on_click=lambda: save_feedback(
                engine, sub_q, answer, "down", base, st.session_state.get(f"fbnote_{base}", ""),
            ),
        )

    if reaction:
        st.caption("Thanks. Saved on this computer.")

    with st.expander("How I got this answer"):

        html(ui.steps_html(answer["repairs"]))

        plan_lines = "\n".join(
            f"{key}: {value}" for key, value in answer["plan"].items()
            if value not in (None, [], {}) and key not in ("unsupported", "notice")
        )
        html(ui.code_block_html(plan_lines))

        if answer["repairs"]:
            st.caption(safe("Corrections: " + "; ".join(answer["repairs"])))

        if explanation["facts"]:
            st.write("Facts behind the insight:")
            for fact_name, value in explanation["facts"]:
                st.write(safe(f"- {fact_name}: {value}"))


def render_result(engine, last):

    items = last["answers"]

    if len(items) > 1:
        st.caption(f"I read this as {len(items)} questions and answered each one.")

    for index, (sub_q, answer) in enumerate(items):
        render_one(engine, last, sub_q, answer, index, single=(len(items) == 1))


def page_ask(engine, name):

    key = st.session_state["engine_key"]

    if st.session_state.get("warm_key") != key:

        with st.spinner("Getting the AI ready (only the first time)..."):
            engine.warm_up()

        st.session_state["warm_key"] = key

    html(ui.hero_html(
        "Ask your data",
        "Type a question in plain English. You get an exact answer, a chart "
        "when it helps, and a short explanation you can trust.",
        eyebrow="Ask AI",
    ))

    with st.container(key="glass-form"):

        with st.form("ask_form", border=False):

            field, button = st.columns([6, 1.15], gap="small")

            field.text_input(
                "Your question",
                key="ask_q",
                placeholder="Try: Which category has the highest revenue?",
                label_visibility="collapsed",
            )

            submitted = button.form_submit_button(
                "Ask", type="primary", **STRETCH
            )

        suggestions = dash.suggest_questions(engine)

        st.caption("Try one of these")

        for start in range(0, len(suggestions), 3):

            row = suggestions[start:start + 3]
            columns = st.columns(len(row), gap="small")

            for offset, (column, text) in enumerate(zip(columns, row)):
                column.button(
                    text, key=f"suggest_{start + offset}",
                    on_click=pick_question, args=(text,),
                    **STRETCH,
                )

    with st.expander("What can I ask?"):

        if st.session_state.get("examples_key") != key:
            st.session_state["examples_groups"] = examples.build(engine)
            st.session_state["examples_key"] = key

        example_groups = st.session_state["examples_groups"]

        if example_groups:
            tabs = st.tabs([g["title"] for g in example_groups])

            for g_index, (tab, group) in enumerate(zip(tabs, example_groups)):
                with tab:
                    for i_index, item in enumerate(group["items"]):
                        st.button(
                            item["q"], key=f"ex_{g_index}_{i_index}",
                            on_click=pick_question, args=(item["q"],),
                            **STRETCH,
                        )

    run_now = st.session_state.pop("run_now", False)
    question = str(st.session_state.get("ask_q", "")).strip()

    if (submitted or run_now) and question:

        with st.spinner("Thinking..."):

            try:
                answers = engine.ask_many(question)

            except RuntimeError as error:
                text = str(error)
                kind = (
                    "ai_offline" if "Cannot reach Ollama" in text
                    else "ai_slow" if "too long" in text else "ai_error"
                )
                answers = [(question, {"status": "error", "message": text, "kind": kind})]

            except Exception as error:
                answers = [(question, {
                    "status": "error",
                    "message": f"Something went wrong: {error}",
                })]

        st.session_state["answer_counter"] = (
            st.session_state.get("answer_counter", 0) + 1
        )

        st.session_state["last"] = {
            "q": question, "answers": answers, "explanation": None,
            "id": st.session_state["answer_counter"],
        }

        history = st.session_state.setdefault("history", [])
        history.insert(0, question)
        del history[8:]

    last = st.session_state.get("last")

    st.write("")

    if last:
        render_result(engine, last)

    history = st.session_state.get("history", [])[1:5]

    if history:

        with st.expander("Recent questions"):
            for earlier in history:
                st.write(safe(f"- {earlier}"))


# ---------------------------------------------------------------- Insights

def page_insights(engine, name):

    html(ui.hero_html(
        "Insights",
        "Things worth knowing about your data, found automatically. Every "
        "sentence is built from numbers calculated in code.",
        eyebrow="Discover",
    ))

    if "insights" not in st.session_state or st.session_state.get("insights_key") != st.session_state["engine_key"]:
        st.session_state["insights"] = ins.build_insights(engine)
        st.session_state["insights_key"] = st.session_state["engine_key"]

    items = st.session_state["insights"]

    if items:
        html(ui.insights_grid_html(items))
    else:
        st.info("Not enough structure in this file to find insights yet.")


# ---------------------------------------------------------------- Visualize

def page_visualize(engine, name):
    builder_ui.render(engine, name, filters_slot)


# ---------------------------------------------------------------- Report

def go_visualize():
    st.session_state["navigation_page"] = "Visualize"


def page_report(engine, name):

    html(ui.hero_html(
        "Report",
        "Download your dashboard as a report you can send: a PDF, a Word file, "
        "an Excel file with the numbers and charts, or a web page that works "
        "offline. It uses the charts and filters you set on the Visualize page.",
        eyebrow="Share",
    ))

    missing = report.missing_libraries()

    if missing:

        html(ui.soon_html(
            "One step first",
            "Reports need a few small tools that are not installed yet. Run "
            "this once in your Terminal, then restart the website "
            "(Ctrl + C, then streamlit run app.py).",
            "file",
        ))
        st.code("pip install " + " ".join(missing), language="bash")
        return

    info = builder_ui.get_info(engine)
    state = builder_ui.get_state(info)
    filters, opts = builder_ui.filters_from_state(info)

    if not state["tiles"]:

        html(ui.empty_state_html(
            "Your dashboard is empty",
            "Build a dashboard first. The report is made from your charts.",
        ))
        st.button("Open Visualize", on_click=go_visualize, type="primary")
        return

    ekey = builder_ui.ekey()
    stem = os.path.splitext(name)[0].replace("_", " ")

    with st.container(key="glass-report"):

        html(ui.card_title("Your report", "Pick a title and what to include"))

        title_key = builder_ui.ensure(f"rp_title_{ekey}", state["title"] or stem.title())

        title = st.text_input("Report title", key=title_key, max_chars=80)

        with_insights = st.toggle(
            "Include the insights (findings about the whole file)",
            value=True, key=f"rp_ins_{ekey}",
        )

        st.caption("Formats")
        columns = st.columns(len(report.FORMATS), gap="small")
        formats = []

        for column, (key, (label, _, _)) in zip(columns, report.FORMATS.items()):
            if column.checkbox(label, value=True, key=f"rp_fmt_{ekey}_{key}"):
                formats.append(key)

        kpi_count = sum(1 for t in state["tiles"] if t["type"] == "kpi")
        chart_count = len(state["tiles"]) - kpi_count

        chips = [
            {"text": f"{kpi_count} key numbers", "tone": "blue"},
            {"text": f"{chart_count} charts", "tone": "blue"},
        ] + [{"text": line} for line in report.describe_filters(info, filters, opts)]

        html(ui.hero_html("", "", chips=chips).replace('class="hero"', 'class="hero" style="margin:14px 0 6px"'))

        if not formats:
            st.warning("Tick at least one format.")

        create = st.button(
            "Create report", type="primary", disabled=not formats, key=f"rp_go_{ekey}",
        )

    signature = hashlib.md5(
        json.dumps([title, state["tiles"], filters, opts, with_insights, formats], sort_keys=True, default=str).encode()
    ).hexdigest()

    if create and formats:

        try:
            with st.spinner("Creating your report... (charts are drawn one by one)"):
                data = report.build_report(
                    engine, info, state["tiles"], filters, opts, title, name, with_insights
                )
                files = report.export(data, formats)

            st.session_state["report_result"] = {"sig": signature, "files": files, "title": title}

        except Exception as error:
            st.session_state.pop("report_result", None)
            st.error(safe(f"The report could not be created: {error}"))

    result = st.session_state.get("report_result")

    if result and result["files"] and result["sig"] == signature:

        with st.container(key="glass-report-done"):

            html(ui.card_title("Your report is ready", "Click to download"))

            buttons = st.columns(len(result["files"]), gap="small")

            for column, (key, content) in zip(buttons, result["files"].items()):

                label, extension, mime = report.FORMATS[key]

                column.download_button(
                    f"Download {label}", content,
                    file_name=report.file_name(result["title"], extension),
                    mime=mime, **STRETCH, key=f"rp_dl_{key}",
                )

            st.caption(
                "Every number in the report comes from your data, calculated "
                "by code. The same numbers as on the Visualize page."
            )

    elif result:
        st.info("You changed something. Press 'Create report' again to refresh the files.")


# ---------------------------------------------------------------- Data

def page_data(engine, name):

    df = engine.df

    numeric = df.select_dtypes(include="number").columns.tolist()
    dates = engine.dataset_understanding["date_columns"]
    text_columns = [c for c in df.columns if c not in numeric and c not in dates]

    show_file_notes()
    st.caption("Read as: " + file_reader.describe(file_info()))

    html(ui.hero_html(
        "Data",
        f"What is inside {name}, column by column.",
        eyebrow="Prepare",
        chips=[
            {"text": f"{len(df):,} rows"},
            {"text": f"{len(df.columns)} columns"},
            {"text": f"{len(numeric)} number", "tone": "blue"},
            {"text": f"{len(text_columns)} text"},
            {"text": f"{len(dates)} date"},
        ],
    ))

    profile = pd.DataFrame({
        "Column": df.columns,
        "Type": [
            "date" if c in dates else ("number" if c in numeric else "text")
            for c in df.columns
        ],
        "Missing": [int(df[c].isnull().sum()) for c in df.columns],
        "Different values": [int(df[c].nunique()) for c in df.columns],
        "Example": [
            str(df[c].dropna().iloc[0])[:40] if df[c].notna().any() else ""
            for c in df.columns
        ],
    })

    tab_columns, tab_quality, tab_preview = st.tabs(["Columns", "Quality", "Preview"])

    with tab_columns:
        st.dataframe(
            profile, hide_index=True, **STRETCH,
            height=min(760, 36 * (len(profile) + 1) + 4),
        )

    with tab_quality:

        missing_total = int(df.isnull().sum().sum())
        duplicates = int(df.duplicated().sum())

        if missing_total == 0 and duplicates == 0:
            st.success("No missing values and no duplicate rows. The data is clean.")
        else:
            st.warning(
                safe(f"{missing_total:,} missing values and {duplicates:,} duplicate rows.")
            )

        gaps = profile[profile["Missing"] > 0][["Column", "Missing"]]

        if len(gaps):
            st.dataframe(gaps, hide_index=True, **STRETCH)

        if engine.conversions:
            st.write("Tidied automatically when the file was opened:")
            for column_name, note in engine.conversions.items():
                st.write(safe(f"- {column_name}: {note}"))

    with tab_preview:
        st.dataframe(df.head(50), hide_index=True, **STRETCH)


# ---------------------------------------------------------------- Clean
# (your original cleaning page, unchanged)

def render_clean(df):
    # Clean column names → consistent format for analysis
    cleaned_df = df.copy()

    cleaned_df.columns = (
        cleaned_df.columns
        .str.strip()                 # Remove extra spaces
        .str.lower()                 # Convert to lowercase
        .str.replace(" ", "_")       # Replace spaces with _
    )

    # Clean text values → remove unnecessary spaces
    for column in cleaned_df.select_dtypes(include="object").columns:
        cleaned_df[column] = cleaned_df[column].str.strip()

    # Handle blank text values → treat them as missing values
    for column in cleaned_df.select_dtypes(include="object").columns:
        cleaned_df[column] = cleaned_df[column].replace(r"^\s*$", pd.NA, regex=True)

    # Detect date columns → prepare data for time-based analysis
    date_columns = []

    possible_date_columns = df.select_dtypes(
        include=["object", "datetime64[ns]"]
    ).columns

    for column in possible_date_columns:
        try:
            sample = df[column].dropna().head(1000)
            converted = pd.to_datetime(
                sample, errors="coerce", format="mixed"
            )
            if len(sample) > 0 and converted.notna().mean() > 0.8:
                date_columns.append(column)
        except:
            pass
    # the columns were renamed above (lowercase, underscores), so the
    # date columns must be looked up by their NEW names
    date_columns = [
        str(c).strip().lower().replace(" ", "_") for c in date_columns
    ]

    # Check missing values → identify incomplete data
    cleaned_missing_values = cleaned_df.isnull().sum()

    st.subheader("Cleaned Data Missing Values")
    st.dataframe(cleaned_missing_values.reset_index(name="Missing Values"))

    # Remove duplicate rows → keep only unique records
    duplicate_count_before = cleaned_df.duplicated().sum()

    cleaned_df = cleaned_df.drop_duplicates()

    duplicate_count_after = cleaned_df.duplicated().sum()

    st.subheader("Duplicate Cleaning")
    st.write(f"Duplicates removed: {duplicate_count_before}")

    st.subheader("Data Preview")
    st.dataframe(df.head(10))

    # Clean numeric columns → convert valid numeric values to numbers
    for column in cleaned_df.columns:
        cleaned_df[column] = pd.to_numeric(
            cleaned_df[column],
            errors="ignore"
        )

    # Check numeric columns → show clean integer values
    numeric_check = {}

    for column in cleaned_df.columns:
        converted = pd.to_numeric(cleaned_df[column], errors="coerce")

        if converted.notna().sum() > 0:
            invalid_count = int(converted.isna().sum())
            numeric_check[column] = invalid_count

    st.subheader("Invalid Numeric Values")
    st.write(numeric_check)

    # Clean date columns → convert valid dates to datetime
    for column in date_columns:
        cleaned_df[column] = pd.to_datetime(
            cleaned_df[column],
            errors="coerce"
        )

    # Check invalid dates → identify dates that could not be converted
    invalid_dates = {}

    for column in date_columns:
        invalid_dates[column] = int(cleaned_df[column].isna().sum())

    st.subheader("Invalid Dates")
    st.write(invalid_dates)

    # Standardize text case → keep categorical values consistent
    for column in cleaned_df.select_dtypes(include="object").columns:
        cleaned_df[column] = cleaned_df[column].str.strip().str.lower()

    # Detect outliers → flag unusually high or low numeric values
    outlier_counts = {}

    for column in cleaned_df.select_dtypes(include="number").columns:
        Q1 = cleaned_df[column].quantile(0.25)
        Q3 = cleaned_df[column].quantile(0.75)
        IQR = Q3 - Q1

        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        outlier_count = (
            (cleaned_df[column] < lower_bound) |
            (cleaned_df[column] > upper_bound)
        ).sum()

        outlier_counts[column] = int(outlier_count)

    # Detect empty columns → identify columns with no usable data
    empty_columns = cleaned_df.columns[
        cleaned_df.isna().all()
    ].tolist()

    st.subheader("Empty Columns")
    st.write(empty_columns)

    # Remove empty columns → keep only columns with usable data
    if empty_columns:
        cleaned_df = cleaned_df.drop(columns=empty_columns)

    # Show cleaned data → preview the result after cleaning
    st.subheader("Cleaned Data Preview")
    st.dataframe(cleaned_df.head(10))

    # Compare rows → see whether cleaning removed any records
    rows_before = len(df)
    rows_after = len(cleaned_df)

    st.subheader("Cleaning Result")
    st.write(f"Rows Before Cleaning: {rows_before}")
    st.write(f"Rows After Cleaning: {rows_after}")
    st.write(f"Rows Removed: {rows_before - rows_after}")

    # Compare missing values → see whether cleaning reduced missing data
    missing_before = df.isnull().sum().sum()
    missing_after = cleaned_df.isnull().sum().sum()

    st.subheader("Missing Value Cleaning")
    st.write(f"Missing Values Before Cleaning: {missing_before}")
    st.write(f"Missing Values After Cleaning: {missing_after}")
    st.write(f"Missing Values Remaining: {missing_after}")

    # Compare duplicates → verify duplicate removal
    duplicates_before = df.duplicated().sum()
    duplicates_after = cleaned_df.duplicated().sum()

    st.subheader("Duplicate Cleaning Result")
    st.write(f"Duplicates Before Cleaning: {duplicates_before}")
    st.write(f"Duplicates After Cleaning: {duplicates_after}")
    st.write(f"Duplicates Removed: {duplicates_before - duplicates_after}")

    # Compare data types → verify type changes after cleaning
    type_comparison = pd.DataFrame({
        "Before": df.dtypes.astype(str),
        "After": cleaned_df.dtypes.astype(str)
    })

    st.subheader("Data Type Changes")
    st.dataframe(type_comparison)

    # Cleaning summary → show the main cleaning results
    st.subheader("Cleaning Action Summary")

    st.write(f"Rows Removed: {rows_before - rows_after}")
    st.write(f"Duplicates Removed: {duplicates_before - duplicates_after}")
    st.write(f"Missing Values Before: {missing_before}")
    st.write(f"Missing Values After: {missing_after}")
    st.write(f"Empty Columns Removed: {len(empty_columns)}")

    # Download cleaned data → save the cleaned dataset as CSV
    cleaned_csv = cleaned_df.to_csv(index=False)

    st.download_button(
        label="Download Cleaned Dataset",
        data=cleaned_csv,
        file_name="cleaned_data.csv",
        mime="text/csv"
    )

    # Final quality check → verify the cleaned dataset
    final_missing = cleaned_df.isnull().sum().sum()
    final_duplicates = cleaned_df.duplicated().sum()
    final_empty_columns = cleaned_df.isna().all().sum()

    st.subheader("Final Data Quality Check")

    st.write(f"Missing Values Remaining: {final_missing}")
    st.write(f"Duplicate Rows Remaining: {final_duplicates}")
    st.write(f"Empty Columns Remaining: {final_empty_columns}")

    # Cleaning status → confirm whether basic quality checks passed
    if (
        final_missing == 0
        and final_duplicates == 0
        and final_empty_columns == 0
    ):
        st.success("Cleaning completed successfully. Data passed the quality checks.")
    else:
        st.warning("Cleaning completed, but some data-quality issues remain.")

    # Business validation → flag suspicious values for review
    suspicious_values = {}

    for column in cleaned_df.select_dtypes(include="number").columns:
        negative_count = int((cleaned_df[column] < 0).sum())

        if negative_count > 0:
            suspicious_values[column] = negative_count

    st.subheader("Suspicious Numeric Values")
    st.write(suspicious_values)

    # Check categories → exclude ID columns from category analysis
    category_check = {}

    for column in cleaned_df.select_dtypes(include="object").columns:
        if "id" not in column.lower():
            category_check[column] = cleaned_df[column].dropna().unique().tolist()

    st.subheader("Category Consistency Check")
    st.write(category_check)

    # Check ID columns → show clean integer values
    id_check = {}

    for column in cleaned_df.columns:
        if "id" in column.lower():
            id_check[column] = {
                "Missing": int(cleaned_df[column].isna().sum()),
                "Duplicates": int(cleaned_df[column].duplicated().sum())
            }

    st.subheader("ID Integrity Check")
    st.write(id_check)

    # Validate numeric values → show clean integer values
    validation_issues = {}

    for column in cleaned_df.select_dtypes(include="number").columns:
        issues = 0

        if "quantity" in column.lower():
            issues += int((cleaned_df[column] < 0).sum())

        if "age" in column.lower():
            issues += int(((cleaned_df[column] < 0) | (cleaned_df[column] > 120)).sum())

        if "discount" in column.lower():
            issues += int(((cleaned_df[column] < 0) | (cleaned_df[column] > 1)).sum())

        if "delivery" in column.lower():
            issues += int((cleaned_df[column] < 0).sum())

        validation_issues[column] = int(issues)

    st.subheader("Business Rule Validation")
    st.write(validation_issues)

    # Final cleaning report → summarize all cleaning actions
    st.subheader("Final Cleaning Report")

    st.write(f"Original Rows: {rows_before}")
    st.write(f"Cleaned Rows: {rows_after}")
    st.write(f"Rows Removed: {rows_before - rows_after}")

    st.write(f"Original Missing Values: {missing_before}")
    st.write(f"Remaining Missing Values: {missing_after}")

    st.write(f"Original Duplicates: {duplicates_before}")
    st.write(f"Remaining Duplicates: {duplicates_after}")

    st.write(f"Empty Columns Removed: {len(empty_columns)}")

    st.subheader("Outlier Detection")
    st.write(outlier_counts)


def do_clean(action):
    """Apply one manual fix to the current table and keep working on the result."""

    source = st.session_state["source"]
    table = load_data(*source)

    try:
        if action == "blank_rows":
            table, message = cleaning.remove_blank_rows(table, st.session_state["cl_blank_col"])
        else:
            table, message = cleaning.fill_blanks(
                table, st.session_state["cl_fill_col"], st.session_state["cl_fill_how"]
            )
    except ValueError as problem:
        st.session_state["clean_msg"] = str(problem)
        return

    keep_original(source)
    before = cleaning.summary(load_data(*source))
    record_step(source, before, cleaning.summary(table), [message])
    set_source(cleaned_name(source[0]), cleaning.to_csv_bytes(table))
    st.session_state["clean_msg"] = message


def cleaned_name(name):
    stem = os.path.splitext(os.path.basename(name))[0]
    return name if name.startswith("cleaned_") else f"cleaned_{stem}.csv"


def keep_original(source):
    if "original_source" not in st.session_state:
        st.session_state["original_source"] = source


def record_step(source, before, after, log):
    """Remember what this cleaning step changed, and what ALL steps changed together."""

    steps = st.session_state.setdefault("clean_steps", [])

    if not steps:
        st.session_state["clean_original_summary"] = before

    steps.append({"log": log, "after": after})
    original = st.session_state["clean_original_summary"]

    st.session_state["clean_result"] = {
        "original": original, "now": after, "log": log, "earlier": steps[:-1],
        "text": cleaning.history_text(st.session_state["original_source"][0], original, steps),
    }


def forget_cleaning():
    for key in ("clean_result", "clean_steps", "clean_original_summary", "original_source"):
        st.session_state.pop(key, None)


@st.cache_data(show_spinner=False)
def diagnose_source(file_name, file_bytes, sheet=None):
    table, _ = load_table(file_name, file_bytes, sheet)
    return cleaning.diagnose(table)


def do_plan():
    """Apply the fixes the person ticked, and remember what changed."""

    source = st.session_state["source"]
    table = load_data(*source)
    prefix = st.session_state["clean_prefix"]
    ids = [i for i in st.session_state["clean_issue_ids"] if st.session_state.get(prefix + i)]

    before = cleaning.summary(table)
    cleaned, log = cleaning.apply_plan(table, ids)
    after = cleaning.summary(cleaned)

    keep_original(source)
    record_step(source, before, after, log)
    set_source(cleaned_name(source[0]), cleaning.to_csv_bytes(cleaned))


def restore_original():
    original = st.session_state.pop("original_source", None)

    if original:
        set_source(*original)
        forget_cleaning()
        st.session_state["clean_msg"] = "Back to your original file."


def page_clean(raw_df, name):

    found = cleaning.summary(raw_df)
    issues = diagnose_source(*st.session_state["source"], st.session_state.get("sheet"))
    serious = [i for i in issues if i["fixable"] and i["severity"] in ("high", "medium")]

    html(ui.hero_html(
        "Clean",
        "Datalyst looks for problems in your data, tells you what it found, and fixes what "
        "you choose. Your original file is never changed.",
        eyebrow="Prepare",
        chips=[
            {"text": f"{found['rows']:,} rows"},
            {"text": f"{len(serious)} problems found" if serious else "No serious problems",
             "tone": "orange" if serious else "green"},
            {"text": f"{found['blank_cells']:,} blank cells", "tone": "orange" if found["blank_cells"] else "green"},
            {"text": f"{found['duplicate_rows']:,} duplicate rows", "tone": "orange" if found["duplicate_rows"] else "green"},
        ],
    ))

    message = st.session_state.pop("clean_msg", None)

    if message:
        st.success(safe(message))

    result = st.session_state.get("clean_result")

    if result:

        with st.container(key="glass-clean-result"):

            html(ui.card_title("Done. Here is what changed", "Your original file compared with now"))

            html(ui.clean_stats_html(result["original"], result["now"]))

            st.markdown("**This step**" if result["earlier"] else "**What was changed**")
            html(ui.changes_html(result["log"]))

            if result["earlier"]:
                with st.expander(f"Earlier steps ({len(result['earlier'])})"):
                    for number, step in enumerate(result["earlier"], start=1):
                        st.markdown(f"**Step {number}**")
                        html(ui.changes_html(step["log"]))

            st.download_button(
                "Download the change log", result["text"], file_name="cleaning_log.txt",
                mime="text/plain", key="cl_download_log",
            )

    with st.container(key="glass-clean-plan"):

        html(ui.card_title(
            "What I found, and what I suggest",
            "Tick what you want fixed. Nothing changes until you press the button.",
        ))

        prefix = f"cl_{name}_{len(raw_df)}_"
        fixable = [i for i in issues if i["fixable"]]
        st.session_state["clean_prefix"] = prefix
        st.session_state["clean_issue_ids"] = [i["id"] for i in fixable]

        if not issues:
            st.success("No problems found. Your data looks clean.")

        for item in issues:

            with st.container(key=f"issue-{item['id']}"):

                if item["fixable"]:
                    st.checkbox(safe(item["title"]), value=item["default_on"], key=prefix + item["id"])
                else:
                    html(ui.issue_title_html(item["title"]))

                html(ui.issue_detail_html(item["severity"], item["detail"], item["fixable"]))

        if fixable:

            ticked = any(st.session_state.get(prefix + i["id"]) for i in fixable)

            st.button(
                "Clean it for me", key="cl_apply", type="primary", on_click=do_plan,
                disabled=not ticked, **STRETCH,
            )
            st.caption("The cleaned copy is what Ask AI, Insights and your dashboard use from now on.")

    blanks = list(found["blank_by_column"])

    with st.expander("Fix one column yourself"):

        if blanks:

            c, d = st.columns([2, 1], gap="small")

            c.selectbox(
                "Columns with blanks", blanks, key="cl_blank_col",
                format_func=lambda x: f"{x}  ({found['blank_by_column'][x]:,} blanks)",
            )
            d.button("Remove those rows", key="cl_rows", on_click=do_clean, args=("blank_rows",), **STRETCH)

            e, f, g = st.columns([2, 1, 1], gap="small")

            e.selectbox(
                "Fill blanks in", blanks, key="cl_fill_col",
                format_func=lambda x: f"{x}  ({found['blank_by_column'][x]:,} blanks)",
            )

            chosen = st.session_state.get("cl_fill_col", blanks[0])
            ways = ["median", "mean", "zero"] if chosen in found["number_columns"] else ["most common", "unknown"]

            f.selectbox("with", ways, key="cl_fill_how")
            g.button("Fill them", key="cl_fill", on_click=do_clean, args=("fill",), **STRETCH)

        else:
            st.caption("There are no blank cells to fix.")

    tidied = st.session_state.get("engine").conversions if st.session_state.get("engine") else {}

    if tidied:
        with st.expander("Already tidied automatically when the file was opened"):
            for column, note in list(tidied.items())[:12]:
                st.markdown(f"- **{safe(column)}**: {safe(note)}")

    with st.container(key="glass-clean-save"):

        html(ui.card_title("Save your work", "The cleaned copy, ready to use anywhere"))

        a, b = st.columns(2, gap="small")

        a.download_button(
            "Download the cleaned data (CSV)", cleaning.to_csv_bytes(raw_df),
            file_name=f"cleaned_{os.path.splitext(os.path.basename(name))[0].replace('cleaned_', '')}.csv",
            mime="text/csv", **STRETCH, key="cl_download",
        )

        if "original_source" in st.session_state:
            b.button("Go back to the original file", key="cl_restore", on_click=restore_original, **STRETCH)


# ============================================================
# The app
# ============================================================

current_page = st.session_state.get("navigation_page", "Dashboard")

html(ui.theme_css(current_page))
accessibility_labels()

# a file to open automatically (set DATALYST_DEMO_FILE to try the app quickly)
if "source" not in st.session_state and os.environ.get(DEMO_ENV):

    demo_path = os.environ[DEMO_ENV]

    if os.path.exists(demo_path):
        with open(demo_path, "rb") as handle:
            accept_upload(os.path.basename(demo_path), handle.read())

source = st.session_state.get("source")

filters_slot = None      # the Visualize page puts its filters here (sidebar)

with st.sidebar:

    html(ui.brand_html())

    if source:

        html('<div class="nav-label">Workspace</div>')

        page = st.radio(
            "Navigation",
            [page_name for page_name, _ in ui.NAV],
            key="navigation_page",
            label_visibility="collapsed",
        )

        # the Visualize page draws its filters here, under the menu
        filters_slot = st.container()

        raw_preview = load_data(*source)

        html(ui.dataset_card_html(source[0], len(raw_preview), len(raw_preview.columns)))

        sheets = file_info().get("sheets") or []

        if len(sheets) > 1:

            current = file_info()["sheet"]
            choice = st.selectbox("Excel sheet", sheets, index=sheets.index(current), key="sheet_pick")

            if choice != current:
                st.session_state["sheet"] = choice
                for key in ["last", "history", "dash", "engine_key", "warm_key", "builder_state", "builder_info_key"]:
                    st.session_state.pop(key, None)
                st.rerun()

        with st.expander("Change dataset"):

            replacement = st.file_uploader(
                "Upload another file", type=["csv", "tsv", "txt", "xlsx", "xls"],
                key="uploader_side", label_visibility="collapsed",
            )

            # act only on a NEW upload. The uploader keeps showing the file it
            # was given, so after "Clean it for me" (which swaps in the cleaned
            # table) it must not treat that old file as a fresh upload.
            if replacement is not None and is_new_upload(replacement, "side_seen"):
                if accept_upload(replacement.name, replacement.getvalue()):
                    st.rerun()

            problem = st.session_state.get("file_problem")

            if problem:
                st.error(safe(problem["message"]))

    else:
        page = None

    status = ai_state()
    html(ui.ai_status_html(status["state"], status["missing"]))


if not source:

    page_landing()

else:

    try:
        engine = get_engine()

    except Exception as error:

        st.error(safe(f"I could not read this file: {error}"))
        st.stop()

    if page == "Dashboard":
        page_dashboard(engine, source[0])

    elif page == "Ask AI":
        page_ask(engine, source[0])

    elif page == "Insights":
        page_insights(engine, source[0])

    elif page == "Visualize":
        page_visualize(engine, source[0])

    elif page == "Report":
        page_report(engine, source[0])

    elif page == "Data":
        page_data(engine, source[0])

    elif page == "Clean":
        page_clean(load_data(*source), source[0])
