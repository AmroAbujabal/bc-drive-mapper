import math
import pandas as pd
from pathlib import Path
from typing import Callable, Optional

from geocoder import geocode_address, geocode_batch
from router import get_drive_matrix

CACHE_FILE = Path(__file__).parent / "enriched_cache.parquet"

TIME_BANDS = [
    (0, 15, "0\u201315 min"),
    (15, 30, "15\u201330 min"),
    (30, 60, "30\u201360 min"),
    (60, 120, "60\u2013120 min"),
    (120, float("inf"), "120+ min"),
]

DISTANCE_BANDS = [
    (0, 25, "0\u201325 km"),
    (25, 50, "25\u201350 km"),
    (50, 100, "50\u2013100 km"),
    (100, 200, "100\u2013200 km"),
    (200, float("inf"), "200+ km"),
]

TIME_BAND_ORDER = [b[2] for b in TIME_BANDS] + ["Unknown"]
DISTANCE_BAND_ORDER = [b[2] for b in DISTANCE_BANDS] + ["Unknown"]


def _assign_band(value, bands: list) -> str:
    if value is None:
        return "Unknown"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    if math.isnan(v):
        return "Unknown"
    for lo, hi, label in bands:
        if lo <= v < hi:
            return label
    return bands[-1][2]


def geocode_focal_point(text: str) -> tuple:
    """
    Parse 'lat,lon' string or geocode an address string.
    Returns (lat, lon). Raises ValueError if neither works.
    """
    text = text.strip()
    if "," in text:
        parts = text.split(",")
        if len(parts) == 2:
            try:
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
            except ValueError:
                pass
    geo = geocode_address(text, "")
    if geo["lat"] is not None:
        return geo["lat"], geo["lon"]
    raise ValueError(f"Could not geocode focal point: {text!r}")


def run(
    df: pd.DataFrame,
    addr_col: str,
    pc_col: str,
    focal_lat: float,
    focal_lon: float,
    osrm_base: str,
    geocode_progress: Optional[Callable] = None,
    route_progress: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    Full pipeline: geocode all rows, then route from focal point.

    Returns an enriched DataFrame with added columns:
      lat, lon, score, match_precision,
      drive_distance_km, drive_time_min,
      time_band, distance_band
    """
    rows = df.to_dict("records")
    geocoded = geocode_batch(rows, addr_col, pc_col, progress_cb=geocode_progress)
    enriched = pd.DataFrame(geocoded)

    valid_mask = enriched["lat"].notna() & enriched["lon"].notna()
    valid_coords = list(zip(enriched.loc[valid_mask, "lat"], enriched.loc[valid_mask, "lon"]))

    drive_results = get_drive_matrix(
        source=(focal_lat, focal_lon),
        destinations=valid_coords,
        osrm_base=osrm_base,
        progress_cb=route_progress,
    )

    enriched["drive_distance_km"] = None
    enriched["drive_time_min"] = None
    valid_indices = enriched.index[valid_mask].tolist()
    for i, idx in enumerate(valid_indices):
        enriched.at[idx, "drive_distance_km"] = drive_results[i]["drive_distance_km"]
        enriched.at[idx, "drive_time_min"] = drive_results[i]["drive_time_min"]

    enriched["time_band"] = enriched["drive_time_min"].apply(
        lambda v: _assign_band(v, TIME_BANDS)
    )
    enriched["distance_band"] = enriched["drive_distance_km"].apply(
        lambda v: _assign_band(v, DISTANCE_BANDS)
    )
    return enriched


def save_cache(df: pd.DataFrame) -> None:
    df.to_parquet(CACHE_FILE, index=False)


def load_cache() -> Optional[pd.DataFrame]:
    if CACHE_FILE.exists():
        return pd.read_parquet(CACHE_FILE)
    return None
