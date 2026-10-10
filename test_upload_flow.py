"""
UPLOAD FLOW TEST: the bug where "Clean it for me" did nothing visible when the
file had been uploaded through the sidebar "Change dataset" box.

    python test_upload_flow.py

Part 1 (always runs, seconds): an uploaded file is treated as new ONCE only.
Part 2 (runs when `playwright` + Chromium exist): drives a real browser:
   sidebar upload -> Clean it for me -> the "Done" tiles must stay, the cleaned
   file must be the one in use; then a NEW upload must still replace it.
   Install once with:  pip install playwright   (browser tests are skipped without it)
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

passed, failed = 0, []


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


source = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

# ---------------------------------------------------------------- part 1
check("def is_new_upload(" in source, "app.py has no is_new_upload()")
check(len(re.findall(r"is_new_upload\(", source)) >= 3,
      "both uploaders (landing + sidebar) must use is_new_upload()")
check("replacement.name != source[0]" not in source,
      "the sidebar uploader compares the file name with the CURRENT (cleaned) file again: that is the old bug")

match = re.search(r"(def is_new_upload\(.*?)(?=\ndef )", source, re.S)
check(match is not None, "could not find is_new_upload() to test")

if match:
    from streamlit.testing.v1 import AppTest

    script = (
        "import streamlit as st\n" + match.group(1) + "\n"
        "class Up:\n"
        "    def __init__(self, i, name, size): self.file_id, self.name, self.size = i, name, size\n"
        "st.session_state.setdefault('log', [])\n"
        "pick = st.session_state.get('pick', 'a')\n"
        "files = {'a': Up('1', 'messy.csv', 100), 'b': Up('2', 'other.csv', 50), 'a2': Up('3', 'messy.csv', 100)}\n"
        "st.session_state['log'].append(is_new_upload(files[pick], 'seen'))\n"
    )
    at = AppTest.from_string(script, default_timeout=30).run()
    at.run(); at.run()
    check(at.session_state["log"] == [True, False, False], f"same file must count as new once, got {at.session_state['log']}")
    at.session_state["pick"] = "b"; at.run()
    check(at.session_state["log"][-1] is True, "a different file must count as new")
    at.run()
    check(at.session_state["log"][-1] is False, "the different file must not count twice")
    at.session_state["pick"] = "a2"; at.run()
    check(at.session_state["log"][-1] is True, "the same name+size uploaded AGAIN (new upload id) must count as new")

# ---------------------------------------------------------------- part 2
browser_note = None
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None
    browser_note = "SKIPPED browser part: pip install playwright"


def find_chromium():
    for base in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), "/opt/pw-browsers"):
        if base and os.path.isdir(base):
            for entry in sorted(os.listdir(base)):
                for sub in ("chrome-linux/chrome", "chrome-linux64/chrome"):
                    path = os.path.join(base, entry, sub)
                    if entry.startswith("chromium-") and os.path.exists(path):
                        return path
    return None


def browser_part():
    import make_demo_files

    folder = tempfile.mkdtemp()
    make_demo_files.make_all(folder)
    clean_file = os.path.join(folder, "1_retail_clean.csv")
    messy_file = os.path.join(folder, "3_retail_very_messy.csv")
    europe_file = os.path.join(folder, "2_retail_messy_europe.csv")

    port = 8650 + os.getpid() % 100
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", os.path.join(HERE, "app.py"), "--server.headless", "true",
         "--server.port", str(port), "--browser.gatherUsageStats", "false"],
        cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(7)

    try:
        with sync_playwright() as pw:
            exe = find_chromium()
            browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
            side = "section[data-testid=stSidebar] input[type=file]"
            sidebar = lambda page: page.locator("section[data-testid=stSidebar]")

            def fresh():
                page = browser.new_page(viewport={"width": 1400, "height": 1000})
                page.goto(f"http://localhost:{port}")
                page.wait_for_timeout(3000)
                return page

            def to_clean(page):
                sidebar(page).get_by_text("Clean", exact=True).first.click()
                page.wait_for_timeout(3500)

            def press_clean(page):
                page.get_by_role("button", name="Clean it for me").first.click()
                page.wait_for_timeout(6000)

            # A: the exact path from the bug report (file replaced through the sidebar)
            page = fresh()
            page.set_input_files("input[type=file]", clean_file)
            page.wait_for_timeout(5000)
            page.get_by_text("Change dataset").click()
            page.wait_for_timeout(800)
            page.set_input_files(side, messy_file)
            page.wait_for_timeout(5000)
            to_clean(page)
            press_clean(page)
            text = page.inner_text("body")
            check("Here is what changed" in text, "A: the Done tiles are missing after Clean it for me (sidebar upload)")
            check("12,029 rows" in text and "22 columns" in text, "A: the cleaned file is not the one in use")
            page.wait_for_timeout(3000)
            check("Here is what changed" in page.inner_text("body"), "A: the Done tiles disappeared a moment later")

            # A2: going to another page and back keeps the result
            sidebar(page).get_by_text("Data", exact=True).first.click()
            page.wait_for_timeout(2500)
            to_clean(page)
            check("Here is what changed" in page.inner_text("body"), "A2: the Done tiles are gone after visiting another page")

            # A3: a genuinely NEW upload still replaces the cleaned file and clears the old result
            page.set_input_files(side, europe_file)
            page.wait_for_timeout(5000)
            text = page.inner_text("body")
            check("2_retail_messy_europe.csv" in text and "Here is what changed" not in text,
                  "A3: a new upload through the sidebar must replace the cleaned file")
            page.close()

            # B: file given on the first (landing) screen
            page = fresh()
            page.set_input_files("input[type=file]", messy_file)
            page.wait_for_timeout(5000)
            to_clean(page)
            press_clean(page)
            text = page.inner_text("body")
            check("Here is what changed" in text and "12,029 rows" in text, "B: landing-screen upload, then Clean it for me")

            # C: Go back to the original file
            page.get_by_role("button", name="Go back to the original file").first.click()
            page.wait_for_timeout(4000)
            text = page.inner_text("body")
            check("12,120 rows" in text and "Here is what changed" not in text, "C: Go back to the original file")
            page.close()
            browser.close()
    finally:
        server.terminate()


if sync_playwright is not None:
    try:
        browser_part()
    except Exception as problem:
        failed.append(f"browser part crashed: {type(problem).__name__}: {str(problem)[:200]}")

print(f"\n{passed + len(failed)} checks, {len(failed)} FAILED")
for message in failed[:12]:
    print("  FAIL:", message)
if browser_note:
    print(browser_note)
sys.exit(1 if failed else 0)
