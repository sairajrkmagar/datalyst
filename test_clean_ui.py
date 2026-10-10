"""
CLEAN PAGE DISPLAY TEST (seconds): the numbers shown are the numbers given,
the colours mean the right thing, and nothing typed into a file can break the page.

    python test_clean_ui.py
"""
import re
import ui

passed, failed = 0, []


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


before = {"rows": 12120, "columns": 23, "blank_cells": 34047, "duplicate_rows": 38}
after = {"rows": 12029, "columns": 22, "blank_cells": 22194, "duplicate_rows": 0}
html = ui.clean_stats_html(before, after)

check(html.count('class="glass kpi') == 4, "stats: expected four tiles")
for number in ("12,029", "22", "22,194", "0", "was 12,120", "was 23", "was 34,047", "was 38"):
    check(number in html, f"stats: missing {number}")
check("\u221291" in html and "\u221211,853" in html and "\u221238" in html, "stats: the changes are not shown with a minus sign")

tiles = re.split(r'<div class="glass kpi', html)[1:]
tone = lambda i: re.search(r'class="delta (\w+)"', tiles[i]).group(1)
check(tone(0) == "same" and tone(1) == "same", "stats: rows and columns changing is not good or bad")
check(tone(2) == "good" and tone(3) == "good", "stats: fewer blanks and duplicates must be green")

worse = ui.clean_stats_html(before, {**before, "blank_cells": before["blank_cells"] + 5})
check('delta worse' in worse and "+5" in worse, "stats: MORE blanks must be flagged")
none = ui.clean_stats_html(before, before)
check(none.count("no change") == 4 and "delta good" not in none, "stats: no change must say so")

# changes list
rows = ui.changes_html(["Removed 91 duplicate rows (12,120 to 12,029 rows).", "Removed 1 empty column(s): 'internal_notes'."])
check(rows.count('class="change"') == 2 and "Removed 91 duplicate rows" in rows, "changes: rows")
check("Nothing needed changing" in ui.changes_html([]), "changes: empty")

# a column name or message from a hostile file is text, never markup
evil = '<img src=x onerror=alert(1)> & "quotes"'
for out in (ui.changes_html([evil]), ui.issue_detail_html("high", evil), ui.issue_title_html(evil), ui.clean_stats_html(before, after)):
    check("<img" not in out and "onerror=alert" not in out.replace("&lt;img src=x onerror=alert", ""), "escape: markup was not escaped")
check("&lt;img" in ui.changes_html([evil]) and "&amp;" in ui.changes_html([evil]), "escape: the text was lost")

# severity tags
for severity, label in (("high", "High"), ("medium", "Medium"), ("info", "Info")):
    out = ui.issue_detail_html(severity, "detail")
    check(f'sev {severity}' in out and label in out, f"tag: {severity}")
check("sev advice" in ui.issue_detail_html("info", "detail", fixable=False), "tag: advice-only issues must say Advice")
check(re.search(r"\n\s*\n", ui.changes_html(["a", "b"])) is None, "markup: blank lines would break Streamlit's markdown")

print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed[:8]:
    print("  FAIL:", f)
