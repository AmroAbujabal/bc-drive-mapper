# Waitlist FIFO Audit — Design Spec

**Goal:** Add a new page to BC Drive Mapper that lets a user upload a surgical waitlist CSV, auto-detect date columns, and produce a ranked table showing whether patients are being served in FIFO order.

**Architecture:** New Streamlit multi-page page (`pages/2_Waitlist_Audit.py`) + pure compute module (`waitlist.py`). Follows the existing `app.py` + `pipeline.py` pattern.

**Tech Stack:** Streamlit, pandas, existing project dependencies (no new packages needed)

---

## File Structure

| File | Role |
|------|------|
| `pages/2_Waitlist_Audit.py` | Streamlit UI — upload, column mapping, table display |
| `waitlist.py` | Pure compute — date parsing, metric calculation, FIFO ranking |
| `tests/test_waitlist.py` | Unit tests for compute logic |

---

## Column Auto-Detection

`waitlist.py` scans the uploaded DataFrame for date columns using two signals:

1. **Name match** — column name contains any of: `referral`, `evaluation`, `consult`, `decision`, `waitlist`, `booking`, `surgery`, `operation`
2. **Content parse** — `pd.to_datetime(col, errors="coerce")` succeeds on ≥ 80% of non-null values

The UI shows detected columns pre-populated in dropdowns. The user must confirm:
- **Waitlist date column** (required — used for FIFO ranking)
- **Surgery date column** (required — used for FIFO ranking; patients without a value are "still waiting")

All other date columns are optional and used only for pathway metric computation.

---

## Compute Logic (`waitlist.py`)

### `detect_date_columns(df) -> list[str]`
Returns column names that are likely dates using the two-signal approach above.

### `parse_dates(df, date_cols) -> pd.DataFrame`
Returns a copy of `df` with the specified columns coerced to `datetime64`.

### `compute_metrics(df, col_map) -> pd.DataFrame`
`col_map` is a dict mapping semantic role → column name (only populated roles are computed):

| Metric column | Formula | Requires |
|---------------|---------|----------|
| `referral_to_evaluation_days` | evaluation_date − referral_date | both |
| `evaluation_to_decision_days` | decision_date − evaluation_date | both |
| `decision_to_waitlist_days` | waitlist_date − decision_date | both |
| `wait_time_days` | surgery_date − waitlist_date (or booking_date) | waitlist/booking + surgery |
| `total_pathway_days` | surgery_date − referral_date | both |

Missing values (e.g. patient still waiting) produce `NaN` for that metric.

### `compute_fifo(df, waitlist_col, surgery_col) -> pd.DataFrame`
Adds three columns to `df`:

- `waitlist_rank` — rank by `waitlist_col` ascending, integers 1…N (all patients, including still-waiting)
- `surgery_rank` — rank by `surgery_col` ascending, integers 1…M for patients with a surgery date; `NaN` for still-waiting
- `deviation` — `surgery_rank − waitlist_rank` (integer; `NaN` for still-waiting)
  - 0 = perfect FIFO
  - Positive = operated later than queue position warranted (delayed)
  - Negative = operated earlier than queue position warranted (jumped queue)

---

## UI (`pages/2_Waitlist_Audit.py`)

1. **File upload** — accepts CSV
2. **Column mapping expander** — dropdowns pre-filled by `detect_date_columns()`:
   - Waitlist date (required)
   - Surgery date (required)
   - Optional: referral date, evaluation date, decision date, booking date (fallback if no waitlist date)
   - Optional: patient ID column (shown in table if present)
3. **Deviation threshold slider** — default 5 positions; rows with `|deviation| > threshold` are flagged
4. **Output table** with columns (in order):
   - patient ID (if mapped)
   - `waitlist_date`, `surgery_date`
   - `wait_time_days` (integer, `—` if still waiting)
   - `waitlist_rank`, `surgery_rank` (`—` if still waiting)
   - `deviation` (`—` if still waiting)
   - Any computed pathway metrics that have data
5. **Row colouring** via `st.dataframe` with `background_gradient` or pandas Styler:
   - `deviation > threshold` → red background
   - `deviation < -threshold` → green background
   - still-waiting rows → no colour
6. **Summary metrics** above the table:
   - Total patients, patients operated, patients still waiting
   - % with |deviation| > threshold (potential FIFO violations)
   - Median wait time
7. **Download button** — enriched CSV with all computed columns

---

## Error Handling

- No date columns detected → show warning and stop
- Waitlist or surgery column not mappable → show error and stop
- Negative pathway durations (data entry errors) → show warning, include in table with a flag column `data_quality_flag = True`

---

## Testing (`tests/test_waitlist.py`)

- `detect_date_columns` correctly identifies date columns by name and content
- `compute_fifo` with perfect FIFO data → all deviations = 0
- `compute_fifo` with known queue jump → correct negative deviation
- `compute_fifo` with still-waiting patients → `surgery_rank` and `deviation` are `NaN`
- `compute_metrics` with missing columns → skips those metrics, no error
- Negative durations → `data_quality_flag` set correctly
