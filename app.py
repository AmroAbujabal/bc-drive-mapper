"""
BC Drive Mapper — Streamlit UI

Calls geocoder/router/pipeline for processing; calls charts for rendering.
No business logic lives here.
"""
import io
import re
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import pipeline
import charts

st.set_page_config(
    page_title="BC Drive Mapper",
    page_icon="🏥",
    layout="wide",
)

DEFAULT_HOSPITAL_LATLON = "49.2404, -123.1189"
DEFAULT_HOSPITAL_ADDRESS = "4480 Oak St, Vancouver, BC"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuration")

    osrm_base = st.text_input(
        "OSRM Base URL",
        value="https://router.project-osrm.org",
        help="Change to http://localhost:5000 for a self-hosted OSRM instance.",
    )

    st.markdown("---")
    focal_mode = st.radio("Focal point input", ["Lat / Lon", "Address"])
    focal_input = (
        st.text_input("Lat, Lon", value=DEFAULT_HOSPITAL_LATLON)
        if focal_mode == "Lat / Lon"
        else st.text_input("Address", value=DEFAULT_HOSPITAL_ADDRESS)
    )

    st.markdown("---")
    score_threshold = st.slider(
        "Low-confidence score threshold", min_value=0, max_value=100, value=70,
        help="Geocode scores below this are flagged as low-confidence.",
    )
    bin_size = st.slider("Histogram bin size (min)", min_value=5, max_value=60, value=15, step=5)

    st.markdown("---")
    if st.button("🗑️ Clear cached results"):
        if pipeline.CACHE_FILE.exists():
            pipeline.CACHE_FILE.unlink()
        st.session_state.pop("enriched_df", None)
        st.success("Cache cleared.")

# ── Main area ─────────────────────────────────────────────────────────────────
st.title("🏥 BC Drive Mapper — Drive Time Analysis")
st.caption("Maps driving distance and time from BC patient addresses to a focal point (default: BC Children's Hospital).")

uploaded = st.file_uploader("Upload patient CSV", type=["csv"])
if uploaded is None:
    st.info("Upload a CSV to get started.")
    st.stop()


@st.cache_data(show_spinner=False)
def load_csv(file_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(file_bytes))


raw_df = load_csv(uploaded.getvalue())
st.write(f"**{len(raw_df):,} rows loaded.** Preview:")
st.dataframe(raw_df.head(5), use_container_width=True)


def _detect_col(cols: list, patterns: list) -> str | None:
    for col in cols:
        for p in patterns:
            if re.search(p, col, re.IGNORECASE):
                return col
    return None


cols = list(raw_df.columns)
detected_addr = _detect_col(cols, [r"address", r"addr", r"street"])
detected_pc = _detect_col(cols, [r"post.?code", r"postal", r"zip"])
detected_out = _detect_col(cols, [r"outcome", r"quality", r"score"])

with st.expander("Column mapping", expanded=(detected_addr is None or detected_pc is None)):
    addr_col = st.selectbox(
        "Address column", options=cols,
        index=cols.index(detected_addr) if detected_addr in cols else 0,
    )
    pc_col = st.selectbox(
        "Postcode column", options=cols,
        index=cols.index(detected_pc) if detected_pc in cols else 0,
    )
    numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(raw_df[c])]
    outcome_options = ["(none)"] + numeric_cols
    default_out_idx = outcome_options.index(detected_out) if detected_out in outcome_options else 0
    outcome_col_raw = st.selectbox("Outcome / quality column (optional)", options=outcome_options, index=default_out_idx)
    outcome_col = None if outcome_col_raw == "(none)" else outcome_col_raw

# ── Focal point ───────────────────────────────────────────────────────────────
try:
    focal_lat, focal_lon = pipeline.geocode_focal_point(focal_input)
    st.sidebar.success(f"Focal point: {focal_lat:.5f}, {focal_lon:.5f}")
except ValueError as e:
    st.sidebar.error(str(e))
    st.stop()

# ── Process / load cache ──────────────────────────────────────────────────────
cached_df = st.session_state["enriched_df"] if "enriched_df" in st.session_state else pipeline.load_cache()

if cached_df is None:
    if st.button("▶ Process — Geocode + Route", type="primary"):
        geocode_bar = st.progress(0, text="Geocoding addresses…")
        route_bar = st.progress(0, text="Routing…")

        def geocode_progress(done, total):
            geocode_bar.progress(done / total, text=f"Geocoding {done}/{total}…")

        def route_progress(done, total):
            route_bar.progress(done / total, text=f"Routing {done}/{total}…")

        try:
            enriched = pipeline.run(
                raw_df, addr_col=addr_col, pc_col=pc_col,
                focal_lat=focal_lat, focal_lon=focal_lon,
                osrm_base=osrm_base,
                geocode_progress=geocode_progress,
                route_progress=route_progress,
            )
            pipeline.save_cache(enriched)
            st.session_state["enriched_df"] = enriched
            geocode_bar.empty()
            route_bar.empty()
            st.success("Processing complete!")
            st.rerun()
        except Exception as exc:
            st.error(f"Processing failed: {exc}")
    st.stop()
