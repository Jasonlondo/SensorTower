# SensorTower — Project Scope

**PI:** Jason Londo, Cornell AgriTech  
**Site:** Instrumented apple block, Cornell AgriTech experimental orchard/vineyard  
**Funding:** Internal / Cornell

---

## Research Question

How does temperature stratify vertically through an apple canopy during frost and freeze events, and how does that stratification translate into actual bud/flower exposure relative to critical damage thresholds?

---

## Objectives

1. **Characterize thermal inversions** — Quantify when and how strongly cold air pools near the ground vs. mixing upward during radiation frost events
2. **Map canopy-level freeze exposure** — Document temperatures buds and flowers at each canopy height actually experience during freeze events
3. **Threshold crossing analysis** — Calculate time spent below critical damage thresholds (0°C, −2.2°C, −4°C) for each canopy height and apple growth stage
4. **Gradient characterization** — Describe magnitude and timing of vertical gradients during frost vs. non-frost nights
5. **Grower-relevant outputs** — Produce visualizations communicating freeze risk in practical terms

---

## System

- **Crop:** Honeycrisp and Fuji apple, semi-dwarf planting system
- **Tower:** Single 9-sensor tower (2 in to 162 in; 20 in spacing; 5-min logging interval)
- **Events documented so far:** Apr 19–20 2026 (Freeze Night 1); Apr 20–21 2026 (Freeze Night 2)

---

## Critical Temperature Thresholds (Apple)

| Growth Stage    | 10% Kill (°C) | 90% Kill (°C) |
|-----------------|---------------|---------------|
| Silver tip      | −9.4          | −16.7         |
| Green tip       | −7.8          | −12.2         |
| Half-inch green | −5.0          | −9.4          |
| Tight cluster   | −2.8          | −6.1          |
| First pink      | −2.2          | −4.4          |
| Full pink       | −2.2          | −3.9          |
| First bloom     | −2.2          | −3.9          |
| Full bloom      | −2.2          | −3.9          |
| Post bloom      | −2.2          | −3.9          |

Source: MSU Extension, *Critical Spring Temperatures for Tree Fruit Bud Development Stages* (apple values from WSU EB0913, compiled by M. Longstroth). Native °F converted to °C.

---

## Methods

- 5-minute temperature data from 9 sensors (2–162 in) logged continuously
- Analysis in Python (pandas, matplotlib, numpy)
- Per-event scripts (one script per freeze event); reusable `load_data.py` module handles deduplication
- Figures produced in both °C and °F

---

## Expected Outputs

- Per-event figures: full timeseries, event detail comparison, delta-from-ground, heatmaps (nearest + bilinear)
- Summary metrics: duration below thresholds, minimum temps, peak inversion magnitude
- Grower-facing summaries (plain-language interpretation of stratification patterns)
- Eventual: publication or extension article on frost management implications of vertical stratification

---

## Status (2026-04-21)

- Tower deployed and operational
- Two freeze events analyzed (Apr 19–21, 2026)
- Python pipeline established (scripts 02 and 03)
- **Next:** New freeze events → add `04_plot_freeze_MMDD.py` + °F companion following existing pattern
