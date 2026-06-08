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
    Numeric columns are excluded regardless of name, to avoid false positives
    on columns like waitlist_score or patient_priority.
    Raises no error if the DataFrame already contains columns named waitlist_rank,
    surgery_rank, or deviation — they will be overwritten.
    """
    detected = []
    for col in df.columns:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        # Skip numeric columns regardless of name — avoids false positives
        # on score/priority columns that happen to have surgical-pathway keywords
        if pd.api.types.is_numeric_dtype(non_null):
            continue
        if _DATE_NAME_RE.search(col):
            detected.append(col)
            continue
        parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
        # Also reject columns where parsed years are outside a plausible clinical range
        # (catches string ID columns like ['1001','1002'] that parse as year 1001, etc.)
        valid = parsed.dropna()
        if len(valid) == 0:
            continue
        if (valid.dt.year < 1900).any() or (valid.dt.year > 2100).any():
            continue
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


def compute_metrics(df: pd.DataFrame, col_map: dict[str, str]) -> pd.DataFrame:
    """
    Compute available pathway duration metrics based on col_map.

    col_map keys (all optional except at least one pair must be present):
        "referral", "evaluation", "decision", "waitlist", "booking", "surgery"

    Added columns (only when both required inputs are present):
        referral_to_evaluation_days, evaluation_to_decision_days,
        decision_to_waitlist_days, wait_time_days, total_pathway_days

    If any computed duration is negative, adds data_quality_flag = True for that row.
    The data_quality_flag column is omitted entirely when no negatives are found.
    """
    df = df.copy()
    quality_flags = pd.Series(False, index=df.index)

    def _diff(from_key: str, to_key: str, out_col: str) -> None:
        if from_key not in col_map or to_key not in col_map:
            return
        delta = (df[col_map[to_key]] - df[col_map[from_key]]).dt.days
        df[out_col] = delta
        quality_flags[delta.notna() & (delta < 0)] = True

    _diff("referral", "evaluation", "referral_to_evaluation_days")
    _diff("evaluation", "decision", "evaluation_to_decision_days")
    _diff("decision", "waitlist", "decision_to_waitlist_days")

    # wait_time_days: surgery minus waitlist (fallback to booking)
    waitlist_src = col_map.get("waitlist") or col_map.get("booking")
    if waitlist_src and "surgery" in col_map:
        delta = (df[col_map["surgery"]] - df[waitlist_src]).dt.days
        df["wait_time_days"] = delta
        quality_flags[delta.notna() & (delta < 0)] = True

    _diff("referral", "surgery", "total_pathway_days")

    if quality_flags.any():
        df["data_quality_flag"] = quality_flags

    return df
