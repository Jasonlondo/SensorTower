"""
02_plot_freeze_event.py
Full Apr 19-21 2026 sensor tower series — two freeze nights.

Figures saved to outputs/:
  fig1_full_timeseries.png   — complete series, all 9 sensors, shaded freeze events
  fig2_event_comparison.png  — side-by-side: Event 1 vs Event 3 freeze detail
  fig3_delta_from_ground.png — departure from 2-in sensor, shaded freeze events
  fig4_heatmap.png           — height x time heatmap, all events annotated

Run from the SensorTower/ directory:
    python scripts/02_plot_freeze_event.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from scripts.load_data import load_tower_data, HEIGHTS, HEIGHT_COLS, THRESHOLDS

# ── Setup ─────────────────────────────────────────────────────────────────────

Path("outputs").mkdir(exist_ok=True)

wide, long = load_tower_data("data")

plt.rcParams.update({
    "figure.dpi": 150,
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})

PALETTE = plt.cm.viridis(np.linspace(0.05, 0.92, len(HEIGHTS)))
HEIGHT_COLORS = {col: PALETTE[i] for i, col in enumerate(HEIGHT_COLS)}

FREEZE_LINE_KW = dict(color="steelblue", linestyle="--", linewidth=1.0, alpha=0.8)
BLOOM_LINE_KW  = dict(color="firebrick", linestyle=":",  linewidth=1.0, alpha=0.9)
DATE_FMT_FULL  = mdates.DateFormatter("%b %d\n%H:%M")
DATE_FMT_HOUR  = mdates.DateFormatter("%H:%M")

# ── Freeze event windows ───────────────────────────────────────────────────────
# Two overnight freeze events (Apr 19-20 and Apr 20-21).
# There is also a brief 25-min reversed-gradient blip Apr 20 10:55-11:15
# which is noted on the heatmap but not treated as a separate named event.
#
#   Night 1: Apr 20 03:50-07:15  mild radiation frost inversion  (~3.5 hrs)
#   Night 2: Apr 20 19:50-Apr 21 07:10  major radiation frost    (~11.3 hrs)

EVENTS = {
    1: {
        "start":  pd.Timestamp("2026-04-20 03:50"),
        "end":    pd.Timestamp("2026-04-20 07:15"),
        "min_t":  pd.Timestamp("2026-04-20 06:15"),
        "label":  "Night 1\n(mild)",
        "color":  "#aec6e8",
        "detail_window": (pd.Timestamp("2026-04-20 01:45"),
                          pd.Timestamp("2026-04-20 09:15")),
    },
    2: {
        "start":  pd.Timestamp("2026-04-20 19:50"),
        "end":    pd.Timestamp("2026-04-21 07:10"),
        "min_t":  pd.Timestamp("2026-04-21 03:20"),
        "label":  "Night 2\n(severe)",
        "color":  "#6baed6",
        "detail_window": (pd.Timestamp("2026-04-20 17:00"),
                          pd.Timestamp("2026-04-21 10:00")),
    },
}

# Small mid-morning blip — used only for heatmap annotation
BLIP = {"start": pd.Timestamp("2026-04-20 10:55"),
        "end":   pd.Timestamp("2026-04-20 11:15")}


def shade_events(ax, events=EVENTS, ymin=-99, ymax=99):
    """Add translucent shaded bands for each freeze event."""
    for ev in events.values():
        ax.axvspan(mdates.date2num(ev["start"]),
                   mdates.date2num(ev["end"]),
                   color=ev["color"], alpha=0.35, zorder=0, label="_nolegend_")


# ── Figure 1: Full time series ────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(12, 5))

shade_events(ax)

for col in HEIGHT_COLS:
    ax.plot(wide["datetime"], wide[col],
            color=HEIGHT_COLORS[col], linewidth=0.8, alpha=0.85,
            label=col.replace("in", " in"))

ax.axhline(0,    label="0 °C (freezing)",          **FREEZE_LINE_KW)
ax.axhline(-2.2, label="-2.2 °C (full bloom kill)", **BLOOM_LINE_KW)

ax.xaxis.set_major_formatter(DATE_FMT_FULL)
ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
ax.set_ylabel("Temperature (°C)")
ax.set_title("Sensor tower — Apr 19-21, 2026 | Shaded = sub-zero periods at 2-in sensor")

handles, labels = ax.get_legend_handles_labels()
# Sensor entries reversed (162 in at top → 2 in at bottom); threshold lines appended after
sensor_h = handles[:9][::-1];  sensor_l = labels[:9][::-1]
other_h  = handles[9:];        other_l  = labels[9:]
ax.legend(sensor_h + other_h, sensor_l + other_l,
          fontsize=8, ncol=1, loc="upper right", framealpha=0.7)

# Add event labels directly on shaded bands
for ev_id, ev in EVENTS.items():
    if ev["label"]:
        mid = ev["start"] + (ev["end"] - ev["start"]) / 2
        ax.text(mdates.date2num(mid), -5.3,
                ev["label"], ha="center", va="bottom", fontsize=7.5,
                color="navy", fontweight="bold")

fig.tight_layout()
fig.savefig("outputs/fig1_full_timeseries.png")
plt.close(fig)
print("Saved fig1_full_timeseries.png")


# ── Figure 2: Side-by-side event comparison ───────────────────────────────────

fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)

night_titles = {
    1: "Freeze Night 1 — Apr 19-20 (mild)",
    2: "Freeze Night 2 — Apr 20-21 (severe)",
}

for ax, (ev_id, ev) in zip(axes, EVENTS.items()):
    w_start, w_end = ev["detail_window"]
    wd = wide[(wide["datetime"] >= w_start) & (wide["datetime"] <= w_end)]

    for col in HEIGHT_COLS:
        ax.plot(wd["datetime"], wd[col],
                color=HEIGHT_COLORS[col], linewidth=1.0,
                marker="o", markersize=2.0, alpha=0.85,
                label=col.replace("in", " in"))

    ax.axhline(0,    **FREEZE_LINE_KW)
    ax.axhline(-2.2, **BLOOM_LINE_KW)
    ax.axvspan(mdates.date2num(ev["start"]), mdates.date2num(ev["end"]),
               color=ev["color"], alpha=0.3, zorder=0)

    ax.xaxis.set_major_formatter(DATE_FMT_FULL)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    peak_inv = (wd["162in"] - wd["2in"]).max()
    title = (f"{night_titles[ev_id]}\n"
             f"Min 2 in: {wd['2in'].min():.1f} °C | Peak inversion: {peak_inv:.2f} °C")
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("Time (EDT)")

axes[0].set_ylabel("Temperature (°C)")
# Legend inside Night 1 panel (upper right — warm, unshaded zone)
# Reversed so highest sensor (162 in) appears at top
handles, labels = axes[0].get_legend_handles_labels()
sensor_h, sensor_l = handles[:9][::-1], labels[:9][::-1]
axes[1].legend(sensor_h, sensor_l, fontsize=8, ncol=1,
               loc="upper right", framealpha=0.8)
fig.suptitle("Freeze event comparison | Dashed = 0 °C | Dotted = -2.2 °C (full bloom kill)",
             fontsize=11, y=1.01)

fig.tight_layout()
fig.savefig("outputs/fig2_event_comparison.png", bbox_inches="tight")
plt.close(fig)
print("Saved fig2_event_comparison.png")


# ── Figure 3: Delta from ground ───────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(12, 5))

shade_events(ax)
ax.axhline(0, color="black", linewidth=0.8, alpha=0.5)

for col in HEIGHT_COLS[1:]:
    delta = wide[col] - wide["2in"]
    ax.plot(wide["datetime"], delta,
            color=HEIGHT_COLORS[col], linewidth=0.8, alpha=0.85,
            label=col.replace("in", " in"))

ax.xaxis.set_major_formatter(DATE_FMT_FULL)
ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
ax.set_ylabel("DT from 2-in sensor (°C)")
ax.set_title("Temperature departure from ground level (2 in)\n"
             "Positive = warmer than ground (inversion) | Shaded = sub-zero periods")

handles, labels = ax.get_legend_handles_labels()
ax.legend(handles[::-1], labels[::-1], fontsize=8, ncol=1, loc="upper right", framealpha=0.7)

fig.tight_layout()
fig.savefig("outputs/fig3_delta_from_ground.png")
plt.close(fig)
print("Saved fig3_delta_from_ground.png")


# ── Figure 4: Heatmap (nearest + bilinear versions) ──────────────────────────

matrix = wide.set_index("datetime")[HEIGHT_COLS].T
matrix.index = HEIGHTS

vmin = np.floor(long["temp_c"].min())
vmax = np.ceil(long["temp_c"].max())
norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

frac_below = (0 - vmin) / (vmax - vmin)
n = 512
n_below = int(round(frac_below * n))
positions = np.concatenate([
    np.linspace(0.0, 0.5, n_below, endpoint=False),
    np.linspace(0.5, 1.0, n - n_below),
])
cmap = mcolors.LinearSegmentedColormap.from_list(
    "RdYlBu_shifted", plt.cm.RdYlBu_r(positions), N=512
)

annot_kw = dict(fontsize=8, color="black", fontweight="bold",
                ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.3", fc="white",
                          ec="black", lw=0.8, alpha=0.75))
arrow_kw = dict(arrowstyle="-|>", color="black", lw=1.0)


def make_heatmap(interp, fname):
    fig, ax = plt.subplots(figsize=(13, 5))

    im = ax.imshow(
        matrix.values,
        aspect="auto",
        origin="lower",
        extent=[
            mdates.date2num(wide["datetime"].iloc[0]),
            mdates.date2num(wide["datetime"].iloc[-1]),
            0, len(HEIGHTS)
        ],
        norm=norm,
        cmap=cmap,
        interpolation=interp,
    )

    ax.xaxis_date()
    ax.xaxis.set_major_formatter(DATE_FMT_FULL)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    ax.set_yticks(np.arange(len(HEIGHTS)) + 0.5)
    ax.set_yticklabels([f"{h} in  ({h/12:.1f} ft)" for h in HEIGHTS], fontsize=8)
    ax.set_ylabel("Height above ground")
    ax.set_title(f"Temperature heatmap — sensor tower Apr 19-21, 2026\n"
                 f"Each row = one sensor | Color = temperature (°C) | interpolation: {interp}")

    cb = fig.colorbar(im, ax=ax, pad=0.01, shrink=0.9)
    cb.set_ticks(np.arange(int(vmin), int(vmax) + 1, 1))
    cb.set_label("°C")

    x1 = mdates.date2num(pd.Timestamp("2026-04-20 05:30"))
    ax.annotate("Freeze Night 1\nRadiation frost\n(ground coldest)",
                xy=(x1, 0.5), xytext=(x1, 5.5),
                arrowprops=dict(**arrow_kw, connectionstyle="arc3,rad=0.0"), **annot_kw)

    x2 = mdates.date2num(pd.Timestamp("2026-04-20 11:05"))
    ax.annotate("Reversed\ngradient",
                xy=(x2, 8.5), xytext=(x2, 6.0),
                arrowprops=dict(**arrow_kw, connectionstyle="arc3,rad=0.0"), **annot_kw)

    x3 = mdates.date2num(pd.Timestamp("2026-04-21 03:15"))
    ax.annotate("Freeze Night 2\nMajor frost\n(ground coldest)",
                xy=(x3, 0.5), xytext=(x3, 5.5),
                arrowprops=dict(**arrow_kw, connectionstyle="arc3,rad=0.0"), **annot_kw)

    fig.tight_layout()
    fig.savefig(f"outputs/{fname}")
    plt.close(fig)
    print(f"Saved {fname}")


make_heatmap("nearest",  "fig4_heatmap.png")
make_heatmap("bilinear", "fig4b_heatmap_bilinear.png")


# ── Console summary ───────────────────────────────────────────────────────────

print("\n=== Freeze Event Summary — Apr 19-21, 2026 ===\n")

for ev_id, ev in EVENTS.items():
    wd = wide[(wide["datetime"] >= ev["start"]) & (wide["datetime"] <= ev["end"])]
    print(f"--- Freeze Night {ev_id} ({ev['start'].strftime('%b %d %H:%M')} to {ev['end'].strftime('%b %d %H:%M')}) ---")
    print(f"  Duration below 0 at 2 in: {len(wd) * 5} min")
    print(f"  Peak inversion (162in - 2in): {(wd['162in'] - wd['2in']).max():.2f} C")
    print(f"  {'Height':>8}  {'Min (C)':>8}  {'Time of min':>12}  {'Min below 0 (min)':>18}")
    for col, h in zip(HEIGHT_COLS, HEIGHTS):
        idx = wd[col].idxmin()
        t   = wide.loc[idx, "datetime"].strftime("%H:%M")
        sub = int((wd[col] < 0).sum() * 5)
        print(f"  {col:>8}  {wd[col].min():>8.2f}  {t:>12}  {sub:>18}")
    print()
