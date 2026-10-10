"""
READ ANY SPREADSHEET FILE SAFELY.

Real files are messy: Excel "CSV" files in Windows encoding, semicolon-separated
files from Europe, files with a title above the header, Excel workbooks with
several sheets, empty or corrupt files. This module works out how to read each
one and says what it did, or explains in plain words why it cannot.

    table, info = read_table("sales.csv", file_bytes)
    info = {"encoding": "windows-1252", "delimiter": "semicolon", "sheet": None,
            "sheets": [], "rows": 120, "columns": 7, "notes": ["..."]}

A file that cannot be read raises FileProblem(message): the message is for the
person using the app, never a Python error.
"""

import csv
import io
import zipfile

import pandas as pd

# limits that stop a small file from using all the memory
MAX_COLUMNS = 5_000
MAX_UNZIPPED_BYTES = 400 * 1024 * 1024        # an .xlsx is a zip: what it unpacks to
MAX_SHEET_CELLS = 100_000_000                  # a sheet that claims to be this big is refused

csv.field_size_limit(16 * 1024 * 1024)         # the sample we read is 200 KB: never trip on a long field

DELIMITERS = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}
TEXT_EXTENSIONS = (".csv", ".tsv", ".txt")
EXCEL_EXTENSIONS = (".xlsx", ".xlsm")

SAMPLE_BYTES = 200_000
MAX_SCAN_LINES = 60


class FileProblem(Exception):
    """A file we cannot use, with a message a person can act on."""

    def __init__(self, message, steps=()):
        super().__init__(message)
        self.message = message
        self.steps = list(steps)


def looks_like(file_bytes):
    """What the first bytes say the file really is."""

    head = file_bytes[:16]

    if head.startswith(b"PK\x03\x04"):
        return "excel"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff") or head.startswith(b"GIF8"):
        return "image"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "old excel"
    return "text"


def decode_sample(file_bytes):
    """(encoding name, decoded sample): the first encoding that fits."""

    sample = file_bytes[:SAMPLE_BYTES]

    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", sample.decode("utf-8-sig", errors="replace")

    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16", sample.decode("utf-16", errors="replace")

    # a sample cut in the middle of a character must not count as an error
    for cut in range(0, 4):
        try:
            return "utf-8", sample[:len(sample) - cut].decode("utf-8")
        except UnicodeDecodeError:
            continue

    # Windows / Excel "CSV": accents are written in a single byte
    try:
        return "windows-1252", sample.decode("windows-1252")
    except UnicodeDecodeError:
        return "latin-1", sample.decode("latin-1")


def mostly_text(text):
    """False for binary garbage."""

    if not text:
        return False

    odd = sum(1 for ch in text[:5000] if ch == "\x00" or (ord(ch) < 32 and ch not in "\r\n\t"))

    return odd / min(len(text), 5000) < 0.02


def sniff_delimiter(text):
    """(delimiter, header row index, number of columns)."""

    lines = [line for line in text.splitlines() if line.strip()][:MAX_SCAN_LINES]

    best = (",", 0, 1, -1.0)

    for delimiter in DELIMITERS:

        try:
            lengths = [len(row) for row in csv.reader(lines, delimiter=delimiter)]
        except csv.Error:
            continue

        if not lengths:
            continue

        counts = {}
        for n in lengths:
            counts[n] = counts.get(n, 0) + 1

        common = max((n for n in counts if n > 1), key=lambda n: (counts[n], n), default=1)
        consistency = counts.get(common, 0) / len(lengths)
        score = consistency if common > 1 else 0.0

        # the header is the first row that has the usual number of columns
        header = next((i for i, n in enumerate(lengths) if n == common), 0)

        if score > best[3] or (score == best[3] and common > best[2]):
            best = (delimiter, header, common, score)

    return best[0], best[1], best[2]


def read_text(file_bytes, notes):

    encoding, sample = decode_sample(file_bytes)

    if not mostly_text(sample):
        raise FileProblem(
            "This does not look like a spreadsheet or CSV file. It seems to be "
            "something else (maybe a corrupted download).",
            ["Open the file in Excel or Numbers and save it again as CSV or XLSX."],
        )

    stripped = sample.lstrip().lower()

    if stripped.startswith(("<!doctype html", "<html", "<?xml")):
        raise FileProblem(
            "This is a web page, not a data file.",
            ["Download the data itself (the CSV or Excel export), not the page."],
        )

    delimiter, header, columns = sniff_delimiter(sample)

    if encoding not in ("utf-8", "utf-8-sig"):
        notes.append(f"The file is not UTF-8, so I read it as {encoding}.")

    if delimiter != ",":
        notes.append(f"The columns are separated by a {DELIMITERS[delimiter]}.")

    if header > 0:
        notes.append(f"I skipped {header} line(s) above the column names.")

    if columns > MAX_COLUMNS:
        raise FileProblem(
            f"This file has more than {MAX_COLUMNS:,} columns, which is too many to work with.",
            ["Check that the right separator is used, or keep only the columns you need."],
        )

    options = dict(sep=delimiter, encoding=encoding, skiprows=header)
    source = io.BytesIO(file_bytes)

    try:
        table = pd.read_csv(source, **options)

    except pd.errors.EmptyDataError:
        raise FileProblem("The file is empty: there are no columns to read.")

    except MemoryError:
        raise FileProblem("This file is too large to read here.", ["Keep only the columns and rows you need."])

    except (pd.errors.ParserError, UnicodeDecodeError, ValueError, OverflowError, csv.Error) as first:

        # a damaged part of the file: read what is readable, and say so
        if isinstance(first, UnicodeDecodeError):
            options["encoding"] = "latin-1"
            notes.append("Part of the file used a different text encoding (read as latin-1).")

        try:
            table = pd.read_csv(io.BytesIO(file_bytes), on_bad_lines="skip", **options)
            notes.append("Some lines were damaged or had the wrong number of columns, and were skipped.")
        except pd.errors.EmptyDataError:
            raise FileProblem("The file is empty: there are no columns to read.")
        except MemoryError:
            raise FileProblem("This file is too large to read here.", ["Keep only the columns and rows you need."])
        except Exception:
            raise FileProblem(
                "I could not make sense of the rows of this file.",
                ["Check that every row has the same number of columns."],
            )

    except Exception:
        raise FileProblem(
            "I could not read this file.",
            ["Open it in Excel or Numbers and save it again as CSV or XLSX."],
        )

    if table.shape[1] > MAX_COLUMNS:
        raise FileProblem(f"This file has more than {MAX_COLUMNS:,} columns, which is too many to work with.")

    return table, {"encoding": encoding, "delimiter": DELIMITERS[delimiter]}


