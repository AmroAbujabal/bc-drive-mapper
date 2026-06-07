from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import router


HOSPITAL = (49.2404, -123.1189)  # BC Children's Hospital


def _make_osrm_response(n_dests: int, duration_s: float = 1800.0, distance_m: float = 25000.0):
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "code": "Ok",
        "durations": [[duration_s] * n_dests],
        "distances": [[distance_m] * n_dests],
    }
    return mock


def test_single_destination(tmp_path):
    dests = [(49.0, -122.0)]
    with patch("requests.get", return_value=_make_osrm_response(1)) as mock_get:
        with patch("time.sleep"):
            results = router.get_drive_matrix(HOSPITAL, dests)
    assert len(results) == 1
    assert results[0]["drive_time_min"] == pytest.approx(30.0)
    assert results[0]["drive_distance_km"] == pytest.approx(25.0)


def test_chunking_calls_api_multiple_times():
    # 250 destinations → ceil(250/100) = 3 chunks
    dests = [(49.0, -122.0)] * 250
    with patch("requests.get", return_value=_make_osrm_response(100)) as mock_get:
        with patch("time.sleep"):
            results = router.get_drive_matrix(HOSPITAL, dests, chunk_size=100)
    assert mock_get.call_count == 3
    assert len(results) == 250


def test_api_failure_returns_none_for_chunk():
    dests = [(49.0, -122.0)] * 5
    with patch("requests.get", side_effect=Exception("network error")):
        with patch("time.sleep"):
            results = router.get_drive_matrix(HOSPITAL, dests)
    assert all(r["drive_time_min"] is None for r in results)
    assert all(r["drive_distance_km"] is None for r in results)


def test_null_duration_in_response():
    # OSRM returns null for unreachable destinations
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "code": "Ok",
        "durations": [[None]],
        "distances": [[None]],
    }
    dests = [(49.0, -122.0)]
    with patch("requests.get", return_value=mock):
        with patch("time.sleep"):
            results = router.get_drive_matrix(HOSPITAL, dests)
    assert results[0]["drive_time_min"] is None
    assert results[0]["drive_distance_km"] is None


def test_progress_callback_called():
    dests = [(49.0, -122.0)] * 3
    calls = []
    with patch("requests.get", return_value=_make_osrm_response(3)):
        with patch("time.sleep"):
            router.get_drive_matrix(HOSPITAL, dests, progress_cb=lambda d, t: calls.append((d, t)))
    assert calls[-1] == (3, 3)
