"""
Daily pull script — retrieves the previous UTC day from LI-COR Cloud and writes
a long-format CSV to data/licor_YYYY-MM-DD.csv.

Intended to run from GitHub Actions on a cron schedule. Works locally too.

Environment variables:
    LICOR_TOKEN      — API token (repo secret in GitHub)
    LICOR_DEVICE_SN  — device serial (defaults to 22411541 if unset)
    PULL_DATE        — optional YYYY-MM-DD; if set, pulls that UTC day. If unset,
                       pulls "yesterday" in UTC.
    DATA_DIR         — optional; defaults to "data".
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# Make project root importable when run from anywhere
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.licor_api import LicorClient, sensors_to_long_records  # noqa: E402


def resolve_target_day() -> tuple[datetime, datetime, str]:
    """Return (start_utc, end_utc, label) for the day to pull."""
    env_date = os.environ.get("PULL_DATE")
    if env_date:
        day = datetime.strptime(env_date, "%Y-%m-%d").date()
    else:
        day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end, day.isoformat()


def main() -> int:
    load_dotenv(ROOT / ".env")
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    client = LicorClient.from_env()
    start, end, label = resolve_target_day()
    print(f"[pull_daily] window {start.isoformat()} -> {end.isoformat()} (UTC)")

    sensor_blocks = client.fetch_window_paginated(start, end)
    rows = sensors_to_long_records(sensor_blocks)
    print(f"[pull_daily] fetched {len(rows)} rows across {len(sensor_blocks)} sensor blocks")

    if not rows:
        print("[pull_daily] no data returned; skipping write")
        return 0

    # Sort for reproducible diffs
    rows.sort(key=lambda r: (r["timestamp_utc"], r["sensor_sn"], r["measurement_type"]))

    out_path = data_dir / f"licor_{label}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp_utc",
                "sensor_sn",
                "measurement_type",
                "data_type",
                "units",
                "value",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "timestamp_utc": r["timestamp_utc"].isoformat(),
                    "sensor_sn": r["sensor_sn"],
                    "measurement_type": r["measurement_type"],
                    "data_type": r["data_type"],
                    "units": r["units"],
                    "value": r["value"],
                }
            )
    print(f"[pull_daily] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
