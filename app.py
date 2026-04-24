"""
Sensor Tower — Streamlit app.

Deployed to Streamlit Community Cloud. Data comes from CSVs committed to the repo,
refreshed daily by the GitHub Actions workflow (.github/workflows/daily_pull.yml).

Run locally:
    streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from scripts.data_loader import (
    HEIGHTS,
    THRESHOLDS,
    LOCAL_TZ,
    load_all,
    load_newa,
    wide_temperature,
)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SENSOR_MAP_PATH = ROOT / "sensor_map.csv"

st.set_page_config(
    page_title="Sensor Tower — Apple Canopy Frost Monitor",
    page_icon="🌡️",
    layout="wide",
)


@st.cache_data(ttl=600)
def cached_load_all() -> pd.DataFrame:
    return load_all(DATA_DIR, SENSOR_MAP_PATH)


@st.cache_data(ttl=600)
def cached_load_newa() -> pd.DataFrame:
    return load_newa(DATA_DIR)


def c_to_f(c: float | pd.Series) -> float | pd.Series:
    return c * 9 / 5 + 32


def show_chart(fig: go.Figure, yformat: str = ".2f") -> None:
    """Render a Plotly figure with consistent tick and hover formatting.

    yformat: Plotly d3-format string for y-axis ticks and hovers.
    Temperature charts use ".2f" (default). Integer-valued charts (e.g.,
    minutes exposure) use ".0f".
    """
    fig.update_yaxes(tickformat=yformat, hoverformat=yformat)
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------- Sidebar ----------------------------
st.sidebar.title("🌡️ Sensor Tower")
st.sidebar.caption("Cornell AgriTech — Honeycrisp/Fuji apple block")

df = cached_load_all()
if df.empty:
    st.error("No data available yet. Check that CSVs exist in `data/` and that the daily pull has run.")
    st.stop()

units = st.sidebar.radio("Units", ["°C", "°F"], horizontal=True)
is_f = units == "°F"

# Date range
min_dt = df["datetime_local"].min()
max_dt = df["datetime_local"].max()
default_start = max(min_dt, max_dt - pd.Timedelta(days=7))
date_range = st.sidebar.date_input(
    "Date range",
    value=(default_start.date(), max_dt.date()),
    min_value=min_dt.date(),
    max_value=max_dt.date(),
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_d, end_d = date_range
else:
    start_d = end_d = date_range  # type: ignore[assignment]

start_ts = pd.Timestamp(start_d, tz=LOCAL_TZ)
end_ts = pd.Timestamp(end_d, tz=LOCAL_TZ) + pd.Timedelta(days=1)

mask = (df["datetime_local"] >= start_ts) & (df["datetime_local"] < end_ts)
df_win = df.loc[mask].copy()

st.sidebar.caption(
    f"Full record: {min_dt.strftime('%Y-%m-%d')} → {max_dt.strftime('%Y-%m-%d')} "
    f"({df['datetime_local'].nunique():,} timestamps)"
)

page = st.sidebar.radio(
    "View",
    [
        "Overview",
        "Time series",
        "Inversions",
        "Threshold exposure",
        "Humidity & dew point",
        "NEWA comparison",
    ],
)

# ---------------------------- Temperature frames ----------------------------
temp_long = df_win[df_win["measurement_type"] == "Temperature"].copy()
wide_c = wide_temperature(temp_long).set_index("datetime_local").sort_index()
if is_f:
    wide_disp = wide_c.apply(c_to_f)
    unit_label = "°F"
    freeze_line = 32.0
    bloom_line = c_to_f(-2.2)
else:
    wide_disp = wide_c
    unit_label = "°C"
    freeze_line = 0.0
    bloom_line = -2.2

height_cols = [h for h in HEIGHTS if h in wide_disp.columns]

# ---------------------------- Pages ----------------------------
if page == "Overview":
    st.header("Current conditions")
    if not wide_c.empty:
        latest_ts = wide_c.index.max()
        latest_row_c = wide_c.loc[latest_ts]
        latest_row_disp = wide_disp.loc[latest_ts]
        st.caption(f"Latest reading: **{latest_ts.strftime('%Y-%m-%d %H:%M %Z')}**")

        cols = st.columns(len(height_cols))
        ref = latest_row_disp.get(2, latest_row_disp.iloc[0])
        for col, h in zip(cols, height_cols):
            val = latest_row_disp[h]
            delta_raw = val - ref
            if h == 2:
                delta_html = "&nbsp;"
                delta_color = "#888"
            else:
                delta_html = f"{delta_raw:+.2f}"
                delta_color = "#2c974b" if delta_raw > 0 else ("#cf222e" if delta_raw < 0 else "#888")
            col.markdown(
                f"""
                <div style="text-align:center; padding:4px 0; border-left:1px solid rgba(128,128,128,0.15);">
                  <div style="font-size:0.75rem; color:#888; letter-spacing:0.5px;">{h} in</div>
                  <div style="font-size:1.15rem; font-weight:600; margin:2px 0;">{val:.2f}<span style="font-size:0.7rem; color:#888; margin-left:2px;">{unit_label}</span></div>
                  <div style="font-size:0.7rem; color:{delta_color};">{delta_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Current inversion state
        top_mean = latest_row_c[[h for h in [122, 142, 162] if h in wide_c.columns]].mean()
        bot_min = latest_row_c[[h for h in [2, 22, 42] if h in wide_c.columns]].min()
        inv_c = top_mean - bot_min
        inv_disp = inv_c * 9 / 5 if is_f else inv_c
        state = "inversion (ground colder than aloft)" if inv_c > 0.3 else (
            "well-mixed" if abs(inv_c) <= 0.3 else "unstable (ground warmer than aloft)"
        )
        st.info(f"Vertical gradient: **{inv_disp:+.2f} {unit_label}** aloft minus ground  →  {state}")

    st.header("Tower at a glance")
    if not wide_disp.empty:
        recent = wide_disp.tail(24 * 12)  # last ~24h at 5-min cadence
        fig = go.Figure()
        palette = px.colors.sequential.Viridis
        for i, h in enumerate(height_cols):
            color = palette[int(i / max(len(height_cols) - 1, 1) * (len(palette) - 1))]
            fig.add_trace(
                go.Scatter(
                    x=recent.index, y=recent[h], mode="lines",
                    name=f"{h} in", line=dict(color=color),
                )
            )
        fig.add_hline(y=freeze_line, line_dash="dash", line_color="steelblue",
                      annotation_text=f"Freeze ({freeze_line:g} {unit_label})")
        fig.add_hline(y=bloom_line, line_dash="dot", line_color="firebrick",
                      annotation_text=f"Full bloom 10% kill ({bloom_line:.1f} {unit_label})")
        fig.update_layout(
            height=450, margin=dict(l=30, r=10, t=30, b=30),
            xaxis_title="Local time", yaxis_title=f"Temperature ({unit_label})",
            legend=dict(traceorder="reversed"),
        )
        show_chart(fig)


elif page == "Time series":
    st.header(f"Full time series ({unit_label})")
    if wide_disp.empty:
        st.warning("No temperature data in selected window.")
    else:
        fig = go.Figure()
        palette = px.colors.sequential.Viridis
        for i, h in enumerate(height_cols):
            color = palette[int(i / max(len(height_cols) - 1, 1) * (len(palette) - 1))]
            fig.add_trace(
                go.Scatter(
                    x=wide_disp.index, y=wide_disp[h], mode="lines",
                    name=f"{h} in", line=dict(color=color),
                )
            )
        fig.add_hline(y=freeze_line, line_dash="dash", line_color="steelblue")
        fig.add_hline(y=bloom_line, line_dash="dot", line_color="firebrick")
        fig.update_layout(
            height=550, margin=dict(l=30, r=10, t=30, b=30),
            xaxis_title="Local time", yaxis_title=f"Temperature ({unit_label})",
            legend=dict(traceorder="reversed"),
        )
        show_chart(fig)

    st.subheader("Delta from ground (2 in)")
    if 2 in wide_disp.columns:
        delta = wide_disp.subtract(wide_disp[2], axis=0)
        fig2 = go.Figure()
        for i, h in enumerate(height_cols):
            if h == 2:
                continue
            color = palette[int(i / max(len(height_cols) - 1, 1) * (len(palette) - 1))]
            fig2.add_trace(
                go.Scatter(
                    x=delta.index, y=delta[h], mode="lines",
                    name=f"{h} in", line=dict(color=color),
                )
            )
        fig2.add_hline(y=0, line_color="black", line_width=1)
        fig2.update_layout(
            height=400, margin=dict(l=30, r=10, t=30, b=30),
            xaxis_title="Local time", yaxis_title=f"ΔT from 2in ({unit_label})",
            legend=dict(traceorder="reversed"),
        )
        show_chart(fig2)


elif page == "Inversions":
    st.header(f"Vertical temperature gradient ({unit_label})")
    if wide_disp.empty:
        st.warning("No temperature data in selected window.")
    else:
        top_mean = wide_disp[[h for h in [122, 142, 162] if h in wide_disp.columns]].mean(axis=1)
        bot_min = wide_disp[[h for h in [2, 22, 42] if h in wide_disp.columns]].min(axis=1)
        gradient = top_mean - bot_min

        # Identify contiguous freezing-inversion periods:
        #   gradient > 0.3 (real inversion) AND ground min below freezing
        freezing_inv = (gradient > 0.3) & (bot_min < freeze_line)
        # Convert to (start, end) pairs of contiguous runs
        runs = []
        in_run = False
        run_start = None
        idx = freezing_inv.index
        for i, flag in enumerate(freezing_inv.values):
            if flag and not in_run:
                run_start = idx[i]
                in_run = True
            elif not flag and in_run:
                runs.append((run_start, idx[i - 1]))
                in_run = False
        if in_run:
            runs.append((run_start, idx[-1]))

        fig = go.Figure()
        # Shade freezing-inversion intervals first so lines draw on top
        for rs, re_ in runs:
            fig.add_vrect(
                x0=rs, x1=re_,
                fillcolor="rgba(135, 206, 250, 0.28)",  # icy blue
                line_width=0, layer="below",
            )
        fig.add_trace(
            go.Scatter(
                x=gradient.index, y=gradient, mode="lines",
                name="Gradient (top mean − ground min)",
                line=dict(color="black"),
            )
        )
        fig.add_hline(y=0, line_color="black", line_width=1)
        caption = (
            f"Shaded periods: inversion AND ground below {freeze_line:g} {unit_label} — "
            f"{len(runs)} event{'' if len(runs)==1 else 's'} in window."
        )
        fig.update_layout(
            height=400, margin=dict(l=30, r=10, t=30, b=30),
            xaxis_title="Local time",
            yaxis_title=f"Aloft minus ground ({unit_label})",
        )
        show_chart(fig)
        st.caption(caption)

        st.subheader("Heatmap")
        z = wide_disp[height_cols].T.values
        fig2 = go.Figure(
            data=go.Heatmap(
                z=z,
                x=wide_disp.index,
                y=[f"{h} in" for h in height_cols],
                colorscale="RdYlBu_r",
                zmid=freeze_line,
                colorbar=dict(title=unit_label),
            )
        )
        fig2.update_layout(
            height=400, margin=dict(l=30, r=10, t=30, b=30),
            xaxis_title="Local time",
            yaxis_title="Height",
        )
        show_chart(fig2)

        st.subheader("Peak inversion events")
        # Find the top-10 inversion peaks, separated by ≥3h
        sorted_g = gradient.sort_values(ascending=False)
        peaks = []
        for ts, val in sorted_g.items():
            if val <= 0.3:
                break
            if all(abs((ts - p[0]).total_seconds()) >= 3 * 3600 for p in peaks):
                peaks.append((ts, val))
            if len(peaks) >= 10:
                break
        if peaks:
            peak_df = pd.DataFrame(
                {
                    "timestamp": [p[0].strftime("%Y-%m-%d %H:%M %Z") for p in peaks],
                    f"gradient ({unit_label})": [f"{p[1]:.2f}" for p in peaks],
                }
            )
            st.dataframe(peak_df, use_container_width=True, hide_index=True)
        else:
            st.info("No significant inversions (>0.3°C) in the selected window.")


elif page == "Threshold exposure":
    st.header("Time below apple bloom-stage kill thresholds")
    if wide_c.empty:
        st.warning("No temperature data in selected window.")
    else:
        stages = list(THRESHOLDS.keys())
        default_idx = stages.index("Full bloom") if "Full bloom" in stages else 0
        stage = st.selectbox("Bloom stage", stages, index=default_idx)
        th_c = THRESHOLDS[stage]
        st.caption(
            f"10% kill: **{th_c['kill10']:.1f}°C** ({c_to_f(th_c['kill10']):.1f}°F) | "
            f"90% kill: **{th_c['kill90']:.1f}°C** ({c_to_f(th_c['kill90']):.1f}°F) · "
            f"Source: [MSU Extension bud-stage table]"
            f"(https://www.canr.msu.edu/fruit/uploads/files/PictureTableofFruitFreezeDamageThresholds.pdf) "
            f"(apple data from WSU EB0913, compiled by M. Longstroth)."
        )

        dt = wide_c.index.to_series().diff().dt.total_seconds().fillna(300)
        rows = []
        for h in height_cols:
            col = wide_c[h]
            below_10 = (col <= th_c["kill10"]) * dt
            below_90 = (col <= th_c["kill90"]) * dt
            rows.append(
                {
                    "Height": f"{h} in",
                    f"Min temp ({unit_label})": f"{(c_to_f(col.min()) if is_f else col.min()):.2f}",
                    "Min in °C": f"{col.min():.2f}",
                    "Minutes ≤ 10% kill": int(below_10.sum() // 60),
                    "Minutes ≤ 90% kill": int(below_90.sum() // 60),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.subheader("Minutes per day below 10% kill threshold")
        # Attribute each interval to the day it started in (local time)
        days = wide_c.index.normalize()
        per_day = {}
        for i, h in enumerate(height_cols):
            mins = ((wide_c[h] <= th_c["kill10"]) * dt / 60)
            per_day[h] = mins.groupby(days).sum()
        per_day_df = pd.DataFrame(per_day)
        per_day_df = per_day_df.loc[(per_day_df.sum(axis=1) > 0)]  # drop zero-exposure days

        if per_day_df.empty:
            st.info("No exposure to 10% kill threshold in the selected window.")
        else:
            fig = go.Figure()
            palette = px.colors.sequential.Viridis
            for i, h in enumerate(height_cols):
                color = palette[int(i / max(len(height_cols) - 1, 1) * (len(palette) - 1))]
                fig.add_trace(
                    go.Bar(
                        x=per_day_df.index, y=per_day_df[h],
                        name=f"{h} in", marker_color=color,
                    )
                )
            fig.update_layout(
                barmode="group",
                height=400, margin=dict(l=30, r=10, t=30, b=50),
                xaxis_title="Date (local)",
                yaxis=dict(
                    title="Minutes ≤ 10% kill",
                    range=[0, 720],           # fixed 0–12 hours across stages
                    dtick=60,                  # major gridline every 60 min
                    minor=dict(dtick=30, showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
                    showgrid=True, gridcolor="rgba(128,128,128,0.35)",
                ),
                yaxis2=dict(
                    title="Hours",
                    range=[0, 12],
                    dtick=1,
                    overlaying="y",
                    side="right",
                    showgrid=False,            # suppress duplicate gridlines
                ),
                legend=dict(traceorder="reversed"),
                bargap=0.15, bargroupgap=0.02,
            )
            show_chart(fig, yformat=".0f")


elif page == "Humidity & dew point":
    st.header("Humidity & dew point")
    rh = df_win[df_win["measurement_type"] == "RH"]
    dp = df_win[df_win["measurement_type"] == "Dew Point"]
    if rh.empty and dp.empty:
        st.warning("Humidity/dew point are only in API-pulled data. Run the daily pull or wait for the next scheduled run.")
    else:
        if not rh.empty:
            st.subheader("Relative humidity (%)")
            rh_wide = rh.pivot_table(
                index="datetime_local", columns="height_in", values="value", aggfunc="last"
            ).sort_index()
            fig = go.Figure()
            palette = px.colors.sequential.Viridis
            rh_cols = [h for h in HEIGHTS if h in rh_wide.columns]
            for i, h in enumerate(rh_cols):
                color = palette[int(i / max(len(rh_cols) - 1, 1) * (len(palette) - 1))]
                fig.add_trace(
                    go.Scatter(x=rh_wide.index, y=rh_wide[h], mode="lines",
                               name=f"{h} in", line=dict(color=color))
                )
            fig.update_layout(
                height=400, margin=dict(l=30, r=10, t=30, b=30),
                xaxis_title="Local time", yaxis_title="RH (%)",
                legend=dict(traceorder="reversed"),
            )
            show_chart(fig)

        if not dp.empty:
            st.subheader(f"Dew point ({unit_label})")
            dp_wide = dp.pivot_table(
                index="datetime_local", columns="height_in", values="value", aggfunc="last"
            ).sort_index()
            if is_f:
                dp_wide = dp_wide.apply(c_to_f)
            fig = go.Figure()
            palette = px.colors.sequential.Viridis
            dp_cols = [h for h in HEIGHTS if h in dp_wide.columns]
            for i, h in enumerate(dp_cols):
                color = palette[int(i / max(len(dp_cols) - 1, 1) * (len(palette) - 1))]
                fig.add_trace(
                    go.Scatter(x=dp_wide.index, y=dp_wide[h], mode="lines",
                               name=f"{h} in", line=dict(color=color))
                )
            fig.update_layout(
                height=400, margin=dict(l=30, r=10, t=30, b=30),
                xaxis_title="Local time", yaxis_title=f"Dew point ({unit_label})",
                legend=dict(traceorder="reversed"),
            )
            show_chart(fig)


elif page == "NEWA comparison":
    st.header("Tower vs NEWA (Geneva AgriTech Gates)")
    st.caption(
        "Our tower at 5-min logging, LI-COR HOBO RX2100, versus the co-located "
        "NEWA Cornell AgriTech Gates station at 1-hour cadence. NEWA sensors are "
        "at ~1.5 m / 59 in standard height, closest to our **62 in** mid-canopy sensor."
    )

    newa_all = cached_load_newa()
    if newa_all.empty:
        st.warning(
            "No NEWA data yet. The daily workflow pulls it on the same schedule as the tower data."
        )
    else:
        newa_win = newa_all[
            (newa_all["datetime_local"] >= start_ts)
            & (newa_all["datetime_local"] < end_ts)
        ].copy()
        if newa_win.empty:
            st.info("No NEWA data in the selected date range.")
        else:
            tower_height = st.selectbox(
                "Tower height to compare",
                height_cols,
                index=height_cols.index(62) if 62 in height_cols else 0,
            )
            tower_series_c = (
                wide_c[tower_height].resample("1h").mean()
                if not wide_c.empty else pd.Series(dtype=float)
            )
            newa_temp = (
                newa_win[newa_win["variable"] == "Temperature"]
                .set_index("datetime_local")["value"]
            )
            newa_rh = (
                newa_win[newa_win["variable"] == "RH"]
                .set_index("datetime_local")["value"]
            )
            newa_dp = (
                newa_win[newa_win["variable"] == "Dew Point"]
                .set_index("datetime_local")["value"]
            )

            # Convert to display units
            if is_f:
                tower_disp = c_to_f(tower_series_c)
                newa_temp_disp = c_to_f(newa_temp)
                newa_dp_disp = c_to_f(newa_dp)
            else:
                tower_disp = tower_series_c
                newa_temp_disp = newa_temp
                newa_dp_disp = newa_dp

            # --- Overlay chart ---
            st.subheader(f"Temperature overlay — tower {tower_height} in vs NEWA")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=tower_disp.index, y=tower_disp, mode="lines",
                name=f"Tower {tower_height} in", line=dict(color="#1f77b4", width=2),
            ))
            fig.add_trace(go.Scatter(
                x=newa_temp_disp.index, y=newa_temp_disp, mode="lines+markers",
                name="NEWA (AgriTech Gates)", line=dict(color="#d62728", width=2, dash="dash"),
                marker=dict(size=4),
            ))
            fig.add_hline(y=freeze_line, line_dash="dot", line_color="steelblue")
            fig.update_layout(
                height=420, margin=dict(l=30, r=10, t=30, b=30),
                xaxis_title="Local time",
                yaxis_title=f"Temperature ({unit_label})",
            )
            show_chart(fig)

            # --- Agreement statistics ---
            st.subheader("Agreement statistics (hourly)")
            stats_rows = []
            for h in height_cols:
                tower_h = wide_c[h].resample("1h").mean() if h in wide_c.columns else pd.Series(dtype=float)
                aligned = pd.concat(
                    [tower_h.rename("tower"), newa_temp.rename("newa")], axis=1
                ).dropna()
                if aligned.empty:
                    continue
                diff = aligned["tower"] - aligned["newa"]
                stats_rows.append({
                    "Height": f"{h} in",
                    "n hours": len(aligned),
                    "Bias °C (tower − NEWA)": round(diff.mean(), 2),
                    "RMSE °C": round((diff ** 2).mean() ** 0.5, 2),
                    "Correlation": round(aligned.corr().iloc[0, 1], 4),
                })
            if stats_rows:
                st.dataframe(pd.DataFrame(stats_rows), use_container_width=True, hide_index=True)
                st.caption(
                    "Positive bias = tower warmer than NEWA. Near-ground sensors (2–22 in) "
                    "typically show larger bias during radiation frost because NEWA's 1.5 m "
                    "sensor sits above the coldest near-surface layer."
                )

            # --- Scatter 1:1 ---
            st.subheader(f"Scatter — tower {tower_height} in vs NEWA")
            scatter = pd.concat(
                [tower_series_c.rename("tower"), newa_temp.rename("newa")], axis=1
            ).dropna()
            if not scatter.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=scatter["newa"], y=scatter["tower"], mode="markers",
                    marker=dict(size=6, color="#1f77b4", opacity=0.7),
                    name="Hourly pairs",
                ))
                lo = min(scatter["newa"].min(), scatter["tower"].min()) - 1
                hi = max(scatter["newa"].max(), scatter["tower"].max()) + 1
                fig.add_trace(go.Scatter(
                    x=[lo, hi], y=[lo, hi], mode="lines",
                    line=dict(color="gray", dash="dash"), name="1:1",
                ))
                fig.update_layout(
                    height=420, margin=dict(l=30, r=10, t=30, b=30),
                    xaxis_title="NEWA temperature (°C)",
                    yaxis_title=f"Tower {tower_height} in (°C)",
                    xaxis=dict(range=[lo, hi]), yaxis=dict(range=[lo, hi]),
                )
                show_chart(fig)

            # --- RH & dew point ---
            st.subheader("Relative humidity & dew point")
            cols = st.columns(2)
            if not newa_rh.empty:
                rh_fig = go.Figure()
                rh_fig.add_trace(go.Scatter(
                    x=newa_rh.index, y=newa_rh, mode="lines",
                    name="NEWA RH", line=dict(color="#d62728"),
                ))
                # Tower RH at the selected height (if API pulls exist)
                tower_rh = df_win[
                    (df_win["measurement_type"] == "RH")
                    & (df_win["height_in"] == tower_height)
                ].set_index("datetime_local")["value"].resample("1h").mean()
                if not tower_rh.empty:
                    rh_fig.add_trace(go.Scatter(
                        x=tower_rh.index, y=tower_rh, mode="lines",
                        name=f"Tower {tower_height} in RH", line=dict(color="#1f77b4"),
                    ))
                rh_fig.update_layout(
                    height=320, margin=dict(l=30, r=10, t=30, b=30),
                    xaxis_title="Local time", yaxis_title="RH (%)",
                )
                cols[0].plotly_chart(rh_fig, use_container_width=True)

            if not newa_dp.empty:
                dp_fig = go.Figure()
                dp_fig.add_trace(go.Scatter(
                    x=newa_dp_disp.index, y=newa_dp_disp, mode="lines",
                    name="NEWA Dew point", line=dict(color="#d62728"),
                ))
                tower_dp = df_win[
                    (df_win["measurement_type"] == "Dew Point")
                    & (df_win["height_in"] == tower_height)
                ].set_index("datetime_local")["value"].resample("1h").mean()
                if not tower_dp.empty:
                    if is_f:
                        tower_dp = c_to_f(tower_dp)
                    dp_fig.add_trace(go.Scatter(
                        x=tower_dp.index, y=tower_dp, mode="lines",
                        name=f"Tower {tower_height} in DP", line=dict(color="#1f77b4"),
                    ))
                dp_fig.update_layout(
                    height=320, margin=dict(l=30, r=10, t=30, b=30),
                    xaxis_title="Local time", yaxis_title=f"Dew point ({unit_label})",
                )
                cols[1].plotly_chart(dp_fig, use_container_width=True)


st.sidebar.markdown("---")
st.sidebar.caption("Data refreshed daily via GitHub Actions. Last commit drives freshness.")
