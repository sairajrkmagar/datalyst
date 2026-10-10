"""
FILE FUZZ TEST: corrupt files on purpose, thousands of ways.

Every uploaded file must either load into a usable table or be refused with a plain-words message
(FileProblem). It must NEVER crash with a Python error, hang, or eat all the memory. Files that do
load must also survive the rest of the app (cleaning check, engine, dashboard, insights).

Also builds "bombs": tiny files that try to exhaust memory (a spreadsheet that claims to be a million
columns wide, a zip that unpacks to gigabytes, a header with millions of columns).

    python test_file_fuzz.py              (about 2 minutes)
    python test_file_fuzz.py 400 7        (variants per base file, random seed)
"""
import io
import os
import random
import signal
import subprocess
import sys
import textwrap
import time
import warnings
import zipfile

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import file_reader as fr

VARIANTS = int(sys.argv[1]) if len(sys.argv) > 1 else 90
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1

failed, passed = [], 0


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


class Slow(Exception):
    pass


def alarm_handler(signum, frame):
    raise Slow()


def limited(seconds, function, *args):
    """Run with a time limit (Unix). Returns ('ok', value) | ('problem', FileProblem) | ('crash', error) | ('slow', None)."""
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(seconds)
    try:
        return "ok", function(*args)
    except fr.FileProblem as problem:
        return "problem", problem
    except Slow:
        return "slow", None
    except BaseException as error:                    # MemoryError and everything else counts as a crash
        return "crash", error
    finally:
        signal.alarm(0)


# ---------------------------------------------------------------- valid files to corrupt
rng0 = np.random.default_rng(3)
base = pd.DataFrame({
    "region": rng0.choice(["North", "South", "East"], 120), "sales": rng0.integers(10, 900, 120),
    "price": rng0.random(120).round(2), "order_date": pd.date_range("2024-01-01", periods=120).astype(str),
    "note": rng0.choice(["ok", "late, urgent", 'said "no"', "caf\u00e9"], 120),
})
xl = io.BytesIO()
with pd.ExcelWriter(xl) as w:
    base.to_excel(w, sheet_name="Summary", index=False)
    base.assign(sales=base.sales * 10).to_excel(w, sheet_name="Data", index=False)

BASES = {
    "comma csv": ("a.csv", base.to_csv(index=False).encode()),
    "semicolon csv": ("a.csv", base.to_csv(index=False, sep=";").encode()),
    "tab file": ("a.tsv", base.to_csv(index=False, sep="\t").encode()),
    "windows csv": ("a.csv", base.to_csv(index=False).encode("cp1252", errors="replace")),
    "utf-16 csv": ("a.csv", base.to_csv(index=False).encode("utf-16")),
    "utf-8 BOM csv": ("a.csv", base.to_csv(index=False).encode("utf-8-sig")),
    "pipe file": ("a.txt", base.to_csv(index=False, sep="|").encode()),
    "excel two sheets": ("a.xlsx", xl.getvalue()),
}


# ---------------------------------------------------------------- the ways to damage a file
def m_truncate(b, r):
    return b[: int(r.integers(0, max(1, len(b))))]


def m_flip(b, r):
    b = bytearray(b)
    for _ in range(int(r.integers(1, 25))):
        if b:
            b[int(r.integers(len(b)))] = int(r.integers(256))
    return bytes(b)


def m_insert(b, r):
    i = int(r.integers(0, len(b) + 1))
    return b[:i] + bytes(r.integers(0, 256, int(r.integers(1, 200)), dtype=np.uint8)) + b[i:]


def m_delete(b, r):
    i = int(r.integers(0, max(1, len(b)))); j = min(len(b), i + int(r.integers(1, 400)))
    return b[:i] + b[j:]


def m_duplicate(b, r):
    i = int(r.integers(0, max(1, len(b)))); j = min(len(b), i + int(r.integers(1, 800)))
    return b[:j] + b[i:j] + b[j:]


def m_nulls(b, r):
    return b.replace(b"\n", b"\x00\n", int(r.integers(1, 20)))


def m_quotes(b, r):
    i = int(r.integers(0, max(1, len(b))))
    return b[:i] + b'"' + b[i:]


