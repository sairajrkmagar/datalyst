from llm_client import LLMClient

llm = LLMClient()

print("TEST 1: normal text answer")
print(llm.generate(
    "What is a data analyst? Answer in one sentence.",
    json_mode=False
))

print("\nTEST 2: JSON answer")
result = llm.generate(
    'Return a JSON object with the key "status" and the value "ok".'
)
print(result)
print("Type:", type(result).__name__)