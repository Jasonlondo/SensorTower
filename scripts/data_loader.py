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

import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

HEIGHTS = [2, 22, 42, 62, 82, 102, 122, 142, 162]
HEIGHT_COLS = [f"{h}in" for h in HEIGHTS]
LOCAL_TZ = ZoneInfo("America/New_York")

INSTALL_LOCAL = pd.Timestamp("2026-04-19 16:00", tz=LOCAL_TZ)

# Extra days kept on top of window_days so the file-level pre-filter is always a
# strict superset of the precise datetime window (guards tz / midnight spill).
_WINDOW_BUFFER_DAYS = 1


def _file_date(path: Path) -> pd.Timestamp | None:
    """Best-effort date embedded in a data filename, as a tz-naive Timestamp.

    Handles the three naming schemes in this repo:
      - API day-files   ``licor_2026-04-27.csv``       -> 2026-04-27
      - NEWA day-files  ``newa_2026-04-27.csv``         -> 2026-04-27
      - legacy exports  ``freeze2-2026_04_21_10_05_...`` -> 2026-04-21
    Returns None if no date can be parsed (such a file is never filtered out).
    """
    name = path.name
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
    if not m:
        m = re.search(r"(\d{4})_(\d{2})_(\d{2})", name)
    if not m:
        return None
    try:
        return pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except (ValueError, TypeError):
        return None


def _window_cutoff(files: list[Path], window_days: int | None) -> pd.Timestamp | None:
    """Cutoff date for a rolling window, measured from the NEWEST available file.

    Anchoring on the newest file (not wall-clock ``today``) keeps the app working
    when the pull pipeline is stalled or backfilling — it always shows the most
    recent ``window_days`` of whatever data exists. Returns None when no window is
    requested or no dated files are found (=> keep everything).
    """
    if window_days is None:
        return None
    dates = [d for d in (_file_date(f) for f in files) if d is not None]
    if not dates:
        return None
    newest = max(dates)
    return newest - pd.Timedelta(days=window_days + _WINDOW_BUFFER_DAYS)


def _keep_within_window(
    files: list[Path], cutoff: pd.Timestamp | None
) -> list[Path]:
    """Drop files whose embedded date is older than ``cutoff`` (undated files kept)."""
    if cutoff is None:
        return files
    kept = []
    for f in files:
        d = _file_date(f)
        if d is None or d >= cutoff:
            kept.append(f)
    return kept

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


def _load_legacy_csvs(data_dir: Path, cutoff: pd.Timestamp | None = None) -> pd.DataFrame:
    """Load datalogger-style wide CSVs. Returns long DataFrame."""
    files = sorted(data_dir.glob("*.csv"))
    legacy = [f for f in files if not f.name.startswith("licor_")]
    legacy = _keep_within_window(legacy, cutoff)
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


def _load_api_csvs(
    data_dir: Path, sensor_map: pd.DataFrame, cutoff: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Load API-pulled long-format CSVs (licor_*.csv). Returns long DataFrame."""
    files = _keep_within_window(sorted(data_dir.glob("licor_*.csv")), cutoff)
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
    window_days: int | None = None,
) -> pd.DataFrame:
    """
    Load CSVs under data_dir (legacy + API) and return a unified long DataFrame:
        datetime_local (tz-aware), height_in, measurement_type, value, units, source, phase

    phase: "pre_install" for rows before tower install (2026-04-19 16:00 local), else "tower".
    Duplicates (same datetime_local × height_in × measurement_type) are resolved: API wins.

    window_days: if set, only day-files within that many days of the NEWEST available
    file are read (files are filtered by their date-stamped names *before* being parsed,
    so old data never enters memory). None => load everything (used by legacy/offline
    analysis scripts). The Streamlit app passes a small window to stay under its RAM cap;
    the full history is preserved in the downloadable archive + git history.
    """
    data_dir = Path(data_dir)
    sensor_map = load_sensor_map(sensor_map_path)

    candidates = sorted(data_dir.glob("*.csv"))
    cutoff = _window_cutoff(candidates, window_days)

    legacy = _load_legacy_csvs(data_dir, cutoff)
    api = _load_api_csvs(data_dir, sensor_map, cutoff)
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


def load_newa(data_dir: str | Path = "data", window_days: int | None = None) -> pd.DataFrame:
    """
    Load NEWA daily CSVs from data/newa/ into a long DataFrame.

    Returns columns: datetime_local, variable, value, units, source.
    Empty DataFrame with the same schema if no files exist.

    window_days: same rolling-window semantics as load_all (relative to the newest
    NEWA file). None => load every file.
    """
    data_dir = Path(data_dir) / "newa"
    cols = ["datetime_local", "variable", "value", "units", "source"]
    if not data_dir.exists():
        return pd.DataFrame(columns=cols)

    files = sorted(data_dir.glob("newa_*.csv"))
    files = _keep_within_window(files, _window_cutoff(files, window_days))
    if not files:
        return pd.DataFrame(columns=cols)

    frames = []
    for f in files:
        df = pd.read_csv(f)
        df["datetime_local"] = pd.to_datetime(df["timestamp_local"], utc=False)
        # NEWA strings carry the -04:00/-05:00 offset; normalize to LOCAL_TZ
        if df["datetime_local"].dt.tz is None:
            df["datetime_local"] = df["datetime_local"].dt.tz_localize(LOCAL_TZ)
        else:
            df["datetime_local"] = df["datetime_local"].dt.tz_convert(LOCAL_TZ)
        df["source"] = f"newa:{f.name}"
        frames.append(df[cols])
    out = pd.concat(frames, ignore_index=True)
    out = (
        out.sort_values(["datetime_local", "variable"])
        .drop_duplicates(subset=["datetime_local", "variable"], keep="last")
        .reset_index(drop=True)
    )
    return out


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
