"""
FILE READER TEST (no AI, seconds): every awkward file a real user might upload.
A file must either load correctly or fail with a friendly FileProblem
(never a Python error, never silently read wrongly).

    python test_file_reader.py
"""
import io
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

import file_reader as fr

passed, failed = 0, []


def check(ok, message):
    global passed
    if ok:
        passed += 1
    else:
        failed.append(message)


def loads(name, data, rows=None, cols=None, note=None, **kw):
    try:
        table, info = fr.read_table(name, data, **kw)
    except Exception as error:
        check(False, f"{name}: should load but raised {type(error).__name__}: {str(error)[:60]}")
        return None, None
    check(rows is None or len(table) == rows, f"{name}: rows {len(table)} != {rows}")
    check(cols is None or table.shape[1] == cols, f"{name}: columns {table.shape[1]} != {cols}")
    check(note is None or any(note in n for n in info["notes"]), f"{name}: missing note {note!r} in {info['notes']}")
    check(isinstance(fr.describe(info), str) and "rows" in fr.describe(info), f"{name}: describe()")
    return table, info


def fails(name, data, word=None):
    try:
        fr.read_table(name, data)
    except fr.FileProblem as problem:
        check(bool(problem.message) and (word is None or word in problem.message.lower()), f"{name}: wrong message {problem.message!r}")
        return
    except Exception as error:
        check(False, f"{name}: raised {type(error).__name__} instead of FileProblem: {str(error)[:60]}")
        return
    check(False, f"{name}: should have been refused")


rng = np.random.default_rng(1)
base = pd.DataFrame({"region": rng.choice(["North", "South"], 50), "sales": rng.integers(10, 500, 50), "date": pd.date_range("2024-01-01", periods=50).astype(str)})
csv = lambda **kw: base.to_csv(index=False, **kw)

# ---------------- files that must LOAD
loads("plain.csv", csv().encode(), 50, 3)
t, i = loads("windows.csv", base.assign(region=["Zürich", "São Paulo"] * 25).to_csv(index=False).encode("cp1252"), 50, 3, note="windows-1252")
check(t is not None and "Zürich" in set(t["region"]), "windows.csv: accents were lost")
t, i = loads("bom.csv", csv().encode("utf-8-sig"), 50, 3)
check(t is not None and list(t.columns)[0] == "region", "bom.csv: the first column name has a hidden mark")
loads("semicolon.csv", csv(sep=";").encode(), 50, 3, note="semicolon")
loads("tab.tsv", csv(sep="\t").encode(), 50, 3, note="tab")
loads("pipe.txt", csv(sep="|").encode(), 50, 3, note="pipe")
loads("utf16.csv", csv().encode("utf-16"), 50, 3)
loads("crlf.csv", csv().replace("\n", "\r\n").encode(), 50, 3)

quoted = 'name,city,amount\n"Smith, John","Paris, France",100\n"Lee, Ann","Rome, Italy",200\n'.encode()
loads("quoted.csv", quoted, 2, 3)

title = b"Monthly sales report\nGenerated on 2024-02-01\n\nregion,sales,date\nNorth,10,2024-01-01\nSouth,20,2024-01-02\nNorth,30,2024-01-03\n"
t, i = loads("title.csv", title, None, 3, note="skipped")
check(t is not None and list(t.columns) == ["region", "sales", "date"], f"title.csv: header not found {None if t is None else list(t.columns)}")

loads("one_row.csv", b"region,sales\nNorth,100\n", 1, 2)
loads("one_column.csv", b"sales\n1\n2\n3\n", 3, 1, note="one column")
loads("dup_blank_headers.csv", b"a,a,,b\n1,2,3,4\n5,6,7,8\n", 2)
loads("trailing_separator.csv", b"a,b,\n1,2,\n3,4,\n", 2, 2)
loads("ragged.csv", b"a,b,c\n1,2,3\n4,5,6,7\n8,9,10\n", None, 3)
loads("wide.csv", pd.DataFrame(rng.integers(0, 9, (200, 400))).to_csv(index=False).encode(), 200, 400)
loads("text_numbers.csv", b'item,amount\nA,"1,234"\nB,"2,500"\n', 2, 2)

# ---------------- Excel
book = io.BytesIO()
with pd.ExcelWriter(book) as w:
    base.to_excel(w, sheet_name="Summary", index=False)
    base.assign(sales=base.sales * 100).to_excel(w, sheet_name="Data", index=False)
xlsx = book.getvalue()
t, i = loads("book.xlsx", xlsx, 50, 3, note="2 sheets")
check(i is not None and i["sheets"] == ["Summary", "Data"] and i["sheet"] == "Summary", f"book.xlsx: sheets {i and i['sheets']}")
t2, i2 = loads("book.xlsx", xlsx, 50, 3, sheet="Data")
check(t2 is not None and int(t2["sales"].sum()) == int(base["sales"].sum() * 100), "book.xlsx: the chosen sheet was not read")
loads("book.xlsx", xlsx, 50, 3, sheet="No such sheet")

book2 = io.BytesIO()
with pd.ExcelWriter(book2) as w:
    pd.DataFrame().to_excel(w, sheet_name="Empty", index=False)
    base.to_excel(w, sheet_name="Real", index=False)
t, i = loads("empty_first.xlsx", book2.getvalue(), 50, 3)
check(i is not None and i["sheet"] == "Real", "empty_first.xlsx: did not skip the empty sheet")
loads("really_excel.csv", xlsx, 50, 3)                          # an Excel file with the wrong name

