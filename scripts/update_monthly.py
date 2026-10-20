"""
Maintain the full-resolution monthly record that the GitHub Pages site reads.

One wide CSV per calendar month (local time) at the native 5-min cadence:
    data/monthly/tower_YYYY-MM.csv
    datetime_local, t_2in..t_162in, rh_2in..rh_162in, dp_2in..dp_162in
    (datetime_local is ISO local time with UTC offset, e.g. 2026-04-19T16:30-04:00)

Raw licor day-files are pruned after 35 days (build_archive.py), so these monthly
files are the permanent 5-min record. Each run merges whatever raw files are present
into the existing monthly files. Stored values are never changed; fresh data only fills
blanks (new timestamps, or late backfill from the logger), so rows already captured
survive after their raw file is pruned. Pre-install rows (all
sensors co-located) are excluded.

Run from the repo root (the workflow runs it after each pull, BEFORE build_archive.py
prunes anything):
    python scripts/update_monthly.py
    python scripts/update_monthly.py --data-dir <dir>   # one-time backfill from a
                                                         # folder of recovered raw files
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.data_loader import HEIGHTS, load_all  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MONTHLY_DIR = ROOT / "data" / "monthly"

_TYPES = {"Temperature": "t", "RH": "rh", "Dew Point": "dp"}


def monthly_columns() -> list[str]:
    cols = ["datetime_local"]
    for prefix in _TYPES.values():
        cols += [f"{prefix}_{h}in" for h in HEIGHTS]
    return cols


def to_wide(long_df: pd.DataFrame) -> pd.DataFrame:
    """Long loader output -> wide 5-min table keyed on naive local wall-clock time."""
    sub = long_df[(long_df["phase"] == "tower") & long_df["measurement_type"].isin(_TYPES)]
    wide = sub.pivot_table(
        index="datetime_local",
        columns=["measurement_type", "height_in"],
        values="value",
        aggfunc="last",
    )
    wide.columns = [f"{_TYPES[m]}_{h}in" for m, h in wide.columns]
    wide = wide.round(2).reset_index()
    # Local wall-clock time with its UTC offset ("2026-11-01T01:30-04:00"). The offset
    # keeps the repeated DST fall-back hour unique; the page shows the first 16 chars.
    wide["datetime_local"] = wide["datetime_local"].map(lambda t: t.isoformat(timespec="minutes"))
    for col in monthly_columns():
        if col not in wide.columns:
            wide[col] = pd.NA
    return wide[monthly_columns()]


def merge_into_months(fresh: pd.DataFrame) -> list[Path]:
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    fresh = fresh.assign(_month=fresh["datetime_local"].str[:7])
    for month, part in fresh.groupby("_month"):
        path = MONTHLY_DIR / f"tower_{month}.csv"
        part = part.drop(columns="_month").set_index("datetime_local")
        if path.exists():
            old = pd.read_csv(path, dtype={"datetime_local": str}).set_index("datetime_local")
            # Cell-wise: stored values win and fresh data only fills blanks. A stored
            # reading never changes, and a blank or legacy-only fresh row (e.g. the April
            # exports once the matching API files are pruned) never overwrites it.
            part = old.combine_first(part)
        part = part.sort_index().reset_index()[monthly_columns()]
        new_text = part.to_csv(index=False, lineterminator="\n")
        if not path.exists() or path.read_text() != new_text:
            path.write_text(new_text, newline="\n")
            written.append(path)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = ap.parse_args()

    long_df = load_all(args.data_dir, ROOT / "sensor_map.csv", window_days=None)
    if long_df.empty:
        print("No raw data found; monthly record unchanged.")
        return
    written = merge_into_months(to_wide(long_df))
    print(f"Monthly record: {len(written)} file(s) updated")
    for p in written:
        print(f"  {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
