# SensorTower — Session Seed

Authoritative state document. Update when architecture or long-term state changes.
Short-lived task state belongs in GitHub issues or commit messages, not here.

---

## What this is

A vertical temperature + humidity tower in an apple block at Cornell AgriTech (Geneva, NY), plus a Streamlit dashboard that makes the data immediately usable for frost/freeze management. The tower's job is to capture canopy-level microclimate that a single standard weather station misses.

- **PI:** Jason Londo, Cornell AgriTech
- **Crops:** Honeycrisp and Fuji apple, semi-dwarf
- **Tower:** One LI-COR / Onset HOBO RX2100 datalogger, 9 T+RH+DewPoint sensor heads at 2, 22, 42, 62, 82, 102, 122, 142, 162 in, 5-min cadence
- **Install:** 2026-04-19 16:00 EDT; sensor height labels set in licor.cloud at 19:00 EDT
- **Dashboard:** Streamlit Community Cloud, deployed from public GitHub repo `Jasonlondo/SensorTower`

---

## Architecture

```
┌────────────────────┐        ┌─────────────────────┐        ┌──────────────────┐
│ LI-COR Cloud       │──API──►│ GitHub Actions      │──push─►│ GitHub repo      │
│ (api.licor.cloud)  │        │ cron */15 * * * *   │        │ data/licor_*.csv │
└────────────────────┘        │                     │        │ data/newa/*.csv  │
                              │ pull_daily.py       │        └────────┬─────────┘
┌────────────────────┐        │ pull_newa_daily.py  │                 │
│ NEWA / NRCC hourly │──API──►│ (rolling            │                 ▼
│ hrly.nrcc...       │        │  yesterday→now      │        ┌──────────────────┐
│ stnHrly            │        │  window)            │        │ Streamlit Cloud  │
└────────────────────┘        └─────────────────────┘        │ auto-rebuilds    │
                                                             │ on every commit  │
                                                             └──────────────────┘
```

**Effective latency:** ~15–30 min (GitHub Actions scheduler adds 5–15 min jitter on top of the 15-min cron).

**No secrets on Streamlit side.** The LI-COR token is a GitHub repository secret (`LICOR_TOKEN`). The app reads committed CSVs, never hits the API itself. NEWA needs no auth at all.

---

## Key decisions

### Sensor SN → height crosswalk (the "match backward" derivation)

The LI-COR Cloud API exposes raw sensor serial numbers (`22411189-1`, etc.) but *not* the human-readable labels set in the licor.cloud UI. We derived the crosswalk empirically by matching temperature values at two timestamps (2026-04-21 13:55 and 14:00 UTC) between the datalogger CSV (which has height column headers like `2in`/`22in`) and the API response (which has SNs). All nine pairs matched to three decimal places at both timestamps.

Crosswalk lives in `sensor_map.csv`. If a sensor is ever swapped, update that one file.

**Pre-install phase:** all 9 sensors were co-located (~62 in) before 2026-04-19 16:00 EDT. Data from that window is flagged `phase='pre_install'` by the loader — valid for sensor intercomparison, not for gradient analysis.

### Apple bud-kill thresholds

Previous values (attributed to NC State) were inherited from an earlier CLAUDE.md with unverified provenance. Replaced with the canonical **MSU Extension compilation (M. Longstroth)**, which republishes **WSU EB0913** for apple. Native units are °F; code stores °C with the °F source values in trailing comments for traceability. See `scripts/data_loader.py :: THRESHOLDS`.

MSU values are materially more conservative at early stages than the old NC State numbers (Silver tip 10% kill: -15 °C → -9.4 °C).

### NEWA API — reverse-engineered

No public docs. Endpoint and payload were captured via browser DevTools from the "All Weather Data Query" form:

- `POST https://hrly.nrcc.cornell.edu/stnHrly`
- Content-Type: **application/json** (not form-encoded — form-encoding returns "Invalid sid")
- Body: `{"sid":"ny_geng nwon","sdate":"YYYYMMDDHH","edate":"YYYYMMDDHH"|"now","extraelems":""}`
- Response: `{"hrlyFields":[...], "hrlyData":[[...],...]}`

