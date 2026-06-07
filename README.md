# BC Drive Mapper

Maps driving distance and time from BC patient addresses to BC Children's Hospital (4480 Oak St, Vancouver), and visualises the distribution to support care-equity analysis.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501.

## Usage

1. Upload a CSV with patient addresses (street address column + postcode column).
2. Confirm the detected columns or select the correct ones from the dropdowns.
3. Optionally select a numeric outcome/quality column for correlation charts.
4. Click **Process** — geocoding + routing runs once and is cached to disk.
5. Explore the charts, filters, and downloadable enriched CSV.

## Self-Hosting OSRM for BC

The public OSRM demo server at https://router.project-osrm.org works but is shared. For 3,000+ points, self-host using the BC extract from Geofabrik. Include these exact Docker commands:

```bash
# Download BC extract
wget https://download.geofabrik.de/north-america/canada/british-columbia-latest.osm.pbf

# Pre-process and start OSRM via Docker
docker run -t -v "$(pwd):/data" osrm/osrm-backend osrm-extract \
  -p /opt/car.lua /data/british-columbia-latest.osm.pbf
docker run -t -v "$(pwd):/data" osrm/osrm-backend osrm-partition /data/british-columbia-latest.osrm
docker run -t -v "$(pwd):/data" osrm/osrm-backend osrm-customize /data/british-columbia-latest.osrm
docker run -d -p 5000:5000 -v "$(pwd):/data" osrm/osrm-backend osrm-routed \
  --algorithm mld /data/british-columbia-latest.osrm
```

Then note: set the OSRM Base URL in the app sidebar to `http://localhost:5000`.
