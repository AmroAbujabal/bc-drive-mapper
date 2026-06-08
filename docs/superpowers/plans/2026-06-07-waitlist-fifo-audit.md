# Waitlist FIFO Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Waitlist FIFO Audit" page to BC Drive Mapper that auto-detects date columns in an uploaded CSV, computes surgical pathway metrics, ranks patients by waitlist entry vs surgery order, and highlights deviations from FIFO.

**Architecture:** New `waitlist.py` pure-compute module + `pages/2_Waitlist_Audit.py` Streamlit UI page. Mirrors the existing `pipeline.py` + `app.py` pattern exactly. No new dependencies.

**Tech Stack:** Python 3.11+, pandas, Streamlit, pytest

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `waitlist.py` | All computation: date detection, parsing, metrics, FIFO ranking |
| Create | `pages/2_Waitlist_Audit.py` | Streamlit UI: upload, column mapping, table, download |
| Create | `tests/test_waitlist.py` | Unit tests for waitlist.py |

---

### Task 1: `waitlist.py` — date detection and parsing

**Files:**
- Create: `waitlist.py`
- Create: `tests/test_waitlist.py`

- [ ] **Step 1: Write failing tests for `detect_date_columns` and `parse_dates`**

Create `tests/test_waitlist.py`:

```python
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
    parse_dates(df, ["waitlist_date"])
    assert df["waitlist_date"].dtype == object

def test_parse_dates_coerces_bad_values_to_nat():
    df = pd.DataFrame({"d": ["2024-01-01", "not-a-date"]})
    result = parse_dates(df, ["d"])
    assert pd.isna(result.loc[1, "d"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/amrabujabal/bc-drive-mapper
pytest tests/test_waitlist.py -v
```

Expected: `ModuleNotFoundError: No module named 'waitlist'`

- [ ] **Step 3: Create `waitlist.py` with `detect_date_columns` and `parse_dates`**

Create `waitlist.py`:

```python
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
    if ≥ 80% of its non-null values parse as dates.
    """
    detected = []
    for col in df.columns:
        if _DATE_NAME_RE.search(col):
            detected.append(col)
            continue
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        parsed = pd.to_datetime(non_null, errors="coerce")
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
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_waitlist.py -v -k "detect or parse"
```

Expected: 8 PASSED

- [ ] **Step 5: Commit**

```bash
git add waitlist.py tests/test_waitlist.py
git commit -m "feat: waitlist — detect_date_columns and parse_dates"
```

---

### Task 2: `waitlist.py` — FIFO ranking (`compute_fifo`)

**Files:**
- Modify: `waitlist.py` (append `compute_fifo`)
- Modify: `tests/test_waitlist.py` (append tests)

- [ ] **Step 1: Append failing tests for `compute_fifo`**

Add to the bottom of `tests/test_waitlist.py`:

```python
from waitlist import compute_fifo


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_waitlist.py -v -k "fifo"
```

Expected: `ImportError: cannot import name 'compute_fifo' from 'waitlist'`

- [ ] **Step 3: Implement `compute_fifo` in `waitlist.py`**

Append to `waitlist.py`:

```python

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_waitlist.py -v -k "fifo"
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add waitlist.py tests/test_waitlist.py
git commit -m "feat: waitlist — compute_fifo with FIFO deviation ranking"
```

---

### Task 3: `waitlist.py` — pathway metrics (`compute_metrics`)

**Files:**
- Modify: `waitlist.py` (append `compute_metrics`)
- Modify: `tests/test_waitlist.py` (append tests)

- [ ] **Step 1: Append failing tests for `compute_metrics`**

Add to the bottom of `tests/test_waitlist.py`:

```python
from waitlist import compute_metrics


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_waitlist.py -v -k "metrics"
```

Expected: `ImportError: cannot import name 'compute_metrics' from 'waitlist'`

- [ ] **Step 3: Implement `compute_metrics` in `waitlist.py`**

Append to `waitlist.py`:

```python

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
    _diff("referral", "surgery", "total_pathway_days")

    # wait_time_days: surgery minus waitlist (fallback to booking)
    waitlist_src = col_map.get("waitlist") or col_map.get("booking")
    if waitlist_src and "surgery" in col_map:
        delta = (df[col_map["surgery"]] - df[waitlist_src]).dt.days
        df["wait_time_days"] = delta
        quality_flags[delta.notna() & (delta < 0)] = True

    if quality_flags.any():
        df["data_quality_flag"] = quality_flags

    return df
```

- [ ] **Step 4: Run all waitlist tests**

```bash
pytest tests/test_waitlist.py -v
```