Station `ny_geng nwon` = Geneva (AgriTech Gates). Note the suffix is `nwon` (NEWA online), *not* the numeric ACIS network code `31` you'd see in `StnMeta`. This is undocumented — if NEWA changes it, the endpoint stops working.

Temperature and dew point come back in **°F**; the parser converts to °C.

### Commit-on-every-run

Every 15-min cron run commits a `data: auto-pull …` entry if CSVs changed. This drives Streamlit rebuilds automatically. Commit noise is expected and desired — it's how freshness reaches the dashboard. If this becomes problematic, the alternative is to pull live from LI-COR inside the Streamlit app itself (requires the token as a Streamlit secret), but that was deliberately not done because it puts the token on a different platform and adds page-load latency.

### NEWA overlay on tower charts

NEWA's 1.5 m sensor sits between tower heights 42 in and 62 in. Overlaying NEWA as a red fine-dashed line (`line_color="#d62728"`, `dash="3,3"`, `mode="lines+markers"`) on every temperature and humidity chart makes the station's position in the vertical profile explicit at a glance.

**Agreement (mid-canopy 62 in vs NEWA, 2026-04-19 → 2026-04-24):** correlation 0.9921, bias +0.10 °C (tower slightly warmer), RMSE 0.85 °C. Tight during freeze events, diverges during morning warm-up because in-canopy air heats faster than NEWA's open-grass siting. **That divergence is scientifically interesting, not a QC problem.**

---

## What's built (2026-04-24)

### Data pipeline
- `scripts/licor_api.py` — LI-COR Cloud client with bearer auth, pagination, retries
- `scripts/newa_api.py` — NEWA hourly client, unit conversions
- `scripts/pull_daily.py` — rolling yesterday→now window, splits to per-UTC-day CSVs
- `scripts/pull_newa_daily.py` — same pattern, per-local-day CSVs
- `scripts/data_loader.py` — `load_all` (legacy+API dedup, phase column), `load_newa`, `wide_temperature`, `THRESHOLDS`
- `scripts/load_data.py` — legacy loader (kept for scripts 02/03)
- `scripts/02_plot_freeze_event.py`, `03_figures_fahrenheit.py` — legacy per-event figure scripts

### Dashboard (`app.py`)
- Sidebar: units (°C/°F), time-range presets (24h / 3d / 7d / 30d / All / Custom)
- Latest-reading freshness indicator
- **Overview** — custom HTML metric cards (small font to fit 9 cards) showing the *latest* reading regardless of window; vertical-gradient info box; chart that follows the sidebar time range, with a header that echoes the active preset ("Tower — last 24 h", etc.) and a NEWA overlay
- **Time series** — full timeseries + delta-from-ground, both with NEWA overlay
- **Inversions** — gradient chart with freezing-inversion shading (light blue rectangles where gradient > 0.3 AND ground < freeze line), heatmap, peak-events table
- **Threshold exposure** — MSU bud-stage selector (default Full bloom), **per-event tables** (one per frost night with ≥1 min of 10% kill exposure, laid out in a 2-column grid), and a per-night bar chart (0–720 min fixed axis + hours on right side). Nights are defined noon-to-noon so events crossing midnight stay in one bucket.
- **Humidity & dew point** — per-height lines + NEWA overlay
- **NEWA comparison** — dedicated page with per-height agreement stats, 1:1 scatter, RH+DP overlays

### Ops
- `.github/workflows/daily_pull.yml` — every 15 min, rebases before commit, concurrency group
- `LICOR_TOKEN` in GitHub repo secrets
- `.gitattributes` normalizes LF for CSV + source files
- Streamlit Community Cloud app, deployed from `main`, auto-rebuild on push

### Backfill available
- Legacy datalogger CSVs: `freeze2-*.csv`, `freezefrost20260421c-*.csv` (covers 2026-04-19 16:30 → 2026-04-21 10:00)
- API-pulled day files: `licor_2026-04-20.csv` → present
- NEWA day files: `newa_2026-04-19.csv` → present

---

## Known events

