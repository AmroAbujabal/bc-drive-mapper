import pandas as pd
import pytest
from waitlist import detect_date_columns, parse_dates


# ── detect_date_columns ────────────────────────────────────────────────────────

def test_detect_by_name_waitlist():
    df = pd.DataFrame({"waitlist_date": ["2024-01-01"], "score": [5]})
    assert "waitlist_date" in detect_date_columns(df)

def test_detect_by_name_surgery():
    df = pd.DataFrame({"surgery_date": ["2024-06-01"], "name": ["Alice"]})
    assert "surgery_date" in detect_date_columns(df)

def test_detect_by_content_parseable():
    df = pd.DataFrame({"when": ["2024-01-01", "2024-02-01", "2024-03-01", None]})
    assert "when" in detect_date_columns(df)

def test_detect_non_date_excluded():
    df = pd.DataFrame({"name": ["Alice", "Bob"], "score": [1, 2]})
    assert detect_date_columns(df) == []

def test_detect_mostly_unparseable_excluded():
    # Only 1/4 values parse as dates — below 80% threshold
    df = pd.DataFrame({"mixed": ["2024-01-01", "hello", "world", "foo"]})
    assert "mixed" not in detect_date_columns(df)


# ── parse_dates ────────────────────────────────────────────────────────────────

def test_parse_dates_converts_strings():
    df = pd.DataFrame({"waitlist_date": ["2024-01-01", "2024-02-01"]})
    result = parse_dates(df, ["waitlist_date"])
    assert pd.api.types.is_datetime64_any_dtype(result["waitlist_date"])

def test_parse_dates_does_not_mutate_original():
    df = pd.DataFrame({"waitlist_date": ["2024-01-01"]})
    original_dtype = df["waitlist_date"].dtype
    parse_dates(df, ["waitlist_date"])
    assert df["waitlist_date"].dtype == original_dtype
    assert not pd.api.types.is_datetime64_any_dtype(df["waitlist_date"])

def test_parse_dates_coerces_bad_values_to_nat():
    df = pd.DataFrame({"d": ["2024-01-01", "not-a-date"]})
    result = parse_dates(df, ["d"])
    assert pd.isna(result.loc[1, "d"])
