"""
FINAL GATE: the last, hardest check of the whole system. One command.

    python final_gate.py              standard: about 30 minutes, no AI needed
    python final_gate.py quick        about 10 minutes (a fast sanity pass)
    python final_gate.py full         several hours: adds the real AI, bigger fuzzing, long robot runs,
                                      a big mutation audit and a 500,000-row performance test
    python final_gate.py --only security,performance
    python final_gate.py --skip mutation

It runs these layers and writes final_gate_report.txt (send me that file):

   static      every file compiles, no undefined names, project files up to date, packages consistent
   suite       the whole existing test suite (the real-AI part only in "full")
   security    hostile text everywhere, exports, malicious AI plans, code scan
   file fuzz   thousands of corrupted files and memory bombs
   metamorphic shuffle / double / scale / rename the data: answers must change exactly as they must
   cleaning    random messy tables: cleaning must obey its rules
   performance time and memory budgets
   robot       a robot clicks the real app at random with hostile text, on many different files
   mutation    deliberate bugs injected into the code: do the tests notice?
"""
import os
import platform
import py_compile
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

MODE = "standard"
ONLY, SKIP = None, set()
for arg in sys.argv[1:]:
    if arg in ("quick", "standard", "full"):
        MODE = arg
    elif arg.startswith("--only"):
        ONLY = set(arg.split("=", 1)[1].split(",")) if "=" in arg else None
    elif arg.startswith("--skip"):
        SKIP = set(arg.split("=", 1)[1].split(",")) if "=" in arg else set()
for i, arg in enumerate(sys.argv):
    if arg == "--only" and i + 1 < len(sys.argv):
        ONLY = set(sys.argv[i + 1].split(","))
    if arg == "--skip" and i + 1 < len(sys.argv):
        SKIP = set(sys.argv[i + 1].split(","))

SIZE = {
    "quick":    dict(fuzz=40,  clean=60,  steps=25, runs=1, offsets=[0],       mutants=0,  perf=[],      suite=["quick", "--skip", "builder"], timeout=900),
    "standard": dict(fuzz=120, clean=200, steps=40, runs=2, offsets=[0, 1],    mutants=10, perf=[],      suite=["quick"],                      timeout=1800),
    "full":     dict(fuzz=400, clean=600, steps=80, runs=3, offsets=[0, 1, 2, 3], mutants=40, perf=["big"], suite=["full", "--fresh"],          timeout=14400),
}[MODE]

PASS_RE = re.compile(r"(\d[\d,]*)\s+checks?,\s+(\d[\d,]*)\s+FAILED")
results = []                     # (layer, passed, detail, seconds, tail)


def run(name, command, judge, timeout=None):
    if (ONLY and not any(o in name for o in ONLY)) or any(s in name for s in SKIP):
        return
    started = time.time()
    print(f"\n>>> {name}", flush=True)
    try:
        process = subprocess.run([PY, "-W", "ignore", *command], cwd=HERE, capture_output=True, text=True,
                                 timeout=timeout or SIZE["timeout"])
        text = process.stdout + process.stderr
        passed, detail = judge(process.returncode, text)
    except subprocess.TimeoutExpired:
        text, passed, detail = "", False, f"timed out after {timeout or SIZE['timeout']}s"
    seconds = time.time() - started
    tail = "\n".join(text.strip().splitlines()[-30:]) if not passed else ""
    results.append((name, passed, detail, seconds, tail))
    print(f"    {'PASS' if passed else 'FAIL'}  {detail}  ({seconds:.0f}s)", flush=True)


def checks_judge(returncode, text):
    """A test that prints 'N checks, M FAILED'."""
    found = [m for m in PASS_RE.finditer(text)]
    if not found:
        return False, "no result line (the test did not finish)" + (": " + text.strip().splitlines()[-1][:90] if text.strip() else "")
    total = sum(int(m.group(1).replace(",", "")) for m in found)
    failed = sum(int(m.group(2).replace(",", "")) for m in found)
    return failed == 0 and returncode == 0, f"{total:,} checks, {failed} failed"


def robot_judge(returncode, text):
    found = re.findall(r"(\d+) robot runs, (\d+) random actions, (\d+) FAILED", text)
    if not found:
        return False, "no result line"
    runs = sum(int(a) for a, _, _ in found)
    actions = sum(int(b) for _, b, _ in found)
    failed = sum(int(c) for _, _, c in found)
    return failed == 0, f"{runs} robot runs, {actions:,} random actions, {failed} failed"


def suite_judge(returncode, text):
    if "ALL CLEAR" in text:
        passed = len(re.findall(r"\] PASS", text))
        return True, f"all {passed} tests passed"
    bad = re.findall(r"\] (?:FAIL|ERROR)\s+(.+?)\s{2,}", text)
    return False, "needs attention: " + ", ".join(bad[:5])


