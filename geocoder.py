import sqlite3
import time
import requests
from pathlib import Path
from typing import Optional

GEOCODER_URL = "https://geocoder.api.gov.bc.ca/addresses.geojson"
CACHE_DB = Path(__file__).parent / "cache.db"
REQ_INTERVAL = 0.065  # ~15 req/sec, well within the 1000 req/min limit


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            address_key  TEXT PRIMARY KEY,
            lat          REAL,
            lon          REAL,
            score        REAL,
            match_precision TEXT,
            cached_at    TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def _cache_get(conn: sqlite3.Connection, key: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT lat, lon, score, match_precision FROM geocode_cache WHERE address_key = ?",
        (key,),
    ).fetchone()
    if row:
        return {"lat": row[0], "lon": row[1], "score": row[2], "match_precision": row[3]}
    return None


def _cache_set(conn: sqlite3.Connection, key: str, result: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO geocode_cache
           (address_key, lat, lon, score, match_precision)
           VALUES (?, ?, ?, ?, ?)""",
        (key, result["lat"], result["lon"], result["score"], result["match_precision"]),
    )
    conn.commit()


def geocode_address(address: str, postcode: str) -> dict:
    """
    Geocode a single address + postcode pair via the BC Address Geocoder.

    Returns dict: {lat, lon, score, match_precision}.
    lat/lon are None on any failure; score is 0.0.
    Always caches result so subsequent calls never hit the network.
    """
    key = f"{address}|{postcode}".upper().strip()
    conn = _get_conn()
    cached = _cache_get(conn, key)
    if cached is not None:
        conn.close()
        return cached

    address_string = f"{address}, {postcode}, BC" if postcode else f"{address}, BC"
    result: dict = {"lat": None, "lon": None, "score": 0.0, "match_precision": ""}

    try:
        resp = requests.get(
            GEOCODER_URL,
            params={"addressString": address_string, "maxResults": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        if features:
            feat = features[0]
            coords = feat["geometry"]["coordinates"]  # [lon, lat]
            props = feat["properties"]
            result = {
                "lon": coords[0],
                "lat": coords[1],
                "score": float(props.get("score", 0)),
                "match_precision": props.get("matchPrecision", ""),
            }
    except Exception:
        pass

    _cache_set(conn, key, result)
    conn.close()
    time.sleep(REQ_INTERVAL)
    return result


def geocode_batch(
    rows: list,
    addr_col: str,
    pc_col: str,
    progress_cb=None,
) -> list:
    """
    Geocode a list of row dicts in place.

    Each dict gets lat, lon, score, match_precision keys added.
    progress_cb(done: int, total: int) is called after each row.
    """
    conn = _get_conn()
    results = []
    total = len(rows)

    for i, row in enumerate(rows):
        key = f"{row.get(addr_col, '')}|{row.get(pc_col, '')}".upper().strip()
        cached = _cache_get(conn, key)

        if cached:
            results.append({**row, **cached})
        else:
            conn.close()
            geo = geocode_address(str(row.get(addr_col, "")), str(row.get(pc_col, "")))
            conn = _get_conn()
            results.append({**row, **geo})

        if progress_cb:
            progress_cb(i + 1, total)

    conn.close()
    return results
