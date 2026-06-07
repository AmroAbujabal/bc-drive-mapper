from pathlib import Path
import pandas as pd
import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import charts
from pipeline import TIME_BAND_ORDER, DISTANCE_BAND_ORDER


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "lat": [49.0, 49.1, 49.2, None],
        "lon": [-122.0, -122.1, -122.2, None],
        "score": [95.0, 80.0, 60.0, 0.0],
        "match_precision": ["CIVIC_NUMBER", "BLOCK", "STREET", ""],
        "drive_distance_km": [25.0, 50.0, 100.0, None],
        "drive_time_min": [20.0, 45.0, 90.0, None],
        "time_band": ["15\u201330 min", "30\u201360 min", "60\u2013120 min", "Unknown"],
        "distance_band": ["0\u201325 km", "25\u201350 km", "50\u2013100 km", "Unknown"],
        "outcome": [7.5, 6.0, 5.0, None],
    })


def test_make_map_returns_folium_map(sample_df):
    import folium
    m = charts.make_map(sample_df, focal_lat=49.24, focal_lon=-123.12, score_threshold=70)
    assert isinstance(m, folium.Map)


def test_make_histogram_returns_figure(sample_df):
    fig = charts.make_histogram(sample_df, bin_size_min=15)
    assert hasattr(fig, "data")


def test_make_time_band_bar_returns_figure(sample_df):
    fig = charts.make_time_band_bar(sample_df)
    assert hasattr(fig, "data")


def test_make_scatter_dist_time_returns_figure(sample_df):
    fig = charts.make_scatter_dist_time(sample_df)
    assert hasattr(fig, "data")


def test_make_outcome_scatter_returns_figure(sample_df):
    fig = charts.make_outcome_scatter(sample_df, outcome_col="outcome")
    assert hasattr(fig, "data")


def test_make_outcome_by_band_returns_figure(sample_df):
    fig = charts.make_outcome_by_band(sample_df, outcome_col="outcome")
    assert hasattr(fig, "data")
