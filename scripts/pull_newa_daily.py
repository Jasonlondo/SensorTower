"""
Daily pull for NEWA Geneva (AgriTech Gates) hourly data.

Writes data/newa/newa_YYYY-MM-DD.csv in long format (timestamp_local, variable, value, units).
Runs in CI after the LI-COR pull — both are invoked by the daily workflow.

PULL_DATE env var (optional) — YYYY-MM-DD, local date. Defaults to yesterday local.
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.newa_api import NEWAClient, parse_response  # noqa: E402

LOCAL_TZ = ZoneInfo("America/New_York")


def resolve_target_day() -> tuple[datetime, datetime, str]:
    """Pull window covers the full local calendar day — 00 to 23 hour inclusive."""
    env_date = os.environ.get("PULL_DATE")
    if env_date:
        day = datetime.strptime(env_date, "%Y-%m-%d").date()
    else:
        day = (datetime.now(LOCAL_TZ) - timedelta(days=1)).date()
    sdate = datetime(day.year, day.month, day.day, 0, tzinfo=LOCAL_TZ)
    edate = sdate + timedelta(hours=23)
    return sdate, edate, day.isoformat()


def main() -> int:
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "data")) / "newa"
    data_dir.mkdir(parents=True, exist_ok=True)

    client = NEWAClient()
    sdate, edate, label = resolve_target_day()
    print(f"[pull_newa_daily] window {sdate.isoformat()} -> {edate.isoformat()} (local)")

    payload = client.fetch_hourly(sdate, edate)
    rows = parse_response(payload)
    print(f"[pull_newa_daily] parsed {len(rows)} long rows from NEWA")

    if not rows:
        print("[pull_newa_daily] no data returned; skipping write")
        return 0

    rows.sort(key=lambda r: (r["timestamp_local"], r["variable"]))

    out_path = data_dir / f"newa_{label}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp_local", "variable", "value", "units"]
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"[pull_newa_daily] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
