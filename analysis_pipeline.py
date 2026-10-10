import copy

import pandas as pd

from ai_engine import AIDataAnalyst
from filters import scope_text, subset_for
from metrics import group_values, month_pick, partial_months, share_values
from plan_repair import repair_plan


# Intents that calculate on a number column
NUMBER_INTENTS = [
    "total", "average", "maximum", "minimum", "top", "bottom", "trend"
]


def distinct_values(rows, column, expected):
    """
    The different values of a column, most common first: [(name, rows)].
    None when the list would not match the calculated count.
    """

    if column not in rows.columns:
        return None

    counts = rows[column].dropna().value_counts()

    if len(counts) != expected:
        return None

    items = [(str(name), int(number)) for name, number in counts.items()]
    items.sort(key=lambda item: (-item[1], item[0]))

    return items


def list_sentence(label, values, scope="", limit=40):
    """'The different category values are: A, B, C (3 in total).'"""

    names = [name for name, _ in values[:limit]]

    if len(values) <= limit:
        return (
            f"The different {label} values{scope} are: "
            + ", ".join(names) + f" ({len(values):,} in total)."
        )

    return (
        f"The {limit} most common {label} values{scope} are: "
        + ", ".join(names) + f" (and {len(values) - limit:,} more, "
        f"{len(values):,} in total)."
    )


def names_sentence(values, limit=30):
    """'They are: A, B, C.'  (or the most common ones, when there are many)"""

    names = [name for name, _ in values[:limit]]

    if len(values) <= limit:
        return "They are: " + ", ".join(names) + "."

    return (
        f"The {limit} most common are: " + ", ".join(names)
        + f" (and {len(values) - limit:,} more)."
    )



PLAN_TEXT_FIELDS = ("intent", "column", "group_column", "value_column", "operation", "agg", "filter_value", "sort", "limit_by")
PLAN_LIST_FIELDS = ("filters", "conditions")


def sanitize_plan(plan):
    """
    The AI is untrusted: it may return the right fields with the WRONG TYPES (a string
    where a list belongs, a dictionary as a column name). Force every field to its type,
    dropping what does not fit, BEFORE any other code reads the plan.
    """

    if not isinstance(plan, dict):
        return {}

    clean = dict(plan)

    for key in PLAN_TEXT_FIELDS:
        value = clean.get(key)
        if value is not None and not isinstance(value, (str, int, float, bool)):
            clean[key] = None

    for key in PLAN_LIST_FIELDS:
        value = clean.get(key)
        if value is None:
            continue
        clean[key] = [
            item for item in value
            if isinstance(item, dict) and "column" in item
        ] if isinstance(value, (list, tuple)) else []

    if "date_filter" in clean and not isinstance(clean["date_filter"], dict):
        clean["date_filter"] = None

    return clean


