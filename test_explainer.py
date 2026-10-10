import pandas as pd

from ask_engine import AskEngine


df = pd.read_csv("sample_sales.csv")

engine = AskEngine(df)

questions = [
    "What is the total revenue?",
    "What is the total revenue for Electronics?",
    "What is the average revenue for Clothing?",
    "What is the maximum order amount?",
    "Which product category earns the most revenue?",
    "Which region has the lowest revenue?",
    "Who is our best customer?",
    "How many customers do we have?",
    "Are there duplicate orders?",
    "How many missing values are there?",
    "Show me monthly revenue",
]

ai_written = 0

print(f"Testing the explanation on {len(questions)} questions...\n",
      flush=True)

for number, question in enumerate(questions, start=1):

    answer = engine.ask(question, explain=True)

    print("=" * 70)
    print(f"{number}. {question}")

    if answer["status"] != "success":
        print("   ERROR:", answer["message"])
        continue

    explanation = answer.get("explanation")

    print("   ANSWER :", answer["response"])

    if explanation is None:
        print("   INSIGHT: (none)")
        continue

    if explanation["source"] == "ai":
        ai_written += 1
        print("   INSIGHT (written by AI, numbers verified):")
    else:
        print(f"   INSIGHT (standard summary; AI text rejected: "
              f"{explanation['reason']}):")

    print("   ", explanation["text"])
    print(flush=True)

print("=" * 70)
print(f"AI-written insights that passed the number check: "
      f"{ai_written} / {len(questions)}")
print("=" * 70)