# ---------------- files that must be REFUSED with a friendly message
fails("empty.csv", b"", "empty")
fails("blank.csv", b"   \n\n", None)
fails("header_only.csv", b"region,sales,date\n", "no rows")
fails("garbage.csv", bytes(np.random.default_rng(5).integers(0, 255, 3000, dtype=np.uint8)), None)
fails("doc.pdf", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3", "pdf")
fails("photo.csv", b"\x89PNG\r\n\x1a\n" + bytes(200), "picture")
fails("page.csv", b"<!DOCTYPE html><html><body>hi</body></html>", "web page")
fails("old.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(200), ".xls")
fails("fake.xlsx", csv().encode(), "excel")
fails("broken.xlsx", b"PK\x03\x04" + bytes(np.random.default_rng(6).integers(0, 255, 500, dtype=np.uint8)), None)

# ---------------- big and fast
big = pd.DataFrame({"id": np.arange(300_000), "v": rng.random(300_000), "g": rng.choice(list("abcd"), 300_000)}).to_csv(index=False).encode()
started = time.time()
loads("big.csv", big, 300_000, 3)
check(time.time() - started < 8, f"big.csv: too slow {time.time() - started:.1f}s")


# ============================================================
# LIMITS AND NOTES: the exact edges, and what the person is told
# ============================================================
# exactly MAX_COLUMNS columns loads; one more is refused (CSV and Excel)
def wide_csv(n):
    return (",".join(f"c{i}" for i in range(n)) + "\n" + ",".join("1" for _ in range(n)) + "\n" + ",".join("2" for _ in range(n)) + "\n").encode()

loads("exactly_max.csv", wide_csv(fr.MAX_COLUMNS), 2, fr.MAX_COLUMNS)
fails("one_too_wide.csv", wide_csv(fr.MAX_COLUMNS + 1), "columns")
check(fr.MAX_COLUMNS == 5000, "limits: the column limit changed without the test being updated")

wide_book = io.BytesIO()
with pd.ExcelWriter(wide_book) as w:
    pd.DataFrame(np.ones((2, fr.MAX_COLUMNS + 1)), columns=[f"c{i}" for i in range(fr.MAX_COLUMNS + 1)]).to_excel(w, index=False)
fails("wide.xlsx", wide_book.getvalue(), "columns")

# an Excel sheet that claims more cells than the limit is refused; exactly the limit is accepted
small_book = io.BytesIO()
with pd.ExcelWriter(small_book) as w:
    pd.DataFrame(np.arange(40).reshape(10, 4), columns=list("abcd")).to_excel(w, index=False)
small_xlsx = small_book.getvalue()
claimed = None
original_limit = fr.MAX_SHEET_CELLS
try:
    table, _ = fr.read_table("s.xlsx", small_xlsx)
    cells = (len(table) + 1) * table.shape[1]                      # what the sheet claims: header row included
    fr.MAX_SHEET_CELLS = cells
    loads("s.xlsx", small_xlsx, 10, 4)                              # exactly at the limit: accepted
    fr.MAX_SHEET_CELLS = cells - 1
    fails("s.xlsx", small_xlsx, "enormous")                        # one cell over: refused
finally:
    fr.MAX_SHEET_CELLS = original_limit

original_zip = fr.MAX_UNZIPPED_BYTES
try:
    fr.MAX_UNZIPPED_BYTES = 10
    fails("s.xlsx", small_xlsx, "unusually large")
    fr.MAX_UNZIPPED_BYTES = 10 ** 9
    loads("s.xlsx", small_xlsx, 10, 4)
finally:
    fr.MAX_UNZIPPED_BYTES = original_zip

# the first 200 KB are used to guess the encoding: a cut in the middle of a character must not look like a wrong encoding
for offset in (1, 2):
    text = b"a,b\n" + b"x," + b"1\n" * 0
    body = (b"id,name\n" + b"1,abc\n" * 33300)
    body = body[: fr.SAMPLE_BYTES - offset] + "\u20ac".encode("utf-8") + b"\n2,def\n"      # a 3-byte character straddles the cut
    table, info = loads(f"cut{offset}.csv", body, None, 2)
    check(info is not None and info["encoding"] == "utf-8" and not any("not UTF-8" in n for n in info["notes"]), f"encoding: a character cut by the sample made the file look non-UTF-8 (offset {offset})")

# a bad byte AFTER the sample: still loads, and the person is told
late = b"id,name\n" + b"1,abc\n" * 40000 + b"2,caf\xe9\n"
check(len(late) > fr.SAMPLE_BYTES, "test file: the bad byte must come after the sample")
table, info = loads("late.csv", late, 40001, 2, note="latin-1")
check(info is not None and any("different text encoding" in n for n in info["notes"]), "notes: a late encoding problem was not reported")

# damaged lines: the rest loads and the person is told
table, info = loads("damaged.csv", b"a,b,c\n1,2,3\n4,5,6,7\n8,9,10\n", 2, 3, note="skipped")
check(info is not None and any("damaged" in n or "wrong number" in n for n in info["notes"]), "notes: skipped lines were not reported")

# a table whose only columns are empty and unnamed has nothing usable
fails("only_empty.csv", b",,\n,,\n,,\n", "usable")
fails("one_blank_column.csv", b",\n,\n", None)

print(f"{passed + len(failed)} checks, {len(failed)} FAILED")
for f in failed[:12]:
    print("  FAIL:", f)
