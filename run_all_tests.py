"""
RUN ALL TESTS: one command, one report.

    python run_all_tests.py quick               tests that need NO AI (a few minutes)
    python run_all_tests.py full                quick + every REAL-AI test (needs Ollama, ~30-40 min)
    python run_all_tests.py full --bank 300     bigger real-AI question-bank run (per file)
    python run_all_tests.py quick --skip builder        leave a slow test out
    python run_all_tests.py full --only bank_REAL --fresh   ask the real AI again (ignore saved answers)
    python run_all_tests.py full --only human,analyst   run only tests whose name contains these words

It writes  test_report.txt  (send me this one file) and a folder  test_logs/
with the full output of every test. Nothing in your project is changed.
"""

import ast
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, "test_logs")

ECOM, SAMPLE = "ecommerce_sales_34500.csv", "sample_sales.csv"
HR, AMAZON = "Cleaned_HR_Data_Analysis.csv", "amazon.csv"
ALL_FILES = [ECOM, SAMPLE, HR, AMAZON]


# ------------------------------------------------------------
# Reading the result lines of each test.  Each returns (verdict, summary)
# verdict: PASS / FAIL / INFO
# ------------------------------------------------------------

def _int(text):
    return int(text.replace(",", ""))


def parse_real_plans(out):
    m = re.search(r"(\d+) / (\d+) real AI plans handled correctly", out)
    return (("PASS" if m.group(1) == m.group(2) else "FAIL"), f"{m.group(1)} of {m.group(2)} real AI plans correct") if m else None


def parse_robustness(out):
    m = re.search(r"Total confident-wrong answers across all damage types: (\d+)", out)
    return (("PASS" if m.group(1) == "0" else "FAIL"), f"{m.group(1)} confident-wrong answers (must be 0)") if m else None


def parse_wrong_intent(out):
    m = re.search(r"total confident-wrong: (\d+)", out)
    return (("PASS" if m.group(1) == "0" else "FAIL"), f"{m.group(1)} confident-wrong answers (must be 0)") if m else None


def parse_checks(out):
    m = re.search(r"(\d[\d,]*) checks?(?: passed)?, (\d+) FAILED", out)
    return (("PASS" if m.group(2) == "0" else "FAIL"), f"{m.group(1)} checks, {m.group(2)} failed") if m else None


def parse_understanding(out):
    m = re.search(r"(\d+) answers checked, (\d+) with a missing detail", out)
    return (("PASS" if m.group(2) == "0" else "FAIL"), f"{m.group(1)} answers checked, {m.group(2)} with a missing detail") if m else None


def parse_bank_offline(out):
    total = re.search(r"^\s*TOTAL\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", out, re.M)
    if not total:
        return None
    correct, refused, wrong, safe, unsafe = map(int, total.groups())
    answered = correct + refused + wrong
    pct = f"{correct / answered * 100:.0f}%" if answered else "-"
    ok = wrong == 0 and unsafe == 0
    return ("PASS" if ok else "FAIL"), f"{correct} correct ({pct}), {refused} refused, {wrong} WRONG, {unsafe} UNSAFE"


def parse_score(out):
    m = re.search(r"SCORE: (\d+) / (\d+)", out)
    return (("PASS" if m.group(1) == m.group(2) else "FAIL"), f"{m.group(1)} of {m.group(2)} correct") if m else None


def parse_analyst(out):
    m = re.search(r"READY.*?: (\d+) / (\d+) correct, (\d+) not yet, (\d+) WRONG", out)
    t = re.search(r"TODAY: (\d+) of (\d+)", out)
    if not m:
        return None
    ok = m.group(4) == "0" and m.group(1) == m.group(2)
    return ("PASS" if ok else "FAIL"), f"READY {m.group(1)}/{m.group(2)} correct, {m.group(4)} WRONG" + (f" | overall {t.group(1)} of {t.group(2)}" if t else "")


