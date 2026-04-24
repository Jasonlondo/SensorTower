# Sensor Tower

Vertical temperature-gradient monitor for an instrumented apple block at Cornell AgriTech. A 9-sensor tower (2–162 in) with LI-COR / HOBO RX2100 datalogger captures air temperature, relative humidity, and dew point at 5-minute resolution through the canopy, feeding a Streamlit dashboard that surfaces frost events, inversions, and bud-stage threshold exposure.

**Live dashboard:** (add Streamlit Cloud URL once deployed)

## Architecture

```
LI-COR Cloud  ──►  GitHub Actions (daily cron)  ──►  data/licor_YYYY-MM-DD.csv  ──►  Streamlit Cloud
                   uses LICOR_TOKEN secret              committed to repo            reads committed CSVs
```

- Data lives in `data/` (committed to git) — no live API calls from the dashboard
- Legacy datalogger CSVs (`freeze*.csv`) and API-pulled CSVs (`licor_*.csv`) are unified by `scripts/data_loader.py`
- The `sensor_map.csv` crosswalk maps each serial number to its physical height — rebuilt empirically by matching API values against the original datalogger CSVs

## Repo layout

```
SensorTower/
├── app.py                         # Streamlit app (entry point)
├── requirements.txt
├── sensor_map.csv                 # SN → height crosswalk
├── .env.example                   # template; copy to .env for local runs
├── .github/workflows/
│   └── daily_pull.yml             # daily cron
├── scripts/
│   ├── licor_api.py               # LI-COR Cloud API client
│   ├── pull_daily.py              # CI entry point — pulls yesterday's data
│   ├── data_loader.py             # unified legacy + API loader
│   ├── load_data.py               # legacy loader (kept for the 02/03 scripts)
│   ├── 02_plot_freeze_event.py    # legacy per-event figure script (°C)
│   └── 03_figures_fahrenheit.py   # legacy per-event figure script (°F)
├── data/
│   ├── freeze2-*.csv              # legacy datalogger export (wide format)
│   ├── freezefrost20260421c-*.csv # legacy datalogger export
│   └── licor_YYYY-MM-DD.csv       # daily API pulls (long format, T + RH + DP)
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

# 4. Run a daily pull (defaults to yesterday UTC)
python scripts/pull_daily.py

# 5. Launch the dashboard
streamlit run app.py
```

## Deployment — GitHub + Streamlit Cloud

1. **Push to GitHub.** The `.env` file is gitignored; the token does not leave your machine.
2. **Add the API token as a repo secret.** On GitHub:
   `Settings > Secrets and variables > Actions > New repository secret`
   - Name: `LICOR_TOKEN`
   - Value: your licor.cloud API token
   - (Optional) also set a repo variable `LICOR_DEVICE_SN` if you ever swap the device; the workflow defaults to `22411541`.
3. **Connect the repo to Streamlit Community Cloud.**
   - [share.streamlit.io](https://share.streamlit.io) → New app → point at `app.py` on the `main` branch.
   - No Streamlit secrets needed — the app reads committed CSVs.
4. **Enable the workflow.** The cron in `.github/workflows/daily_pull.yml` runs at 10:00 UTC daily. You can also trigger it manually from the Actions tab (workflow_dispatch) with an optional `pull_date` input to backfill a specific day.

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
