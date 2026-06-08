import pandas as pd
from waitlist import detect_date_columns, parse_dates, compute_fifo, compute_metrics


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

def test_tied_waitlist_dates_use_min_rank_with_gap():
    # Two patients joined on the same day → both get waitlist_rank = 1.
    # The next patient gets waitlist_rank = 3 (not 2) because method="min" creates a gap.
    # This means their deviation reflects the gap: if operated first, deviation = 1 - 3 = -2.
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"]),
        "sx": pd.to_datetime(["2024-06-02", "2024-06-03", "2024-06-01"]),
    })
    result = compute_fifo(df, "wl", "sx")
    # Patients 0 and 1 share waitlist_rank = 1 (tied)
    assert result.loc[0, "waitlist_rank"] == 1
    assert result.loc[1, "waitlist_rank"] == 1
    # Patient 2 gets waitlist_rank = 3 (gap due to tie cluster of size 2)
    assert result.loc[2, "waitlist_rank"] == 3
    # Patient 2 operated first (surgery_rank = 1), deviation = 1 - 3 = -2
    assert result.loc[2, "deviation"] == -2


# ── compute_metrics ───────────────────────────────────────────────────────────

def test_wait_time_days_computed():
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-01"]),
        "sx": pd.to_datetime(["2024-04-10"]),  # 100 days later
    })
    result = compute_metrics(df, {"waitlist": "wl", "surgery": "sx"})
    assert result.loc[0, "wait_time_days"] == 100

def test_total_pathway_days_computed():
    df = pd.DataFrame({
        "ref": pd.to_datetime(["2024-01-01"]),
        "sx": pd.to_datetime(["2024-07-19"]),  # 200 days later
    })
    result = compute_metrics(df, {"referral": "ref", "surgery": "sx"})
    assert result.loc[0, "total_pathway_days"] == 200

def test_missing_column_pair_skipped_no_error():
    # No referral column — referral_to_evaluation_days must not appear
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-01"]),
        "sx": pd.to_datetime(["2024-04-10"]),
    })
    result = compute_metrics(df, {"waitlist": "wl", "surgery": "sx"})
    assert "referral_to_evaluation_days" not in result.columns

def test_negative_duration_sets_data_quality_flag():
    # Surgery date before waitlist date — bad data
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-06-01"]),
        "sx": pd.to_datetime(["2024-01-01"]),
    })
    result = compute_metrics(df, {"waitlist": "wl", "surgery": "sx"})
    assert "data_quality_flag" in result.columns
    assert bool(result.loc[0, "data_quality_flag"]) is True

def test_no_negative_durations_no_flag_column():
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-01"]),
        "sx": pd.to_datetime(["2024-06-01"]),
    })
    result = compute_metrics(df, {"waitlist": "wl", "surgery": "sx"})
    assert "data_quality_flag" not in result.columns

def test_still_waiting_produces_nan_wait_time():
    df = pd.DataFrame({
        "wl": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "sx": [pd.NaT, pd.Timestamp("2024-06-01")],
    })
    result = compute_metrics(df, {"waitlist": "wl", "surgery": "sx"})
    assert pd.isna(result.loc[0, "wait_time_days"])
    assert result.loc[1, "wait_time_days"] == 151
