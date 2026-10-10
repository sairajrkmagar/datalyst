"""
ASK DEBUG: shows what happened to ONE question (uses your real AI).

    python ask_debug.py ecommerce_sales_34500.csv "What is the median order value?"
    python ask_debug.py retail "Who is our best customer by revenue?"      (a catalogue dataset)

Prints the plan the AI gave, what the code repaired, and the answer.
Paste this output when a question gives a wrong answer or a refusal.
"""
import json
import sys
import warnings

warnings.filterwarnings("ignore")

import pandas as pd

from ask_engine import AskEngine

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(1)

source, question = sys.argv[1], " ".join(sys.argv[2:])

try:
    import analyst_data
    if source in analyst_data.BUILDERS:
        df, _ = analyst_data.BUILDERS[source]()
    else:
        df = pd.read_csv(source)
except Exception:
    df = pd.read_csv(source)

engine = AskEngine(df)
engine.warm_up()
answer = engine.ask(question)

raw = getattr(engine.pipeline, "last_raw_plan", None)
print("QUESTION :", question)
print("AI PLAN  :", json.dumps(raw, default=str) if raw else "(the question was answered by code, no AI needed)")
print("STATUS   :", answer["status"])

if answer["status"] == "success":
    print("REPAIRS  :", answer.get("repairs"))
    print("RESULT   :", str(answer["result"])[:300])
    print("ANSWER   :", answer["response"])
else:
    print("MESSAGE  :", answer["message"])
