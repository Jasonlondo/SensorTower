"""
LI-COR Cloud API client.

API docs: https://api.licor.cloud/v1/docs/
Auth: Bearer token (generate in licor.cloud UI: Data > API > Add Token)
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

BASE_URL = "https://api.licor.cloud"
DEFAULT_TIMEOUT = 30
MAX_RECORDS_PER_CALL = 100_000


class LicorAPIError(RuntimeError):
    pass


@dataclass
class LicorClient:
    token: str
    device_sn: str
    base_url: str = BASE_URL
    timeout: int = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls) -> "LicorClient":
        token = os.environ.get("LICOR_TOKEN")
        device = os.environ.get("LICOR_DEVICE_SN")
        if not token:
            raise LicorAPIError("LICOR_TOKEN not set in environment")
        if not device:
            raise LicorAPIError("LICOR_DEVICE_SN not set in environment")
        return cls(token=token, device_sn=device)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        for attempt in range(3):
            r = requests.get(url, headers=self._headers(), params=params, timeout=self.timeout)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 200:
                return r.json()
            raise LicorAPIError(f"{r.status_code} {r.reason}: {r.text[:300]}")
        raise LicorAPIError("Rate-limited after 3 retries")

    def list_devices(self, include_sensors: bool = True) -> dict[str, Any]:
        return self._get("/v2/devices", {"includeSensors": str(include_sensors).lower()})

    def fetch_window(
        self,
        start: datetime,
        end: datetime,
        sensor_sn: str | None = None,
    ) -> dict[str, Any]:
        """Fetch data for the device between two tz-aware datetimes (UTC recommended)."""
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start/end must be timezone-aware")
        start_ms = int(start.astimezone(timezone.utc).timestamp() * 1000)
        end_ms = int(end.astimezone(timezone.utc).timestamp() * 1000)
        params: dict[str, Any] = {
            "deviceSerialNumber": self.device_sn,
            "startTime": start_ms,
            "endTime": end_ms,
        }
        if sensor_sn:
            params["sensorSerialNumber"] = sensor_sn
        return self._get("/v2/data", params)

    def fetch_window_paginated(
        self, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """Fetch a window, following moreResults pagination. Returns list of sensor blocks."""
        all_sensors: list[dict[str, Any]] = []
        cursor_start = start
        while True:
            payload = self.fetch_window(cursor_start, end)
            sensors = payload.get("sensors", [])
            all_sensors.extend(sensors)
            if not payload.get("moreResults"):
                break
            latest = max(
                (s.get("latestTimestamp", 0) for s in sensors), default=0
            )
            if latest == 0:
                break
            cursor_start = datetime.fromtimestamp(latest / 1000 + 0.001, tz=timezone.utc)
            if cursor_start >= end:
                break
        return all_sensors


def sensors_to_long_records(sensor_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Flatten /v2/data response into long rows:
    [{sensor_sn, measurement_type, data_type, units, timestamp_utc, value}, ...]
    """
    rows: list[dict[str, Any]] = []
    for block in sensor_blocks:
        sn = block.get("sensorSerialNumber")
        for stream in block.get("data", []):
            mt = stream.get("measurementType")
            dt = stream.get("dataType")
            units = stream.get("units")
            for ts_ms, val in stream.get("records", []):
                rows.append(
                    {
                        "sensor_sn": sn,
                        "measurement_type": mt,
                        "data_type": dt,
                        "units": units,
                        "timestamp_utc": datetime.fromtimestamp(
                            ts_ms / 1000, tz=timezone.utc
                        ),
                        "value": val,
                    }
                )
    return rows
