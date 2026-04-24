"""
Unified data loader: merges legacy datalogger CSVs (wide format, temperature only)
and new LI-COR API pulls (long format, temperature + RH + dew point).

Legacy CSV format:
    Date, 2in, 22in, 42in, ..., 162in   (temperature °C, local EDT)

API pull format (one file per day, long format):
    timestamp_utc, sensor_sn, measurement_type, data_type, units, value

Returns a normalized long DataFrame keyed on (datetime_local, height_in, measurement_type)
and a wide temperature DataFrame for backward compatibility with existing scripts.
"""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

HEIGHTS = [2, 22, 42, 62, 82, 102, 122, 142, 162]
HEIGHT_COLS = [f"{h}in" for h in HEIGHTS]
LOCAL_TZ = ZoneInfo("America/New_York")

INSTALL_LOCAL = pd.Timestamp("2026-04-19 16:00", tz=LOCAL_TZ)

# Apple bloom-stage critical temps (°C).
# Source: MSU Extension "Critical Spring Temperatures for Tree Fruit Bud
# Development Stages" (compiled by Mark Longstroth from WSU EB0913).
# https://www.canr.msu.edu/fruit/uploads/files/PictureTableofFruitFreezeDamageThresholds.pdf
# Native source units are °F; values below are converted from the
# published °F table (shown in the trailing comment).
THRESHOLDS = {
    "Silver tip":        {"kill10":  -9.44, "kill90": -16.67},  # 15°F / 2°F
    "Green tip":         {"kill10":  -7.78, "kill90": -12.22},  # 18°F / 10°F
    "Half-inch green":   {"kill10":  -5.00, "kill90":  -9.44},  # 23°F / 15°F
    "Tight cluster":     {"kill10":  -2.78, "kill90":  -6.11},  # 27°F / 21°F
    "First pink":        {"kill10":  -2.22, "kill90":  -4.44},  # 28°F / 24°F
    "Full pink":         {"kill10":  -2.22, "kill90":  -3.89},  # 28°F / 25°F
    "First bloom":       {"kill10":  -2.22, "kill90":  -3.89},  # 28°F / 25°F
    "Full bloom":        {"kill10":  -2.22, "kill90":  -3.89},  # 28°F / 25°F
    "Post bloom":        {"kill10":  -2.22, "kill90":  -3.89},  # 28°F / 25°F
}


def load_sensor_map(path: str | Path = "sensor_map.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"sensor_sn": str})
    df["sensor_sn"] = df["sensor_sn"].astype(str).str.strip()
    df["height_in"] = df["height_in"].astype(int)
    return df


def _load_legacy_csvs(data_dir: Path) -> pd.DataFrame:
    """Load datalogger-style wide CSVs. Returns long DataFrame."""
    files = sorted(data_dir.glob("*.csv"))
    legacy = [f for f in files if not f.name.startswith("licor_")]
    if not legacy:
        return pd.DataFrame(
            columns=["datetime_local", "height_in", "measurement_type", "value", "units", "source"]
        )

    frames = []
    for f in legacy:
        df = pd.read_csv(f, skipinitialspace=True)
        df.columns = df.columns.str.strip()
        if "Date" not in df.columns:
            continue
        df["datetime_local"] = pd.to_datetime(
            df["Date"].astype(str).str.strip(), format="%y-%m-%d %H:%M:%S"
        ).dt.tz_localize(LOCAL_TZ)
        df = df.drop(columns=["Date"])
        present_heights = [c for c in HEIGHT_COLS if c in df.columns]
        melted = df.melt(
            id_vars=["datetime_local"],
            value_vars=present_heights,
            var_name="height_label",
            value_name="value",
        )
        melted["height_in"] = melted["height_label"].str.replace("in", "").astype(int)
        melted["measurement_type"] = "Temperature"
        melted["units"] = "°C"
        melted["source"] = f"legacy:{f.name}"
        frames.append(
            melted[["datetime_local", "height_in", "measurement_type", "value", "units", "source"]]
        )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _load_api_csvs(data_dir: Path, sensor_map: pd.DataFrame) -> pd.DataFrame:
    """Load API-pulled long-format CSVs (licor_*.csv). Returns long DataFrame."""
    files = sorted(data_dir.glob("licor_*.csv"))
    if not files:
        return pd.DataFrame(
            columns=["datetime_local", "height_in", "measurement_type", "value", "units", "source"]
        )

    sn_to_height = dict(zip(sensor_map["sensor_sn"], sensor_map["height_in"]))

    frames = []
    for f in files:
        df = pd.read_csv(f, dtype={"sensor_sn": str})
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
        df["datetime_local"] = df["timestamp_utc"].dt.tz_convert(LOCAL_TZ)
        # Strip channel suffix: "22411189-1" -> "22411189"
        df["sensor_base"] = df["sensor_sn"].str.split("-").str[0]
        df["height_in"] = df["sensor_base"].map(sn_to_height)
        df = df.dropna(subset=["height_in"])  # drops battery channels and unmapped SNs
        df["height_in"] = df["height_in"].astype(int)
        df["source"] = f"api:{f.name}"
        frames.append(
            df[["datetime_local", "height_in", "measurement_type", "value", "units", "source"]]
        )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_all(
    data_dir: str | Path = "data",
    sensor_map_path: str | Path = "sensor_map.csv",
) -> pd.DataFrame:
    """
    Load every CSV under data_dir (legacy + API) and return a unified long DataFrame:
        datetime_local (tz-aware), height_in, measurement_type, value, units, source, phase

    phase: "pre_install" for rows before tower install (2026-04-19 16:00 local), else "tower".
    Duplicates (same datetime_local × height_in × measurement_type) are resolved: API wins.
    """
    data_dir = Path(data_dir)
    sensor_map = load_sensor_map(sensor_map_path)

    legacy = _load_legacy_csvs(data_dir)
    api = _load_api_csvs(data_dir, sensor_map)
    combined = pd.concat([legacy, api], ignore_index=True)

    if combined.empty:
        return combined

    combined["api_priority"] = combined["source"].str.startswith("api:").astype(int)
    combined = (
        combined.sort_values(["datetime_local", "height_in", "measurement_type", "api_priority"])
        .drop_duplicates(
            subset=["datetime_local", "height_in", "measurement_type"], keep="last"
        )
        .drop(columns=["api_priority"])
        .reset_index(drop=True)
    )

    combined["phase"] = (combined["datetime_local"] >= INSTALL_LOCAL).map(
        {True: "tower", False: "pre_install"}
    )
    return combined


def wide_temperature(long_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long DataFrame to wide temperature format.

    Returns a DataFrame with a datetime_local column and one integer-named
    column per height (e.g., 2, 22, 42, ..., 162). Integer columns keep the
    app's `wide_disp[h]` lookups straightforward.
    """
    temp = long_df[long_df["measurement_type"] == "Temperature"].copy()
    if temp.empty:
        return pd.DataFrame()
    wide = temp.pivot_table(
        index="datetime_local", columns="height_in", values="value", aggfunc="last"
    ).reset_index()
    wide.columns.name = None
    wide = wide.sort_values("datetime_local").reset_index(drop=True)
    return wide
