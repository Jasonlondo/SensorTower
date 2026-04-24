# SensorTower Project

> **Dashboard & deployment:** see [`README.md`](README.md) for the Streamlit app, daily GitHub Actions pull, and sensor_map crosswalk. This file documents the underlying physics, thresholds, and legacy analysis scripts.

## Project Overview

This project analyzes vertical temperature gradient data from an instrumented sensor tower at Jason Londo's experimental orchard/vineyard (Cornell). The tower captures fine-scale temperature stratification through the apple canopy and above-canopy air to characterize frost and freeze events as trees experience them — with the goal of informing grower management decisions during critical low-temperature periods.

Target crops: **Honeycrisp** and **Fuji** apple on various rootstocks (semi-dwarf planting system).

---

## Sensor Tower Configuration

| Column Name | Height (inches) | Height (feet) | Position in Canopy |
|-------------|----------------|---------------|---------------------|
| `2in`       | 2              | 0.17          | Near-ground / grass layer |
| `22in`      | 22             | 1.83          | Lower trunk / mulch zone |
| `42in`      | 42             | 3.5           | Lower canopy |
| `62in`      | 62             | 5.17          | Mid-canopy |
| `82in`      | 82             | 6.83          | Mid-to-upper canopy |
| `102in`     | 102            | 8.5           | Upper canopy |
| `122in`     | 122            | 10.17         | Top of canopy / canopy edge |
| `142in`     | 142            | 11.83         | Above canopy |
| `162in`     | 162            | 13.5          | Well above canopy |

- **Sensor spacing:** 20 inches between each sensor
- **Logging interval:** 5 minutes
- **Temperature units:** Degrees Celsius (°C) in raw data

---

## Data Format

Files are CSV exports from the datalogger. The filename prefix (e.g., `freeze2`, `freezefrost20260421c`) is just the download name — it does not indicate tower ID or deployment. There is one tower.

**Naming pattern:** `<download_name>-<YYYY_MM_DD_HH_MM_SS_TZ>.csv`

**Columns:**
- `Date` — timestamp in `YY-MM-DD HH:MM:SS` format (local time, EDT)
- `2in` through `162in` — temperature (°C) at each sensor height

**Important:** New downloads from the datalogger frequently overlap with previous files (the datalogger re-exports from the beginning). Drop all files into `data/` — `load_tower_data()` handles deduplication automatically (keeps last record when timestamps collide).

---

## Research Goals & Key Questions

1. **Temperature inversion detection** — Does cold air pool near the ground or is it mixed? When and under what conditions?
2. **Canopy-level freeze exposure** — What temperatures do buds/flowers at different canopy positions actually experience during freeze events?
3. **Threshold crossings** — Time spent below critical damage thresholds (e.g., 0°C, −2°C, −4°C for apple bloom stages)
4. **Gradient characterization** — Magnitude and timing of vertical temperature gradients during frost events vs. non-frost nights
5. **Grower-relevant outputs** — Summaries and visualizations that communicate freeze risk in practical terms

---

## Critical Temperature Thresholds (Apple)

| Growth Stage    | 10% Kill (°C) | 90% Kill (°C) | 10% Kill (°F) | 90% Kill (°F) |
|-----------------|---------------|---------------|---------------|---------------|
| Silver tip      | −9.4          | −16.7         | 15            | 2             |
| Green tip       | −7.8          | −12.2         | 18            | 10            |
| Half-inch green | −5.0          | −9.4          | 23            | 15            |
| Tight cluster   | −2.8          | −6.1          | 27            | 21            |
| First pink      | −2.2          | −4.4          | 28            | 24            |
| Full pink       | −2.2          | −3.9          | 28            | 25            |
| First bloom     | −2.2          | −3.9          | 28            | 25            |
| Full bloom      | −2.2          | −3.9          | 28            | 25            |
| Post bloom      | −2.2          | −3.9          | 28            | 25            |

