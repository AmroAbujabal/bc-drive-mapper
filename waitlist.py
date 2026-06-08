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


def compute_fifo(
    df: pd.DataFrame,
    waitlist_col: str,
    surgery_col: str,
) -> pd.DataFrame:
    """
    Add waitlist_rank, surgery_rank, and deviation columns.

    waitlist_rank: all patients ranked by waitlist date (1 = earliest, ties get min rank)
    surgery_rank:  patients WITH a surgery date ranked by surgery date (1 = first operated)
                   still-waiting patients get pd.NA
    deviation:     surgery_rank - waitlist_rank (0 = FIFO, positive = delayed, negative = jumped)
                   still-waiting patients get pd.NA

    Raises no error if the DataFrame already contains columns named waitlist_rank,
    surgery_rank, or deviation — they will be overwritten.
    """
    df = df.copy()

    df["waitlist_rank"] = (
        df[waitlist_col].rank(method="min", ascending=True, na_option="keep")
        .astype("Int64")
    )

    has_surgery = df[surgery_col].notna()
    df["surgery_rank"] = pd.array([pd.NA] * len(df), dtype="Int64")
    if has_surgery.any():
        ranks = df.loc[has_surgery, surgery_col].rank(method="min", ascending=True)
        df.loc[has_surgery, "surgery_rank"] = ranks.astype("Int64")

    df["deviation"] = pd.array([pd.NA] * len(df), dtype="Int64")
    if has_surgery.any():
        df.loc[has_surgery, "deviation"] = (
            df.loc[has_surgery, "surgery_rank"] - df.loc[has_surgery, "waitlist_rank"]
        )

    return df
