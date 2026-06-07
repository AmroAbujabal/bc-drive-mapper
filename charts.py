"""
Pure chart-builder functions. No st.* calls — only return figures/maps.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium

from pipeline import TIME_BAND_ORDER

TIME_BAND_COLORS = {
    "0\u201315 min":   "#2196F3",
    "15\u201330 min":  "#4CAF50",
    "30\u201360 min":  "#FFC107",
    "60\u2013120 min": "#FF5722",
    "120+ min":        "#9C27B0",
    "Unknown":         "#9E9E9E",
}

_FALLBACK_COLOR = "#9E9E9E"


def make_map(
    df: pd.DataFrame,
    focal_lat: float,
    focal_lon: float,
    score_threshold: float = 70,
) -> folium.Map:
    """Folium map: red marker for hospital, patient points coloured by time band."""
    m = folium.Map(location=[focal_lat, focal_lon], zoom_start=8, tiles="CartoDB positron")

    folium.Marker(
        location=[focal_lat, focal_lon],
        popup="BC Children's Hospital",
        tooltip="BC Children's Hospital",
        icon=folium.Icon(color="red", icon="plus-sign", prefix="glyphicon"),
    ).add_to(m)

    valid = df[df["lat"].notna() & df["lon"].notna()]

    for _, row in valid.iterrows():
        is_high_conf = row["score"] >= score_threshold
        if is_high_conf:
            band = row["time_band"] if pd.notna(row["time_band"]) else "Unknown"
            color = TIME_BAND_COLORS.get(band, _FALLBACK_COLOR)
            time_val = f"{row['drive_time_min']:.0f} min" if pd.notna(row["drive_time_min"]) else "N/A"
            dist_val = f"{row['drive_distance_km']:.1f} km" if pd.notna(row["drive_distance_km"]) else "N/A"
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=5,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                weight=1,
                tooltip=f"{band} \u00b7 {time_val} \u00b7 {dist_val}",
            ).add_to(m)
        else:
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=4,
                color=_FALLBACK_COLOR,
                fill=False,
                weight=1,
                tooltip=f"Low confidence (score={row['score']:.0f})",
            ).add_to(m)

    legend_html = (
        '<div style="position:fixed;bottom:30px;left:30px;z-index:1000;'
        'background:white;padding:10px;border-radius:8px;'
        'box-shadow:0 2px 6px rgba(0,0,0,.3);font-size:12px;">'
        "<b>Drive time</b><br>"
    )
    for band, colour in TIME_BAND_COLORS.items():
        legend_html += (
            f'<span style="background:{colour};width:12px;height:12px;'
            f'display:inline-block;border-radius:50%;margin-right:4px;"></span>'
            f"{band}<br>"
        )
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def make_histogram(df: pd.DataFrame, bin_size_min: int = 15) -> go.Figure:
    """Histogram of drive_time_min."""
    valid = df["drive_time_min"].dropna()
    stats = valid.agg(["min", "max"])
    nbins = max(1, int((stats["max"] - stats["min"]) / bin_size_min)) if len(valid) > 1 else 10
    fig = px.histogram(
        valid,
        nbins=nbins,
        title="Distribution of Drive Time to Hospital",
        labels={"value": "Drive Time (min)", "count": "Patients"},
        color_discrete_sequence=["#2196F3"],
    )
    fig.update_layout(bargap=0.05, xaxis_title="Drive Time (min)", yaxis_title="Number of Patients")
    return fig


def make_time_band_bar(df: pd.DataFrame) -> go.Figure:
    """Bar chart: count per time band."""
    present_set = set(df["time_band"])
    present = [b for b in TIME_BAND_ORDER if b in present_set]
    counts = df["time_band"].value_counts().reindex(present, fill_value=0).reset_index()
    counts.columns = ["time_band", "count"]
    fig = px.bar(
        counts,
        x="time_band",
        y="count",
        title="Patients by Drive-Time Band",
        labels={"time_band": "Drive-Time Band", "count": "Patients"},
        color="time_band",
        color_discrete_map=TIME_BAND_COLORS,
    )
    fig.update_layout(showlegend=False, xaxis_title="Drive-Time Band", yaxis_title="Number of Patients")
    return fig


def make_scatter_dist_time(df: pd.DataFrame) -> go.Figure:
    """Scatter: drive_distance_km vs drive_time_min, coloured by time_band."""
    valid = df[df["drive_distance_km"].notna() & df["drive_time_min"].notna()]
    fig = px.scatter(
        valid,
        x="drive_distance_km",
        y="drive_time_min",
        color="time_band",
        color_discrete_map=TIME_BAND_COLORS,
        title="Drive Distance vs Drive Time",
        labels={"drive_distance_km": "Drive Distance (km)", "drive_time_min": "Drive Time (min)"},
        opacity=0.6,
    )
    fig.update_traces(marker=dict(size=5))
    return fig


def make_outcome_scatter(df: pd.DataFrame, outcome_col: str) -> go.Figure:
    """Scatter: outcome vs drive_time_min with OLS trendline."""
    valid = df[df["drive_time_min"].notna() & df[outcome_col].notna()]
    fig = px.scatter(
        valid,
        x="drive_time_min",
        y=outcome_col,
        color="time_band",
        color_discrete_map=TIME_BAND_COLORS,
        title=f"{outcome_col} vs Drive Time",
        labels={"drive_time_min": "Drive Time (min)", outcome_col: outcome_col},
        trendline="ols",
        opacity=0.6,
    )
    fig.update_traces(selector=dict(mode="markers"), marker=dict(size=5))
    return fig


def make_outcome_by_band(df: pd.DataFrame, outcome_col: str) -> go.Figure:
    """Box plot: outcome distribution per time band."""
    valid = df[df[outcome_col].notna() & df["time_band"].notna()]
    present_set = set(valid["time_band"])
    ordered = [b for b in TIME_BAND_ORDER if b in present_set]
    fig = px.box(
        valid,
        x="time_band",
        y=outcome_col,
        category_orders={"time_band": ordered},
        color="time_band",
        color_discrete_map=TIME_BAND_COLORS,
        title=f"{outcome_col} by Drive-Time Band",
        labels={"time_band": "Drive-Time Band", outcome_col: outcome_col},
    )
    fig.update_layout(showlegend=False)
    return fig