def parse_human(out):
    a = re.search(r"SHOULD ANSWER\s*: (\d+) / (\d+) correct, (\d+) refused, (\d+) WRONG", out)
    r = re.search(r"SHOULD REFUSE\s*: (\d+) / (\d+) safely refused, (\d+) DANGEROUS", out)
    if not (a and r):
        return None
    ok = a.group(1) == a.group(2) and a.group(4) == "0" and r.group(3) == "0"
    return ("PASS" if ok else "FAIL"), f"answer {a.group(1)}/{a.group(2)} ({a.group(4)} wrong), refuse {r.group(1)}/{r.group(2)} ({r.group(3)} dangerous)"


def parse_other(out):
    m = re.search(r"(HR|Amazon): (\d+) / (\d+) correct, (\d+) refused, (\d+) WRONG", out)
    if not m:
        return None
    ok = m.group(5) == "0" and m.group(2) == m.group(3)
    return ("PASS" if ok else "FAIL"), f"{m.group(2)} of {m.group(3)} correct, {m.group(4)} refused, {m.group(5)} WRONG"


def parse_bank_real(out):
    m = re.search(r"SUMMARY: (\{.*?\})", out)
    if not m:
        return None
    counts = ast.literal_eval(m.group(1))
    wrong, unsafe = counts.get("WRONG", 0), counts.get("UNSAFE", 0)
    shown = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    done = re.search(r"(\d+) questions chosen, (\d+) already done", out)
    if done and int(done.group(2)) > 0:
        shown += f"   [reused {done.group(2)} earlier answers: add --fresh to ask the AI again]"
    return ("PASS" if wrong == 0 and unsafe == 0 else "FAIL"), shown


def parse_report(out):
    if "SKIPPED: missing libraries" in out:
        line = [l for l in out.splitlines() if l.startswith("SKIPPED")][0]
        return "INFO", line[:160]
    return parse_checks(out)


def parse_insights(out):
    m = re.search(r"passed the number check: (\d+) / (\d+)", out)
    return ("INFO", f"{m.group(1)} of {m.group(2)} AI-written insights passed the number check") if m else None


