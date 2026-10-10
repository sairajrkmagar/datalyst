"""
PROJECT CHECK: tells you which files in this folder are right, old, missing
or no longer needed. It never deletes anything.

    python project_check.py                 (only look and report)
    python project_check.py --move          (fix wrong names, and move files that are
                                              no longer needed into a folder old_files)
    python project_check.py --move-unknown   (also move .py files it does not know)

Keep this file and manifest.json in your project folder.
"""

import ast
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = json.load(open(os.path.join(HERE, "manifest.json")))
OLD = os.path.join(HERE, "old_files")


def fingerprint(path):
    """Same text = same fingerprint (line endings and a last empty line do not matter)."""
    text = open(path, encoding="utf-8", errors="replace").read()
    text = text.replace("\r\n", "\n").rstrip("\n")
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def find(name):
    """The file in this folder with this name (ignoring capital letters), or None."""
    for existing in os.listdir(HERE):
        if existing.lower() == name.lower():
            return existing
    return None


def check_group(title, files, required):
    print(f"\n{title}")
    problems = 0
    for name, wanted in sorted(files.items()):
        actual = find(name)
        if actual is None:
            print(f"   MISSING      {name}" + ("   <- the app cannot run without it" if required else ""))
            problems += 1
        elif fingerprint(os.path.join(HERE, actual)) != wanted:
            print(f"   OUT OF DATE  {name}   <- replace it with the newest copy")
            problems += 1
        elif actual != name:
            print(f"   RENAME       {actual}  ->  {name}   (only the capital letters differ)")
            problems += 1
        else:
            print(f"   ok           {name}")
    return problems


def local_imports_missing():
    """Does any app file import a file that is not here?"""
    present = {f[:-3] for f in os.listdir(HERE) if f.endswith(".py")}
    missing = []
    for name in MANIFEST["app"]:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError as error:
            missing.append(f"{name} has a syntax error: {error}")
            continue
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module.split(".")[0]]
            for module in modules:
                known = {n[:-3] for n in MANIFEST["app"]} | {n[:-3] for n in MANIFEST["tests"]} | {"auto_benchmark"}
                if module in known and module not in present:
                    missing.append(f"{name} imports '{module}', which is not in this folder")
    return sorted(set(missing))


def fix_names():
    """Capital letters (Test_human_questions.py) and mangled downloads
    (question_bank_py.) get their right name. Nothing is overwritten."""

    wanted = {n.lower(): n for group in ("app", "tests", "helpers") for n in MANIFEST[group]}

    for existing in sorted(os.listdir(HERE)):

        low = existing.lower()
        target = None

        if low in wanted and existing != wanted[low]:
            target = wanted[low]
        elif low.endswith("_py.") and (low[:-4] + ".py") in wanted:
            target = wanted[low[:-4] + ".py"]

        if not target:
            continue

        if os.path.exists(os.path.join(HERE, target)) and target.lower() != low:
            # a correct copy already exists: the badly named one is a leftover
            os.makedirs(OLD, exist_ok=True)
            leftover = os.path.join(OLD, existing)
            while os.path.exists(leftover):
                leftover += ".copy"
            shutil.move(os.path.join(HERE, existing), leftover)
            print(f"   moved leftover: {existing}  (the correct {target} is already here)")
            continue

        temp = os.path.join(HERE, existing + ".renaming")
        os.rename(os.path.join(HERE, existing), temp)
        os.rename(temp, os.path.join(HERE, target))
        print(f"   renamed: {existing}  ->  {target}")


def main():
    move = "--move" in sys.argv or "--move-unknown" in sys.argv
    move_unknown = "--move-unknown" in sys.argv

    print("=" * 66)
    print(" PROJECT CHECK:", HERE)
    print("=" * 66)

    problems = check_group("1. THE APP (all of these must be here and up to date)", MANIFEST["app"], True)
    problems += check_group("2. TESTS YOU CAN RUN (optional, but useful)", MANIFEST["tests"], False)
    problems += check_group("3. HELPER USED BY THE TESTS", MANIFEST["helpers"], False)

    print("\n4. DATA FILES")
    for name in MANIFEST["data"]:
        print(f"   {'ok     ' if find(name) else 'not here'}      {name}")

    broken = local_imports_missing()
    print("\n5. DOES EVERY APP FILE FIND THE FILES IT IMPORTS?")
    if broken:
        for line in broken:
            print("   PROBLEM     ", line)
    else:
        print("   ok")

    for existing in sorted(os.listdir(HERE)):
        if existing.lower().endswith("_py.") and find(existing.lower()[:-4] + ".py") is None:
            print(f"\n   NAME PROBLEM  '{existing}' should be called '{existing[:-4]}.py'   (run with --move to fix)")

    keep = {n.lower() for group in ("app", "tests", "helpers") for n in MANIFEST[group]}
    keep |= {n.lower() for n in MANIFEST["data"]} | {"project_check.py"}

    old = [f for f in sorted(os.listdir(HERE))
           if f.lower() in {n.lower() for n in MANIFEST["obsolete"]}]
    unknown = [f for f in sorted(os.listdir(HERE))
               if f.endswith(".py") and f.lower() not in keep and f not in old]

    print("\n6. FILES YOU DO NOT NEED ANY MORE (safe to move to old_files)")
    print("\n".join(f"   {f}" for f in old) or "   none")

    print("\n7. .py FILES THIS CHECK DOES NOT RECOGNISE (look at them yourself)")
    print("\n".join(f"   {f}" for f in unknown) or "   none")

    if move:
        fix_names()
        os.makedirs(OLD, exist_ok=True)
        moved = old + (unknown if move_unknown else [])
        for f in moved:
            target = os.path.join(OLD, f)
            while os.path.exists(target):
                target += ".copy"
            shutil.move(os.path.join(HERE, f), target)
        print(f"\nMOVED {len(moved)} file(s) into old_files/ (nothing was deleted).")

    print("\n" + "=" * 66)
    if problems or broken:
        print(f" {problems} file(s) need attention. Replace the OUT OF DATE / MISSING ones with the newest copies.")
    else:
        print(" Everything in your project is correct and up to date.")
    if old and not move:
        print(f" {len(old)} old file(s) found. Run:  python project_check.py --move   to tidy them away.")
    print("=" * 66)


if __name__ == "__main__":
    main()
