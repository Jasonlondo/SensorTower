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


def _gh_write(var: str, key: str, value: str) -> None:
    """Append 'key=value' to a GitHub Actions file ($GITHUB_OUTPUT/$GITHUB_STEP_SUMMARY). No-op locally."""
    path = os.environ.get(var)
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n" if key else f"{value}\n")


def report_staleness(client: "LicorClient", n_rows: int) -> None:
    """Warn loudly if the tower hasn't connected to the LI-COR cloud recently.

    A dropped uplink makes the pull return zero rows while still exiting 0, so the
    scheduled job stays green (see the July 2026 month-long silent outage). This
    surfaces the device's lastConnectionTime as a GitHub Actions warning + step
    output so a stall is visible within a day instead of at the next data request.
    """
    threshold = float(os.environ.get("STALE_HOURS", "24"))
    try:
        dev = client.list_devices(include_sensors=False)
        last_conn = dev["devices"][0].get("lastConnectionTime")
    except Exception as e:  # never let the health check break the pull
        print(f"[staleness] could not read device status: {type(e).__name__}: {e}")
        return
    if not last_conn:
        print("[staleness] device has no lastConnectionTime; skipping check")
        return

    last = datetime.fromisoformat(last_conn.replace("Z", "+00:00"))
    hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600.0
    stale = hours > threshold
    print(
        f"[staleness] tower last cloud connection {hours:.1f}h ago "
        f"(lastConnectionTime={last_conn}); this pull returned {n_rows} rows"
    )
    _gh_write("GITHUB_OUTPUT", "tower_stale", "1" if stale else "0")
    _gh_write("GITHUB_OUTPUT", "tower_stale_hours", f"{hours:.1f}")
    if stale:
        msg = (
            f"LI-COR tower has not connected to the cloud for {hours:.1f}h "
            f"(threshold {threshold:.0f}h). Data may be buffering on the logger, "
            f"or the field uplink is down."
        )
        print(f"::warning title=Tower uplink stale::{msg}")
        _gh_write("GITHUB_STEP_SUMMARY", "", f"⚠️ **Tower uplink stale** — {msg}")


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

    # Health check runs regardless of whether rows came back — zero rows is itself
    # the symptom of a dropped uplink, so this must fire before the early return.
    report_staleness(client, len(rows))

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