def m_swap_delimiter(b, r):
    return b.replace(b",", b";", int(r.integers(1, 40))).replace(b"\t", b",", int(r.integers(1, 5)))


def m_line_endings(b, r):
    return b.replace(b"\n", b"\r", int(r.integers(1, 60)))


def m_shuffle_lines(b, r):
    lines = b.split(b"\n")
    r.shuffle(lines)
    return b"\n".join(lines)


def m_prefix_junk(b, r):
    return bytes(r.integers(32, 126, int(r.integers(1, 3000)), dtype=np.uint8)) + b"\n" + b


def m_long_line(b, r):
    return b + b"\n" + b"x" * int(r.integers(10_000, 600_000))


def m_empty_lines(b, r):
    return b.replace(b"\n", b"\n\n\n", int(r.integers(1, 30)))


def m_unicode(b, r):
    return b.replace(b"North", "N\u00f6rth\u202e\u0000\U0001F600".encode("utf-8"), 3)


MUTATIONS = [m_truncate, m_flip, m_insert, m_delete, m_duplicate, m_nulls, m_quotes, m_swap_delimiter,
             m_line_endings, m_shuffle_lines, m_prefix_junk, m_long_line, m_empty_lines, m_unicode]

# ---------------------------------------------------------------- 1. byte-level damage
loaded = []
counts = {"ok": 0, "problem": 0, "crash": 0, "slow": 0}
started = time.time()

for label, (name, data) in BASES.items():
    for variant in range(VARIANTS):
        rng = np.random.default_rng(SEED * 100_003 + variant * 31 + len(label))
        chain = [MUTATIONS[int(rng.integers(len(MUTATIONS)))] for _ in range(int(rng.integers(1, 4)))]
        damaged = data
        for mutation in chain:
            damaged = mutation(damaged, rng)
        what = f"{label} variant {variant} ({'+'.join(m.__name__[2:] for m in chain)})"

        kind, value = limited(10, fr.read_table, name, damaged)
        counts[kind] += 1

        if kind == "crash":
            check(False, f"{what}: Python error instead of a plain message: {type(value).__name__}: {str(value)[:80]}")
        elif kind == "slow":
            check(False, f"{what}: took more than 10 seconds")
        elif kind == "problem":
            check(bool(value.message) and len(value.message) < 400, f"{what}: the message is empty or too long")
        else:
            table, info = value
            check(table.shape[0] >= 1 and table.shape[1] >= 1 and table.shape[1] <= fr.MAX_COLUMNS, f"{what}: loaded an unusable table {table.shape}")
            check(isinstance(fr.describe(info), str), f"{what}: describe() failed")
            loaded.append((what, table))

print(f"byte-level damage: {sum(counts.values())} files -> loaded {counts['ok']}, refused politely {counts['problem']}, "
      f"crashed {counts['crash']}, too slow {counts['slow']} ({time.time() - started:.0f}s)")

# ---------------------------------------------------------------- 2. what loads must survive the rest of the app
import question_understanding as qu  # noqa: E402

qu.QuestionUnderstanding.understand = lambda self, q: dict(intent="count", column=None, group_column=None, value_column=None, filter_value=None, operation="row_count")

import cleaning as cl  # noqa: E402
import dashboard as dash  # noqa: E402
import insights as ins  # noqa: E402
from ask_engine import AskEngine  # noqa: E402

picked = random.Random(SEED).sample(loaded, min(len(loaded), 130)) if loaded else []
for what, table in picked:
    def whole_app():
        engine = AskEngine(table)
        cl.diagnose(table)
        dash.build_dashboard(engine)
        ins.build_insights(engine)
        engine.ask("What is the total?")
        return True

    kind, value = limited(30, whole_app)
    where = ""
    if kind == "crash":
        import traceback
        frame = traceback.extract_tb(value.__traceback__)[-1]
        where = f" at {os.path.basename(frame.filename)}:{frame.lineno} ({frame.name})"
    check(kind == "ok" or (kind == "problem"), f"after loading, {what} broke the app: {kind} {type(value).__name__ if value else ''} {str(value)[:80]}{where}")

print(f"loaded files pushed through engine, cleaning, dashboard and insights: {len(picked)}")

