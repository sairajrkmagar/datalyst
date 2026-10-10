"""
MUTATION AUDIT: how strong are the tests, really?

It makes small deliberate mistakes in the code (a "mutant"): turns < into <=, + into -, and into or,
removes a "not", changes a number, or deletes a statement. Then it runs the tests. If the tests
FAIL, the mistake was caught (good). If they all PASS, a real bug of that kind could slip through
(a gap in the safety net). Some survivors are harmless ("equivalent": the change does not alter
behaviour); the report lists each one so a person can judge.

    python mutation_audit.py                      (every file, 10 mutants each)
    python mutation_audit.py cleaning.py 40       (one file, 40 mutants)
    python mutation_audit.py all 25 3             (every file, 25 mutants, random seed 3)
"""
import ast
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# the file to mutate -> the fast test commands that must notice a mistake in it
TARGETS = {
    "cleaning.py": [["test_cleaning.py"], ["test_clean_ui.py"]],
    "file_reader.py": [["test_file_reader.py"]],
    "followup.py": [["test_followup.py"]],
    "clarify.py": [["test_clarify.py"]],
    "advanced.py": [["test_analyst_catalog.py", "noplan"], ["test_metamorphic.py"]],
    "feedback.py": [["test_feedback.py"]],
    "safe_numbers.py": [["test_safe_numbers.py"]],
    "examples.py": [["test_examples.py"]],
}
TIMEOUT = 240


# ------------------------------------------------------------------ finding places to change
SWAPS = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
}
ARITH = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}


class Sites(ast.NodeVisitor):
    """Collect every node that has a sensible mutation."""

    def __init__(self):
        self.found = []                      # (node, kind, description)
        self.skip = set()

    def mark_docstrings(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                    self.skip.add(id(body[0]))

    def visit_Compare(self, node):
        for i, op in enumerate(node.ops):
            if type(op) in SWAPS:
                self.found.append((node, ("compare", i), f"{type(op).__name__} -> {SWAPS[type(op)].__name__}"))
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if type(node.op) in ARITH and not isinstance(node.left, ast.Constant) or (type(node.op) in ARITH and not isinstance(node.right, ast.Constant)):
            self.found.append((node, ("arith", 0), f"{type(node.op).__name__} -> {ARITH[type(node.op)].__name__}"))
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        self.found.append((node, ("bool", 0), "and <-> or"))
        self.generic_visit(node)

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.Not):
            self.found.append((node, ("not", 0), "remove 'not'"))
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, bool):
            self.found.append((node, ("const", 0), f"{node.value} -> {not node.value}"))
        elif isinstance(node.value, (int, float)) and not isinstance(node.value, bool) and node.value not in (0, 1, -1):
            self.found.append((node, ("const", 0), f"{node.value} -> {node.value + 1}"))

    def visit_Expr(self, node):
        if id(node) not in self.skip and isinstance(node.value, ast.Call):
            self.found.append((node, ("delete", 0), "delete this statement"))
        self.generic_visit(node)


def apply_mutation(tree, node, kind):
    what, index = kind
    if what == "compare":
        node.ops[index] = SWAPS[type(node.ops[index])]()
    elif what == "arith":
        node.op = ARITH[type(node.op)]()
    elif what == "bool":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif what == "not":
        pass                                   # handled by replacing the node in its parent (see below)
    elif what == "const":
        node.value = (not node.value) if isinstance(node.value, bool) else node.value + 1
    elif what == "delete":
        node.value = ast.Constant(value=None)


def mutants_for(path, count, seed):
    source = open(path, encoding="utf-8").read()
    tree = ast.parse(source)
    sites = Sites()
    sites.mark_docstrings(tree)
    sites.visit(tree)
    candidates = [s for s in sites.found if not (s[1][0] == "not")] + [s for s in sites.found if s[1][0] == "not"]
    random.Random(seed).shuffle(candidates)
    return source, candidates[:count]


def mutate_source(source, wanted_index, count_seed_candidates):
    tree = ast.parse(source)
    sites = Sites()
    sites.mark_docstrings(tree)
    sites.visit(tree)
    node, kind, description = sites.found[wanted_index]
    if kind[0] == "not":
        class Unnot(ast.NodeTransformer):
            def visit_UnaryOp(self, n):
                if n is node:
                    return n.operand
                return self.generic_visit(n)
        tree = Unnot().visit(tree)
    else:
        apply_mutation(tree, node, kind)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), description, getattr(node, "lineno", 0)


