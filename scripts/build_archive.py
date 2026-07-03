"""
Build/refresh the downloadable long-term archive, then prune stale raw day-files.

Why this exists
---------------
The Streamlit app only loads a rolling window of recent day-files to stay under
Streamlit Community Cloud's ~1 GB RAM cap (see data_loader.load_all(window_days=...)).
Everything older is rolled into a compact, downloadable archive so no history is lost
from the dashboard's perspective, and the big long-format LI-COR day-files are pruned
from the working tree so the repo stops growing ~0.6 MB/day forever.

Archive contents
----------------
- Hourly means of Temperature and Relative Humidity only (dew point is derivable from
  the two; battery is dropped). Wide format: one column per height per variable.
- Cumulative and idempotent: each run recomputes hourly stats from whatever raw files
  are present and unions them with the existing archive, so pruned-away days survive in
  the archive even after their raw files are gone.

Safety
------
The order is strict: (1) update the archive, (2) only then delete raw files whose data
is already captured. Raw 5-min data also remains recoverable from git history.

Run from the repo root:
    python scripts/build_archive.py            # build archive + prune
    python scripts/build_archive.py --no-prune # build archive only (dry-run-ish)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.data_loader import (  # noqa: E402
    HEIGHTS,
    _file_date,
    load_all,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_PATH = ARCHIVE_DIR / "tower_hourly_archive.csv"

# Keep this many days of raw LI-COR day-files in the working tree. Must be >= the
# app's window_days so there is never a gap between "in the hot files" and "in the
# archive". App uses 30; we keep 35 for a safe buffer.
RETENTION_DAYS = 35

# Only these variables go into the archive (the "just temp/humidity" request).
_ARCHIVE_TYPES = {"Temperature": "t", "RH": "rh"}


def _archive_columns() -> list[str]:
    """Canonical column order: all temp columns (low->high), then all RH columns."""
    cols = ["datetime_local"]
    cols += [f"t_{h}in" for h in HEIGHTS]
    cols += [f"rh_{h}in" for h in HEIGHTS]
    return cols


def compute_hourly(long_df: pd.DataFrame) -> pd.DataFrame:
    """Hourly means of Temperature + RH per height, wide format, ISO datetime strings."""
    sub = long_df[long_df["measurement_type"].isin(_ARCHIVE_TYPES)].copy()
    if sub.empty:
        return pd.DataFrame(columns=_archive_columns())

    sub = sub.set_index("datetime_local").sort_index()
    wide = sub.pivot_table(
        index="datetime_local",
        columns=["measurement_type", "height_in"],
        values="value",
        aggfunc="mean",
    )
    hourly = wide.resample("1h").mean()

    hourly.columns = [
        f"{_ARCHIVE_TYPES[mtype]}_{height}in" for mtype, height in hourly.columns
    ]
    hourly = hourly.round(2).reset_index()
    # tz-aware ISO strings survive a CSV round-trip unambiguously.
    hourly["datetime_local"] = hourly["datetime_local"].apply(lambda t: t.isoformat())

    for col in _archive_columns():
        if col not in hourly.columns:
            hourly[col] = pd.NA
    return hourly[_archive_columns()]


def load_existing_archive() -> pd.DataFrame:
    if not ARCHIVE_PATH.exists():
        return pd.DataFrame(columns=_archive_columns())
    df = pd.read_csv(ARCHIVE_PATH, dtype={"datetime_local": str})
    for col in _archive_columns():
        if col not in df.columns:
            df[col] = pd.NA
    return df[_archive_columns()]


def merge_archive(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """Union old + freshly recomputed hours; on collision the fresh value wins."""
    merged = pd.concat([existing, fresh], ignore_index=True)
    merged = (
        merged.drop_duplicates(subset=["datetime_local"], keep="last")
        .sort_values("datetime_local")
        .reset_index(drop=True)
    )
    return merged


def prune_raw_files(dry_run: bool = False) -> list[Path]:
    """Delete LI-COR day-files older than RETENTION_DAYS from the NEWEST licor file.

    Only touches licor_*.csv — those are the large long-format files driving both the
    RAM and repo-growth problems. NEWA files (tiny) and legacy datalogger exports (fixed
    count, the original freeze-event record) are left in place.
    Returns the list of files removed.
    """
    licor = sorted(DATA_DIR.glob("licor_*.csv"))
    dates = [d for d in (_file_date(f) for f in licor) if d is not None]
    if not dates:
        return []
    cutoff = max(dates) - pd.Timedelta(days=RETENTION_DAYS)

    removed = []
    for f in licor:
        d = _file_date(f)
        if d is not None and d < cutoff:
            removed.append(f)
            if not dry_run:
                f.unlink()
    return removed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--no-prune",
        action="store_true",
        help="Build/refresh the archive but do not delete any raw day-files.",
    )
    args = ap.parse_args()

    # Full history — window_days=None so every available day-file is captured.
    long_df = load_all(DATA_DIR, ROOT / "sensor_map.csv", window_days=None)
    if long_df.empty:
        print("No data found; nothing to archive.")
        return

    fresh = compute_hourly(long_df)
    existing = load_existing_archive()
    merged = merge_archive(existing, fresh)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(ARCHIVE_PATH, index=False)
    print(
        f"Archive: {len(merged):,} hourly rows "
        f"({merged['datetime_local'].min()} -> {merged['datetime_local'].max()}) "
        f"-> {ARCHIVE_PATH.relative_to(ROOT)}"
    )

    if args.no_prune:
        pruned = prune_raw_files(dry_run=True)
        print(f"--no-prune: {len(pruned)} raw licor file(s) WOULD be pruned (kept).")
    else:
        pruned = prune_raw_files(dry_run=False)
        print(f"Pruned {len(pruned)} raw licor file(s) older than {RETENTION_DAYS} days.")
        for f in pruned:
            print(f"  removed {f.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
