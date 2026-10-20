# Sensor Tower

Vertical temperature-gradient monitor for an instrumented apple block at Cornell AgriTech. A 9-sensor tower (2–162 in) with LI-COR / HOBO RX2100 datalogger captures air temperature, relative humidity, and dew point at 5-minute resolution through the canopy.

**Live dashboard:** https://jasonlondo.github.io/SensorTower/ (static GitHub Pages site, since 2026-10-20).

## GitHub Pages site (current)

```
LI-COR Cloud + NEWA ──► GitHub Actions (every 15 min) ──► data/ committed ──► deploy job ──► GitHub Pages
                         pull_daily.py, pull_newa_daily.py      data/monthly/      build_site.py
                         update_monthly.py, build_archive.py    data/archive/      -> _site/
```

- `data/monthly/tower_YYYY-MM.csv` is the permanent 5-min record (T, RH, DP at all heights, ISO local time with UTC offset). `scripts/update_monthly.py` merges raw day-files into it each run; stored values never change and new data only fills blanks.
- `scripts/build_archive.py` rebuilds the hourly T + RH download (`data/archive/tower_hourly_archive.csv`) from the monthly record, then prunes raw `licor_*.csv` older than 35 days once their days are in the monthly record.
- `scripts/build_site.py` copies `site/index.html`, the monthly files, monthly NEWA files and the archive into `_site/`, which the workflow's `deploy` job publishes. The page loads only the months a chosen window needs.
- Time ranges are last 24 h, 7 days, 30 days, or a custom range of up to 30 days anywhere in the record. The URL hash stores the view, so links are shareable.
- Pages source is set to "GitHub Actions" in repo Settings → Pages.

Preview locally:

```bash
python scripts/build_site.py --out _site
python -m http.server 8000 --directory _site
```

## Repo layout

```
SensorTower/
├── site/index.html                # dashboard page (JS + Plotly), published by the deploy job
├── requirements.txt
├── sensor_map.csv                 # SN → height crosswalk
├── .env.example                   # template; copy to .env for local runs
├── .github/workflows/
│   └── daily_pull.yml             # 15-min pull + Pages deploy
├── scripts/
│   ├── licor_api.py, newa_api.py  # API clients
│   ├── pull_daily.py, pull_newa_daily.py
│   ├── data_loader.py             # unified legacy + API loader, THRESHOLDS
│   ├── update_monthly.py          # raw day-files -> data/monthly/
│   ├── build_archive.py           # monthly -> hourly archive, prune raw files
│   ├── build_site.py              # assemble _site/ for Pages
│   ├── load_data.py               # legacy loader (kept for the 02/03 scripts)
│   └── 02_plot_freeze_event.py, 03_figures_fahrenheit.py
├── data/
│   ├── monthly/tower_YYYY-MM.csv  # permanent 5-min record (T, RH, DP)
│   ├── archive/tower_hourly_archive.csv
│   ├── licor_YYYY-MM-DD.csv       # raw API pulls, last ~35 days
│   ├── newa/newa_YYYY-MM-DD.csv   # NEWA hourly pulls
│   └── freeze2-*.csv, freezefrost20260421c-*.csv   # legacy datalogger exports
└── outputs/                       # static figures from legacy scripts
```

## Local setup

```bash
# 1. Clone and create a virtual environment
git clone <this repo>
cd SensorTower
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 2. Install deps
pip install -r requirements.txt

# 3. Copy .env.example to .env and paste your LI-COR token
cp .env.example .env
# edit .env and set LICOR_TOKEN=...

# 4. Pull, then update the monthly record and archive
python scripts/pull_daily.py
python scripts/update_monthly.py
python scripts/build_archive.py --no-prune

# 5. Build and preview the site
python scripts/build_site.py --out _site
python -m http.server 8000 --directory _site
```

## Deployment

1. **Add the API token as a repo secret.** `Settings > Secrets and variables > Actions > New repository secret`, name `LICOR_TOKEN`. Optionally set a repo variable `LICOR_DEVICE_SN` if the device changes (default `22411541`).
2. **Set Pages to deploy from Actions.** `Settings > Pages > Source: GitHub Actions`.
3. **The workflow does the rest.** `.github/workflows/daily_pull.yml` runs every 15 minutes. The `pull` job pulls and commits data, then the `deploy` job builds `_site/` and publishes it. Trigger it by hand from the Actions tab (workflow_dispatch), optionally with a `pull_date` to backfill one day. A code push alone does not deploy.

The Streamlit Community Cloud app that served the dashboard until 2026-10-20 was shut down that day and `app.py` removed.

## Token rotation

If the token is ever exposed or needs to change:

1. In licor.cloud: Data > API, delete the old token, add a new one.
2. Update `.env` locally and the `LICOR_TOKEN` secret in GitHub.
3. No other changes needed.

## Sensor → height mapping

The API exposes raw serial numbers, not the human-readable labels set in the licor.cloud UI. The crosswalk in `sensor_map.csv` was derived by matching temperature values at two timestamps (2026-04-21 13:55 and 14:00 UTC) between the datalogger CSV (which has height column headers) and the API (which has serial numbers). All nine pairs matched to three decimal places.

To swap or add a sensor:
1. Replace the row(s) in `sensor_map.csv`.
2. Re-run `python scripts/pull_daily.py` to regenerate any affected CSVs (or backfill manually).

## Data phases

- `pre_install` — timestamps before **2026-04-19 16:00 local**. All nine sensors were co-located (~62 in) before tower install. Useful only for sensor intercomparison / calibration; filter out for gradient analyses.
- `tower` — everything after tower install. Full vertical gradient.

The `phase` column is added automatically by `data_loader.load_all()`.

## Reference — LI-COR Cloud API

- Base URL: `https://api.licor.cloud`
- Auth: `Authorization: Bearer <token>` (up to 5 tokens per account, generated in the UI)
- Docs: [api.licor.cloud/v1/docs](https://api.licor.cloud/v1/docs/) (Swagger UI)
- Key endpoints used:
  - `GET /v2/devices?includeSensors=true` — list devices & their sensor channels
  - `GET /v2/data?deviceSerialNumber=<sn>&startTime=<ms>&endTime=<ms>` — time-series data
- Rate limits: 100,000 records per call; HTTP 429 on throttle. `fetch_window_paginated()` handles both.