**Source:** MSU Extension, *Critical Spring Temperatures for Tree Fruit Bud Development Stages* ([PDF](https://www.canr.msu.edu/fruit/uploads/files/PictureTableofFruitFreezeDamageThresholds.pdf)). Apple values originate from **WSU EB0913**; compiled by Mark Longstroth, MSU Extension Educator. Native publication units are °F; °C values above are converted from the published °F table.

---

## Coding Preferences

- **Primary language:** Python (all analysis and visualization)
- **R:** reserved for data validation only, not primary development
- **Python interpreter:** `C:/Users/jpl275/AppData/Local/anaconda3/python.exe`
- **Key packages:** `pandas`, `matplotlib`, `numpy`
- **Style:** Reproducible scripts; long (tidy) format preferred for multi-sensor analyses
- **Figures produced in both °C and °F** — °C scripts save without suffix, °F scripts save with `_F` suffix

### Typical Data Wrangling Steps
1. Import via `scripts/load_data.py` — handles date parsing (`%y-%m-%d %H:%M:%S`), deduplication, returns `(wide, long)` DataFrames
2. `wide`: one row per timestamp, one column per sensor height (e.g., `2in`, `22in`, …)
3. `long`: melted — columns `datetime`, `height`, `height_in`, `height_ft`, `temp_c`
4. Delta from ground: `wide[col] - wide["2in"]` for each sensor column; multiply by 9/5 for °F delta
5. °F conversion: `temp_f = temp_c * 9/5 + 32`

---

## Visualization Conventions (locked in)

- **Line plot palette:** `viridis` — sequential, height-intuitive, no temperature connotation
- **Legend order:** highest sensor (162 in) at top → lowest (2 in) at bottom; single column (`ncol=1`)
- **Heatmap colormap:** custom-shifted `RdYlBu_r` with linear `Normalize` so 0°C/32°F sits at the blue/yellow boundary without stretching the colorbar
- **Heatmap colorbar ticks:** equidistant — every 1°C or 2°F over the actual data range
- **No contour lines** on heatmaps — the color boundary communicates the freezing threshold
- **Two heatmap versions per event:** `nearest` interpolation (shows real block structure) and `bilinear` (smoothed)
- **Freeze event annotations:** black text, white semi-transparent box, black arrow
- **Threshold reference lines:** 0°C/32°F dashed steelblue; −2.2°C/28°F dotted firebrick
- **Shaded bands** on full timeseries and delta figures mark each sub-zero event period

---

## File Organization

```
SensorTower/
├── CLAUDE.md                         ← this file
├── data/                             ← raw CSV downloads (do not modify)
│   └── *.csv
├── scripts/
│   ├── __init__.py
│   ├── load_data.py                  ← reusable import module; import from all analysis scripts
│   ├── 02_plot_freeze_event.py       ← full Apr 19-21 2026 series, °C figures
│   └── 03_figures_fahrenheit.py      ← same figures in °F
└── outputs/                          ← all figures (°C and °F versions)
```

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/load_data.py` | Reusable module — loads all CSVs from `data/`, deduplicates by timestamp, parses dates, returns `(wide, long)`. Import this from all analysis scripts. |
| `scripts/02_plot_freeze_event.py` | Full Apr 19–21 2026 series in °C — 5 figures + console summary. Run from `SensorTower/`. |
| `scripts/03_figures_fahrenheit.py` | Same figures as script 02 but in °F. Saves with `_F` suffix. Run from `SensorTower/`. |

**Run from the `SensorTower/` directory:**
```
python scripts/02_plot_freeze_event.py
python scripts/03_figures_fahrenheit.py
```

---

## Figures Produced

| Filename | Description |
|----------|-------------|
| `fig1_full_timeseries.png` / `_F` | Complete series, all 9 sensors, shaded freeze events |
| `fig2_event_comparison.png` / `_F` | Side-by-side: Freeze Night 1 vs Night 2 detail |
| `fig3_delta_from_ground.png` / `_F` | Temperature departure from 2-in sensor |
| `fig4_heatmap.png` / `_F` | Height × time heatmap, nearest interpolation |
| `fig4b_heatmap_bilinear.png` / `_F` | Same heatmap, bilinear interpolation |

---

## Notes & Context

- **Single tower** positioned at the center of a 4-row apple block.
- Both apple and grapevine blocks are present at the site.
- Datalogger export filenames are just download names — not tower IDs. There is one tower.
- "Freeze events" refers to radiation frost nights (calm, clear, cold) where temperature inversions are most likely, as well as advective freeze events.
- Sensor heights above 122 in are above the apple canopy; near-ground sensors (2–42 in) capture the cold air drainage layer most relevant to radiation frost management.
- During radiation frost: **inversion signature** — 2 in colder than 162 in (ΔT from ground positive for upper sensors).
- During advective freeze or daytime: normal lapse rate — upper sensors similar to or cooler than ground.
- A thermal stratification boundary has been observed around 62–82 in (mid-canopy). Persists under bilinear interpolation, suggesting a real physical effect at the canopy interior boundary.

## Ongoing Data Summary

As new data files arrive, drop them into `data/`. The `load_tower_data()` function reads and deduplicates all CSVs automatically. New freeze events should get their own script (e.g., `04_plot_freeze_MMDD.py`) following the same pattern as `02_plot_freeze_event.py`, with a matching °F companion script.

### Events recorded so far

| Event | Date | Duration below 0°C at 2 in | Min temp (2 in) | Peak inversion |
|-------|------|---------------------------|-----------------|----------------|
| Freeze Night 1 | Apr 19–20, 2026 | 210 min | −2.0°C (28.4°F) | 0.47°C (1.5°F) |
| Reversed gradient blip | Apr 20, 2026 ~11:00 | 25 min | −0.9°C (30.4°F) | −0.56°C (upper colder) |
| Freeze Night 2 | Apr 20–21, 2026 | 685 min | −5.1°C (22.8°F) | 3.06°C (9.9°F) |