def build_tests(bank):
    t = []   # (name, needs_ai, [script, args...], timeout seconds, parser)
    for f in (ECOM, AMAZON, SAMPLE):
        t.append((f"real_plans {f}", False, ["test_real_ai_plans.py", f], 600, parse_real_plans))
    t.append(("robustness", False, ["test_robustness.py", ECOM], 900, parse_robustness))
    for f in ALL_FILES:
        t.append((f"wrong_intent {f}", False, ["test_wrong_intent.py", f], 900, parse_wrong_intent))
    for f in ALL_FILES:
        t.append((f"dashboard_numbers {f}", False, ["test_dashboard_numbers.py", f], 600, parse_checks))
    for f in (ECOM, HR, AMAZON):
        t.append((f"understanding {f}", False, ["test_understanding.py", f], 600, parse_understanding))
    for f in ALL_FILES:
        t.append((f"bank_ideal {f}", False, ["question_bank.py", f, "ideal"], 900, parse_bank_offline))
    for f in ALL_FILES:
        t.append((f"bank_noplan {f}", False, ["question_bank.py", f, "noplan"], 900, parse_bank_offline))
    t.append(("file_reader", False, ["test_file_reader.py"], 600, parse_checks))
    t.append(("cleaning", False, ["test_cleaning.py"], 600, parse_checks))
    t.append(("clean page display", False, ["test_clean_ui.py"], 600, parse_checks))
    t.append(("upload flow (sidebar + clean)", False, ["test_upload_flow.py"], 900, parse_checks))
    t.append(("safe numbers", False, ["test_safe_numbers.py"], 600, parse_checks))
    t.append(("followup", False, ["test_followup.py"], 600, parse_checks))
    t.append(("clarify", False, ["test_clarify.py"], 600, parse_checks))
    t.append(("pin to dashboard", False, ["test_pin.py"], 600, parse_checks))
    t.append(("examples", False, ["test_examples.py"], 600, parse_checks))
    t.append(("feedback log", False, ["test_feedback.py"], 600, parse_checks))
    t.append(("code_health", False, ["test_code_health.py"], 600, parse_checks))
    t.append(("number_formats", False, ["test_number_formats.py"], 600, parse_checks))
    t.append(("dataset_fuzz normal", False, ["test_dataset_fuzz.py", "12", "1"], 1800, parse_checks))
    t.append(("dataset_fuzz HARD", False, ["test_dataset_fuzz.py", "12", "1", "--hard"], 1800, parse_checks))
    t.append(("analyst_catalog (no AI)", False, ["test_analyst_catalog.py", "noplan"], 1800, parse_checks))
    t.append(("analyst_catalog (AI says total)", False, ["test_analyst_catalog.py", "weak"], 1800, parse_checks))
    t.append(("report exports", False, ["test_report.py"], 1800, parse_report))
    t.append(("builder (slow)", False, ["test_builder.py"], 3600, parse_checks))
    # ---- the real AI (needs Ollama)
    t.append(("golden", True, ["test_golden.py"], 1800, parse_score))
    t.append(("golden_sales", True, ["test_golden_sales.py"], 1800, parse_score))
    t.append(("analyst", True, ["test_analyst_questions.py", ECOM], 3600, parse_analyst))
    t.append(("human", True, ["test_human_questions.py", ECOM], 3600, parse_human))
    t.append(("other HR", True, ["test_other_datasets.py", HR], 3600, parse_other))
    t.append(("other Amazon", True, ["test_other_datasets.py", AMAZON], 3600, parse_other))
    for f in ALL_FILES:
        t.append((f"bank_REAL {f}", True, ["question_bank.py", f, "real", str(bank)], 7200, parse_bank_real))
    t.append(("analyst_catalog REAL", True, ["test_analyst_catalog.py", "real", str(max(bank * 3, 300))], 14400, parse_bank_real))
    t.append(("insight writer", True, ["test_explainer.py"], 1800, parse_insights))
    return t


MARKERS = ("WRONG", "REFUSED", "UNSAFE", "FAIL", "DANGEROUS", "NOT YET", "PROBLEM")


def gaps(out, limit=10):
    lines = out.splitlines()
    found = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(("WRONG (", "REFUSED (", "UNSAFE (")) or "Total confident" in s or "must be 0" in s:
            continue
        if re.search(r"\d+ / \d+ (correct|safely|real AI)", s) or s.startswith("SUMMARY"):
            continue                      # a summary line, not a problem
        if not (any(m in s for m in MARKERS) and len(s) > 12 and not s.startswith(("=", "-"))):
            continue
        if s.startswith("["):
            # a block: the question, then what was expected, what came back, and the AI's plan
            block = [s[:170]] + [l.strip()[:170] for l in lines[i + 1:i + 4] if l.strip()]
            found.append(("\n        ").join(block))
        else:
            found.append(s[:170])
    return found[:limit]


def ollama_running():
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False


