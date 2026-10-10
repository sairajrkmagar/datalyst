import copy
import time

from question_understanding import QuestionUnderstanding
from plan_validator import PlanValidator
from plan_repair import repair_plan


# ------------------------------------------------------------
# The dataset we test on (same as your other tests)
# ------------------------------------------------------------

DATASET_UNDERSTANDING = {
    "dataset_type": "transactional",
    "measures": ["sales"],
    "dimensions": ["customer", "category"],
    "date_columns": ["order_date"],
    "identifier_columns": [],
    "possible_analysis": [],
    "dimension_values": {
        "customer": ["C001", "C002", "C003"],
        "category": ["Electronics", "Home"]
    }
}

PROFILE = {
    "basic_info": {
        "column_names": ["customer", "category", "sales", "order_date"]
    },
    "numeric_columns": ["sales"],
    "identifier_columns": [],
    "column_semantics": {
        "customer": "customer",
        "category": "category",
        "sales": "monetary",
        "order_date": "date"
    }
}


# ------------------------------------------------------------
# Small helpers that build the EXPECTED plan for each question
# ------------------------------------------------------------

def plan(intent, operation, column=None, group=None,
         value=None, filter_value=None):
    return {
        "intent": intent,
        "column": column,
        "group_column": group,
        "value_column": value,
        "filter_value": filter_value,
        "operation": operation,
    }


def total(filter_value=None):
    group = "category" if filter_value else None
    return plan("total", "sum", "sales", group, "sales", filter_value)


def average(filter_value=None):
    group = "category" if filter_value else None
    return plan("average", "average", "sales", group, "sales", filter_value)


MAXIMUM = plan("maximum", "max", "sales", None, "sales")
MINIMUM = plan("minimum", "min", "sales", None, "sales")


def top(group):
    return plan("top", "group_sum", "sales", group, "sales")


def bottom(group):
    return plan("bottom", "group_sum", "sales", group, "sales")


UNIQUE_CUSTOMERS = plan("unique", "unique", "customer", None, "customer")
ROW_COUNT = plan("count", "row_count")
DUPLICATE = plan("duplicate", "duplicate_count")
MISSING = plan("missing", "missing_count")
TREND = plan("trend", "time_series", "sales", "order_date", "sales")


# ------------------------------------------------------------
# THE GOLDEN QUESTIONS  (question, expected plan)
# ------------------------------------------------------------

GOLDEN = [
    # total
    ("What is the total sales?", total()),
    ("How much revenue did we make?", total()),
    ("What did we sell in total?", total()),
    ("What is the total sales for Electronics?", total("Electronics")),
    ("How much did Electronics sell?", total("Electronics")),

    # average
    ("What is the average sales?", average()),
    ("What is the average sales for Electronics?", average("Electronics")),

    # maximum / minimum (single biggest / smallest value)
    ("What is the maximum sales?", MAXIMUM),
    ("What is the minimum sales?", MINIMUM),

    # best / worst category
    ("Which category has the highest sales?", top("category")),
    ("Which category sells the most?", top("category")),
    ("Which category has the lowest sales?", bottom("category")),
    ("Which category sold the least?", bottom("category")),

    # best / worst customer
    ("Which customer generated the highest sales?", top("customer")),
    ("Who is our highest-selling customer?", top("customer")),
    ("Who brought in the most revenue?", top("customer")),
    ("Which customer spent the most?", top("customer")),
    ("Which customer generated the lowest sales?", bottom("customer")),
    ("Who generated the least sales?", bottom("customer")),

    # customers (a customer who buys twice is still ONE customer)
    ("How many customers are there?", UNIQUE_CUSTOMERS),
    ("How many unique customers are there?", UNIQUE_CUSTOMERS),

    # rows
    ("How many orders are there?", ROW_COUNT),
    ("How many transactions are there?", ROW_COUNT),
    ("How many records do we have?", ROW_COUNT),
    ("How many rows are in the dataset?", ROW_COUNT),

    # duplicates
    ("How many duplicate rows are there?", DUPLICATE),
    ("Are there any duplicates?", DUPLICATE),

    # missing
    ("How many missing values are there?", MISSING),
    ("Do we have any nulls?", MISSING),
    ("Do we have missing data?", MISSING),

    # trend
    ("What are the monthly sales?", TREND),
    ("Show me sales by month.", TREND),
    ("What is the sales trend over time?", TREND),
]


# ------------------------------------------------------------
# Compare expected plan and real plan
# ------------------------------------------------------------

def same(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    return a == b


def find_differences(expected, got):
    differences = []
    for key, expected_value in expected.items():
        got_value = got.get(key)
        if not same(expected_value, got_value):
            differences.append((key, expected_value, got_value))
    return differences


# ------------------------------------------------------------
# Run everything
# ------------------------------------------------------------

def run():
    understanding = QuestionUnderstanding(DATASET_UNDERSTANDING)
    validator = PlanValidator(PROFILE)

    total_questions = len(GOLDEN)
    passed = 0
    repaired_count = 0
    failures = []

    print(f"Running {total_questions} questions. Please wait...\n",
          flush=True)

    for number, (question, expected) in enumerate(GOLDEN, start=1):

        started = time.time()

        raw_plan = understanding.understand(question)
        raw_copy = copy.deepcopy(raw_plan)

        repaired_plan, notes = repair_plan(raw_plan, question, PROFILE)
        final_plan = validator.validate(repaired_plan)

        seconds = time.time() - started

        if final_plan is None:
            status = "FAIL"
            differences = [("REJECTED by validator", "valid plan", raw_copy)]
        else:
            differences = find_differences(expected, final_plan)
            status = "PASS" if not differences else "FAIL"

        if status == "PASS":
            passed += 1
        else:
            failures.append((question, differences))

        extra = ""
        if notes:
            repaired_count += 1
            extra = "   [repaired: " + "; ".join(notes) + "]"

        print(f"{number:>2}. {status}  {seconds:4.0f}s  {question}{extra}",
              flush=True)

    percent = round(100 * passed / total_questions)

    print("\n" + "=" * 60)
    print(f"SCORE: {passed} / {total_questions} passed  ({percent}%)")
    print(f"Plans the AI got slightly wrong and the code repaired: "
          f"{repaired_count}")
    print("=" * 60)

    if failures:
        print("\nWHAT WENT WRONG:\n")
        for question, differences in failures:
            print(f"Q: {question}")
            for key, expected_value, got_value in differences:
                print(f"   {key}: expected {expected_value!r}, got {got_value!r}")
            print()


if __name__ == "__main__":
    run()
