# SensorTower — Session Seed

Authoritative state document. Update when architecture or long-term state changes.
Short-lived task state belongs in GitHub issues or commit messages, not here.

---

## What this is

A vertical temperature + humidity tower in an apple block at Cornell AgriTech (Geneva, NY), plus a GitHub Pages dashboard that makes the data immediately usable for frost/freeze management. The tower's job is to capture canopy-level microclimate that a single standard weather station misses.

- **PI:** Jason Londo, Cornell AgriTech
- **Crops:** Honeycrisp and Fuji apple, semi-dwarf
- **Tower:** One LI-COR / Onset HOBO RX2100 datalogger, 9 T+RH+DewPoint sensor heads at 2, 22, 42, 62, 82, 102, 122, 142, 162 in, 5-min cadence
- **Install:** 2026-04-19 16:00 EDT; sensor height labels set in licor.cloud at 19:00 EDT
- **Dashboard:** GitHub Pages, https://jasonlondo.github.io/SensorTower/, built from public repo `Jasonlondo/SensorTower` (Streamlit Community Cloud until 2026-10-20)

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
│ stnHrly            │        │  window)            │        │ GitHub Pages     │
└────────────────────┘        └─────────────────────┘        │ auto-rebuilds    │
                                                             │ on every commit  │
                                                             └──────────────────┘
