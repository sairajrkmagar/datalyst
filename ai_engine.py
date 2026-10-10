import pandas as pd

from filters import to_dates


class AIDataAnalyst:

    def __init__(self, df):
        self.df = df

    def dataset_info(self):
        return {
            "rows": len(self.df),
            "columns": len(self.df.columns),
            "column_names": self.df.columns.tolist()
        }

    def numeric_columns(self):
        return self.df.select_dtypes(include="number").columns.tolist()

    def categorical_columns(self):
        return self.df.select_dtypes(
            include=["object", "category"]
        ).columns.tolist()

    # Detect date columns
    def date_columns(self):

        date_columns = []

        for column in self.df.columns:

            # Skip numeric columns
            if pd.api.types.is_numeric_dtype(self.df[column]):
                continue

            try:
                converted = pd.to_datetime(
                    self.df[column],
                    errors="coerce",
                    format="mixed"
                )

                valid_ratio = converted.notna().mean()

                if valid_ratio > 0.8:
                    date_columns.append(column)

            except (ValueError, TypeError):
                continue

        return date_columns

    # Detect missing values
    def missing_values(self):
        return self.df.isnull().sum().to_dict()

    # Detect duplicate rows
    def duplicate_rows(self):
        return int(self.df.duplicated().sum())

    # Inspect categorical values
    def unique_values(self):

        result = {}

        for column in self.categorical_columns():
            result[column] = (
                self.df[column]
                .dropna()
                .unique()
                .tolist()
            )

        return result

    # Numeric summary
    def numeric_summary(self):
        return (
            self.df
            .select_dtypes(include="number")
            .describe()
            .to_dict()
        )

    # Correlations
    def correlations(self):
        return (
            self.df
            .select_dtypes(include="number")
            .corr()
            .to_dict()
        )

    # Group summary
    def group_summary(self, column):
        return (
            self.df
            .groupby(column)
            .sum(numeric_only=True)
            .to_dict()
        )

    # Total
    def total(self, column):
        return self.df[column].sum()

    # Average
    def average(self, column):
        return self.df[column].mean()

    # Minimum
    def minimum(self, column):
        return self.df[column].min()

    # Maximum
    def maximum(self, column):
        return self.df[column].max()

    # Count
    def count(self, column=None):

        if column is None:
            return len(self.df)

        return int(self.df[column].count())

    # Median
    def median(self, column):
        return self.df[column].median()

    # Standard deviation
    def standard_deviation(self, column):
        return self.df[column].std()

    # Sum column
    def sum_column(self, column):
        return self.df[column].sum()

    # Average column
    def average_column(self, column):
        return self.df[column].mean()

    # Maximum column
    def max_column(self, column):
        return self.df[column].max()

    # Minimum column
    def min_column(self, column):
        return self.df[column].min()

    # Count column
    def count_column(self, column):
        return self.count(column)

    # Percentage change
    def percentage_change(self, old_value, new_value):

        if old_value == 0:
            return None

        return ((new_value - old_value) / old_value) * 100

    # Group average
    def group_average(self, group_column, value_column):

        return (
            self.df
            .groupby(group_column)[value_column]
            .mean()
            .to_dict()
        )

    # Group sum
    def group_sum(self, group_column, value_column):

        return (
            self.df
            .groupby(group_column)[value_column]
            .sum()
            .to_dict()
        )

    # Group count
    def group_count(self, group_column):

        return (
            self.df
            .groupby(group_column)
            .size()
            .to_dict()
        )
    
    # Filter dataset based on a column value
    def filter_data(self, column, value):

        filtered_data = self.df[
            self.df[column].astype(str).str.lower()
            == str(value).lower()
        ]

        return filtered_data

    # Unique count
    def unique_count(self, column):
        return int(self.df[column].nunique())

    # Unique records
    def unique_records(self):
        return int(len(self.df.drop_duplicates()))

    # Duplicate count
    def duplicate_count(self):
        return int(self.df.duplicated().sum())

    # Missing count
    def missing_count(self, column=None):

        if column is None:
            return int(self.df.isnull().sum().sum())

        return int(self.df[column].isnull().sum())
    
    # Filter and sum
    def filtered_sum(self, filter_column, filter_value, value_column):

        filtered_df = self.filter_data(
            filter_column,
            filter_value
        )

        if filtered_df.empty:
            return 0

        if value_column not in filtered_df.columns:
            return None

        return filtered_df[value_column].sum()


    # Filter and average
    def filtered_average(
        self,
        filter_column,
        filter_value,
        value_column
    ):

        filtered_df = self.filter_data(
            filter_column,
            filter_value
        )

        if filtered_df.empty:
            return 0

        return filtered_df[value_column].mean()


    # Filter and maximum
    def filtered_maximum(
        self,
        filter_column,
        filter_value,
        value_column
    ):

        filtered_df = self.filter_data(
            filter_column,
            filter_value
        )

        if filtered_df.empty:
            return None

        return filtered_df[value_column].max()


    # Filter and minimum
    def filtered_minimum(
        self,
        filter_column,
        filter_value,
        value_column
    ):

        filtered_df = self.filter_data(
            filter_column,
            filter_value
        )

        if filtered_df.empty:
            return None

        return filtered_df[value_column].min()


    # Filter and count
    def filtered_count(
        self,
        filter_column,
        filter_value,
        value_column=None
    ):

        filtered_df = self.filter_data(
            filter_column,
            filter_value
        )

        if value_column is None:
            return len(filtered_df)

        return int(filtered_df[value_column].count())


    # Filter and unique count
    def filtered_unique_count(
        self,
        filter_column,
        filter_value,
        value_column
    ):

        filtered_df = self.filter_data(
            filter_column,
            filter_value
        )

        if filtered_df.empty:
            return 0

        return int(
            filtered_df[value_column].nunique()
        )


    # Filtered group sum
    def filtered_group_sum(
        self,
        filter_column,
        filter_value,
        group_column,
        value_column
    ):

        filtered_df = self.filter_data(
            filter_column,
            filter_value
        )

        if filtered_df.empty:
            return {}

        return (
            filtered_df
            .groupby(group_column)[value_column]
            .sum()
            .to_dict()
        )


    # Filtered group average
    def filtered_group_average(
        self,
        filter_column,
        filter_value,
        group_column,
        value_column
    ):

        filtered_df = self.filter_data(
            filter_column,
            filter_value
        )

        if filtered_df.empty:
            return {}

        return (
            filtered_df
            .groupby(group_column)[value_column]
            .mean()
            .to_dict()
        )


    # Filtered data
    def filtered_data(
        self,
        filter_column,
        filter_value
    ):

        return self.filter_data(
            filter_column,
            filter_value
        )
    
    # Time-series analysis
    def time_series(
        self,
        date_column,
        value_column,
        period="month"
    ):

        data = self.df.copy()

        # Convert date column (day-first dates are detected)
        data[date_column] = to_dates(data[date_column])

        # Convert value column to numeric
        data[value_column] = pd.to_numeric(
            data[value_column],
            errors="coerce"
        )

        # Remove invalid rows
        data = data.dropna(
            subset=[date_column, value_column]
        )

        # Make sure date conversion actually worked
        if data.empty:
            return None

        # Create time period
        if period == "day":

            data["time_period"] = (
                data[date_column]
                .dt
                .to_period("D")
            )

        elif period == "month":

            data["time_period"] = (
                data[date_column]
                .dt
                .to_period("M")
            )

        elif period == "year":

            data["time_period"] = (
                data[date_column]
                .dt
                .to_period("Y")
            )

        else:
            return None

        # Group ONLY the value column
        result = (
            data
            .groupby("time_period")[value_column]
            .sum()
            .to_dict()
        )

        # Convert Period keys to strings
        return {
            str(time_period): value
            for time_period, value in result.items()
        }