"""
THE QUESTION BANK: every kind of question a user can ask, with the correct
answer worked out independently in pandas.

    python question_bank.py file.csv                 (offline, 'ideal' AI plans)
    python question_bank.py file.csv noplan          (offline, the AI says NOTHING:
                                                      only the words are left)
    python question_bank.py file.csv weak            (offline, the AI always says "total")
    python question_bank.py file.csv real 300        (your real Ollama AI, 300 questions,
                                                      saved to bank_results_<file>.csv,
                                                      safe to stop and run again)

Each answer is CORRECT, REFUSED (safe) or WRONG (a confident wrong answer = a bug).
Questions that must be refused (median, correlation ...) count as SAFE when refused.
"""

import copy
import csv
import math
import os
import random
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import pandas as pd

import auto_benchmark as ab
from ask_engine import AskEngine
from dashboard import humanize, main_measure, uses_total
from filters import to_dates
from question_understanding import QuestionUnderstanding
from semantics import non_additive_reason

YES_NO = {"yes", "no", "true", "false", "0", "1", "y", "n"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def plural(word):
    if word.endswith("y") and not word.endswith(("ay", "ey", "oy")):
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    return word + "s"


def casual(question):
    """'What is the total amount?' -> 'what is the total amount'"""
    return question.strip().rstrip("?.").lower()


def nice(value):
    """A round number for a threshold: 1234.5 -> 1200"""
    value = float(value)
    if value == 0:
        return 0
    magnitude = 10 ** max(0, int(math.floor(math.log10(abs(value)))) - 1)
    rounded = round(value / magnitude) * magnitude
    return int(rounded) if rounded == int(rounded) else round(rounded, 2)


# ------------------------------------------------------------
# Build the bank
# ------------------------------------------------------------

def build_bank(df, engine):

    u = engine.dataset_understanding
    profile = engine.profile
    measures = u["measures"]
    dates = u["date_columns"]
    values_of = u["dimension_values"]
    noun = profile.get("count_noun") or "records"
    semantics = profile["column_semantics"]
    identifiers = u["identifier_columns"]
    main_map = profile.get("main_columns", {})

    items = []
    seen = set()

    def add(kind, question, truth, plan=None, expect="answer", check="value"):
        if question in seen:
            return
        seen.add(question)
        items.append({"id": len(items) + 1, "kind": kind, "question": question,
                      "truth": truth, "plan": plan, "expect": expect, "check": check})

    def both(kind, question, truth, plan=None, **kw):
        """the question as written + the casual way people type it"""
        add(kind, question, truth, plan, **kw)
        add(kind + "_casual", casual(question), truth, plan, **kw)

    if not measures:
        return items

    money = [m for m in measures if semantics.get(m) == "monetary"]
    primary = main_measure(engine) or measures[0]
    ordered = [primary] + [m for m in measures if m != primary]

    # dimensions: (column used for the data, words the user types, values)
    dims = []
    for column, values in values_of.items():
        if column not in df.columns or column in identifiers:
            continue
        shown = next((o for o, m in main_map.items() if m == column), column)
        if column in main_map.values() or column not in main_map:
            dims.append((column, humanize(shown), values))
    dims = dims[:7]

    owners = {}
    for column_, words_, values_ in dims:
        for value_ in values_:
            owners.setdefault(str(value_).strip().lower(), set()).add(column_)

    def named(words_, value):
        """'Full-Time' -> 'employee type Full-Time' when two columns share that value."""
        return f"{words_} {value}" if len(owners.get(str(value).strip().lower(), ())) > 1 else str(value)

    def total_label(m):
        h = humanize(m)
        return h if h.startswith("total") else f"total {h}"

    def is_non_additive(m):
        return bool(non_additive_reason(m, float(df[m].max())))

    # ---------------- numbers: every measure x total / average / max / min
    for m in ordered[:10]:
        h = humanize(m)
        if is_non_additive(m):
            total_truth = lambda d, m=m: d[m].mean()          # defined behaviour
        else:
            total_truth = lambda d, m=m: d[m].sum()
        both("total", f"What is the {total_label(m)}?", total_truth, ab.plan("total", "sum", m, None, m))
        both("average", f"What is the average {h}?", lambda d, m=m: d[m].mean(), ab.plan("average", "average", m, None, m))
        both("maximum", f"What is the highest {h}?", lambda d, m=m: d[m].max(), ab.plan("maximum", "max", m, None, m))
        both("minimum", f"What is the lowest {h}?", lambda d, m=m: d[m].min(), ab.plan("minimum", "min", m, None, m))

    # ---------------- whole table
    both("rows", f"How many {noun} are there?", lambda d: len(d), ab.plan("count", "row_count"))
    both("duplicates", "How many duplicate rows are there?", lambda d: int(d.duplicated().sum()), ab.plan("duplicate", "duplicate_count"))
    both("missing", "How many missing values are there?", lambda d: int(d.isnull().sum().sum()), ab.plan("missing", "missing_count"))

    # ---------------- groups
    for column, words_, values in dims:
        plural_words = plural(words_)
        yes_no = {str(v).strip().lower() for v in values} <= YES_NO

        # how many different + which ones (numbers AND words)
        both("unique_names", f"How many different {plural_words} are there?",
             lambda d, c=column: (d[c].nunique(), {str(v) for v in d[c].dropna().unique()}),
             ab.plan("unique", "unique", column, None, column), check="names")
        both("list_names", f"List the {plural_words}",
             lambda d, c=column: (d[c].nunique(), {str(v) for v in d[c].dropna().unique()}),
             ab.plan("unique", "unique", column, None, column), check="names")
        add("list_names", f"What are the different {plural_words}?",
            lambda d, c=column: (d[c].nunique(), {str(v) for v in d[c].dropna().unique()}),
            ab.plan("unique", "unique", column, None, column), check="names")

        if yes_no:
            continue

        for m in ordered[:2]:
            h = humanize(m)
            adds = "total" if not is_non_additive(m) else "average"
            if is_non_additive(m):
                continue
            add("top", f"Which {words_} has the highest {h}?", lambda d, c=column, m=m: ab._best(d, c, m, True), ab.plan("top", "group_sum", m, column, m))
            add("bottom", f"Which {words_} has the lowest {h}?", lambda d, c=column, m=m: ab._best(d, c, m, False), ab.plan("bottom", "group_sum", m, column, m))
            add("top_n", f"What are the top 3 {plural_words} by {h}?", lambda d, c=column, m=m: (c, m, 3, True), ab.plan("top", "group_sum", m, column, m), check="topk")
            add("bottom_n", f"What are the 3 lowest {plural_words} by {h}?", lambda d, c=column, m=m: (c, m, 3, False), ab.plan("bottom", "group_sum", m, column, m), check="topk")
            add("breakdown", f"Show {h} by {words_}", lambda d, c=column, m=m: {str(k): v for k, v in d.groupby(c)[m].sum().items()}, None)

        # counts per group
        add("count_per_group", f"How many {noun} are there in each {words_}?",
            lambda d, c=column: {str(k): v for k, v in d.groupby(c).size().items()}, None)
        add("popular", f"Which {words_} has the most {noun}?",
            lambda d, c=column: ab._best(d, c, c, True) if False else (
                {str(k).lower() for k, v in d.groupby(c).size().items() if v == d.groupby(c).size().max()}, float(d.groupby(c).size().max())),
            None)

        # one value at a time (the most common values)
        common = list(df[column].value_counts().index[:4])
        for v in common:
            for m in ordered[:2]:
                h = humanize(m)
                if is_non_additive(m):
                    add("filter_avg", f"What is the average {h} for {named(words_, v)}?",
                        lambda d, c=column, v=v, m=m: ab.rows_where(d, c, v)[m].mean(),
                        ab.plan("average", "average", m, column, m, str(v)))
                    continue
                add("filter_total", f"What is the {total_label(m)} for {named(words_, v)}?",
                    lambda d, c=column, v=v, m=m: ab.rows_where(d, c, v)[m].sum(),
                    ab.plan("total", "sum", m, column, m, str(v)))
                add("filter_avg", f"What is the average {h} for {named(words_, v)}?",
                    lambda d, c=column, v=v, m=m: ab.rows_where(d, c, v)[m].mean(),
                    ab.plan("average", "average", m, column, m, str(v)))
            add("filter_count", f"How many {noun} are there for {named(words_, v)}?",
                lambda d, c=column, v=v: len(ab.rows_where(d, c, v)),
                ab.plan("count", "row_count", None, column, None, str(v)))
            add("share", f"What percentage of {noun} are {named(words_, v)}?",
                lambda d, c=column, v=v: len(ab.rows_where(d, c, v)) / len(d) * 100, None)
        low = str(common[0]).lower()
        add("filter_lowercase", f"What is the {total_label(primary)} for {named(words_, low)}?",
            lambda d, c=column, v=common[0]: ab.rows_where(d, c, v)[primary].sum() if not is_non_additive(primary) else ab.rows_where(d, c, v)[primary].mean(),
            ab.plan("total", "sum", primary, column, primary, low))

    # yes / no columns: "how many orders were returned"
    for column, words_, values in dims:
        lowered = {str(v).strip().lower(): v for v in values}
        if set(lowered) <= YES_NO and column.lower().endswith("ed"):
            positive = next((lowered[k] for k in lowered if k in {"yes", "true", "y", "1"}), None)
            if positive is not None:
                both("boolean_count", f"How many {noun} were {words_}?",
                     lambda d, c=column, p=positive: len(ab.rows_where(d, c, p)),
                     ab.plan("count", "row_count", None, column, None, str(positive)))
                add("boolean_share", f"What percentage of {noun} were {words_}?",
                    lambda d, c=column, p=positive: len(ab.rows_where(d, c, p)) / len(d) * 100, None)
                break

    # two filters at once
    multi = [(c, w, list(df[c].value_counts().index[:2])) for c, w, v in dims
             if not ({str(x).strip().lower() for x in v} <= YES_NO)][:3]
    for i in range(len(multi) - 1):
        (c1, w1, v1), (c2, w2, v2) = multi[i], multi[i + 1]
        add("multi_filter", f"What is the {total_label(primary)} for {named(w1, v1[0])} in {named(w2, v2[0])}?",
            lambda d, a=c1, x=v1[0], b=c2, y=v2[0]: (lambda r: r[primary].sum() if not is_non_additive(primary) else r[primary].mean())(ab.rows_where(ab.rows_where(d, a, x), b, y)),
            ab.plan("total", "sum", primary, c1, primary, str(v1[0])))

    # ---------------- number conditions
    for m in ordered[:3]:
        h = humanize(m)
        s = df[m].dropna()
        hi, lo = nice(s.quantile(0.75)), nice(s.quantile(0.25))
        if hi == lo or hi <= 0:
            continue
        add("cond_above", f"How many {noun} have {h} above {hi}?", lambda d, m=m, x=hi: int((d[m] > x).sum()), None)
        add("cond_below", f"How many {noun} have {h} below {lo}?", lambda d, m=m, x=lo: int((d[m] < x).sum()), None)
        add("cond_between", f"How many {noun} have {h} between {lo} and {hi}?", lambda d, m=m, a=lo, b=hi: int(((d[m] >= a) & (d[m] <= b)).sum()), None)

    # ---------------- time
    if dates:
        date = ab.pick_date_column(humanize(primary), dates)
        stamps = to_dates(df[date])
        valid = stamps.dropna()
        years = sorted(valid.dt.year.unique())
        agg = (lambda r: r[primary].sum()) if not is_non_additive(primary) else (lambda r: r[primary].mean())

        both("trend", f"Show me monthly {humanize(primary)}", lambda d: ab._monthly(d, date, primary), ab.plan("trend", "time_series", primary, date, primary))
        for y in years[1:-1] or years[:1]:
            both("year_total", f"What is the {total_label(primary)} in {y}?",
                 lambda d, y=y: agg(d[to_dates(d[date]).dt.year == y]), ab.plan("total", "sum", primary, date, primary))
            count_q = f"How many {noun} were there in {y}?"
            count_date = ab.pick_date_column(count_q, dates)      # the same rule the app uses
            add("year_count", count_q, lambda d, y=y, cd=count_date: int((to_dates(d[cd]).dt.year == y).sum()), None)
        middle = valid.sort_values().iloc[len(valid) // 2]
        name = f"{MONTHS[middle.month - 1]} {middle.year}"
        both("month_total", f"What is the {total_label(primary)} in {name}?",
             lambda d, y=middle.year, mo=middle.month: agg(d[(to_dates(d[date]).dt.year == y) & (to_dates(d[date]).dt.month == mo)]),
             ab.plan("total", "sum", primary, date, primary))
        q = (middle.month - 1) // 3 + 1
        add("quarter_total", f"What is the {total_label(primary)} in Q{q} {middle.year}?",
            lambda d, y=middle.year, qq=q: agg(d[(to_dates(d[date]).dt.year == y) & (to_dates(d[date]).dt.quarter == qq)]), None)
        if dims:
            c, w, v = dims[0]
            if not ({str(x).strip().lower() for x in v} <= YES_NO):
                top_value = df[c].value_counts().index[0]
                add("date_and_filter", f"What is the {total_label(primary)} for {top_value} in {name}?",
                    lambda d, y=middle.year, mo=middle.month, cc=c, vv=top_value: agg(ab.rows_where(d[(to_dates(d[date]).dt.year == y) & (to_dates(d[date]).dt.month == mo)], cc, vv)), None)

    # ---------------- two questions in one sentence
    first = f"What is the {total_label(primary)}"
    both_q = f"{first} and how many {noun} are there?"
    add("multi_part", both_q,
        lambda d: [d[primary].sum() if not is_non_additive(primary) else d[primary].mean(), len(d)], None, check="multi")
    m2 = ordered[1] if len(ordered) > 1 else primary
    add("multi_part", f"What is the average {humanize(primary)} and what is the highest {humanize(m2)}?",
        lambda d: [d[primary].mean(), d[m2].max()], None, check="multi")

    # ---------------- must be refused: the future, the past without a date, missing data
    for phrase in [f"What was the {humanize(primary)} last month?",
                   f"Forecast the {humanize(primary)} for next month",
                   f"Why did {humanize(primary)} drop?",
                   "What is the average temperature?",
                   f"What if {humanize(primary)} grows by 10 percent?",
                   f"What is the total {humanize(primary)} in the last 30 days?",
                   f"Predict the {humanize(primary)} for next year",
                   "What is the weather like?"]:
        add("must_refuse", phrase, None, None, expect="refuse")

    return items


# ------------------------------------------------------------
# Compare answers
# ------------------------------------------------------------

def judge(item, answer, df):
    """CORRECT / REFUSED / WRONG / SAFE / UNSAFE and a short 'got' text."""

    if item["expect"] == "refuse":
        if answer["status"] != "success":
            return "SAFE", answer["message"][:60]
        return "UNSAFE", answer["response"][:80]

    if answer["status"] != "success":
        return "REFUSED", answer["message"][:80]

    expected = item["truth"](df)
    got = answer["result"]
    check = item["check"]

    if check == "names":
        count, names = expected
        values = answer.get("values") or []
        shown = {name for name, _ in values}
        ok_count = ab.close(got, count)
        ok_names = (len(values) >= min(count, 100) and shown >= {n for n in names if len(values) >= len(names)}) if count <= 100 else True
        in_text = all(n in answer["response"] for n in names) if count <= 30 else True
        return ("CORRECT" if ok_count and ok_names and in_text else "WRONG"), f"{got} | {answer['response'][:70]}"

    if check == "multi":
        return "SKIP", ""

    if check == "topk":
        column, measure, k, highest = expected
        truth_values = df.groupby(column)[measure].sum()
        want = sorted(truth_values.sort_values(ascending=not highest).iloc[:k].tolist())
        pairs = list(got) if isinstance(got, list) else []
        names_ok = all(str(n) in {str(x) for x in truth_values.index} for n, _ in pairs)
        values_ok = names_ok and all(ab.close(v, float(truth_values[[x for x in truth_values.index if str(x) == str(n)][0]])) for n, v in pairs)
        ok = len(pairs) == min(k, len(truth_values)) and values_ok and all(ab.close(a, b) for a, b in zip(sorted(v for _, v in pairs), want))
        return ("CORRECT" if ok else "WRONG"), f"{str(answer['response'])[:90]}"

    if check == "value" and isinstance(expected, (int, float)) and not isinstance(expected, bool):
        ok = ab.matches(got, float(expected))
    else:
        ok = ab.matches(got, expected)

    return ("CORRECT" if ok else "WRONG"), f"{str(answer['response'])[:90]}"


# ------------------------------------------------------------
# Run
# ------------------------------------------------------------

def run(path, mode="ideal", limit=None, quiet=False):
    return run_frame(pd.read_csv(path), mode, limit)


def run_frame(df, mode="ideal", limit=None):
    """The same as run(), for a table that is already in memory."""

    engine = AskEngine(df)
    df = engine.df
    items = build_bank(df, engine)

    if not items:
        return []

    primary = main_measure(engine) or engine.dataset_understanding["measures"][0]
    weak = ab.plan("total", "sum", primary, None, primary)
    empty = ab.plan(None, None)

    if limit and limit < len(items):
        random.Random(7).shuffle(items)
        items = sorted(items[:limit], key=lambda i: i["id"])

    oracle = {}
    for item in items:
        if mode == "ideal":
            plan = item["plan"] or weak
        elif mode == "weak":
            plan = weak
        else:
            plan = empty
        oracle[item["question"]] = plan
    # sub-questions of a two-part sentence use the same mode
    for item in items:
        if item["check"] == "multi":
            for part in re.split(r"\s+and\s+(?=how|what)", item["question"].rstrip("?"), flags=re.I):
                oracle[part.strip(" ?")] = weak if mode != "noplan" else empty

    if mode != "real":
        QuestionUnderstanding.understand = lambda self, q: copy.deepcopy(oracle.get(q, oracle.get(q.strip(" ?"), weak if mode == "weak" else empty)))
    else:
        engine.warm_up()

    results = []
    for item in items:
        started = time.time()
        if item["check"] == "multi":
            pairs = engine.ask_many(item["question"])
            expected = item["truth"](df)
            ok = len(pairs) == 2 and all(a["status"] == "success" and ab.matches(a["result"], float(e)) for (_, a), e in zip(pairs, expected))
            refused = len(pairs) == 2 and any(a["status"] != "success" for _, a in pairs)
            outcome = "CORRECT" if ok else ("REFUSED" if refused or len(pairs) != 2 else "WRONG")
            got = " | ".join((a.get("response") or a.get("message"))[:50] for _, a in pairs)
        else:
            answer = engine.ask(item["question"])
            outcome, got = judge(item, answer, df)
        results.append((item, outcome, got, time.time() - started))

    return results


def report(path, mode, results, show=8):
    kinds = {}
    for item, outcome, got, _ in results:
        base = item["kind"].replace("_casual", "")
        kinds.setdefault(base, {}).setdefault(outcome, 0)
        kinds[base][outcome] += 1

    totals = {}
    print(f"\n{os.path.basename(path)}  mode={mode}  {len(results)} questions")
    print(f"  {'kind':18s} {'correct':>8s} {'refused':>8s} {'WRONG':>6s} {'safe':>5s} {'UNSAFE':>6s}")
    for kind in sorted(kinds):
        c = kinds[kind]
        print(f"  {kind:18s} {c.get('CORRECT', 0):8d} {c.get('REFUSED', 0):8d} {c.get('WRONG', 0):6d} {c.get('SAFE', 0):5d} {c.get('UNSAFE', 0):6d}")
        for k, v in c.items():
            totals[k] = totals.get(k, 0) + v

    answerable = totals.get("CORRECT", 0) + totals.get("REFUSED", 0) + totals.get("WRONG", 0)
    print(f"  {'TOTAL':18s} {totals.get('CORRECT', 0):8d} {totals.get('REFUSED', 0):8d} {totals.get('WRONG', 0):6d} {totals.get('SAFE', 0):5d} {totals.get('UNSAFE', 0):6d}")
    if answerable:
        print(f"  answered correctly: {totals.get('CORRECT', 0) / answerable * 100:.1f}%   wrong (must be 0): {totals.get('WRONG', 0)}   unsafe (must be 0): {totals.get('UNSAFE', 0)}")

    for label in ("WRONG", "UNSAFE", "REFUSED"):
        bad = [(i, g) for i, o, g, _ in results if o == label]
        if bad:
            print(f"\n  {label} ({len(bad)}), first {min(show, len(bad))}:")
            for i, g in bad[:show]:
                print(f"     [{i['kind']}] {i['question'][:70]}  ->  {g[:100]}")
    return totals


def run_real(path, limit, out_path):
    """The real AI: resumable, written to a spreadsheet as it goes."""
    df = pd.read_csv(path)
    engine = AskEngine(df)
    df = engine.df
    items = build_bank(df, engine)

    # a fair sample of every kind
    by_kind = {}
    for item in items:
        by_kind.setdefault(item["kind"], []).append(item)
    chosen, rng = [], random.Random(11)
    while len(chosen) < min(limit, len(items)):
        for kind in sorted(by_kind):
            if by_kind[kind] and len(chosen) < limit:
                chosen.append(by_kind[kind].pop(rng.randrange(len(by_kind[kind]))))
        if not any(by_kind.values()):
            break

    done = set()
    if os.path.exists(out_path):
        with open(out_path, newline="", encoding="utf-8") as handle:
            done = {row["question"] for row in csv.DictReader(handle)}

    print(f"{len(chosen)} questions chosen, {len(done)} already done. Getting the AI ready...", flush=True)
    engine.warm_up()

    new_file = not os.path.exists(out_path)
    with open(out_path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["id", "kind", "question", "outcome", "seconds", "got"])
        for n, item in enumerate(chosen, start=1):
            if item["question"] in done:
                continue
            started = time.time()
            if item["check"] == "multi":
                pairs = engine.ask_many(item["question"])
                expected = item["truth"](df)
                ok = len(pairs) == 2 and all(a["status"] == "success" and ab.matches(a["result"], float(e)) for (_, a), e in zip(pairs, expected))
                outcome = "CORRECT" if ok else ("REFUSED" if any(a["status"] != "success" for _, a in pairs) or len(pairs) != 2 else "WRONG")
                got = " | ".join((a.get("response") or a.get("message"))[:60] for _, a in pairs)
            else:
                outcome, got = judge(item, engine.ask(item["question"]), df)
            seconds = time.time() - started
            writer.writerow([item["id"], item["kind"], item["question"], outcome, f"{seconds:.1f}", got])
            handle.flush()
            print(f"{n:4d}/{len(chosen)} {outcome:8s} {seconds:4.0f}s [{item['kind']}] {item['question'][:70]}", flush=True)

    # summary from the file
    with open(out_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    counts = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    print("\nSUMMARY:", counts, "| WRONG and UNSAFE must be 0")
    for row in rows:
        if row["outcome"] in ("WRONG", "UNSAFE"):
            print("   ", row["outcome"], "|", row["question"], "->", row["got"][:100])


if __name__ == "__main__":
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "ideal"

    if mode == "real":
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 300
        run_real(path, limit, f"bank_results_{os.path.splitext(os.path.basename(path))[0]}.csv")
    else:
        report(path, mode, run(path, mode))