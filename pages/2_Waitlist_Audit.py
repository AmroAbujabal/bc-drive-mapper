"""
Waitlist FIFO Audit — Streamlit page.

Lets the user upload a surgical waitlist CSV, auto-detects date columns,
computes pathway metrics and FIFO deviation, and shows a ranked table.
"""
import io
import pandas as pd
import streamlit as st

import waitlist as wl

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
    # Fall back to the first date-detected column, not cols[0]
    return cols.index(detected[0]) if detected else 0


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

if waitlist_col == surgery_col:
    st.error("Waitlist date column and Surgery date column must be different.")
    st.stop()

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
    st.metric("Median wait time", f"{round(med):,} days" if pd.notna(med) else "N/A")

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


def _status(dev) -> str:
    if pd.isna(dev):
        return ""
    if dev > deviation_threshold:
        return "⚠ Delayed"
    if dev < -deviation_threshold:
        return "✓ Early"
    return ""


display_df.insert(0, "Status", display_df.get("deviation", pd.NA).apply(_status))

_day_cols = [
    "wait_time_days",
    "referral_to_evaluation_days",
    "evaluation_to_decision_days",
    "decision_to_waitlist_days",
    "total_pathway_days",
]
_date_cols = [c for c in [waitlist_col, surgery_col] if c in display_df.columns]

_fmt = {c: "{:.0f}" for c in _day_cols if c in display_df.columns}
_fmt.update({c: lambda v: v.strftime("%Y-%m-%d") if pd.notna(v) else "" for c in _date_cols})

styled = display_df.style.format(_fmt, na_rep="")

st.subheader("FIFO Audit Table")
st.caption(
    "⚠ Delayed: operated later than queue position warranted. "
    "✓ Early: operated earlier (jumped queue). "
    "Blank: within threshold or still waiting."
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

st.markdown("---")
st.markdown("## 🏥 Drive Time Analysis")
st.markdown("Map driving distance and time from patient addresses to a hospital focal point.")
st.page_link("drive_time.py", label="← Back to Drive Time Analysis", icon="🏥")