class AnalysisPipeline:

    def __init__(
        self,
        dataset_understanding,
        question_understanding,
        plan_validator,
        analyzer,
        response_generator
    ):

        self.dataset_understanding = dataset_understanding
        self.question_understanding = question_understanding
        self.plan_validator = plan_validator
        self.analyzer = analyzer
        self.response_generator = response_generator

    def run(self, question):

        # STEP 1
        # The AI turns the question into a plan
        raw_plan = sanitize_plan(self.question_understanding.understand(question))

        # Kept so that tests can show what the AI really answered
        self.last_raw_plan = copy.deepcopy(raw_plan)

        # STEP 2
        # Code repairs small, obvious slips in the plan
        repaired_plan, repairs = repair_plan(
            raw_plan,
            question,
            self.plan_validator.profile
        )

        # A reason the code already found not to answer
        if isinstance(repaired_plan, dict) and repaired_plan.get(
            "unsupported"
        ):
            return self.error(repaired_plan["unsupported"])

        # STEP 3
        # Validate the plan (rejects anything unsafe)
        validated_plan = self.plan_validator.validate(repaired_plan)

        if validated_plan is None:

            columns = self.plan_validator.profile["basic_info"][
                "column_names"
            ]

            return self.error(
                "I could not turn that into an analysis I can run "
                "safely. Please rephrase, and mention a column name "
                "if you can. Columns I can use: "
                + ", ".join(str(column) for column in columns)
            )

        # STEP 4
        # Safety checks against the real data
        if validated_plan.get("unsupported"):
            return self.error(validated_plan["unsupported"])

        problem = self.check_plan_against_data(validated_plan)

        if problem is not None:
            return self.error(problem)

        # STEP 5
        # Python calculates the exact answer (on the filtered rows)
        values = None

        try:
            if validated_plan["intent"] == "share":

                result = self.execute_share(validated_plan)

            else:

                rows = subset_for(validated_plan, self.analyzer.df)

                if len(rows) == 0 and validated_plan["intent"] == "count":

                    # "how many orders have quantity below 1?": none. That is an answer
                    result = 0

                elif len(rows) == 0:
                    return self.error(self.empty_message(validated_plan))

                else:

                    if len(rows) == len(self.analyzer.df):
                        analyzer = self.analyzer
                    else:
                        analyzer = AIDataAnalyst(rows)

                    result = self.execute_plan(validated_plan, analyzer)

                if validated_plan["intent"] == "unique":
                    values = distinct_values(
                        rows, validated_plan["value_column"], result
                    )

        except Exception as error:

            return self.error(
                f"Something went wrong while calculating: {error}"
            )

        if result is None:

            return self.error(
                "I could not calculate that from your data."
            )

        # rows exist, but every value of the column is blank there:
        # "average ... is n/a" is not an answer
        if isinstance(result, float) and result != result:

            return self.error(
                f"There is nothing to calculate: '{validated_plan.get('value_column')}' "
                f"has no values for that selection (all of them are blank)."
            )

        # STEP 6
        # Turn the exact result into a sentence
        response = self.response_generator.generate(
            question,
            validated_plan,
            result
        )

        answer = {
            "status": "success",
            "question": question,
            "plan": validated_plan,
            "repairs": repairs,
            "result": result,
            "response": response
        }

        # "how many unique categories?" also says WHICH ones
        if values:

            answer["values"] = values[:100]
            answer["values_total"] = len(values)

            if validated_plan.get("want_list"):
                answer["response"] = list_sentence(
                    self.response_generator.label(validated_plan["value_column"]),
                    values, scope_text(validated_plan),
                )
            else:
                answer["response"] = response.rstrip(".") + ". " + names_sentence(values)

        return answer

    def error(self, message):

        return {
            "status": "error",
            "message": message
        }

    def years_text(self):

        profile = self.plan_validator.profile

        return profile.get("date_range") or ""

    def empty_message(self, plan):

        scope = scope_text(plan)

        message = f"No rows match {scope or 'that filter'}."

        if plan.get("date_filter") and self.years_text():
            message += f" Your data covers {self.years_text()}."

        return message

    def check_plan_against_data(self, plan):
        """
        Look at the REAL data before calculating.
        Returns a message if something is wrong, otherwise None.
        """

        df = self.analyzer.df

        intent = plan["intent"]
        group_column = plan["group_column"]
        value_column = plan["value_column"]
        filter_value = plan["filter_value"]

        # A number is needed for total / average / max / min ...
        counting = plan.get("agg") == "count"

        needs_number = not counting and (
            intent in NUMBER_INTENTS
            or intent in ["breakdown", "month_pick"]
            or (intent == "share" and plan.get("agg") == "sum")
        )

        if needs_number:

            if not pd.api.types.is_numeric_dtype(df[value_column]):

                return (
                    f"'{value_column}' is not a number column, so I "
                    f"cannot calculate {intent} on it."
                )

        # A month or quarter without a year, when the data has several
        date_filter = plan.get("date_filter")

        if date_filter and date_filter.get("needs_year"):

            return (
                f"Your data covers {self.years_text()}. Which year do "
                f"you mean for {date_filter['label']}?"
            )

        # Older plans: a single filter that must exist in the data
        if plan.get("filters") is None and filter_value is not None and (
            intent in ["top", "bottom", "trend"]
        ):

            return (
                "Filtering is not supported for this type of question "
                "yet, so I will not guess an answer."
            )

        # Every filter value must really exist in the data
        for item in plan.get("filters") or []:

            existing = df[item["column"]].astype(str).str.lower()

            if str(item["value"]).lower() not in set(existing):

                examples = (
                    df[item["column"]].dropna().astype(str).unique()[:8]
                )

                return (
                    f"I could not find '{item['value']}' in the column "
                    f"'{item['column']}'. Some values that exist: "
                    + ", ".join(examples)
                )

        if plan.get("filters") is None and filter_value is not None:

            if group_column is None:

                return (
                    "I understood that you want to filter, but I could "
                    "not tell which column to filter. Please mention "
                    "the column name."
                )

            existing = df[group_column].astype(str).str.lower()

            if str(filter_value).lower() not in set(existing):

                examples = (
                    df[group_column]
                    .dropna()
                    .astype(str)
                    .unique()[:8]
                )

                return (
                    f"I could not find '{filter_value}' in the column "
                    f"'{group_column}'. Some values that exist: "
                    + ", ".join(examples)
                )

        return None

    def execute_share(self, plan):
        """Percent that the filtered rows make of the whole."""

        percent, part, whole = share_values(self.analyzer.df, plan)

        if percent is None:
            return None

        plan["share_detail"] = {"part": part, "whole": whole}

        return percent

    def execute_plan(self, plan, analyzer=None):

        if analyzer is None:
            analyzer = self.analyzer


        intent = plan["intent"]
        column = plan["column"]
        group_column = plan["group_column"]
        value_column = plan["value_column"]
        filter_value = plan["filter_value"]

        # The filters were already applied to the rows (by code),
        # so the older single-filter paths below must not run again.
        if plan.get("filters") is not None and intent not in [
            "top", "bottom", "trend"
        ]:
            filter_value = None

        # TOTAL
        if intent == "total":

            if filter_value is not None:

                return analyzer.filtered_sum(
                    group_column,
                    filter_value,
                    value_column
                )

            return analyzer.sum_column(
                value_column
            )

        # AVERAGE
        elif intent == "average":

            if filter_value is not None:

                return analyzer.filtered_average(
                    group_column,
                    filter_value,
                    value_column
                )

            return analyzer.average_column(
                value_column
            )

        # MAXIMUM
        elif intent == "maximum":

            if filter_value is not None:

                return analyzer.filtered_maximum(
                    group_column,
                    filter_value,
                    value_column
                )

            return analyzer.max_column(
                value_column
            )

        # MINIMUM
        elif intent == "minimum":

            if filter_value is not None:

                return analyzer.filtered_minimum(
                    group_column,
                    filter_value,
                    value_column
                )

            return analyzer.min_column(
                value_column
            )

        # COUNT
        elif intent == "count":

            # Count rows/orders
            if plan["operation"] == "row_count":

                return analyzer.count()

            # Count values in a column
            if filter_value is not None:

                return analyzer.filtered_count(
                    group_column,
                    filter_value,
                    value_column
                )

            return analyzer.count_column(
                value_column
            )

        # UNIQUE
        elif intent == "unique":

            if filter_value is not None:

                return analyzer.filtered_unique_count(
                    group_column,
                    filter_value,
                    value_column
                )

            return analyzer.unique_count(
                value_column
            )

        # TOP / BOTTOM  (one answer, or a list for "top 3")
        elif intent in ["top", "bottom"]:

            agg = plan.get("agg") or "sum"

            if agg == "count":
                grouped = analyzer.group_count(group_column)

            elif agg == "mean":
                grouped = analyzer.group_average(group_column, value_column)

            else:
                grouped = analyzer.group_sum(group_column, value_column)

            if not grouped:
                return None

            ordered = sorted(
                grouped.items(),
                key=lambda x: x[1],
                reverse=(intent == "top")
            )

            top_n = plan.get("top_n")

            if top_n and top_n > 1:
                return ordered[:top_n]

            return ordered[0]

        # GROUP TABLE ("revenue by category")
        elif intent == "breakdown":

            values = group_values(
                analyzer.df,
                group_column,
                plan.get("agg") or "sum",
                value_column
            )

            # "share by category": each group as a percent of the total
            if plan.get("as_percent"):

                total = sum(values.values())

                if not total:
                    return None

                values = {
                    name: number / total * 100
                    for name, number in values.items()
                }

            return values

        # BEST / WEAKEST / AVERAGE MONTH
        elif intent == "month_pick":

            monthly = analyzer.time_series(
                group_column,
                value_column,
                period="month"
            )

            if not monthly:
                return None

            partial = partial_months(self.analyzer.df, group_column)

            result, used, left_out = month_pick(
                monthly, plan["pick"], partial
            )

            plan["month_detail"] = {"months_used": used, "left_out": left_out}

            return result

        # TREND
        elif intent == "trend":

            # The validated plan already tells us the date column
            return analyzer.time_series(
                group_column,
                value_column,
                period="month"
            )

        # DUPLICATE
        elif intent == "duplicate":

            return analyzer.duplicate_count()

        # MISSING
        elif intent == "missing":

            return analyzer.missing_count(
                column
            )

        return None
