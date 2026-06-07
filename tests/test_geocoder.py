import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import geocoder as gc


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(gc, "CACHE_DB", db_path)
    return db_path


def test_cache_miss_returns_none(tmp_db):
    conn = gc._get_conn()
    result = gc._cache_get(conn, "NONEXISTENT")
    conn.close()
    assert result is None


def test_cache_set_and_get(tmp_db):
    conn = gc._get_conn()
    gc._cache_set(conn, "123 MAIN ST|V1V1V1", {"lat": 49.1, "lon": -122.5, "score": 95.0, "match_precision": "CIVIC_NUMBER"})
    result = gc._cache_get(conn, "123 MAIN ST|V1V1V1")
    conn.close()
    assert result["lat"] == pytest.approx(49.1)
    assert result["lon"] == pytest.approx(-122.5)
    assert result["score"] == pytest.approx(95.0)
    assert result["match_precision"] == "CIVIC_NUMBER"


def test_geocode_address_uses_cache(tmp_db):
    conn = gc._get_conn()
    gc._cache_set(conn, "4480 OAK ST|V6H3V4", {"lat": 49.24, "lon": -123.12, "score": 99.0, "match_precision": "CIVIC_NUMBER"})
    conn.close()
    with patch("requests.get") as mock_get:
        result = gc.geocode_address("4480 Oak St", "V6H3V4")
        mock_get.assert_not_called()
    assert result["lat"] == pytest.approx(49.24)


def test_geocode_address_api_call(tmp_db):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "features": [{
            "geometry": {"coordinates": [-123.12, 49.24]},
            "properties": {"score": 99, "matchPrecision": "CIVIC_NUMBER"}
        }]
    }
    mock_response.raise_for_status = MagicMock()
    with patch("requests.get", return_value=mock_response):
        with patch("time.sleep"):
            result = gc.geocode_address("4480 Oak St", "V6H3V4")
    assert result["lat"] == pytest.approx(49.24)
    assert result["lon"] == pytest.approx(-123.12)
    assert result["score"] == pytest.approx(99.0)


def test_geocode_address_api_failure_returns_empty(tmp_db):
    with patch("requests.get", side_effect=Exception("network error")):
        with patch("time.sleep"):
            result = gc.geocode_address("BAD ADDRESS", "X0X0X0")
    assert result["lat"] is None
    assert result["lon"] is None
    assert result["score"] == 0.0


def test_geocode_batch(tmp_db):
    rows = [
        {"address": "4480 Oak St", "postcode": "V6H3V4"},
        {"address": "123 Main St", "postcode": "V1A1A1"},
    ]
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "features": [{
            "geometry": {"coordinates": [-123.12, 49.24]},
            "properties": {"score": 95, "matchPrecision": "CIVIC_NUMBER"}
        }]
    }
    mock_response.raise_for_status = MagicMock()
    with patch("requests.get", return_value=mock_response):
        with patch("time.sleep"):
            results = gc.geocode_batch(rows, "address", "postcode")
    assert len(results) == 2
    assert "lat" in results[0]
    assert "lat" in results[1]