# ---------------------------------------------------------------- 3. bombs
BOMB_CODE = '''
import io, os, resource, sys, time, zipfile, warnings
warnings.filterwarnings("ignore")


def limit_memory():
    """At most 3 GB, where the system allows it (Linux). macOS refuses: then we only MEASURE the peak."""
    if os.environ.get("DATALYST_NO_RLIMIT"):
        return "no limit (simulated)"
    for name in ("RLIMIT_AS", "RLIMIT_DATA"):
        try:
            resource.setrlimit(getattr(resource, name), (3 * 1024**3, 3 * 1024**3))
            return name
        except (ValueError, OSError, AttributeError):
            continue
    return "none"


LIMIT = limit_memory()


def peak_mb():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


sys.path.insert(0, %(here)r)
import file_reader as fr
kind = sys.argv[1]

def build(kind):
    import openpyxl
    if kind == "wide header":
        return "bomb.csv", ("a," * 250_000 + "z\\n" + "1," * 250_000 + "2\\n").encode()
    if kind == "millions of commas":
        return "bomb.csv", ("," * 4_000_000 + "\\n1\\n").encode()
    if kind == "one huge cell":
        return "bomb.csv", ("a,b\\n" + "x" * 12_000_000 + ",1\\n").encode()
    if kind == "excel claims a huge sheet":
        book = openpyxl.Workbook(); sheet = book.active; sheet["A1"] = "h"; sheet["A2"] = 1; sheet["XFD1048576"] = 5
        out = io.BytesIO(); book.save(out); return "bomb.xlsx", out.getvalue()
    if kind == "zip bomb":
        book = openpyxl.Workbook(); sheet = book.active; sheet["A1"] = "h"; sheet["A2"] = 1
        out = io.BytesIO(); book.save(out)
        src = zipfile.ZipFile(io.BytesIO(out.getvalue())); new = io.BytesIO()
        with zipfile.ZipFile(new, "w", zipfile.ZIP_DEFLATED) as z:
            for item in src.infolist():
                z.writestr(item, src.read(item))
            z.writestr("xl/worksheets/padding.xml", b"A" * 900_000_000)
        return "bomb.xlsx", new.getvalue()
    if kind == "many sheets":
        book = openpyxl.Workbook()
        for i in range(400):
            s = book.create_sheet(f"s{i}"); s["A1"] = "h"; s["A2"] = i
        out = io.BytesIO(); book.save(out); return "bomb.xlsx", out.getvalue()
    raise SystemExit("unknown")

name, data = build(kind)
started = time.time()
try:
    table, info = fr.read_table(name, data)
    print("LOADED", table.shape, round(time.time() - started, 1))
except fr.FileProblem as problem:
    print("REFUSED", problem.message[:80], round(time.time() - started, 1))
except BaseException as error:
    print("CRASH", type(error).__name__, str(error)[:80])
print("PEAK", round(peak_mb()), LIMIT)
''' % {"here": os.path.dirname(os.path.abspath(__file__))}

for kind in ("wide header", "millions of commas", "one huge cell", "excel claims a huge sheet", "zip bomb", "many sheets"):
    started = time.time()
    try:
        result = subprocess.run([sys.executable, "-W", "ignore", "-c", BOMB_CODE, kind], capture_output=True, text=True, timeout=60)
        lines = result.stdout.strip().splitlines()
        out = next((l for l in lines if l.startswith(("LOADED", "REFUSED", "CRASH"))), "(no result: " + (result.stderr.strip()[-80:] or "empty") + ")")
        peak = next((l for l in lines if l.startswith("PEAK")), "PEAK 0 ?").split()
    except subprocess.TimeoutExpired:
        out, peak = "HANG (more than 60 seconds)", ["PEAK", "0", "?"]
    peak_mb, how = int(peak[1]), " ".join(peak[2:])
    ok = (out.startswith("REFUSED") or (out.startswith("LOADED") and float(out.split()[-1]) < 30)) and peak_mb < 3000
    check(ok, f"bomb '{kind}': {out[:100]} (peak memory {peak_mb} MB, limit: {how})")
    print(f"bomb {kind:28s} -> {out[:70]}  peak {peak_mb} MB ({time.time() - started:.0f}s)")

print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed[:12]:
    print("  FAIL:", f)