def read_excel(file_name, file_bytes, sheet, notes):

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            unpacked = sum(item.file_size for item in archive.infolist())
    except Exception:
        unpacked = 0                                    # not a readable zip: the next step explains

    if unpacked > MAX_UNZIPPED_BYTES:
        raise FileProblem(
            "This Excel file unpacks to an unusually large size, so I will not open it.",
            ["Save the data again as CSV, or keep only the rows you need."],
        )

    try:
        book = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception:
        raise FileProblem(
            "I could not open this Excel file. It may be password protected or damaged.",
            ["Open it in Excel, remove the password, and save it again as .xlsx"],
        )

    sheets = list(book.sheet_names)

    # a sheet that CLAIMS to be enormous is refused before a single cell is read
    for name in sheets:
        try:
            worksheet = book.book[name]
            claimed = int(getattr(worksheet, "max_row", 0) or 0) * int(getattr(worksheet, "max_column", 0) or 0)
        except Exception:
            claimed = 0

        if claimed > MAX_SHEET_CELLS:
            raise FileProblem(
                f"The sheet '{name}' claims to be enormous, so I will not open it.",
                ["Copy the data into a new, clean workbook and save it again."],
            )

    if sheet is None or sheet not in sheets:

        # the first sheet that really holds data
        sheet = next(
            (name for name in sheets if not book.parse(name, nrows=2).dropna(how="all").empty),
            sheets[0],
        )

    if len(sheets) > 1:
        notes.append(f"This workbook has {len(sheets)} sheets. I am reading '{sheet}'.")

    try:
        table = book.parse(sheet)
    except MemoryError:
        raise FileProblem(f"The sheet '{sheet}' is too large to read here.")
    except Exception:
        raise FileProblem(f"I could not read the sheet '{sheet}'.")

    if table.shape[1] > MAX_COLUMNS:
        raise FileProblem(f"The sheet '{sheet}' has more than {MAX_COLUMNS:,} columns, which is too many to work with.")

    return table, {"sheet": sheet, "sheets": sheets}


def read_table(file_name, file_bytes, sheet=None):
    """(DataFrame, info). Raises FileProblem with a human message."""

    name = str(file_name).lower()
    notes = []

    if not file_bytes:
        raise FileProblem("The file is empty.", ["Choose another file."])

    kind = looks_like(file_bytes)

    if kind in ("pdf", "image"):
        raise FileProblem(
            f"This is a {'PDF' if kind == 'pdf' else 'picture'}, not a spreadsheet.",
            ["Upload the CSV or Excel file the data came from."],
        )

    if kind == "old excel" or name.endswith(".xls"):
        raise FileProblem(
            "Old Excel files (.xls) are not supported.",
            ["In Excel choose File, Save As, and pick 'Excel Workbook (.xlsx)'."],
        )

    info = {"kind": "csv", "encoding": None, "delimiter": None, "sheet": None, "sheets": []}

    if kind == "excel" or name.endswith(EXCEL_EXTENSIONS):

        if kind != "excel":
            raise FileProblem("This file is called Excel but is not an Excel workbook.")

        table, extra = read_excel(file_name, file_bytes, sheet, notes)
        info.update(extra, kind="excel")

    else:
        table, extra = read_text(file_bytes, notes)
        info.update(extra)

    if table.shape[1] == 0:
        raise FileProblem("No columns were found in this file.")

    if table.shape[0] == 0:
        raise FileProblem(
            "I found the column names but no rows of data.",
            ["Check that the file has data under the header row."],
        )

    # an empty trailing column made by a closing separator
    unnamed = [c for c in table.columns if str(c).startswith("Unnamed:") and table[c].isna().all()]
    if unnamed:
        table = table.drop(columns=unnamed)

    if table.shape[1] == 0 or table.shape[0] == 0:
        raise FileProblem("I could not find any usable columns and rows in this file.")

    if table.shape[1] == 1 and info["kind"] == "csv":
        notes.append("Only one column was found. If your file has more, it may use an unusual separator.")

    info.update(rows=len(table), columns=table.shape[1], notes=notes)

    return table, info


def describe(info):
    """One line: 'UTF-8 · comma separated · 34,500 rows x 17 columns'."""

    parts = []

    if info.get("kind") == "excel":
        parts.append(f"Excel sheet '{info.get('sheet')}'")
    else:
        encoding = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8", "utf-16": "UTF-16"}.get(info.get("encoding"), info.get("encoding") or "")
        parts += [encoding, f"{info.get('delimiter')} separated"]

    parts.append(f"{info.get('rows', 0):,} rows x {info.get('columns', 0)} columns")

    return " · ".join(p for p in parts if p)
