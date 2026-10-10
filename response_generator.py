from safe_numbers import is_whole
from filters import plural_label, scope_text


class ResponseGenerator:

    def label(self, name):

        if name is None:
            return None

        text = str(name)

        # "category_main" (the first level of a long path) is just "category"
        if text.endswith("_main"):
            text = text[:-5]

        return text.replace("_", " ")

    def total_label(self, column):

        if str(column).lower().startswith("total"):
            return str(column).capitalize()

        return f"Total {column}"

    def fmt(self, value):

        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)

        if number != number or number in (float("inf"), float("-inf")):
            return "n/a"

        if is_whole(number):
            return f"{int(number):,}"

        return f"{number:,.2f}"

    def generate(self, question, plan, result):

        intent = plan["intent"]
        raw_column = plan["column"]
        column = self.label(plan["column"] or plan["value_column"])
        group_column = self.label(plan["group_column"])
        operation = plan["operation"]

        agg = plan.get("agg") or "sum"
        value_label = self.label(plan["value_column"])

        noun = plan.get("count_noun") or "orders"

        # "number of orders" / "average price" / "price"
        if agg == "count":
            metric_words = f"number of {noun}"
        elif agg == "mean":
            metric_words = f"average {value_label}"
        else:
            metric_words = value_label

        # " for Fashion in September 2024"  (empty if no filter)
        scope = scope_text(plan)
        scope = f" {scope}" if scope else ""

        # TOTAL
        if intent == "total":

            return f"{self.total_label(column)}{scope} is {self.fmt(result)}."

        # AVERAGE
        if intent == "average":

            return f"Average {column}{scope} is {self.fmt(result)}."

        # MAXIMUM
        if intent == "maximum":

            return f"Maximum {column}{scope} is {self.fmt(result)}."

        # MINIMUM
        if intent == "minimum":

            return f"Minimum {column}{scope} is {self.fmt(result)}."

        # COUNT
        if intent == "count":

            if operation == "row_count":
                return f"There are {self.fmt(result)} records{scope}."

            if raw_column == "customer":
                return f"There are {self.fmt(result)} customers{scope}."

            return f"There are {self.fmt(result)} {column} values{scope}."

        # UNIQUE
        if intent == "unique":

            return (
                f"There are {self.fmt(result)} unique {column} "
                f"values{scope}."
            )

        # DUPLICATE
        if intent == "duplicate":

            return f"Number of duplicate rows{scope} is {self.fmt(result)}."

        # MISSING
        if intent == "missing":

            if plan["column"] is None:
                return (
                    f"Total missing values{scope} are {self.fmt(result)}."
                )

            return f"Missing values in {column}{scope} are {self.fmt(result)}."

        # TOP / BOTTOM
        if intent in ["top", "bottom"]:

            if result is None:
                return "No result found."

            # "top 3" -> a list of (name, value)
            if isinstance(result, list):

                word = "Top" if intent == "top" else "Bottom"

                items = ", ".join(
                    f"{name} ({self.fmt(value)})" for name, value in result
                )

                return (
                    f"{word} {len(result)} {plural_label(group_column)} by "
                    f"{metric_words}{scope}: {items}."
                )

            category, value = result

            word = "top" if intent == "top" else "lowest"

            by_text = "" if agg == "sum" else f" by {metric_words}"

            return (
                f"The {word} {group_column}{scope}{by_text} is "
                f"{category} with {self.fmt(value)}."
            )

        # GROUP TABLE
        if intent == "breakdown":

            if agg == "count":
                metric = f"Number of {noun}"
            elif agg == "mean":
                metric = f"Average {value_label}"
            else:
                metric = self.total_label(value_label)

            items = list(result.items())

            if plan.get("as_percent"):

                shown = ", ".join(
                    f"{name} {number:.1f}%" for name, number in items[:8]
                )
                metric = f"Share of {metric_words if agg != 'count' else noun}"

            else:

                shown = ", ".join(
                    f"{name} ({self.fmt(number)})"
                    for name, number in items[:8]
                )

            more = f", and {len(items) - 8} more" if len(items) > 8 else ""

            return f"{metric} by {group_column}{scope}: {shown}{more}."

        # PERCENTAGE / SHARE
        if intent == "share":

            detail = plan.get("share_detail") or {}

            phrase = noun if agg == "count" else value_label

            if isinstance(result, dict):

                shown = ", ".join(
                    f"{name} {number:.1f}%"
                    for name, number in sorted(
                        result.items(), key=lambda x: -x[1]
                    )[:8]
                )

                return (
                    f"Share of {phrase}{scope} by "
                    f"{self.label(plan['share_group'])}: {shown}."
                )

            if plan.get("ratio_denominator"):
                return (
                    f"{self.label(plan['value_column']).capitalize()} as a "
                    f"percent of {self.label(plan['ratio_denominator'])}"
                    f"{scope}: {result:.1f}% "
                    f"({self.fmt(detail.get('part'))} of "
                    f"{self.fmt(detail.get('whole'))})."
                )

            return (
                f"Share of {phrase}{scope}: {result:.1f}% "
                f"({self.fmt(detail.get('part'))} of "
                f"{self.fmt(detail.get('whole'))})."
            )

        # BEST / WEAKEST / AVERAGE MONTH
        if intent == "month_pick":

            detail = plan.get("month_detail") or {}

            note = ""

            if detail.get("left_out"):
                note = (
                    " (partly covered months left out: "
                    + ", ".join(detail["left_out"]) + ")"
                )

            if plan["pick"] == "mean":
                return (
                    f"Average monthly {value_label} is "
                    f"{self.fmt(result)}{note}."
                )

            month, number = result

            word = "weakest" if plan["pick"] == "min" else "best"

            return (
                f"The {word} month for {value_label} is {month} with "
                f"{self.fmt(number)}{note}."
            )

        # TREND
        if intent == "trend":

            return (
                f"Here is the {column} trend by month{scope} "
                f"({len(result)} months)."
            )

        return "I could not generate a response."
