"""
01_load_data.py
Reusable data loader for sensor tower CSVs.
Import this module from any analysis script: from scripts.load_data import load_tower_data, HEIGHTS, THRESHOLDS
"""

import pandas as pd
from pathlib import Path

HEIGHTS = [2, 22, 42, 62, 82, 102, 122, 142, 162]   # inches above ground
HEIGHT_COLS = [f"{h}in" for h in HEIGHTS]

# Apple bloom-stage critical temps (°C), NC State Extension
THRESHOLDS = {
    "Tight cluster": {"kill10": -5.0, "kill90": -8.9},
    "Pink":          {"kill10": -3.9, "kill90": -6.7},
    "Full bloom":    {"kill10": -2.2, "kill90": -4.0},
}


def load_tower_data(data_dir: str | Path = "data") -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load all CSVs from data_dir, parse timestamps, return (wide, long) DataFrames.

    wide: one row per timestamp, columns = datetime + one per sensor height
    long: one row per timestamp × sensor, columns = datetime, height_in, height_ft, temp_c
    """
    data_dir = Path(data_dir)
    files = sorted(data_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")

    frames = []
    for f in files:
        df = pd.read_csv(f, skipinitialspace=True)
        df.columns = df.columns.str.strip()
        # Parse YY-MM-DD HH:MM:SS from the datalogger
        df["datetime"] = pd.to_datetime(df["Date"].str.strip(), format="%y-%m-%d %H:%M:%S")
        df = df.drop(columns=["Date"])
        df["source_file"] = f.name
        frames.append(df)

    wide = (pd.concat(frames, ignore_index=True)
              .sort_values("datetime")
              .drop_duplicates(subset="datetime", keep="last")
              .reset_index(drop=True))

    long = wide.melt(
        id_vars=["datetime", "source_file"],
        value_vars=HEIGHT_COLS,
        var_name="height",
        value_name="temp_c",
    )
    long["height_in"] = long["height"].str.replace("in", "").astype(int)
    long["height_ft"] = (long["height_in"] / 12).round(2)
    long["height"] = pd.Categorical(long["height"], categories=HEIGHT_COLS, ordered=True)
    long = long.sort_values(["datetime", "height_in"]).reset_index(drop=True)

    return wide, long