Expected: all tests PASSED (8 from Task 1 + 5 from Task 2 + 6 from Task 3 = 19 PASSED)

- [ ] **Step 5: Commit**

```bash
git add waitlist.py tests/test_waitlist.py
git commit -m "feat: waitlist — compute_metrics with pathway durations and quality flagging"
```

---

### Task 4: `pages/2_Waitlist_Audit.py` — Streamlit UI

**Files:**
- Create: `pages/2_Waitlist_Audit.py`

No unit tests for the UI (Streamlit pages are tested by running the app). Manually verify after writing.

- [ ] **Step 1: Create `pages/` directory and `pages/2_Waitlist_Audit.py`**

```bash
mkdir -p pages
```

Create `pages/2_Waitlist_Audit.py`:

```python
"""
Waitlist FIFO Audit — Streamlit page.

Lets the user upload a surgical waitlist CSV, auto-detects date columns,
computes pathway metrics and FIFO deviation, and shows a ranked table.
"""
import io
import pandas as pd
import streamlit as st

import waitlist as wl

st.set_page_config(
    page_title="Waitlist FIFO Audit",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 Waitlist FIFO Audit")
st.caption(
    "Upload a surgical waitlist CSV to check whether patients are served in FIFO order."
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuration")
    deviation_threshold = st.slider(
        "Deviation threshold (positions)",
        min_value=1,
        max_value=20,
        value=5,
        help="Rows where |deviation| > this are flagged as potential FIFO violations.",
    )

# ── Upload ────────────────────────────────────────────────────────────────────
uploaded = st.file_uploader("Upload waitlist CSV", type=["csv"])
if uploaded is None:
    st.info("Upload a CSV to get started.")
    st.stop()


@st.cache_data(show_spinner=False)
def _load(file_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(file_bytes))


raw_df = _load(uploaded.getvalue())
st.write(f"**{len(raw_df):,} rows loaded.** Preview:")
st.dataframe(raw_df.head(5), use_container_width=True)

cols = list(raw_df.columns)
detected = wl.detect_date_columns(raw_df)

if not detected:
    st.warning(
        "No date columns detected. Make sure your CSV has columns with date values "
        "or names containing: referral, evaluation, decision, waitlist, surgery, etc."
    )
    st.stop()


# ── Column mapping ────────────────────────────────────────────────────────────
def _best_match(keywords: list[str]) -> int:
    """Return the cols index of the first detected column whose name contains a keyword."""
    for kw in keywords:
        for c in detected:
            if kw in c.lower():
                return cols.index(c)
    return 0


with st.expander("Column mapping", expanded=True):
    waitlist_col = st.selectbox(
        "Waitlist date column (required)",
        options=cols,
        index=_best_match(["waitlist", "booking"]),
    )
    surgery_col = st.selectbox(
        "Surgery date column (required)",
        options=cols,
        index=_best_match(["surgery", "operation"]),
    )

    opt = ["(none)"] + cols

    def _opt_idx(keywords: list[str]) -> int:
        for kw in keywords:
            for c in detected:
                if kw in c.lower():
                    return opt.index(c)
        return 0

    referral_raw = st.selectbox(
        "Referral date (optional)", options=opt, index=_opt_idx(["referral"])
    )
    evaluation_raw = st.selectbox(
        "Evaluation / consult date (optional)",
        options=opt,
        index=_opt_idx(["evaluation", "consult"]),
    )
    decision_raw = st.selectbox(
        "Decision date (optional)", options=opt, index=_opt_idx(["decision"])
    )
    # Patient ID is never a date column, so search all cols not just detected
    id_default = next(
        (i + 1 for i, c in enumerate(cols) if any(kw in c.lower() for kw in ["patient_id", "_id", "patient"])),
        0,
    )
    id_raw = st.selectbox(
        "Patient ID column (optional)",
        options=opt,
        index=id_default,
    )

# ── Compute ───────────────────────────────────────────────────────────────────
col_map: dict[str, str] = {"waitlist": waitlist_col, "surgery": surgery_col}
if referral_raw != "(none)":
    col_map["referral"] = referral_raw
if evaluation_raw != "(none)":
    col_map["evaluation"] = evaluation_raw
if decision_raw != "(none)":
    col_map["decision"] = decision_raw

date_cols_to_parse = list(set(col_map.values()))
parsed_df = wl.parse_dates(raw_df, date_cols_to_parse)
enriched = wl.compute_metrics(parsed_df, col_map)
enriched = wl.compute_fifo(enriched, waitlist_col, surgery_col)

# ── Summary metrics ───────────────────────────────────────────────────────────
total = len(enriched)
operated = enriched[surgery_col].notna().sum()
waiting = total - operated
has_dev = enriched["deviation"].notna()
violations = int((enriched.loc[has_dev, "deviation"].abs() > deviation_threshold).sum())
pct_violations = violations / operated * 100 if operated > 0 else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total patients", f"{total:,}")
c2.metric("Operated", f"{operated:,}")
c3.metric("Still waiting", f"{waiting:,}")
c4.metric(
    "FIFO violations",
    f"{violations:,}",
    delta=f"{pct_violations:.1f}% of operated" if operated > 0 else None,
    delta_color="inverse",
    help=f"|deviation| > {deviation_threshold} positions",
)

if "wait_time_days" in enriched.columns:
    med = enriched["wait_time_days"].median()
    st.metric("Median wait time", f"{int(med):,} days" if pd.notna(med) else "N/A")

if "data_quality_flag" in enriched.columns:
    bad = int(enriched["data_quality_flag"].sum())
    st.warning(
        f"{bad} row(s) have negative durations (surgery/evaluation date before an earlier date). "
        "These are marked with `data_quality_flag = True` in the table."
    )

st.markdown("---")

# ── Table ─────────────────────────────────────────────────────────────────────
display_cols = []
if id_raw != "(none)":
    display_cols.append(id_raw)
display_cols += [waitlist_col, surgery_col]
for c in [
    "wait_time_days",
    "waitlist_rank",
    "surgery_rank",
    "deviation",
    "referral_to_evaluation_days",
    "evaluation_to_decision_days",
    "decision_to_waitlist_days",
    "total_pathway_days",
    "data_quality_flag",
]:
    if c in enriched.columns:
        display_cols.append(c)

display_df = enriched[display_cols].copy()


def _highlight_row(row: pd.Series) -> list[str]:
    dev = row.get("deviation", pd.NA)
    if pd.isna(dev):
        return [""] * len(row)
    if dev > deviation_threshold:
        return ["background-color: #FFCCCC"] * len(row)
    if dev < -deviation_threshold:
        return ["background-color: #CCFFCC"] * len(row)
    return [""] * len(row)


styled = display_df.style.apply(_highlight_row, axis=1)

st.subheader("FIFO Audit Table")
st.caption(
    "Red rows: operated later than queue position warranted. "
    "Green rows: operated earlier (jumped queue). "
    "No colour: within threshold or still waiting."
)
st.dataframe(styled, use_container_width=True, height=500)

# ── Download ──────────────────────────────────────────────────────────────────
csv_bytes = display_df.to_csv(index=False).encode()
st.download_button(
    label="⬇️ Download enriched CSV",
    data=csv_bytes,
    file_name="waitlist_fifo_audit.csv",
    mime="text/csv",
)
```

