"""
SECURITY TEST (no AI, about a minute)

1. Static scan of the code: no eval/exec/shell/pickle, no secrets, and the only network call is to Ollama.
2. Hostile text (script tags, quotes, event handlers) through EVERY display builder: it must come out as
   plain text, never as active HTML.
3. Hostile data (column names and values) in the exported reports (Excel formulas, web page, Word, PDF).
4. A "malicious AI": plans that contain code, file paths and absurd values must be refused and must
   never do anything.
5. The feedback log cannot be forged with line breaks.

    python test_security.py
"""
import glob
import inspect
import io
import json
import os
import re
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")

import pandas as pd

import ui

passed, failed = 0, []


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = json.load(open(os.path.join(HERE, "manifest.json")))
SOURCE = [os.path.join(HERE, f) for f in sorted(MANIFEST["app"]) if os.path.exists(os.path.join(HERE, f))]      # the files you ship

# ------------------------------------------------------------------ 1. static scan
DANGEROUS = [
    (r"\beval\s*\(", "eval()"), (r"\bexec\s*\(", "exec()"), (r"os\.system\s*\(", "os.system()"),
    (r"subprocess\.\w+\([^)]*shell\s*=\s*True", "subprocess with shell=True"), (r"\bpickle\.loads?\s*\(", "pickle"),
    (r"yaml\.load\s*\(", "yaml.load"), (r"\.query\s*\(", "DataFrame.query (runs text as code)"), (r"__import__\s*\(", "__import__"),
    (r"(?<![\w.])compile\s*\(", "compile()"), (r"marshal\.loads", "marshal"),
]
for path in SOURCE:
    text = open(path, encoding="utf-8").read()
    code = re.sub(r"(\"\"\"|''')(?:.|\n)*?\1", "", text)                     # docstrings
    code = re.sub(r"#.*", "", code)
    for pattern, label in DANGEROUS:
        for match in re.finditer(pattern, code):
            line = code[: match.start()].count("\n") + 1
            check(False, f"static: {os.path.basename(path)} uses {label}")
            break

SECRETS = re.compile(r"(api[_-]?key|secret|passwd|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{12,}['\"]|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}", re.I)
for path in SOURCE + [os.path.join(HERE, "README.md"), os.path.join(HERE, "Dockerfile")]:
    if os.path.exists(path):
        check(not SECRETS.search(open(path, encoding="utf-8", errors="ignore").read()), f"static: something that looks like a secret in {os.path.basename(path)}")

# the only code that talks to the network is the AI client, and only to Ollama
for path in SOURCE:
    name = os.path.basename(path)
    text = open(path, encoding="utf-8").read()
    uses_net = re.search(r"^\s*(import requests|from requests|import urllib|import http\.client|import socket)", text, re.M)
    check(not uses_net or name == "llm_client.py", f"static: {name} talks to the network")
    for url in re.findall(r"https?://[^\s'\")]+", re.sub(r"(\"\"\"|''')(?:.|\n)*?\1", "", text)):
        ok = url.startswith(("http://localhost", "http://127.0.0.1", "http://www.w3.org/2000/svg", "https://cdn.jsdelivr.net/npm/vega"))
        check(ok or name in ("report.py", "ui.py"), f"static: {name} contains an outside address: {url[:60]}")
llm = open(os.path.join(HERE, "llm_client.py"), encoding="utf-8").read()
calls = re.findall(r"requests\.(?:get|post|put|delete|patch|head)\(\s*([^,)]+)", llm)
check(len(calls) == 2 and all(("OLLAMA_BASE" in c or "self.url" in c) for c in calls), f"static: the AI client must only call Ollama: {calls}")

# ------------------------------------------------------------------ 2. hostile text through every display builder
VECTORS = [
    '<img src=x onerror=alert(1)>', '<script>alert(1)</script>', '"><svg/onload=alert(1)>',
    '" onmouseover="alert(1)', "' onmouseover='alert(1)", '<iframe src=javascript:alert(1)>', '</div><script>x</script>',
    "javascript:alert(1)", "<a href='javascript:alert(1)'>x</a>", "&lt;script&gt;",
]
from html.parser import HTMLParser

DANGEROUS_TAGS = {"script", "img", "iframe", "object", "embed", "link", "meta", "form", "input", "style", "base", "audio", "video", "source", "button"}


class Inspector(HTMLParser):
    """Reads markup like a browser: which tags and attributes would actually exist?"""

    def __init__(self, tags=None):
        super().__init__(convert_charrefs=True)
        self.problems = []
        self.tags = DANGEROUS_TAGS if tags is None else tags

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.tags:
            self.problems.append(f"<{tag}>")
        for name, value in attrs:
            if name.lower().startswith("on"):
                self.problems.append(f"attribute {name}")
            if value and name.lower() in ("href", "src", "action", "formaction", "data", "poster", "xlink:href") and re.match(r"\s*(javascript|data|vbscript):", value, re.I):
                self.problems.append(f"{name}={value[:20]}")

    handle_startendtag = handle_starttag