def main():
    args = sys.argv[1:]
    mode = "full" if "full" in args else "quick"

    def option(name):
        return args[args.index(name) + 1].split(",") if name in args else []

    bank = int(option("--bank")[0]) if "--bank" in args else 150
    only, skip = option("--only"), option("--skip")

    tests = build_tests(bank)
    if mode == "quick":
        tests = [x for x in tests if not x[1]]
    if only:
        tests = [x for x in tests if any(w.lower() in x[0].lower() for w in only)]
    if skip:
        tests = [x for x in tests if not any(w.lower() in x[0].lower() for w in skip)]

    missing = [x[2][0] for x in tests if not os.path.exists(os.path.join(HERE, x[2][0]))]
    if missing:
        print("These test files are missing, run  python project_check.py  first:", sorted(set(missing)))
        sys.exit(1)

    if "--fresh" in args and any(x[0].startswith(("bank_REAL", "analyst_catalog REAL")) for x in tests):
        for f in sorted(os.listdir(HERE)):
            if (f.startswith("bank_results_") and f.endswith(".csv")) or f == "catalog_results.csv":
                os.remove(os.path.join(HERE, f))
                print(f"--fresh: removed the old saved answers {f}")

    os.makedirs(LOGS, exist_ok=True)
    ai_ok = ollama_running() if any(x[1] for x in tests) else True
    if not ai_ok:
        print("\n!! Ollama is not running: the real-AI tests will be SKIPPED. Open the Ollama app and run again.\n")

    started = time.time()
    results = []
    env = dict(os.environ, PYTHONWARNINGS="ignore", PYTHONUNBUFFERED="1")

    print(f"Running {len(tests)} tests ({mode}). Each result appears when it finishes.\n")

    for number, (name, needs_ai, command, timeout, parser) in enumerate(tests, start=1):

        if needs_ai and not ai_ok:
            results.append((name, "SKIPPED", "Ollama is not running", []))
            print(f"[{number:2d}/{len(tests)}] SKIPPED  {name}")
            continue

        t0 = time.time()
        log = os.path.join(LOGS, re.sub(r"[^A-Za-z0-9_.-]+", "_", name) + ".log")
        try:
            done = subprocess.run([sys.executable] + command, cwd=HERE, capture_output=True, text=True, timeout=timeout, env=env)
            out = done.stdout + "\n" + done.stderr
        except subprocess.TimeoutExpired as error:
            out = (error.stdout or "") if isinstance(error.stdout, str) else ""
            out += "\nTIMEOUT"

        open(log, "w", encoding="utf-8").write(out)
        parsed = parser(out)

        if parsed is None:
            tail = " / ".join(l.strip() for l in out.strip().splitlines()[-3:])[:200]
            verdict, summary = "ERROR", f"could not read the result. Last lines: {tail}"
        else:
            verdict, summary = parsed

        results.append((name, verdict, summary, gaps(out)))
        print(f"[{number:2d}/{len(tests)}] {verdict:7s}  {name:38s} {summary}   ({time.time() - t0:.0f}s)", flush=True)

    # ------------------------------------------------ the report
    bad = [r for r in results if r[1] in ("FAIL", "ERROR")]
    lines = ["TEST REPORT  " + time.strftime("%Y-%m-%d %H:%M"), f"mode: {mode} | {len(results)} tests | {(time.time() - started) / 60:.1f} minutes", ""]
    skipped = [r for r in results if r[1] == "SKIPPED"]
    if bad:
        lines.append(f"RESULT: {len(bad)} TEST(S) NEED ATTENTION: " + ", ".join(r[0] for r in bad))
    elif skipped:
        lines.append(f"RESULT: INCOMPLETE. Nothing failed, but {len(skipped)} test(s) were SKIPPED because Ollama was not running.")
    else:
        lines.append("RESULT: ALL CLEAR (no wrong answers, nothing failed)")
    lines += ["", f"{'verdict':8s} test", "-" * 100]
    for name, verdict, summary, _ in results:
        lines.append(f"{verdict:8s} {name:38s} {summary}")
    lines += ["", "GAPS: refused / wrong / failing questions found (first lines of each test)", "-" * 100]
    any_gap = False
    for name, verdict, summary, g in results:
        if g:
            any_gap = True
            lines.append(f"[{name}]")
            lines += ["    " + x for x in g]
    if not any_gap:
        lines.append("none")
    lines += ["", "Send me this file (test_report.txt). The full output of every test is in the folder test_logs/."]
    report = "\n".join(lines)
    open(os.path.join(HERE, "test_report.txt"), "w", encoding="utf-8").write(report)

    print("\n" + "=" * 70)
    print(lines[3])
    for name, verdict, summary, g in results:
        if verdict in ("FAIL", "ERROR") and g:
            print(f"\n[{name}] what went wrong (first lines):")
            for item in g[:8]:
                print("    " + item)
    print("\nReport written to test_report.txt  (send me this file)")
    print("=" * 70)


if __name__ == "__main__":
    main()