- [ ] **Step 2: Run all tests to confirm nothing broke**

```bash
pytest tests/ -v
```

Expected: all previous tests PASS (19 from test_waitlist.py + existing tests)

- [ ] **Step 3: Run the app and verify manually**

```bash
streamlit run app.py
```

- Navigate to "2 Waitlist Audit" in the sidebar
- Upload `sample_patients.csv` (has `address`, `postcode`, `reported_km`, `reported_drive_hours` — no date columns, so the "no date columns" warning should appear — this is correct behaviour)
- Create a quick test file to verify the happy path:

```bash
python - <<'EOF'
import pandas as pd
df = pd.DataFrame({
    "patient_id": [1, 2, 3, 4, 5],
    "waitlist_date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
    "surgery_date": ["2024-06-01", "2024-06-05", "2024-06-03", None, "2024-06-02"],
    "referral_date": ["2023-10-01", "2023-10-15", "2023-11-01", "2023-11-15", "2023-12-01"],
})
df.to_csv("/tmp/test_waitlist.csv", index=False)
print("Saved /tmp/test_waitlist.csv")
EOF
```

- Upload `/tmp/test_waitlist.csv` — verify:
  - 5 total, 4 operated, 1 still waiting
  - Patient 4 (waitlist rank 4) has no surgery rank or deviation
  - Patient 5 (waitlist rank 5, surgery rank 1) has deviation = -4 (jumped queue) → green row
  - Deviation threshold slider adjusts highlighting

- [ ] **Step 4: Commit**

```bash
git add pages/2_Waitlist_Audit.py
git commit -m "feat: waitlist FIFO audit — Streamlit page with column mapping, ranked table, deviation highlighting"
```

- [ ] **Step 5: Push to GitHub**

```bash
git push
```

Streamlit Cloud will auto-redeploy. The new page appears in the sidebar automatically.
