"""
DECLINE AUDIT: is the app's "no" cautious enough, or too cautious?

    python decline_audit.py

Reads the real-AI result files that your tests already saved in this folder
(catalog_results.csv and bank_results_*.csv). No AI and no internet needed, it
takes a second. It writes decline_audit_report.txt and decline_audit.csv.

How to read it (this is how the tests were built):
  - Some questions have a KNOWN correct answer (a total, a ranking, a growth ...).
      CORRECT  the app gave the right number
      REFUSED  the app said no, although the answer exists   <- TOO CAUTIOUS
      WRONG    the app gave a wrong number                    <- must be 0
  - Some questions must be refused (the future, missing data, "delete rows" ...).
      SAFE     the app said no                                <- rightly cautious
      UNSAFE   the app answered anyway                        <- NOT cautious enough, must be 0

So two honest numbers come out:
  too-cautious rate   = REFUSED / (CORRECT + REFUSED + WRONG)
  not-cautious rate   = UNSAFE / (SAFE + UNSAFE)
"""
import csv
import glob
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = 3


def load():
    """Every saved real-AI result, in one shape: source, dataset, area, question, outcome, got."""

    rows, files = [], []
    paths = sorted(glob.glob(os.path.join(HERE, "bank_results_*.csv")))
    catalog = os.path.join(HERE, "catalog_results.csv")

    if os.path.exists(catalog):
        paths.append(catalog)

    for path in paths:
        name = os.path.basename(path)
        count = 0

        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if not row.get("outcome") or not row.get("question"):
                    continue

                if name == "catalog_results.csv":
                    dataset, area = row.get("dataset", "?"), row.get("area", "?")
                else:
                    dataset = name[len("bank_results_"):-len(".csv")]
                    area = row.get("kind", "?")

                rows.append({
                    "source": "catalog" if name == "catalog_results.csv" else "bank",
                    "dataset": dataset, "area": area, "question": row["question"],
                    "outcome": row["outcome"], "got": row.get("got", ""),
                })
                count += 1

        files.append((name, count))

    return rows, files


def reason_of(text):
    """The app's own words for saying no, with names and numbers blurred so that similar refusals group together."""

    text = (text or "").lower()
    text = re.sub(r"'[^']*'|\"[^\"]*\"|“[^”]*”", "'..'", text)
    text = re.sub(r"\d[\d,\.]*", "#", text)
    return " ".join(text.split()[:9]) or "(no reason given)"


def percent(part, whole):
    return f"{part / whole * 100:.1f}%" if whole else "n/a"


