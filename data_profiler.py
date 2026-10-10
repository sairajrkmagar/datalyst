import re

import pandas as pd


class DataProfiler:

    def __init__(self, df):

        self.df = df

        # Remember results so big files are not scanned again and again
        self._datetime_cache = None
        self._boolean_cache = None

    # Basic dataset information
    def basic_info(self):

        return {
            "rows": len(self.df),
            "columns": len(self.df.columns),
            "column_names": list(self.df.columns)
        }

    # Detect numeric columns
    def numeric_columns(self):

        return list(
            self.df.select_dtypes(
                include="number"
            ).columns
        )

    # Detect categorical columns
    def categorical_columns(self):

        datetime_cols = self.datetime_columns()

        return [
            column
            for column in self.df.select_dtypes(
                include=["object", "category"]
            ).columns
            if column not in datetime_cols
        ]

    # Detect datetime columns
    def datetime_columns(self):

        if self._datetime_cache is not None:
            return self._datetime_cache

        date_columns = []

        for column in self.df.columns:

            if pd.api.types.is_numeric_dtype(self.df[column]):
                continue

            # Look only at the first 1000 filled values (much faster)
            sample = self.df[column].dropna().head(1000)

            if sample.empty:
                continue

            converted = pd.to_datetime(
                sample,
                errors="coerce",
                format="mixed"
            )

            if converted.notna().mean() >= 0.8:
                date_columns.append(column)

        self._datetime_cache = date_columns

        return date_columns
    # Missing values
    def missing_values(self):

        return self.df.isnull().sum().to_dict()

    # Unique values
    def unique_counts(self):

        return self.df.nunique().to_dict()
    
    # Detailed profile of every column
    def column_profile(self):

        profile = {}

        for column in self.df.columns:

            profile[column] = {
                "dtype": str(self.df[column].dtype),
                "missing": int(self.df[column].isnull().sum()),
                "unique": int(self.df[column].nunique())
            }

            # Numeric information
            if pd.api.types.is_numeric_dtype(self.df[column]):

                profile[column]["min"] = self.df[column].min()
                profile[column]["max"] = self.df[column].max()
                profile[column]["mean"] = self.df[column].mean()

            # Categorical information
            elif column in self.categorical_columns():

                profile[column]["sample_values"] = (
                    self.df[column]
                    .dropna()
                    .unique()
                    .tolist()[:10]
                )

            # Date information
            elif column in self.datetime_columns():

                converted = pd.to_datetime(
                    self.df[column],
                    errors="coerce"
                )

                profile[column]["min_date"] = str(converted.min())
                profile[column]["max_date"] = str(converted.max())

        return profile
    
    # Detect boolean columns
    def boolean_columns(self):

        if self._boolean_cache is not None:
            return self._boolean_cache

        boolean_columns = []

        for column in self.df.columns:

            values = set(
                self.df[column]
                .dropna()
                .astype(str)
                .str.lower()
                .unique()
            )

            if values and values.issubset({"true", "false", "yes", "no", "0", "1"}):
                boolean_columns.append(column)

        self._boolean_cache = boolean_columns

        return boolean_columns
    
    # Detect identifier columns
    def identifier_columns(self):

        identifier_columns = []

        datetime_cols = self.datetime_columns()

        # "id" always means an identifier. "code" / "number" only when the
        # column has many different values (GenderCode has just 2)
        strong_id_words = {"id", "uuid", "key"}
        weak_id_words = {"code", "number", "no", "num"}

        for column in self.df.columns:

            # Never classify datetime as identifier
            if column in datetime_cols:
                continue

            series = self.df[column]

            # Decimal numbers (money, prices, weights) are never IDs
            if pd.api.types.is_float_dtype(series):
                continue

            # Name-based: a whole word like id / code / number
            # (so "paid_amount" is NOT an identifier, "customer_id" is)
            name = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(column))
            words = re.split(r"[^a-z0-9]+", name.lower())

            if any(word in strong_id_words for word in words) or (
                any(word in weak_id_words for word in words)
                and series.nunique() > 50
            ):
                identifier_columns.append(column)
                continue

            if len(self.df) <= 20 or pd.api.types.is_bool_dtype(series):
                continue

            # Numbers: only a run of consecutive whole numbers
            # (1, 2, 3, 4 ...) looks like an ID. Money amounts do not.
            if pd.api.types.is_numeric_dtype(series):

                values = series.dropna()

                if (
                    len(values) > 0
                    and values.nunique() == len(values)
                    and values.max() - values.min() + 1 == len(values)
                ):
                    identifier_columns.append(column)

                continue

            # Text: almost every row has a different value
            if series.nunique() / len(self.df) >= 0.95:
                identifier_columns.append(column)

        return identifier_columns

    # Detect business meaning of columns
    def column_semantics(self):

        semantics = {}

        for column in self.df.columns:

            name = column.lower()

            # DATE
            if column in self.datetime_columns():
                semantics[column] = "date"

            # BOOLEAN
            elif column in self.boolean_columns():
                semantics[column] = "boolean"

            # CUSTOMER
            elif any(word in name for word in [
                "customer", "client", "buyer", "user"
            ]):
                semantics[column] = "customer"

            # PRODUCT
            elif any(word in name for word in [
                "product", "item", "sku"
            ]):
                semantics[column] = "product"

            # MONEY / REVENUE
            elif any(word in name for word in [
                "sales", "revenue", "amount", "price",
                "income", "profit", "cost", "mrr", "arr"
            ]):
                semantics[column] = "monetary"

            # CATEGORY
            elif column in self.categorical_columns():
                semantics[column] = "category"

            # NUMERIC
            elif column in self.numeric_columns():
                semantics[column] = "numeric"

            else:
                semantics[column] = "unknown"

        return semantics
    
    # Create complete dataset profile
    def full_profile(self):

        return {
            "basic_info": self.basic_info(),
            "numeric_columns": self.numeric_columns(),
            "categorical_columns": self.categorical_columns(),
            "datetime_columns": self.datetime_columns(),
            "boolean_columns": self.boolean_columns(),
            "identifier_columns": self.identifier_columns(),
            "missing_values": self.missing_values(),
            "unique_counts": self.unique_counts(),
            "column_profile": self.column_profile(),
            "column_semantics": self.column_semantics()
        }