# ------------------------------------------------------------------ running the tests on a mutant
def run_tests(workdir, commands):
    """True when ANY test noticed the mistake (a failure, a crash, or a timeout)."""
    for command in commands:
        try:
            result = subprocess.run([sys.executable, "-W", "ignore", *command], cwd=workdir, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return True, "timeout"
        text = result.stdout + result.stderr
        if result.returncode != 0 or "Traceback" in text:
            return True, "crash"
        for line in text.splitlines():
            if " FAILED" in line and not line.strip().startswith(("0 ", "FAIL:")) and "checks," in line:
                failures = line.split("checks,")[1].split("FAILED")[0].strip()
                if failures.isdigit() and int(failures) > 0:
                    return True, line.strip()[:60]
            if "wrong answers" in line or "WRONG" in line and "0 WRONG" not in line:
                return True, line.strip()[:60]
    return False, ""


def audit(file_name, count, seed):
    commands = TARGETS[file_name]
    path = os.path.join(HERE, file_name)
    source, picked = mutants_for(path, count, seed)
    tree = ast.parse(source)
    all_sites = Sites(); all_sites.mark_docstrings(tree); all_sites.visit(tree)
    index_of = {id(s[0]): i for i, s in enumerate(all_sites.found)}

    killed, survivors = 0, []
    for number, (node, kind, description) in enumerate(picked, start=1):
        # the tree is parsed again for each mutant, so the index is looked up by position in a fresh walk
        fresh = Sites(); fresh.mark_docstrings(ast.parse(source)); fresh.visit(ast.parse(source))
        position = next(i for i, s in enumerate(fresh.found) if s[1] == kind and getattr(s[0], "lineno", 0) == getattr(node, "lineno", 0) and s[2] == description)
        mutated, description, line = mutate_source(source, position, None)
        with open(os.path.join(WORK, file_name), "w", encoding="utf-8") as handle:
            handle.write(mutated)
        caught, how = run_tests(WORK, commands)
        killed += caught
        mark = "caught " if caught else "SURVIVED"
        print(f"  [{number:2d}/{len(picked)}] {mark} line {line:4d}: {description:28s} {how}", flush=True)
        if not caught:
            lines = source.splitlines()
            survivors.append((line, description, lines[line - 1].strip()[:90] if 0 < line <= len(lines) else ""))
    shutil.copy(path, os.path.join(WORK, file_name))
    return killed, len(picked), survivors


def main():
    global WORK
    args = sys.argv[1:]
    target = args[0] if args else "all"
    count = int(args[1]) if len(args) > 1 else 10
    seed = int(args[2]) if len(args) > 2 else 1

    WORK = tempfile.mkdtemp(prefix="mutants_")
    for name in os.listdir(HERE):
        full = os.path.join(HERE, name)
        if os.path.isfile(full) and name.endswith((".py", ".csv", ".json", ".toml")):
            shutil.copy(full, os.path.join(WORK, name))
    os.makedirs(os.path.join(WORK, ".streamlit"), exist_ok=True)
    if os.path.exists(os.path.join(HERE, ".streamlit", "config.toml")):
        shutil.copy(os.path.join(HERE, ".streamlit", "config.toml"), os.path.join(WORK, ".streamlit", "config.toml"))

    names = list(TARGETS) if target == "all" else [target]
    started = time.time()
    total_killed = total = 0
    report = []

    for name in names:
        print(f"{name}  ({count} mutants)", flush=True)
        killed, tried, survivors = audit(name, count, seed)
        total_killed += killed
        total += tried
        report.append((name, killed, tried, survivors))

    print("\n=========== MUTATION AUDIT ===========")
    for name, killed, tried, survivors in report:
        print(f"{name:20s} caught {killed:3d} of {tried:3d}  ({(100 * killed / max(tried, 1)):.0f}%)")
        for line, description, code in survivors:
            print(f"      survived: line {line}: {description}   |  {code}")
    score = 100 * total_killed / max(total, 1)
    print(f"\nOVERALL: {total_killed} of {total} mistakes caught = {score:.0f}%  ({time.time() - started:.0f}s)")
    shutil.rmtree(WORK, ignore_errors=True)
    return 0


WORK = ""

if __name__ == "__main__":
    sys.exit(main())