def main():
    rows, files = load()

    if not rows:
        print("No result files found in this folder.")
        print("They are made by the real-AI tests, for example:  python run_all_tests.py full")
        print("(catalog_results.csv and bank_results_<file>.csv). Put this script in the same folder and run it again.")
        return 1

    out = []
    say = out.append

    say("=" * 78)
    say(" DECLINE AUDIT: is the app's 'no' too cautious, or not cautious enough?")
    say("=" * 78)
    say(" read: " + ", ".join(f"{n} ({c} questions)" for n, c in files))

    totals = Counter(r["outcome"] for r in rows)
    answerable = totals["CORRECT"] + totals["REFUSED"] + totals["WRONG"]
    must_refuse = totals["SAFE"] + totals["UNSAFE"]

    say("")
    say(" 1. QUESTIONS THAT HAVE A KNOWN ANSWER")
    say(f"    asked            {answerable}")
    say(f"    correct          {totals['CORRECT']}   ({percent(totals['CORRECT'], answerable)})")
    say(f"    declined         {totals['REFUSED']}   ({percent(totals['REFUSED'], answerable)})   <- TOO CAUTIOUS: the answer existed")
    say(f"    wrong            {totals['WRONG']}   (must be 0)")

    say("")
    say(" 2. QUESTIONS THAT MUST BE REFUSED (future, missing data, 'delete rows' ...)")
    if must_refuse:
        say(f"    asked            {must_refuse}")
        say(f"    rightly refused  {totals['SAFE']}   ({percent(totals['SAFE'], must_refuse)})")
        say(f"    answered anyway  {totals['UNSAFE']}   (must be 0)   <- NOT CAUTIOUS ENOUGH")
    else:
        say("    none in the saved files (the question bank and catalogue keep them in the quick tests)")

    other = {k: v for k, v in totals.items() if k not in ("CORRECT", "REFUSED", "WRONG", "SAFE", "UNSAFE")}
    if other:
        say(f"    other outcomes   {other}")

    # ---- by dataset
    say("")
    say(" 3. TOO-CAUTIOUS RATE BY DATASET")
    by_dataset = defaultdict(Counter)
    for r in rows:
        by_dataset[r["dataset"]][r["outcome"]] += 1
    for name, c in sorted(by_dataset.items()):
        a = c["CORRECT"] + c["REFUSED"] + c["WRONG"]
        say(f"    {name:34s} {c['REFUSED']:4d} declined of {a:4d} answerable  ({percent(c['REFUSED'], a)})")

    # ---- by kind of question
    say("")
    say(" 4. WHICH KINDS OF QUESTION GET DECLINED MOST (this is the to-do list)")
    by_area = defaultdict(Counter)
    for r in rows:
        by_area[r["area"]][r["outcome"]] += 1
    table = []
    for name, c in by_area.items():
        a = c["CORRECT"] + c["REFUSED"] + c["WRONG"]
        if c["REFUSED"]:
            table.append((c["REFUSED"] / a if a else 0, c["REFUSED"], a, name))
    for rate, refused, a, name in sorted(table, reverse=True)[:15]:
        say(f"    {name:40s} {refused:4d} of {a:4d} declined  ({percent(refused, a)})")
    if not table:
        say("    nothing was declined")

    # ---- the reasons
    say("")
    say(" 5. THE REASONS THE APP GAVE (similar ones grouped), with examples")
    refused_rows = [r for r in rows if r["outcome"] == "REFUSED"]
    groups = defaultdict(list)
    for r in refused_rows:
        groups[reason_of(r["got"])].append(r)
    for reason, items in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:12]:
        say(f"    {len(items):3d} x  {reason}")
        for r in items[:EXAMPLES]:
            say(f"           e.g. [{r['dataset']}] {r['question'][:90]}")

    # ---- the unsafe ones
    unsafe = [r for r in rows if r["outcome"] == "UNSAFE"]
    wrong = [r for r in rows if r["outcome"] == "WRONG"]
    if unsafe or wrong:
        say("")
        say(" 6. MUST BE FIXED FIRST")
        for r in wrong + unsafe:
            say(f"    {r['outcome']:7s} [{r['dataset']}] {r['question'][:70]} -> {r['got'][:60]}")

    say("")
    say("-" * 78)
    say(" What this does NOT tell you: how often a real person's question is declined.")
    say(" These are my own test questions. Real users will ask differently.")
    say(" Because every 'declined' above has a known answer, each one is a question the app COULD")
    say(" have answered. They are the roadmap: fix the biggest group, run the tests again, compare.")
    say("=" * 78)

    text = "\n".join(out)
    print(text)

    with open(os.path.join(HERE, "decline_audit_report.txt"), "w", encoding="utf-8") as handle:
        handle.write(text + "\n")

    with open(os.path.join(HERE, "decline_audit.csv"), "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source", "dataset", "area", "question", "outcome", "why_the_app_said_no", "your_note"])
        for r in rows:
            if r["outcome"] in ("REFUSED", "UNSAFE", "WRONG"):
                writer.writerow([r["source"], r["dataset"], r["area"], r["question"], r["outcome"], r["got"], ""])

    print("\nSaved: decline_audit_report.txt and decline_audit.csv (send me the report)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