| Event | Date | Duration <0°C at 2 in | Min 2 in | Peak inversion (top − ground) |
|-------|------|------------------------|----------|--------------------------------|
| Freeze Night 1 | Apr 19–20, 2026 | 210 min | −2.0 °C | 0.47 °C |
| Reversed-gradient blip | Apr 20, 2026 ~11:00 | 25 min | −0.9 °C | −0.56 °C (upper colder) |
| Freeze Night 2 | Apr 20–21, 2026 | 685 min | −5.1 °C | 3.06 °C at 21:45 EDT (classic radiation inversion) |
| Strong inversion, no freeze | Apr 22, 2026 22:00 EDT | — | — | **4.90 °C** (largest in record; warmer starting point, still textbook structure) |

---

## Open items / future work

- [ ] Add alerts (email/SMS/Slack) when tower gradient flips into freezing-inversion territory, or when 2 in drops below a user-set threshold. Likely a separate scheduled workflow checking the most recent CSV row.
- [ ] Phenology-stage auto-picker on the Threshold page based on date / GDD, so the threshold defaults make sense for the current time of year instead of always Full bloom.
- [ ] Add humidity to the threshold analysis — dew-point depression is itself a radiation-frost predictor (T approaching DP + RH climbing toward 100 % is the classic setup).
- [ ] Reduce commit noise: either throttle the cron during quiet periods or move to live-API-from-Streamlit with the token as a Streamlit secret.
- [ ] Pursue official NEWA API access (email newa@cornell.edu) so we're not dependent on a reverse-engineered endpoint.
- [ ] Add a second tower at another site for comparison, once one exists.
- [ ] Ingest historical NEWA data for the AgriTech Gates station (multi-year) to characterize "typical" April inversion patterns and put this year's events in context.

---

## Non-obvious gotchas

- **Streamlit ≠ browser reload.** After a code push, Streamlit Cloud needs an explicit *app reboot* (Manage app → ⋯ → Reboot) to pick up new code. A browser reload only re-renders the current container.
- **Charts must respect the sidebar time range.** Earlier bug: the Overview chart was `.tail(24*12)` which ignored the preset selector. Any new chart should slice the already-filtered frame (`wide_disp` for tower T, `newa_series(var, start_ts, end_ts)` for NEWA) — never re-window with `.tail()` or `.head()` unless there's a specific "latest N" reason.
- **Group by "frost night," not calendar day, for freeze-event aggregation.** A radiation frost typically starts ~20:00 and ends ~07:00, crossing midnight. Grouping by calendar day splits one event into two buckets and hides the total duration. We use `(index − 12h).normalize()` so 12:00–23:59 belongs to its own night and 00:00–11:59 belongs to the *previous* night. Labels read "Night of YYYY-MM-DD" meaning that afternoon into the next morning.
- **Private repo breaks Streamlit free tier.** Streamlit Community Cloud only has OAuth access to public repos by default; installing the "Deploy to Streamlit" GitHub App for a private repo was brittle. Currently the repo is public — keep it that way unless you set up the GitHub App properly.
- **Line endings matter.** GitHub Actions runners produce LF; Windows git produces CRLF. `.gitattributes` forces LF on the data CSVs and source files to prevent every CI run from rewriting the whole file with cosmetic diffs.
- **NEWA sid has a space in it.** `"ny_geng nwon"` — the space is significant. URL-encode it correctly if you ever move to form-encoded POST.
- **`replace_all` in edit tools is sharp.** During development, an `st.plotly_chart → show_chart` replace_all hit the body of `show_chart` itself and produced infinite recursion. Lesson applies to any helper that calls the primitive it's wrapping.

---

## Repo layout

```
SensorTower/
├── app.py                          # Streamlit entrypoint
├── requirements.txt
├── sensor_map.csv                  # SN → height crosswalk
├── CLAUDE.md, project_scope.md, README.md, SESSION_SEED_sensortower.md
├── .env, .env.example, .gitignore, .gitattributes
├── .github/workflows/daily_pull.yml
├── scripts/
│   ├── licor_api.py, newa_api.py
│   ├── pull_daily.py, pull_newa_daily.py
│   ├── data_loader.py, load_data.py
│   └── 02_plot_freeze_event.py, 03_figures_fahrenheit.py
├── data/
│   ├── freeze2-*.csv, freezefrost20260421c-*.csv   # legacy datalogger wide CSVs
│   ├── licor_YYYY-MM-DD.csv                         # per-UTC-day long CSVs
│   └── newa/newa_YYYY-MM-DD.csv                     # per-local-day NEWA long CSVs
└── outputs/                                          # static figures from legacy scripts
```
