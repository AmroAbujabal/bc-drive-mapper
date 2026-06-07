import time
import requests
from typing import Callable, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

BATCH_DELAY = 0.5  # seconds between chunks to avoid hammering public server


@retry(
    retry=retry_if_exception_type((requests.RequestException, TimeoutError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=False,
)
def _osrm_request(url: str, params: dict) -> dict:
    """Single OSRM request with automatic retry on network errors."""
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def get_drive_matrix(
    source: tuple,
    destinations: list,
    osrm_base: str = "https://router.project-osrm.org",
    chunk_size: int = 100,
    progress_cb: Optional[Callable] = None,
) -> list:
    """
    Compute driving distance + time from one source to many destinations via OSRM /table.

    source: (lat, lon)
    destinations: list of (lat, lon)
    Returns list of dicts: [{drive_distance_km, drive_time_min}, ...], one per destination.
    Values are None if OSRM returned null or the request failed after retries.
    """
    n = len(destinations)
    results = [{"drive_distance_km": None, "drive_time_min": None} for _ in range(n)]

    # OSRM expects lon,lat order
    src_coord = f"{source[1]},{source[0]}"

    for chunk_start in range(0, n, chunk_size):
        chunk = destinations[chunk_start : chunk_start + chunk_size]
        dest_coords = [f"{d[1]},{d[0]}" for d in chunk]

        # source is coordinate index 0; destinations are 1..len(chunk)
        all_coords = ";".join([src_coord] + dest_coords)
        dest_indices = ";".join(str(i) for i in range(1, len(chunk) + 1))

        url = f"{osrm_base.rstrip('/')}/table/v1/driving/{all_coords}"
        params = {
            "sources": "0",
            "destinations": dest_indices,
            "annotations": "distance,duration",
        }

        try:
            data = _osrm_request(url, params)
            durations = (data.get("durations") or [[]])[0]  # seconds, may contain null
            distances = (data.get("distances") or [[]])[0]  # metres, may contain null

            for i, (dur, dist) in enumerate(zip(durations, distances)):
                idx = chunk_start + i
                results[idx] = {
                    "drive_distance_km": round(dist / 1000, 2) if dist is not None else None,
                    "drive_time_min": round(dur / 60, 1) if dur is not None else None,
                }
        except Exception:
            pass  # chunk stays as None values after all retries exhausted

        done = min(chunk_start + chunk_size, n)
        if progress_cb:
            progress_cb(done, n)

        if chunk_start + chunk_size < n:
            time.sleep(BATCH_DELAY)

    return results
