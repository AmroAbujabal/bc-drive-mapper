"""
Waitlist FIFO Audit — compute module.

No Streamlit imports. All functions are pure: they take DataFrames and return DataFrames.
"""
import re
import pandas as pd

_DATE_NAME_RE = re.compile(
    r"referral|evaluation|consult|decision|waitlist|booking|surgery|operation",
    re.IGNORECASE,
)
_DETECT_THRESHOLD = 0.80  # fraction of non-null values that must parse as dates


def detect_date_columns(df: pd.DataFrame) -> list[str]:
    """
    Return column names that are likely to contain dates.

    A column qualifies if its name matches a surgical-pathway keyword OR
    if ≥ 80% of its non-null values parse as dates (and are not numeric).
    """
    detected = []
    for col in df.columns:
        if _DATE_NAME_RE.search(col):
            detected.append(col)
            continue
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        # Skip purely numeric columns
        if pd.api.types.is_numeric_dtype(non_null):
            continue
        parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
        if parsed.notna().sum() / len(non_null) >= _DETECT_THRESHOLD:
            detected.append(col)
    return detected


def parse_dates(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    """
    Return a copy of df with the specified columns coerced to datetime64.
    Unparseable values become NaT.
    """
    df = df.copy()
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
    return df
