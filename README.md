# BC Drive Mapper

A Streamlit app that maps **driving distance and time** from BC patient addresses to a hospital, and visualises how commute distance relates to care outcomes.

Built for BC Children's Hospital (default), but works with any focal point.

---

## Quick Start

### 1. Install Python dependencies

You need Python 3.11 or newer. In your terminal:

```bash
cd bc-drive-mapper
pip install -r requirements.txt
```

### 2. Run the app

```bash
streamlit run app.py
```

The app opens automatically at **http://localhost:8501**

---

## How to Use It

### Step 1 — Upload a CSV
Click **"Upload patient CSV"** and select your file. The app auto-detects address and postcode columns. If it gets them wrong, expand the **Column mapping** section and pick the right columns from the dropdowns.

A sample file (`sample_patients.csv`) is included so you can test without real data.

### Step 2 — Configure the focal point (optional)
In the **sidebar**, the focal point defaults to BC Children's Hospital (`49.2404, -123.1189`). You can change it to any hospital by entering a different `lat, lon` pair or a street address.

### Step 3 — Click Process
Hit the **▶ Process — Geocode + Route** button. The app will:
1. Geocode each patient address using the BC Address Geocoder (free, no API key needed)
2. Calculate driving distance + time to the hospital via OSRM routing
3. Cache the results to disk — so **reloading the page is instant** next time

Processing 30 rows takes ~10 seconds. 3,000 rows takes ~5–10 minutes on first run.

### Step 4 — Explore the results
Once processed you'll see:
- **Metric cards** — total rows, geocoding success rate, low-confidence count, median/mean/max drive time
- **Interactive map** — patients coloured by drive-time band, hospital marked in red
- **Histogram** — distribution of drive times (adjust bin size in the sidebar)
- **Bar chart** — patient count per time band (0–15 / 15–30 / 30–60 / 60–120 / 120+ min)
- **Scatter plot** — drive distance vs drive time
- **Outcome charts** — if your CSV has a numeric outcome column, scatter + box plot vs drive time
- **Data table** — sortable, filterable, with a download button for the enriched CSV

---

## Sample Data

`sample_patients.csv` is included with 30 fake patient addresses spread across BC (Vancouver, Surrey, Kelowna, Victoria, Whistler, Kamloops, Prince George) and a dummy `outcome_score` column (0–10).

To use it: upload `sample_patients.csv` in the app. The columns will auto-detect as:
- **Address column** → `address`
- **Postcode column** → `postcode`
- **Outcome column** → `outcome_score`

---

## Output CSV Columns

When you download the enriched CSV, you get your original columns plus:

| Column | Description |
|--------|-------------|
| `lat` | Geocoded latitude |
| `lon` | Geocoded longitude |
| `score` | Geocoder confidence (0–100) |
| `match_precision` | Match type (e.g. CIVIC_NUMBER, BLOCK) |
| `drive_distance_km` | Road distance to hospital |
| `drive_time_min` | Estimated driving time |
| `time_band` | Bucketed time (0–15 min, 15–30 min, …) |
| `distance_band` | Bucketed distance (0–25 km, 25–50 km, …) |

---

## Notes

- **No API key required** — uses the free BC Address Geocoder and the public OSRM routing server
- **Geocoding cache** — results are saved to `cache.db` so re-runs never re-query addresses you've already geocoded
- **Low-confidence addresses** — shown as hollow grey dots on the map; adjust the confidence threshold in the sidebar
- **Clear cache** — sidebar button removes the cached results so you can re-process with a different focal point

---

## Self-Hosting OSRM (optional, for large datasets)

The default public OSRM server at `https://router.project-osrm.org` is shared and may be slow for 3,000+ points. To run your own local server using the BC road network:

```bash
# Download the BC road network extract from Geofabrik (~100 MB)
wget https://download.geofabrik.de/north-america/canada/british-columbia-latest.osm.pbf

# Pre-process with Docker (takes ~5–10 min first time)
docker run -t -v "$(pwd):/data" osrm/osrm-backend osrm-extract \
  -p /opt/car.lua /data/british-columbia-latest.osm.pbf
docker run -t -v "$(pwd):/data" osrm/osrm-backend osrm-partition /data/british-columbia-latest.osrm
docker run -t -v "$(pwd):/data" osrm/osrm-backend osrm-customize /data/british-columbia-latest.osrm

# Start the server
docker run -d -p 5000:5000 -v "$(pwd):/data" osrm/osrm-backend osrm-routed \
  --algorithm mld /data/british-columbia-latest.osrm
```

Then in the app sidebar, change **OSRM Base URL** to `http://localhost:5000`.
