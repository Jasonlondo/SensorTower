"""
Assemble the static GitHub Pages site into an output folder.

    _site/
      index.html                      <- copied from site/index.html
      data/manifest.json              <- months available, first/last reading, build time
      data/tower_YYYY-MM.csv          <- copied from data/monthly/ (5-min T, RH, DP)
      data/newa_YYYY-MM.csv           <- NEWA Geneva hourly T, RH, DP, built from data/newa/
      data/tower_hourly_archive.csv   <- full-history download (hourly T + RH)

Nothing here is committed; the workflow rebuilds it after each pull and deploys it.

Run from the repo root, then preview locally:
    python scripts/build_site.py --out _site
    python -m http.server 8000 --directory _site
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.data_loader import load_newa  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MONTHLY_DIR = DATA_DIR / "monthly"
ARCHIVE_PATH = DATA_DIR / "archive" / "tower_hourly_archive.csv"

_NEWA_VARS = {"Temperature": "t", "RH": "rh", "Dew Point": "dp"}


def write_newa_months(out_data: Path) -> list[str]:
    newa = load_newa(DATA_DIR, window_days=None)
    newa = newa[newa["variable"].isin(_NEWA_VARS)]
    if newa.empty:
        return []
    wide = newa.pivot_table(
        index="datetime_local", columns="variable", values="value", aggfunc="last"
    ).rename(columns=_NEWA_VARS).round(2)
    wide = wide.reindex(columns=list(_NEWA_VARS.values())).reset_index()
    wide["datetime_local"] = wide["datetime_local"].map(lambda t: t.isoformat(timespec="minutes"))
    months = []
    for month, part in wide.groupby(wide["datetime_local"].str[:7]):
        part.to_csv(out_data / f"newa_{month}.csv", index=False, lineterminator="\n")
        months.append(month)
    return months


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "_site")
    args = ap.parse_args()

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out_data = out / "data"
    out_data.mkdir(parents=True)

    shutil.copy2(ROOT / "site" / "index.html", out / "index.html")

    tower_files = sorted(MONTHLY_DIR.glob("tower_*.csv"))
    if not tower_files:
        raise SystemExit("No monthly record in data/monthly; run update_monthly.py first.")
    for f in tower_files:
        shutil.copy2(f, out_data / f.name)
    months = [f.stem.removeprefix("tower_") for f in tower_files]

    first = pd.read_csv(tower_files[0], usecols=["datetime_local"], nrows=1)["datetime_local"].iloc[0]
    last = pd.read_csv(tower_files[-1], usecols=["datetime_local"])["datetime_local"].iloc[-1]

    newa_months = write_newa_months(out_data)
    has_archive = ARCHIVE_PATH.exists()
    if has_archive:
        shutil.copy2(ARCHIVE_PATH, out_data / ARCHIVE_PATH.name)

    manifest = {
        "months": months,
        "newa_months": newa_months,
        "first": first,
        "last": last,
        "archive": ARCHIVE_PATH.name if has_archive else None,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out_data / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"Site -> {out} | tower months {months[0]}..{months[-1]} | last reading {last}")


if __name__ == "__main__":
    main()
