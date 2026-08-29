"""
One-off export: full tower record at native 5-min resolution, every height,
temperature + RH, from install (2026-04-19 16:00 EDT) through now, pulled
directly from the LI-COR cloud. Adjacent NEWA station temp + RH (hourly) is
merged on matching timestamps.

Output: outputs/tower_5min_temp_rh_with_newa_<start>_to_<end>.csv
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from scripts.licor_api import LicorClient, sensors_to_long_records
from scripts.data_loader import load_sensor_map, load_newa, LOCAL_TZ, HEIGHTS

load_dotenv(ROOT / ".env")

START_UTC = datetime(2026, 4, 19, 20, 0, tzinfo=timezone.utc)  # 16:00 EDT install
CHUNK_DAYS = 10


def pull_licor_wide() -> pd.DataFrame:
    client = LicorClient.from_env()
    smap = load_sensor_map(ROOT / "sensor_map.csv")
    sn_to_h = dict(zip(smap["sensor_sn"], smap["height_in"]))

    now = datetime.now(timezone.utc)
    all_rows: list[dict] = []
    cur = START_UTC
    while cur < now:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS), now)
        blocks = client.fetch_window_paginated(cur, chunk_end)
        recs = sensors_to_long_records(blocks)
        all_rows.extend(recs)
        print(f"[export] {cur.date()}..{chunk_end.date()}  +{len(recs):>7} rows "
              f"(running {len(all_rows)})", flush=True)
        cur = chunk_end

    df = pd.DataFrame(all_rows)
    df = df[df["measurement_type"].isin(["Temperature", "RH"])].copy()
    df["sensor_base"] = df["sensor_sn"].str.split("-").str[0]
    df["height_in"] = df["sensor_base"].map(sn_to_h)
    df = df.dropna(subset=["height_in"])
    df["height_in"] = df["height_in"].astype(int)
    df["datetime_local"] = pd.to_datetime(df["timestamp_utc"], utc=True).dt.tz_convert(LOCAL_TZ)

    # Deduplicate (overlap-safe), then pivot to wide
    df = df.drop_duplicates(subset=["datetime_local", "height_in", "measurement_type"], keep="last")

    frames = {}
    for mt, prefix in [("Temperature", "t"), ("RH", "rh")]:
        sub = df[df["measurement_type"] == mt]
        wide = sub.pivot_table(index="datetime_local", columns="height_in",
                               values="value", aggfunc="last")
        wide.columns = [f"{prefix}_{h}in" for h in wide.columns]
        frames[mt] = wide

    wide = frames["Temperature"].join(frames["RH"], how="outer").sort_index()
    ordered = [f"t_{h}in" for h in HEIGHTS] + [f"rh_{h}in" for h in HEIGHTS]
    wide = wide.reindex(columns=ordered)
    return wide


def newa_wide() -> pd.DataFrame:
    n = load_newa(ROOT / "data")
    n = n[n["variable"].isin(["Temperature", "RH"])]
    if n.empty:
        return pd.DataFrame()
    w = n.pivot_table(index="datetime_local", columns="variable", values="value", aggfunc="last")
    w = w.rename(columns={"Temperature": "newa_temp_c", "RH": "newa_rh_pct"})
    return w


def main() -> int:
    tower = pull_licor_wide()
    print(f"[export] tower wide: {tower.shape[0]} rows x {tower.shape[1]} cols "
          f"({tower.index.min()} -> {tower.index.max()})", flush=True)

    newa = newa_wide()
    if not newa.empty:
        merged = tower.join(newa, how="left")   # NEWA populated on its native hourly marks
        print(f"[export] NEWA merged: {newa.shape[0]} hourly rows, "
              f"{merged['newa_temp_c'].notna().sum()} tower rows carry a NEWA reading", flush=True)
    else:
        merged = tower
        print("[export] WARNING: no NEWA data found", flush=True)

    merged = merged.reset_index().rename(columns={"index": "datetime_local"})
    merged["datetime_local"] = merged["datetime_local"].apply(lambda t: t.isoformat())

    start = merged["datetime_local"].iloc[0][:10]
    end = merged["datetime_local"].iloc[-1][:10]
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"tower_5min_temp_rh_with_newa_{start}_to_{end}.csv"
    merged.to_csv(out, index=False, float_format="%.3f")
    print(f"[export] wrote {out}  ({len(merged)} rows, {merged.shape[1]} cols)", flush=True)
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
