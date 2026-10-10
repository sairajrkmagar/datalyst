import re

import pandas as pd

from data_profiler import DataProfiler
from ai_engine import AIDataAnalyst
from question_understanding import QuestionUnderstanding
from plan_validator import PlanValidator
from analysis_pipeline import AnalysisPipeline
from response_generator import ResponseGenerator
from explainer import Explainer
from data_typing import (
    add_hierarchy_columns, convert_text_numbers, strip_text
)
from filters import to_dates
import advanced
import followup


# Show the AI the real values of a column only if there are few of them
MAX_VALUES_PER_COLUMN = 30

# A column of whole numbers named like one of these, with few different
# values, is a CATEGORY (zone 101..105, grade 1..5), not something to add up.
CODE_WORDS = {
    "code", "zone", "grade", "level", "class", "group", "type", "dept",
    "department", "branch", "floor", "section", "ward", "category",
    "segment", "tier", "band", "zip", "zipcode", "pin", "pincode",
    "postal", "area", "plan", "region", "district", "store", "shift",
    "batch", "cohort", "stage", "bucket", "cluster", "rank", "class",
}


def looks_like_code(name, series):
    """True for 'ZONE', 'BranchCode', 'grade_level' holding whole numbers."""

    if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
        return False

    values = series.dropna()

    if values.empty or values.nunique() > MAX_VALUES_PER_COLUMN:
        return False

    if not (values == values.round()).all():
        return False

    words = {
        w for w in re.split(
            r"[^a-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name)).lower()
        ) if w
    }

    return bool(words & CODE_WORDS)


from multi_question import split_question

FOLLOW_UP = re.compile(
    r"^(?:and\s+)?(?:which|what)\s+(?:are|were)\s+(?:those|they|these|them)\b|"
    r"^(?:list|show|name|give)\s+(?:me\s+)?(?:them|those|these|all of them)\b"
)


