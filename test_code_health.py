"""
CODE HEALTH (no AI, seconds): catches silent mistakes in the code itself.

  - every file parses and imports
  - no name defined twice at the top of a file (the second silently replaces the
    first: this once broke every "top 3" question)
  - no function defined twice in the same file
  - no name used that does not exist (needs pyflakes: pip install pyflakes)

    python test_code_health.py
"""
import ast
import collections
import importlib
import json
import os
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
manifest = json.load(open(os.path.join(HERE, "manifest.json")))
app_files = sorted(manifest["app"])
sys.path.insert(0, HERE)

problems, checks = [], 0


def check(ok, message):
    global checks
    checks += 1
    if not ok:
        problems.append(message)


for name in app_files:

    path = os.path.join(HERE, name)

    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError as error:
        check(False, f"{name}: syntax error {error}")
        continue

    check(True, "")

    assigned = collections.defaultdict(list)
    defined = collections.Counter()

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned[target.id].append((node.lineno, type(node.value).__name__))
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defined[node.name] += 1

    for variable, places in assigned.items():
        kinds = {kind for _, kind in places}
        check(len(places) == 1 or len(kinds) == 1 and variable.isupper() is False,
              f"{name}: '{variable}' is defined {len(places)} times (lines {[l for l, _ in places]}); "
              f"the last one silently replaces the others")

    for function, count in defined.items():
        check(count == 1, f"{name}: '{function}' is defined {count} times")

    if name != "app.py":
        try:
            importlib.import_module(name[:-3])
            check(True, "")
        except Exception as error:
            check(False, f"{name}: cannot be imported: {error!r}")

# names that do not exist (a typo that only shows when that line runs)
try:
    import pyflakes  # noqa: F401
    done = subprocess.run([sys.executable, "-m", "pyflakes"] + app_files, cwd=HERE, capture_output=True, text=True)
    for line in done.stdout.splitlines():
        if "undefined name" in line or "redefinition of unused" in line or "syntax" in line.lower():
            check(False, line.strip())
    check(True, "")
except ImportError:
    print("(pyflakes is not installed: the undefined-name check was skipped. pip install pyflakes)")

print(f"{checks} checks, {len(problems)} FAILED")
for p in problems[:15]:
    print("  FAIL:", p)
