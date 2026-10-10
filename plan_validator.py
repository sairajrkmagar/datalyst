class PlanValidator:

    def __init__(self, profile):

        self.profile = profile

    def validate(self, plan):

        # --------------------------------
        # PLAN MUST BE DICTIONARY
        # --------------------------------

        if not isinstance(plan, dict):
            return None

        columns = self.profile["basic_info"]["column_names"]

        # --------------------------------
        # GET VALUES
        # --------------------------------

        intent = plan.get("intent")
        column = plan.get("column")
        group_column = plan.get("group_column")
        value_column = plan.get("value_column")
        filter_value = plan.get("filter_value")
        operation = plan.get("operation")

        # --------------------------------
        # REJECT STRING "NULL"
        # --------------------------------

        for key in [
            "column",
            "group_column",
            "value_column",
            "filter_value"
        ]:

            if plan.get(key) in ["null", "None", "NULL"]:

                plan[key] = None

        # Refresh values after repair

        column = plan.get("column")
        group_column = plan.get("group_column")
        value_column = plan.get("value_column")
        filter_value = plan.get("filter_value")

        # --------------------------------
        # VALID INTENTS
        # --------------------------------

        valid_intents = [
            "total",
            "average",
            "maximum",
            "minimum",
            "count",
            "unique",
            "top",
            "bottom",
            "trend",
            "duplicate",
            "missing",
            "breakdown",
            "share",
            "month_pick"
        ]

        if intent not in valid_intents:
            return None

        # --------------------------------
        # CHECK COLUMNS
        # --------------------------------

        for col in [
            column,
            group_column,
            value_column
        ]:

            if col is not None and col not in columns:
                return None

        # --------------------------------
        # NUMERICAL ANALYSIS
        # --------------------------------

        if intent in [
            "total",
            "average",
            "maximum",
            "minimum",
            "top",
            "bottom",
            "trend"
        ]:

            # a ranking by number of orders needs no number column
            if value_column is None and plan.get("agg") != "count":
                return None

        # --------------------------------
        # NEW QUESTION TYPES (decided by code)
        # --------------------------------

        if intent == "breakdown":

            if group_column is None:
                return None

            if value_column is None and plan.get("agg") != "count":
                return None

        if intent == "month_pick":

            if value_column is None or group_column is None:
                return None

        if intent == "share":

            if value_column is None and plan.get("agg") == "sum":
                return None

        # --------------------------------
        # TOP / BOTTOM
        # --------------------------------

        if intent in ["top", "bottom"]:

            if group_column is None:
                return None

            if operation != "group_sum":
                plan["operation"] = "group_sum"

        # --------------------------------
        # TREND
        # --------------------------------

        if intent == "trend":

            if group_column is None:
                return None

            if operation != "time_series":
                plan["operation"] = "time_series"

        # --------------------------------
        # DUPLICATE
        # --------------------------------

        if intent == "duplicate":

            plan["column"] = None
            plan["group_column"] = None
            plan["value_column"] = None
            plan["filter_value"] = None
            plan["operation"] = "duplicate_count"
        # --------------------------------
        # MISSING
        # --------------------------------

        if intent == "missing":

            # "missing values in rating": keep the column the plan names
            plan["column"] = column if column in columns else None
            plan["group_column"] = None
            plan["value_column"] = None
            plan["filter_value"] = None
            plan["operation"] = "missing_count"
        # --------------------------------
        # COUNT
        # --------------------------------

        if intent == "count":

            # Row count
            if operation == "row_count":

                plan["column"] = None
                plan["group_column"] = None
                plan["value_column"] = None
                plan["filter_value"] = None
                plan["operation"] = "row_count"

            # Column count
            else:

                if column is None:
                    return None

                plan["value_column"] = column
                plan["operation"] = "count"

        # --------------------------------
        # UNIQUE
        # --------------------------------

        if intent == "unique":

            if column is None:
                return None

            plan["value_column"] = column
            plan["operation"] = "unique"

        # --------------------------------
        # RETURN VALIDATED PLAN
        # --------------------------------

        return plan