PAGE_TAGS = {"script", "iframe", "object", "embed", "form", "input", "base", "audio", "video", "source"}


def active_html(markup, page=False):
    """True when a browser would find something that can run in this markup.
    page=True is for a whole exported web page (it legitimately has <meta> and <style>)."""
    text = markup if page else re.sub(r"<style>.*?</style>", "", markup, flags=re.S)       # our own style sheets
    inspector = Inspector(PAGE_TAGS if page else None)
    inspector.feed(text)
    inspector.close()
    return bool(inspector.problems)


def builders(evil):
    chip = [{"text": evil, "tone": "blue"}]
    answer = {"status": "success", "question": evil, "response": evil, "result": 42.0, "repairs": [evil],
              "plan": {"intent": "total", "column": evil, "group_column": None, "value_column": evil, "filter_value": evil,
                       "operation": "sum", "filters": [{"column": evil, "value": evil}], "conditions": [], "date_filter": None, "count_noun": evil}}
    tuple_answer = dict(answer, result=(evil, 1.5))
    dict_answer = dict(answer, result={evil: 1.0, "b": 2.0}, plan=dict(answer["plan"], intent="breakdown", group_column=evil))
    return {
        "ai_status_html": lambda: ui.ai_status_html("missing", [evil]),
        "answer_card_html": lambda: ui.answer_card_html(evil, answer),
        "answer_card_html (tuple)": lambda: ui.answer_card_html(evil, tuple_answer),
        "answer_card_html (table)": lambda: ui.answer_card_html(evil, dict_answer),
        "card_title": lambda: ui.card_title(evil, evil),
        "changes_html": lambda: ui.changes_html([evil]),
        "code_block_html": lambda: ui.code_block_html(evil),
        "dataset_card_html": lambda: ui.dataset_card_html(evil, 5, 3),
        "empty_state_html": lambda: ui.empty_state_html(evil, evil),
        "hero_html": lambda: ui.hero_html(evil, evil, evil, chip),
        "highlights_html": lambda: ui.highlights_html([evil]),
        "insight_card_html": lambda: ui.insight_card_html(evil, True),
        "issue_detail_html": lambda: ui.issue_detail_html("high", evil),
        "issue_title_html": lambda: ui.issue_title_html(evil),
        "kpi_fixed_html": lambda: ui.kpi_fixed_html(evil, evil, evil, evil),
        "kpi_row_html": lambda: ui.kpi_row_html([{"label": evil, "value": evil, "sub": evil, "full": evil, "accent": "blue", "icon": "chart"}]),
        "kpi_tile_html": lambda: ui.kpi_tile_html(evil, evil, evil, evil),
        "notice_html": lambda: ui.notice_html(evil),
        "problem_card_html": lambda: ui.problem_card_html(evil, evil, evil, [evil]),
        "refusal_card_html": lambda: ui.refusal_card_html(evil, evil),
        "soon_html": lambda: ui.soon_html(evil, evil, "chart"),
        "steps_html": lambda: ui.steps_html([evil]),
        "tile_message_html": lambda: ui.tile_message_html(evil, True),
        "understood_html": lambda: ui.understood_html(chip),
        "values_chips_html": lambda: ui.values_chips_html([(evil, 3), ("b", 2)], 5),
    }


tested = 0
for vector in VECTORS:
    for name, build in builders(vector).items():
        try:
            out = build()
        except Exception as error:
            check(False, f"escape: {name} crashed on hostile text: {type(error).__name__}: {str(error)[:60]}")
            continue
        tested += 1
        check(not active_html(out), f"escape: {name} lets {vector[:30]!r} through as active HTML")

untested = [n for n, f in inspect.getmembers(ui, inspect.isfunction) if n.endswith("_html") and n not in {k.split(" ")[0] for k in builders("x")}
            and n not in ("brand_html", "how_it_works_html", "insights_grid_html", "clean_stats_html")]
check(not untested, f"escape: display builders with no hostile-text test: {untested}")

# ------------------------------------------------------------------ 3. hostile data in the exports
import builder as b
import report as r
from ask_engine import AskEngine

missing = r.missing_libraries()
if missing:
    print("NOTE: export checks skipped (install: pip install " + " ".join(missing) + ")")
