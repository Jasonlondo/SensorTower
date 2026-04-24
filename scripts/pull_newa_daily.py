"""
NEWA hourly pull — runs on the same short cron cadence as pull_daily.py.

Default behavior: pull from yesterday 00:00 local through now, splitting
into one CSV per local calendar day. Matches the LI-COR pull pattern.

Environment variables:
    PULL_DATE — optional YYYY-MM-DD (local). If set, pulls that one day.
    DATA_DIR  — optional; defaults to "data".
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.newa_api import NEWAClient, parse_response  # noqa: E402

LOCAL_TZ = ZoneInfo("America/New_York")


def resolve_window() -> tuple[datetime, datetime]:
    env_date = os.environ.get("PULL_DATE")
    if env_date:
        day = datetime.strptime(env_date, "%Y-%m-%d").date()
        start = datetime(day.year, day.month, day.day, 0, tzinfo=LOCAL_TZ)
        end = start + timedelta(hours=23)
        return start, end
    # Default: yesterday 00:00 local through now
    now = datetime.now(LOCAL_TZ)
    yesterday = (now - timedelta(days=1)).date()
    start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, tzinfo=LOCAL_TZ)
    return start, now


def write_day_file(data_dir: Path, day_iso: str, rows: list[dict]) -> Path:
    rows.sort(key=lambda r: (r["timestamp_local"], r["variable"]))
    out_path = data_dir / f"newa_{day_iso}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp_local", "variable", "value", "units"]
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return out_path


def main() -> int:
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "data")) / "newa"
    data_dir.mkdir(parents=True, exist_ok=True)

    client = NEWAClient()
    start, end = resolve_window()
    print(f"[pull_newa_daily] window {start.isoformat()} -> {end.isoformat()} (local)")

    payload = client.fetch_hourly(start, end)
    rows = parse_response(payload)
    print(f"[pull_newa_daily] parsed {len(rows)} long rows from NEWA")

    if not rows:
        print("[pull_newa_daily] no data returned; skipping write")
        return 0

    # Split by local calendar day (the timestamp_local string is ISO with tz offset)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        # timestamp_local looks like "2026-04-23T14:00:00-04:00" — take the date prefix
        day_iso = r["timestamp_local"][:10]
        by_day[day_iso].append(r)

    for day_iso, day_rows in sorted(by_day.items()):
        out_path = write_day_file(data_dir, day_iso, day_rows)
        print(f"[pull_newa_daily] wrote {out_path} ({len(day_rows)} rows)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
