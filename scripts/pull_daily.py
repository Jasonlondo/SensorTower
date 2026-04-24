"""
LI-COR Cloud data pull — runs on a short cron cadence for near-realtime updates.

Default behavior: pull from yesterday 00:00 UTC through now, splitting results
into one CSV per UTC calendar day. Yesterday's file gets its final rows before
today's file begins, and today's file keeps growing through the day.

Environment variables:
    LICOR_TOKEN      — API token (repo secret in GitHub)
    LICOR_DEVICE_SN  — device serial (defaults to 22411541 if unset)
    PULL_DATE        — optional YYYY-MM-DD; if set, pulls that one UTC day only.
                       Useful for manual backfill via workflow_dispatch.
    DATA_DIR         — optional; defaults to "data".
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.licor_api import LicorClient, sensors_to_long_records  # noqa: E402


def resolve_window() -> tuple[datetime, datetime]:
    """Return (start_utc, end_utc) for this pull."""
    env_date = os.environ.get("PULL_DATE")
    if env_date:
        day = datetime.strptime(env_date, "%Y-%m-%d").date()
        start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return start, end
    # Default: yesterday 00:00 UTC through now. Covers the midnight handoff
    # gap and refreshes today's partial file on every invocation.
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).date()
    start = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc)
    return start, now


def write_day_file(data_dir: Path, day_iso: str, rows: list[dict]) -> Path:
    rows.sort(key=lambda r: (r["timestamp_utc"], r["sensor_sn"], r["measurement_type"]))
    out_path = data_dir / f"licor_{day_iso}.csv"
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
    return out_path


def main() -> int:
    load_dotenv(ROOT / ".env")
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    client = LicorClient.from_env()
    start, end = resolve_window()
    print(f"[pull_daily] window {start.isoformat()} -> {end.isoformat()} (UTC)")

    sensor_blocks = client.fetch_window_paginated(start, end)
    rows = sensors_to_long_records(sensor_blocks)
    print(f"[pull_daily] fetched {len(rows)} rows across {len(sensor_blocks)} sensor blocks")

    if not rows:
        print("[pull_daily] no data returned; skipping write")
        return 0

    # Split rows by UTC calendar day
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_day[r["timestamp_utc"].date().isoformat()].append(r)

    for day_iso, day_rows in sorted(by_day.items()):
        out_path = write_day_file(data_dir, day_iso, day_rows)
        print(f"[pull_daily] wrote {out_path} ({len(day_rows)} rows)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