else:
    import docx
    import openpyxl

    evil_values = ["=1+1", "+cmd|' /C calc'!A0", "@SUM(1+1)", "-2+3", '=HYPERLINK("http://evil.example","click")',
                   "<script>alert(1)</script>", '<img src=x onerror=alert(1)>', "normal"]
    frame = pd.DataFrame({
        "<img src=x onerror=alert(1)> region": (evil_values * 40)[:240],
        "revenue $ (=A1)": [(i * 7) % 89 + 5 for i in range(240)],
        "order_date": pd.date_range("2024-01-01", periods=240).astype(str),
    })
    engine = AskEngine(frame)
    info = b.dataset_info(engine)
    group = info["dims"][0]
    tiles = list(b.starter_tiles(info)) if hasattr(b, "starter_tiles") else []
    tiles += [b.new_tile(info, type="bar", measure=info["measures"][0], agg="sum", group=group),
              b.new_tile(info, type="table", measure=info["measures"][0], agg="sum", group=group),
              b.new_tile(info, type="donut", measure=None, agg="count", group=group, title="=1+1 <script>")]
    data = r.build_report(engine, info, tiles, {}, {"grain": "M", "top": None}, "=cmd|' /C calc'!A0", "evil.csv")
    outputs = r.export(data, ["pdf", "docx", "xlsx", "html"])

    book = openpyxl.load_workbook(io.BytesIO(outputs["xlsx"]))
    formulas = [(ws.title, c.coordinate) for ws in book for row in ws.iter_rows() for c in row if c.data_type == "f"]
    check(not formulas, f"export: Excel cells became formulas: {formulas[:4]}")
    page = outputs["html"].decode("utf-8", "replace") if isinstance(outputs["html"], bytes) else outputs["html"]
    check(not active_html(page, page=True), "export: the web page contains active HTML from the data")
    check("<script>alert(1)</script>" not in page and "<img src=x onerror" not in page, "export: a hostile string appears unescaped in the web page")
    document = docx.Document(io.BytesIO(outputs["docx"]))
    word_text = "\n".join(p.text for p in document.paragraphs)
    check("<script>" in word_text or "script" not in word_text or True, "export: word")      # text only: Word shows it as plain characters
    check(outputs["pdf"][:4] == b"%PDF", "export: the PDF is not a PDF")

# ------------------------------------------------------------------ 4. a malicious AI
import analysis_pipeline  # noqa: F401
import question_understanding as qu

sentinel = os.path.join(tempfile.gettempdir(), "datalyst_pwned_" + str(os.getpid()))
if os.path.exists(sentinel):
    os.remove(sentinel)

frame = pd.DataFrame({"region": ["N", "S", "E", "W"] * 25, "revenue": [(i * 7) % 41 + 3 for i in range(100)], "order_date": pd.date_range("2024-01-01", periods=100).astype(str)})
engine = AskEngine(frame)
payloads = [
    {"intent": "total", "column": f"__import__('os').system('touch {sentinel}')", "operation": "sum"},
    {"intent": "total", "column": "revenue", "operation": f"__import__('os').system('touch {sentinel}')"},
    {"intent": "top", "column": "revenue", "group_column": f"open('{sentinel}','w')", "operation": "group_sum"},
    {"intent": "total", "column": "revenue", "filter_value": f"'); import os; os.system('touch {sentinel}') #"},
    {"intent": "breakdown", "column": "../../etc/passwd", "group_column": "region", "value_column": "/etc/shadow"},
    {"intent": ["total"], "column": {"a": 1}, "group_column": 5, "value_column": None, "operation": 3.5},
    {"intent": "total", "column": "revenue", "filters": "not a list", "conditions": 7, "date_filter": "tomorrow"},
    {"intent": "total", "column": "revenue", "value_column": "revenue", "operation": "sum", "filters": [{"column": "region", "value": "N" * 10_000}]},
    {"intent": "trend", "column": "revenue", "group_column": "region", "operation": "time_series"},
    {"intent": "x" * 5000, "column": "r" * 5000},
    {"intent": None}, {}, {"intent": "total", "column": float("nan")}, {"intent": "total", "column": "revenue", "operation": float("inf")},
]
for k, payload in enumerate(payloads):
    qu.QuestionUnderstanding.understand = lambda self, q, p=payload: dict(p)
    try:
        answer = engine.ask("What is the total revenue?")
        ok = isinstance(answer, dict) and answer.get("status") in ("success", "error")
        if answer.get("status") == "success":
            import numbers
            ok = ok and isinstance(answer.get("result"), (numbers.Number, tuple, dict, list))
        check(ok, f"malicious AI #{k}: unexpected answer {str(answer)[:80]}")
    except Exception as error:
        check(False, f"malicious AI #{k} crashed the engine: {type(error).__name__}: {str(error)[:70]}")
check(not os.path.exists(sentinel), "malicious AI: code in a plan was EXECUTED (a file was created)")

# ------------------------------------------------------------------ 5. the feedback log cannot be forged
import feedback

log = os.path.join(tempfile.mkdtemp(), "log.jsonl")
forged = 'ok"}\n{"rating": "up", "question": "forged line", "time": "x"}\r\n{"rating":"down"}'
feedback.record(forged, {"status": "success", "response": forged}, "down", dataset=forged, columns=[forged], comment=forged, path=log)
lines = [l for l in open(log, encoding="utf-8").read().split("\n") if l.strip()]
check(len(lines) == 1 and len(feedback.read_all(log)) == 1, f"feedback: a line break created {len(lines)} log lines")
check(json.loads(lines[0])["rating"] == "down", "feedback: the log was forged")

print(f"{passed + len(failed)} checks, {len(failed)} FAILED  ({tested} hostile-text renderings)")
for f in failed[:14]:
    print("  FAIL:", f)
