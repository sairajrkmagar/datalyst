"""
FEEDBACK LOG: real users become test cases.

Every thumbs-up / "not right" click is saved as one line in feedback_log.jsonl
ON THIS COMPUTER. It stores the question, what the app said, and the column names
(never the rows of your data). `python feedback_report.py` lists the problems so
each one can become a test.
"""

import json
import os
import time

LOG_FILE = os.environ.get("DATALYST_FEEDBACK_FILE", "feedback_log.jsonl")
MAX_TEXT = 600


def short(text, limit=MAX_TEXT):
    text = str(text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def record(question, answer, rating, dataset="", columns=(), comment="", path=None):
    """Save one reaction. rating: 'up' (helpful) or 'down' (not right). Returns the entry."""

    if rating not in ("up", "down"):
        raise ValueError("rating must be 'up' or 'down'")

    answer = answer if isinstance(answer, dict) else {}
    plan = answer.get("plan") or {}

    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rating": rating,
        "question": short(question),
        "status": answer.get("status", ""),
        "said": short(answer.get("response") or answer.get("message") or ""),
        "intent": plan.get("intent"),
        "how": (plan.get("advanced") or {}).get("kind") if plan.get("intent") == "advanced" else None,
        "dataset": short(dataset, 120),
        "columns": [short(c, 60) for c in list(columns)[:80]],
        "comment": short(comment, 500),
    }

    with open(path or LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def read_all(path=None):
    """Every saved entry (damaged lines are skipped)."""

    path = path or LOG_FILE

    if not os.path.exists(path):
        return []

    entries = []

    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
                if isinstance(item, dict) and item.get("rating") in ("up", "down"):
                    entries.append(item)
            except ValueError:
                continue

    return entries


def summary(entries):
    """{'total', 'up', 'down', 'refused_but_wanted'}"""

    down = [e for e in entries if e["rating"] == "down"]

    return {
        "total": len(entries),
        "up": sum(1 for e in entries if e["rating"] == "up"),
        "down": len(down),
        "refused_but_wanted": sum(1 for e in down if e.get("status") == "error"),
    }