class AskEngine:
    """
    One object per uploaded file.
    Profile the data -> describe it to the AI -> answer questions.
    """

    def __init__(self, df):

        df = df.copy()

        # headers from real exports come with stray spaces ("Amount ") and
        # sometimes twice the same name: clean them, and say so
        names, seen, renamed = [], {}, {}

        for position, column in enumerate(df.columns):

            name = str(column).strip() or f"column_{position + 1}"

            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 1

            if name != str(column):
                renamed[name] = "the column name was tidied (extra spaces removed)"

            names.append(name)

        df.columns = names

        # "Production   " and "Production" are the same value
        df, spaces = strip_text(df)

        # numbers stored as text ("₹1,099", "64%") become real numbers
        df, self.conversions = convert_text_numbers(df)
        self.conversions.update(spaces)
        self.conversions.update(renamed)

        # "Electronics|Cables|HDMI" also gets a column with just the
        # first level, because that is what people mean by "category"
        df, derived, self.main_columns = add_hierarchy_columns(df)
        self.conversions.update(derived)

        self.df = df

        self.profile = self.build_profile(df)

        self.dataset_understanding = self.build_understanding(
            df,
            self.profile
        )

        # Facts that code (not the AI) uses to read questions
        self.add_question_facts(df)

        self.pipeline = AnalysisPipeline(
            self.dataset_understanding,
            QuestionUnderstanding(self.dataset_understanding),
            PlanValidator(self.profile),
            AIDataAnalyst(df),
            ResponseGenerator()
        )

        self.explainer = Explainer()

    def ask(self, question, explain=False):

        question = str(question)

        # "and for 2024?", "what about Home?": made complete from the question before
        complete = followup.rewrite(self, question, getattr(self, "last_question", None))

        if complete and complete != question:
            answer = self.ask(complete, explain=explain)
            answer["question"] = complete
            answer["rewritten_from"] = question
            return answer

        # "which are those categories?" refers to the answer before it
        if FOLLOW_UP.match(question.strip().lower()):

            plan = getattr(self, "last_plan", None)

            if plan and plan.get("intent") == "unique" and plan.get("value_column"):
                question = f"list the different {str(plan['value_column']).replace('_', ' ')} values"

            else:
                return {
                    "status": "error",
                    "message": (
                        "I do not remember earlier questions yet. Please ask "
                        "the full question, for example 'list the different "
                        "categories'."
                    ),
                }

        # statistics, ratio KPIs, growth, rankings ...: answered by code
        answer = advanced.try_answer(self, question)

        if answer is None:
            answer = self.pipeline.run(question)

        if answer["status"] == "success":
            self.last_plan = answer["plan"]
            self.last_question = question

        # Add a written insight (its numbers are checked by code)
        if explain and answer["status"] == "success":
            answer["explanation"] = self.explain(answer)

        return answer

    def ask_many(self, question):
        """[(question, answer)]: one item, or one per question in the sentence."""

        parts = split_question(question)

        if not parts:
            return [(question, self.ask(question))]

        return [(part, self.ask(part)) for part in parts]

    def explain(self, answer):
        """The written insight for an answer (None if it fails)."""

        try:
            return self.explainer.explain(answer, self.df)

        except Exception:
            return None

    def warm_up(self):
        """
        Load both AI models and read the long instructions once,
        so the first real question is fast.
        """

        try:
            self.pipeline.question_understanding.understand(
                "How many rows are there?"
            )

            self.explainer.llm.generate(
                "Reply with the word OK.",
                json_mode=False,
                max_tokens=3
            )

        except Exception:
            pass

    # ------------------------------------------------------------
    # Facts about the data, found by code (not by the AI)
    # ------------------------------------------------------------

    def build_profile(self, df):

        profiler = DataProfiler(df)

        return {
            "basic_info": profiler.basic_info(),
            "numeric_columns": profiler.numeric_columns(),
            "categorical_columns": profiler.categorical_columns(),
            "datetime_columns": profiler.datetime_columns(),
            "identifier_columns": profiler.identifier_columns(),
            "column_semantics": profiler.column_semantics()
        }

    def add_question_facts(self, df):

        understanding = self.dataset_understanding

        self.profile["dimension_values"] = understanding["dimension_values"]
        self.profile["dimensions"] = understanding["dimensions"]
        self.profile["measures"] = understanding["measures"]

        self.profile["row_nouns"] = self.find_row_nouns(df)
        self.profile["count_noun"] = next(
            (n for n in self.profile["row_nouns"] if n.endswith("s")),
            "records"
        )
        self.profile["main_columns"] = self.main_columns

        self.profile["revenue_column"] = self.pick_revenue_column(
            understanding["measures"]
        )

        self.profile["numeric_max"] = {
            column: float(df[column].max())
            for column in understanding["measures"]
        }

        self.profile["date_years"] = []
        self.profile["date_range"] = ""

        dates = understanding["date_columns"]

        if dates:

            stamps = to_dates(df[dates[0]]).dropna()

            if len(stamps) > 0:

                self.profile["date_years"] = sorted(
                    int(year) for year in stamps.dt.year.unique()
                )

                self.profile["date_range"] = (
                    f"{stamps.min():%Y-%m-%d} to {stamps.max():%Y-%m-%d}"
                )

    def find_row_nouns(self, df):
        """
        If every row has its own ID ("Employee ID"), a row IS an employee.
        'how many employees' then means: count the rows.
        """

        nouns = []

        for column in self.profile["identifier_columns"]:

            # one value per row (a few repeats are allowed: Amazon's
            # product_id is 92% unique, and a row there IS a product)
            if df[column].nunique() < 0.9 * len(df):
                continue

            name = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(column))
            words = [w for w in re.split(r"[^A-Za-z]+", name.strip().lower()) if w]

            # only a real ID column ("Employee ID", "order_id"),
            # never a link or image column that merely looks unique
            if not any(w in ("id", "uuid", "number", "no", "num") for w in words):
                continue

            first = words[0]

            if len(first) >= 3 and first not in ("key", "code", "number"):
                nouns += [first, first + "s"]

        return sorted(set(nouns))

    def pick_revenue_column(self, measures):
        """The money column that 'revenue' / 'sales' most likely means."""

        semantics = self.profile["column_semantics"]

        money = [m for m in measures if semantics.get(m) == "monetary"]

        # ("income" is not revenue: a borrower's or an employee's income is not ours)
        for word in ["revenue", "sales", "mrr"]:
            for measure in money:
                if word in measure.lower():
                    return measure

        # "total_amount" / "order_value" are the revenue of an order table,
        # but "loan_amount" or "salary_amount" are not revenue
        whole_names = {
            "total amount", "amount", "order amount", "order value", "net amount",
            "total price", "grand total", "total", "invoice amount", "sale amount",
        }

        for measure in money:
            spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(measure))
            if spaced.replace("_", " ").strip().lower() in whole_names:
                return measure

        return None

    # ------------------------------------------------------------
    # What the AI is told about the data
    # ------------------------------------------------------------

    def build_understanding(self, df, profile):

        dates = profile["datetime_columns"]
        identifiers = profile["identifier_columns"]

        # Measures = numbers we can add up (not IDs, not numeric codes)
        measures = [
            column
            for column in profile["numeric_columns"]
            if column not in identifiers and not looks_like_code(column, df[column])
        ]

        # Dimensions = everything we can group or filter by
        dimensions = [
            column
            for column in df.columns
            if column not in dates and column not in measures
        ]

        # The real values inside small dimension columns
        dimension_values = {}

        for column in dimensions:

            values = df[column].dropna().astype(str).str.strip().unique()

            if 0 < len(values) <= MAX_VALUES_PER_COLUMN:
                dimension_values[column] = sorted(set(values))

        return {
            "dataset_type": "tabular",
            "measures": measures,
            "dimensions": dimensions,
            "date_columns": dates,
            "identifier_columns": identifiers,
            "possible_analysis": [],
            "dimension_values": dimension_values
        }