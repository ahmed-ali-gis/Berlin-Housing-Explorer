# Berlin Housing Explorer

**Explore Berlin housing prices, workplace distance and public transport coverage in one Web GIS application.**

Python · FastAPI · PostgreSQL/PostGIS · Leaflet · JavaScript

![Berlin project data overview](docs/overview.svg)

*Overview generated from the bundled district geometries; this is not an application screenshot. Counts describe the supplied data, not performance improvements.*

## Project at a glance

| Spatial data | Application capabilities |
|---|---|
| 96 Berlin Ortsteile; 80 area-price records | Budget and straight-line distance filters |
| 10,731 bounding-box boarding points | Switchable U-Bahn, S-Bahn, tram, bus, rail and ferry layers |
| 3,643 route shape variants | Per-area transport summaries and expandable line lists |
| Dated VBB snapshot: 30 September 2026 | Create, edit and delete saved search profiles |

## Problem and approach

Housing choices combine price and location. This student project connects area-level housing prices with a selected workplace, then adds public transport context. A Leaflet interface sends requests to a FastAPI service; PostGIS stores geometries and profiles, calculates spatial distances and assigns boarding points to areas.

```mermaid
flowchart LR
    A[Leaflet map and search profile] --> B[FastAPI REST API]
    B --> C[PostgreSQL and PostGIS]
    D[Districts and area prices] --> C
    E[Dated VBB GTFS snapshot] --> C
    C --> B
    B --> A
```

The ranking filters by budget and distance, then calculates `0.6 × price/budget + 0.4 × distance/maximum distance`. Lower scores rank first. SQL parameters protect values in database queries; profile keys are stored as SHA-256 hashes in the database.

## Scope and limitations

- Prices describe areas, not individual apartments. Their observation date and collection method are not documented; 16 areas have no prices.
- Distance is a straight-line geodesic distance to a representative point inside an area. It is not a travel time.
- Transit coverage counts boarding points, including separate platforms. It does not estimate service frequency or accessible walking distance.
- Boundaries date to 2014 and transit to 2026. The 60/40 ranking is a demonstration choice.
- This is a local student demonstration; it is not prepared for public hosting.

<details>
<summary><strong>Run locally and configure the database</strong></summary>

## Run locally

1. Install Python 3.12 and PostgreSQL with PostGIS. Create a separate local database for this demonstration. Enable PostGIS using `CREATE EXTENSION IF NOT EXISTS postgis;` as a database administrator. The application account needs permission to create the `housing` schema and its tables. Do not connect this demo to an existing production database.
2. Open a terminal in this repository folder and create a Python environment:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

3. Set `DATABASE_URL` to your local PostgreSQL connection URL. Enter it privately rather than storing it in a repository file. On macOS/Linux:

   ```sh
   read -s DATABASE_URL
   export DATABASE_URL
   ```

   Type the connection URL and press Enter. The format is `postgresql://USER:PASSWORD@HOST:PORT/DATABASE`; replace each placeholder with your local settings. URL-encode special characters in credentials. Input is hidden. Do not upload credentials or environment files.
4. Start the application:

   ```sh
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

5. Open http://localhost:8000. API documentation: http://localhost:8000/docs. Internet is needed for Leaflet and OpenStreetMap background tiles.
6. Inspect area boundaries, select transport categories and zoom to level 13+ for boarding points. Search profiles can be saved, changed and deleted. The supplied prices enable housing recommendations for the 80 matched areas; 16 mapped areas have no price records.

Profile keys grant access to saved profiles and must remain private. This classroom demonstration is not prepared for public hosting.


</details>

## Repository structure

```text
app/           API, spatial queries and interactive map
scripts/       GTFS snapshot builder
data/         Boundaries, housing prices and transit snapshot
tests/        Snapshot and API checks
docs/         Data overview illustration
```

## Validation

Checked on 7 October 2026: Python syntax, JSON parsing, positive finite price values and matching of all 80 price-area names. The synthetic GTFS test passed for calendar exceptions, mode classification, boarding eligibility and geographic filtering. A targeted security scan found no embedded credentials or personal documents.

**Runtime status:** the full application and API checks have not been verified for this portfolio copy. No live demo or benchmark is claimed.

```sh
python tests/test_transit_snapshot.py
# With the application running and bundled prices loaded:
python tests/verify_portfolio_api.py
python tests/verify_transit.py
```

<details>
<summary><strong>Dataset provenance and redistribution</strong></summary>

## Dataset sources and redistribution

| Files | Provider and date | Redistribution |
|---|---|---|
| `data/districts.geojson` | Amt für Statistik Berlin-Brandenburg; Berlin Ortsteile, 31 December 2014 | Yes, with attribution and a license reference. Supplied metadata states CC BY 3.0 Germany; the official portal confirms CC BY. |
| `data/transit_stops.geojson`, `data/transit_routes.geojson` | Verkehrsverbund Berlin-Brandenburg (VBB); scheduled services on 30 September 2026 | Yes, CC BY 4.0, with attribution, license link and modification notice. |
| `data/transit_metadata.json` | Snapshot provenance, date, archive checksum and license | Included to retain attribution and processing provenance for the VBB data. |
| `data/prices.csv` | Dataset created by the project author, as confirmed on 7 October 2026; source URLs point to ImmobilienScout24 | Included following the author's explicit request to publish it. No separate license for third-party reuse is specified. Observation date and collection method remain undocumented. |

Boundary attribution: © Amt für Statistik Berlin-Brandenburg. Source: [RBS-Ortsteile, Dezember 2014](https://daten.berlin.de/datensaetze/rbs-ortsteile-dezember-2014). License: [CC BY 3.0 Germany](https://creativecommons.org/licenses/by/3.0/de/). Delivered as GeoJSON in longitude/latitude; the supplied QGIS metadata describes the original projected source layer.

Transit attribution: © Verkehrsverbund Berlin-Brandenburg (VBB). Source: [VBB Open Data](https://unternehmen.vbb.de/digitale-services/datensaetze/). License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Modifications: date selection, geographic subset and mode classification; geometry simplification and district coverage are performed by the application. The original GTFS ZIP is not included.

Housing source links: [ImmobilienScout24](https://www.immobilienscout24.de/), retained per row in the CSV. I confirmed that I created the dataset and want it included in the public portfolio. Source links are attribution, not a claim about the source website's reuse terms. No live price verification has been performed.

Leaflet and OpenStreetMap are accessed online; their libraries and background tiles are not bundled datasets. The map retains OpenStreetMap attribution. Dataset licenses apply to the data, not the application code.


</details>

## How this project was built

I used AI assistance to improve the code and the visual presentation of the project.