else:
    st.session_state["enriched_df"] = cached_df

enriched_df = st.session_state["enriched_df"]

# ── Metric cards ──────────────────────────────────────────────────────────────
def _fmt_time(mins) -> str:
    if not pd.notna(mins):
        return "N/A"
    m = int(round(mins))
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60} min"

total = len(enriched_df)
geocoded_ok = enriched_df["lat"].notna().sum()
low_conf = ((enriched_df["score"] < score_threshold) & enriched_df["lat"].notna()).sum()
med_time = enriched_df["drive_time_min"].median()
mean_time = enriched_df["drive_time_min"].mean()
max_time = enriched_df["drive_time_min"].max()
med_dist = enriched_df["drive_distance_km"].median()

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric("Total rows", f"{total:,}")
c2.metric("Geocoded OK", f"{geocoded_ok:,}")
c3.metric("Low confidence", f"{low_conf:,}")
c4.metric("Median time", _fmt_time(med_time))
c5.metric("Mean time", _fmt_time(mean_time))
c6.metric("Max time", _fmt_time(max_time))
c7.metric("Median distance", f"{med_dist:.0f} km" if pd.notna(med_dist) else "N/A")

st.markdown("---")

# ── Map ───────────────────────────────────────────────────────────────────────
st.subheader("Patient Map")
m = charts.make_map(enriched_df, focal_lat=focal_lat, focal_lon=focal_lon, score_threshold=score_threshold)
st_folium(m, use_container_width=True, height=500, returned_objects=[])

st.markdown("---")

# ── Histogram + time-band bar ─────────────────────────────────────────────────
col_h, col_b = st.columns(2)
with col_h:
    st.subheader("Drive Time Distribution")
    st.plotly_chart(charts.make_histogram(enriched_df, bin_size_min=bin_size), use_container_width=True)
with col_b:
    st.subheader("Patients by Time Band")
    st.plotly_chart(charts.make_time_band_bar(enriched_df), use_container_width=True)

# ── Scatter: distance vs time ─────────────────────────────────────────────────
st.subheader("Drive Distance vs Drive Time")
st.plotly_chart(charts.make_scatter_dist_time(enriched_df), use_container_width=True)

# ── Outcome charts ────────────────────────────────────────────────────────────
if outcome_col:
    st.markdown("---")
    st.subheader(f"Outcome Analysis: {outcome_col}")
    col_os, col_ob = st.columns(2)
    with col_os:
        st.plotly_chart(charts.make_outcome_scatter(enriched_df, outcome_col), use_container_width=True)
    with col_ob:
        st.plotly_chart(charts.make_outcome_by_band(enriched_df, outcome_col), use_container_width=True)

st.markdown("---")

# ── Data table + download ─────────────────────────────────────────────────────
st.subheader("Enriched Data Table")

show_low_conf = st.checkbox("Show low-confidence rows only", value=False)
display_df = enriched_df[enriched_df["score"] < score_threshold] if show_low_conf else enriched_df

sort_col = st.selectbox("Sort by", options=["drive_time_min", "drive_distance_km", "score"], index=0)
sort_asc = st.checkbox("Ascending", value=True)
display_df = display_df.sort_values(sort_col, ascending=sort_asc, na_position="last")

st.dataframe(display_df, use_container_width=True, height=400)

download_cols = list(raw_df.columns) + [
    "lat", "lon", "score", "match_precision",
    "drive_distance_km", "drive_time_min", "time_band", "distance_band",
]
download_cols = [c for c in download_cols if c in enriched_df.columns]
csv_bytes = enriched_df[download_cols].to_csv(index=False).encode()
st.download_button(
    label="⬇️ Download enriched CSV",
    data=csv_bytes,
    file_name="bc_drive_mapper_enriched.csv",
    mime="text/csv",
)

st.markdown("---")
st.markdown("## 🔍 Patient Waitlist Timing")
st.markdown("Check whether surgical patients on your waitlist are being served in first-in, first-out order. Upload a waitlist CSV to see queue rankings, deviations, and wait times.")
st.page_link("pages/2_Waitlist_Audit.py", label="Open Waitlist FIFO Audit →", icon="🔍")
