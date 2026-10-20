"""
Rebuild the downloadable hourly archive from the monthly record, then prune stale raw
day-files.

Archive contents
----------------
- Hourly means of Temperature and Relative Humidity (dew point is derivable from the
  two). Wide format, one column per height per variable.
- Rebuilt in full every run from data/monthly/tower_*.csv (the permanent 5-min record
  kept by update_monthly.py), so it always matches the full history.

  History: until 2026-10-20 this script merged freshly resampled raw files into the
  existing archive. resample("1h") filled every hour between the April legacy exports
  and the 35-day raw window with blanks, and those blank rows overwrote real archived
  values, so most of May to September was blank. Deriving from the monthly record
  removes that failure mode.

Safety
------
Order in the workflow: update_monthly.py (raw -> monthly) runs first and fails the job
on error, then this script. Raw files are only pruned when every dated raw file older
than the cutoff has its day present in the monthly record. Raw 5-min data also remains
recoverable from git history.

Run from the repo root:
    python scripts/build_archive.py            # build archive + prune
    python scripts/build_archive.py --no-prune # build archive only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.data_loader import HEIGHTS, LOCAL_TZ, _file_date  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MONTHLY_DIR = DATA_DIR / "monthly"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_PATH = ARCHIVE_DIR / "tower_hourly_archive.csv"

# Keep this many days of raw LI-COR day-files in the working tree.
RETENTION_DAYS = 35


def archive_columns() -> list[str]:
    return (
        ["datetime_local"]
        + [f"t_{h}in" for h in HEIGHTS]
        + [f"rh_{h}in" for h in HEIGHTS]
    )


def load_monthly() -> pd.DataFrame:
    files = sorted(MONTHLY_DIR.glob("tower_*.csv"))
    if not files:
        return pd.DataFrame()
    return pd.concat(
        [pd.read_csv(f, dtype={"datetime_local": str}) for f in files], ignore_index=True
    )


def compute_hourly(monthly: pd.DataFrame) -> pd.DataFrame:
    value_cols = archive_columns()[1:]
    # Group on UTC hours so the repeated DST fall-back hour stays two hours.
    utc = pd.to_datetime(monthly["datetime_local"], utc=True)
    hourly = monthly[value_cols].groupby(utc.dt.floor("h")).mean().round(2)
    hourly = hourly.dropna(how="all")
    idx = hourly.index.tz_convert(LOCAL_TZ)
    hourly.insert(0, "datetime_local", [t.isoformat() for t in idx])
    return hourly.reset_index(drop=True)[archive_columns()]


def prune_raw_files(monthly_days: set[str], dry_run: bool = False) -> list[Path]:
    """Delete licor day-files older than RETENTION_DAYS from the newest licor file,
    only if each one's UTC day appears in the monthly record."""
    licor = sorted(DATA_DIR.glob("licor_*.csv"))
    dates = [d for d in (_file_date(f) for f in licor) if d is not None]
    if not dates:
        return []
    cutoff = max(dates) - pd.Timedelta(days=RETENTION_DAYS)
    stale = [f for f in licor if (d := _file_date(f)) is not None and d < cutoff]
    missing = [f.name for f in stale if _file_date(f).strftime("%Y-%m-%d") not in monthly_days]
    if missing:
        raise SystemExit(f"Refusing to prune: not in monthly record: {missing}")
    if not dry_run:
        for f in stale:
            f.unlink()
    return stale


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-prune", action="store_true",
                    help="Build the archive but do not delete any raw day-files.")
    args = ap.parse_args()

    monthly = load_monthly()
    if monthly.empty:
        print("No monthly record found; nothing to archive or prune.")
        return

    hourly = compute_hourly(monthly)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    hourly.to_csv(ARCHIVE_PATH, index=False, lineterminator="\n")
    print(
        f"Archive: {len(hourly):,} hourly rows "
        f"({hourly['datetime_local'].iloc[0]} -> {hourly['datetime_local'].iloc[-1]}) "
        f"-> {ARCHIVE_PATH.relative_to(ROOT)}"
    )

    utc_days = set(
        pd.to_datetime(monthly["datetime_local"], utc=True).dt.strftime("%Y-%m-%d")
    )
    pruned = prune_raw_files(utc_days, dry_run=args.no_prune)
    verb = "WOULD prune (kept)" if args.no_prune else "Pruned"
    print(f"{verb} {len(pruned)} raw licor file(s) older than {RETENTION_DAYS} days.")


if __name__ == "__main__":
    main()
