import pandas as pd
from waitlist import detect_date_columns, parse_dates, compute_fifo


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


# ── compute_fifo ──────────────────────────────────────────────────────────────


def test_perfect_fifo_all_deviations_zero():
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        "sx": pd.to_datetime(["2024-06-01", "2024-06-02", "2024-06-03"]),
    })
    result = compute_fifo(df, "wl", "sx")
    assert list(result["deviation"]) == [0, 0, 0]

def test_queue_jump_detected():
    # Patient 0 waited longer → positive deviation; patient 1 jumped → negative
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "sx": pd.to_datetime(["2024-06-02", "2024-06-01"]),  # order swapped
    })
    result = compute_fifo(df, "wl", "sx")
    assert result.loc[0, "deviation"] == 1
    assert result.loc[1, "deviation"] == -1

def test_still_waiting_patient_has_null_surgery_rank_and_deviation():
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "sx": [pd.NaT, pd.Timestamp("2024-06-01")],
    })
    result = compute_fifo(df, "wl", "sx")
    assert pd.isna(result.loc[0, "surgery_rank"])
    assert pd.isna(result.loc[0, "deviation"])

def test_all_still_waiting_no_surgery_ranks():
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "sx": [pd.NaT, pd.NaT],
    })
    result = compute_fifo(df, "wl", "sx")
    assert result["surgery_rank"].isna().all()
    assert result["deviation"].isna().all()

def test_waitlist_rank_assigned_to_all_patients():
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-02"]),
        "sx": [pd.NaT, pd.Timestamp("2024-06-01"), pd.Timestamp("2024-07-01")],
    })
    result = compute_fifo(df, "wl", "sx")
    # waitlist_rank should be 3, 1, 2 (by wl date order)
    assert result.loc[0, "waitlist_rank"] == 3
    assert result.loc[1, "waitlist_rank"] == 1
    assert result.loc[2, "waitlist_rank"] == 2
