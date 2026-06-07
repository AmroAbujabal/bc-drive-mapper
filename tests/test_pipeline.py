from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import pipeline


def test_assign_time_band():
    assert pipeline._assign_band(0, pipeline.TIME_BANDS) == "0\u201315 min"
    assert pipeline._assign_band(14.9, pipeline.TIME_BANDS) == "0\u201315 min"
    assert pipeline._assign_band(15, pipeline.TIME_BANDS) == "15\u201330 min"
    assert pipeline._assign_band(30, pipeline.TIME_BANDS) == "30\u201360 min"
    assert pipeline._assign_band(60, pipeline.TIME_BANDS) == "60\u2013120 min"
    assert pipeline._assign_band(120, pipeline.TIME_BANDS) == "120+ min"
    assert pipeline._assign_band(None, pipeline.TIME_BANDS) == "Unknown"


def test_assign_distance_band():
    assert pipeline._assign_band(0, pipeline.DISTANCE_BANDS) == "0\u201325 km"
    assert pipeline._assign_band(50, pipeline.DISTANCE_BANDS) == "50\u2013100 km"
    assert pipeline._assign_band(300, pipeline.DISTANCE_BANDS) == "200+ km"


def test_geocode_focal_point_parses_latlon():
    lat, lon = pipeline.geocode_focal_point("49.24, -123.12")
    assert lat == pytest.approx(49.24)
    assert lon == pytest.approx(-123.12)


def test_geocode_focal_point_geocodes_address():
    with patch("pipeline.geocode_address", return_value={"lat": 49.24, "lon": -123.12, "score": 99, "match_precision": "CIVIC_NUMBER"}):
        lat, lon = pipeline.geocode_focal_point("4480 Oak St, Vancouver")
    assert lat == pytest.approx(49.24)
    assert lon == pytest.approx(-123.12)


def test_run_returns_enriched_dataframe():
    df = pd.DataFrame([
        {"address": "100 Main St", "postcode": "V1A1A1"},
        {"address": "200 Oak St", "postcode": "V2B2B2"},
    ])
    geocoded_rows = [
        {"address": "100 Main St", "postcode": "V1A1A1", "lat": 49.0, "lon": -122.0, "score": 90.0, "match_precision": "CIVIC_NUMBER"},
        {"address": "200 Oak St", "postcode": "V2B2B2", "lat": 49.1, "lon": -122.1, "score": 85.0, "match_precision": "BLOCK"},
    ]
    drive_results = [
        {"drive_distance_km": 25.0, "drive_time_min": 30.0},
        {"drive_distance_km": 50.0, "drive_time_min": 60.0},
    ]
    with patch("pipeline.geocode_batch", return_value=geocoded_rows):
        with patch("pipeline.get_drive_matrix", return_value=drive_results):
            result = pipeline.run(df, "address", "postcode", 49.24, -123.12, "http://localhost:5000")
    assert "drive_distance_km" in result.columns
    assert "drive_time_min" in result.columns
    assert "time_band" in result.columns
    assert "distance_band" in result.columns
    assert result.iloc[0]["time_band"] == "30\u201360 min"
    assert result.iloc[1]["time_band"] == "60\u2013120 min"


def test_save_and_load_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "CACHE_FILE", tmp_path / "test_cache.parquet")
    df = pd.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
    pipeline.save_cache(df)
    loaded = pipeline.load_cache()
    assert loaded is not None
    pd.testing.assert_frame_equal(df, loaded)


def test_load_cache_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "CACHE_FILE", tmp_path / "nonexistent.parquet")
    assert pipeline.load_cache() is None