def mutation_judge(returncode, text):
    found = re.search(r"OVERALL: (\d+) of (\d+) mistakes caught = (\d+)%", text)
    if not found:
        return False, "no result line"
    caught, total, score = (int(g) for g in found.groups())
    survivors = len(re.findall(r"survived:", text))
    ok = score >= 70
    return ok, f"{caught} of {total} deliberate bugs caught ({score}%), {survivors} survivors to review (needs 70%)"


# ------------------------------------------------------------------ the layers
def static_layer():
    if (ONLY and "static" not in ONLY and not any("static" in o for o in ONLY)) or "static" in SKIP:
        return
    started = time.time()
    print("\n>>> static: every file compiles", flush=True)
    import json
    manifest = json.load(open(os.path.join(HERE, "manifest.json")))
    files = sorted(set(manifest["app"]) | set(manifest["tests"]) | set(manifest["helpers"]))
    broken = []
    for name in files:
        try:
            py_compile.compile(os.path.join(HERE, name), doraise=True)
        except Exception as error:
            broken.append(f"{name}: {str(error)[:80]}")
    results.append(("static: every file compiles", not broken, f"{len(files)} files" if not broken else "; ".join(broken[:3]), time.time() - started, "\n".join(broken)))
    print(f"    {'PASS' if not broken else 'FAIL'}  {len(files)} files", flush=True)


static_layer()
run("static: no undefined names (code health)", ["test_code_health.py"], checks_judge, 300)
run("static: project files up to date", ["project_check.py"],
    lambda rc, t: ("Everything in your project is correct and up to date" in t, "all files are the right version" if "Everything in your project" in t else "some files are missing or out of date"), 120)
run("static: packages consistent (pip check)", ["-m", "pip", "check"],
    lambda rc, t: (rc == 0, t.strip().splitlines()[0][:100] if t.strip() else "ok"), 120)
run("suite: the whole test suite", ["run_all_tests.py", *SIZE["suite"]], suite_judge)
run("security", ["test_security.py"], checks_judge, 600)
run("file fuzz", ["test_file_fuzz.py", str(SIZE["fuzz"]), "11"], checks_judge)
run("upload flow (real browser if installed)", ["test_upload_flow.py"], checks_judge, 900)
run("metamorphic", ["test_metamorphic.py"], checks_judge, 900)
run("cleaning fuzz", ["test_cleaning_fuzz.py", str(SIZE["clean"]), "11"], checks_judge, 900)
for perf in (SIZE["perf"] or [""]):
    run("performance" + (" (500,000 rows)" if perf else ""), ["test_performance.py"] + ([perf] if perf else []), checks_judge, 1200)
for offset in SIZE["offsets"]:
    run(f"robot (random paths set {offset})", ["test_ui_monkey.py", str(SIZE["steps"]), str(SIZE["runs"]), str(offset)], robot_judge, 1800)
if SIZE["mutants"]:
    run("mutation audit", ["mutation_audit.py", "all", str(SIZE["mutants"]), "5"], mutation_judge, 7200)

# ------------------------------------------------------------------ the report
width = max((len(r[0]) for r in results), default=30)
lines = ["=" * 78, f" FINAL GATE ({MODE})   {time.strftime('%Y-%m-%d %H:%M')}", "=" * 78]
for name, passed, detail, seconds, _ in results:
    lines.append(f" {'PASS' if passed else 'FAIL'}  {name:{width}s}  {detail}  ({seconds:.0f}s)")

failed = [r for r in results if not r[1]]
lines += ["", "-" * 78]
if not results:
    lines.append(" nothing was run (check --only / --skip)")
elif failed:
    lines.append(f" {len(failed)} OF {len(results)} LAYERS NEED ATTENTION:")
    for name, _, detail, _, tail in failed:
        lines += ["", f"  * {name}: {detail}"] + [f"      {l[:150]}" for l in tail.splitlines()[-14:]]
else:
    lines.append(f" ALL {len(results)} LAYERS PASSED. No layer found a problem.")

try:
    import pandas
    import streamlit
    versions = f"python {platform.python_version()}, pandas {pandas.__version__}, streamlit {streamlit.__version__}, {platform.system()} {platform.machine()}"
except Exception:
    versions = f"python {platform.python_version()}"
lines += ["", f" environment: {versions}", f" total time: {sum(r[3] for r in results) / 60:.1f} minutes", "=" * 78]

report = "\n".join(lines)
print("\n" + report)
with open(os.path.join(HERE, "final_gate_report.txt"), "w", encoding="utf-8") as handle:
    handle.write(report + "\n")
print("\nreport written to final_gate_report.txt  (send me this file)")
sys.exit(1 if failed else 0)