```

**Effective latency:** ~15–30 min (GitHub Actions scheduler adds 5–15 min jitter on top of the 15-min cron).

**No secrets in the page.** The LI-COR token is a GitHub repository secret (`LICOR_TOKEN`). The site reads committed CSVs, never hits the API itself. NEWA needs no auth at all.

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

Every 15-min cron run commits a `data: auto-pull …` entry if CSVs changed. The `deploy` job then rebuilds and publishes the Pages site. Commit noise is expected; the commits are the permanent data record.

### App memory bound — rolling window + downloadable archive (2026-07-03)

By July the committed day-files had accumulated to ~75 days. `load_all()` read *every* file on each rerun (~1.9 MB RAM/day, measured), which pushed the app past Streamlit Community Cloud's ~1 GB RAM cap. Fixed in commit `b9e892a`:

- **Rolling window.** `data_loader.load_all` / `load_newa` take a `window_days` arg that filters day-files by their date-stamped *filenames before reading them*, so old data never enters RAM. The window is anchored on the **newest available file, not wall-clock** — a stalled or backfilling pipeline still shows its last N days instead of going blank. `window_days=None` keeps load-everything for the legacy analysis scripts. The app uses `APP_WINDOW_DAYS = 30`.
- **Archive + prune.** `scripts/build_archive.py` rolls all history into `data/archive/tower_hourly_archive.csv` — **hourly means of Temperature + RH only**, wide (one column per height) — then prunes raw `licor_*.csv` older than `RETENTION_DAYS = 35`. Order is strict: **archive first, delete second**, so nothing is removed before it's captured; raw 5-min data also stays in git history. NEWA files (tiny) and the legacy freeze-event exports (irreplaceable) are never pruned.
- **Download.** The app exposes the archive via a sidebar "Download full history" button; it never loads the archive into memory for charts.

Post-fix growth: app RAM flat at ~35 days × 1.9 MB ≈ 67 MB; archive ≈ 1.2 MB/yr. **Invariant: keep `APP_WINDOW_DAYS ≤ RETENTION_DAYS`** so the loaded window never outruns the raw files still on disk.

### GitHub Pages site + monthly record (2026-10-20)

The dashboard moved from Streamlit Community Cloud to a static GitHub Pages site (`site/index.html`, plain JS + Plotly), following the grape-ripening-explorer pattern. Reasons: Streamlit's free tier sleeps when idle and caps RAM at ~1 GB, which forced the 30-day window.

- **Permanent 5-min record.** `data/monthly/tower_YYYY-MM.csv`, wide T/RH/DP, ISO local time with offset (keeps the DST fall-back hour unique). Backfilled from git history of pruned licor files. `update_monthly.py` merge rule is stored-values-win; fresh data only fills blanks.
- **Archive bug fixed.** The old `build_archive.py` merged `resample("1h")` output into the archive with fresh-wins, so blank hours between the April legacy exports and the 35-day window overwrote real values (May–Sep blank by Oct 2026). The archive is now rebuilt from the monthly record each run, and pruning refuses to delete a raw file whose day is not in the monthly record.
- **Page behavior.** Presets 24 h / 7 d / 30 d plus custom (max 30 days). NEWA comparison tab dropped; NEWA red fine-dash overlay kept on T/RH/DP charts. Threshold exposure counts 5 min per reading at or below a threshold (previously time since the prior reading, which over-counted after gaps). Inversion threshold 0.3 °C is applied in °C regardless of display units.
- **Known data gap.** 2026-08-28 08:30–14:55 EDT is missing from LI-COR Cloud itself; the rest of the Jul 27–Aug 29 uplink outage backfilled.

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
- `scripts/data_loader.py` — `load_all` (legacy+API dedup, phase column, `window_days` rolling filter), `load_newa`, `wide_temperature`, `THRESHOLDS`
- `scripts/build_archive.py` — rolls history into `data/archive/tower_hourly_archive.csv` (hourly T+RH) and prunes raw `licor_*.csv` older than 35 days; run by the workflow after each pull
- `scripts/load_data.py` — legacy loader (kept for scripts 02/03)
- `scripts/02_plot_freeze_event.py`, `03_figures_fahrenheit.py` — legacy per-event figure scripts

### Dashboard (`site/index.html`, GitHub Pages)
- Live at https://jasonlondo.github.io/SensorTower/ and linked from the lab website tools page. Plain JS + Plotly; loads only the monthly files a window needs
- Controls: units (°C/°F), time range (last 24 h / 7 days / 30 days / custom up to 30 days anywhere in the record), "Download this window (5-min CSV)", "Download full history (hourly T + RH)". The URL hash stores the view
- Freshness line flags the tower as possibly offline if the newest reading is over 3 h old
- **Overview**: cards for the latest reading, 2 in on the left to 162 in on the right; vertical-gradient box; temperature chart with NEWA overlay
- **Time series**: temperature + departure from 2 in, NEWA overlay
- **Inversions**: gradient with freezing-inversion shading, shifted RdYlBu_r heatmap (matches `02_plot_freeze_event.py`), top-10 peaks
- **Threshold exposure**: MSU bud-stage selector, per-night tables (noon to noon), per-night bar chart (0–720 min fixed axis + hours axis)
- **Humidity & dew point**: per-height lines + NEWA overlay
- Streamlit app (`app.py`) retired and removed 2026-10-20

### Ops
- `.github/workflows/daily_pull.yml` — every 15 min, rebases before commit, concurrency group; runs `build_archive.py` after the pulls and stages prunes + archive via `git add -A data/`
- `LICOR_TOKEN` in GitHub repo secrets
- `.gitattributes` normalizes LF for CSV + source files
- `deploy` job publishes `_site/` to GitHub Pages after every pull (Pages source: GitHub Actions)

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
- [ ] Reduce commit noise: throttle the cron during quiet periods (e.g. hourly outside frost season).
- [ ] Pursue official NEWA API access (email newa@cornell.edu) so we're not dependent on a reverse-engineered endpoint.
- [ ] Add a second tower at another site for comparison, once one exists.
- [ ] Ingest historical NEWA data for the AgriTech Gates station (multi-year) to characterize "typical" April inversion patterns and put this year's events in context.

---

## Non-obvious gotchas

- **Pages caches for ~10 min.** After a deploy, a hard refresh (Ctrl+Shift+R) shows the new page. Data files carry a `?v=<build time>` query so they refresh on each build.
- **A code push does not deploy by itself.** The workflow runs on its cron or by hand (`gh workflow run daily_pull.yml`).
- **Charts must respect the selected time range.** New charts in `site/index.html` should draw from `view.rows` / `view.newa` (already windowed), and only the Overview cards deliberately show the latest reading.
- **Group by "frost night," not calendar day, for freeze-event aggregation.** A radiation frost typically starts ~20:00 and ends ~07:00, crossing midnight. Grouping by calendar day splits one event into two buckets and hides the total duration. We use `(index − 12h).normalize()` so 12:00–23:59 belongs to its own night and 00:00–11:59 belongs to the *previous* night. Labels read "Night of YYYY-MM-DD" meaning that afternoon into the next morning.
- **Don't use `min(2,22,42)` as the near-ground reference for "current gradient."** That metric was tuned for nighttime inversion detection where 2 in is the coldest sensor (cold-air drainage). On sunny afternoons the sun-heated 2 in is the *warmest* sensor near ground, so `min()` silently skips it and the displayed gradient gets compressed by 1–2 °C. The Overview page now uses the 2 in reading directly. Inversion-detection logic on the Inversions page still uses `min(2,22,42)` because there it serves the original purpose.
- **API clients must retry on `requests.Timeout` / `requests.ConnectionError`, not only on 429.** Caught 2026-04-26: an overnight LI-COR pull failed with a 30 s read timeout because `_get` only retried on rate-limit responses. Both `licor_api.py` and `newa_api.py` now use 5 attempts with exponential backoff (1, 2, 4, 8, 16 s) and a 60 s default timeout. The workflow also marks each pull `continue-on-error: true` so a single-source transient failure doesn't block the other source's commit.
- **Keep the repo public.** GitHub Pages on a free account requires a public repo.
- **Line endings matter.** GitHub Actions runners produce LF; Windows git produces CRLF. `.gitattributes` forces LF on the data CSVs and source files to prevent every CI run from rewriting the whole file with cosmetic diffs.
- **NEWA sid has a space in it.** `"ny_geng nwon"` — the space is significant. URL-encode it correctly if you ever move to form-encoded POST.

---

## Repo layout

```
SensorTower/
├── site/index.html                 # Pages dashboard
├── requirements.txt
├── sensor_map.csv                  # SN → height crosswalk
├── CLAUDE.md, project_scope.md, README.md, SESSION_SEED_sensortower.md
├── .env, .env.example, .gitignore, .gitattributes
├── .github/workflows/daily_pull.yml
├── scripts/
│   ├── licor_api.py, newa_api.py
│   ├── pull_daily.py, pull_newa_daily.py
│   ├── data_loader.py, load_data.py
│   ├── update_monthly.py                           # raw -> data/monthly 5-min record
│   ├── build_archive.py                            # monthly -> hourly archive, prune raw files
│   ├── build_site.py                               # assemble _site/ for Pages
│   └── 02_plot_freeze_event.py, 03_figures_fahrenheit.py
├── data/
│   ├── freeze2-*.csv, freezefrost20260421c-*.csv   # legacy datalogger wide CSVs
│   ├── licor_YYYY-MM-DD.csv                         # per-UTC-day long CSVs (last ~35 days)
│   ├── monthly/tower_YYYY-MM.csv                   # permanent 5-min record (T, RH, DP)
│   ├── archive/tower_hourly_archive.csv            # full history, hourly T+RH, downloadable
│   └── newa/newa_YYYY-MM-DD.csv                     # per-local-day NEWA long CSVs
└── outputs/                                          # static figures from legacy scripts
```
