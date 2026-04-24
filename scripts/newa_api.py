"""
NEWA hourly weather data client.

Reverse-engineered from the NEWA "All Weather Data Query" tool — no public API
docs exist, but the tool hits this endpoint with a JSON body.

Endpoint:  POST https://hrly.nrcc.cornell.edu/stnHrly
Body:      {"sid":"ny_geng nwon","sdate":"YYYYMMDDHH","edate":"YYYYMMDDHH"|"now","extraelems":""}
Response:  {"hrlyFields": [...], "hrlyData": [[...], ...]}

Native units are imperial (°F, mph, in. precip). We convert temperature and
dew point to °C on ingest so they match the tower data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

ENDPOINT = "https://hrly.nrcc.cornell.edu/stnHrly"
DEFAULT_TIMEOUT = 30

# Geneva (AgriTech Gates) is the station nearest our sensor tower.
# The internal NEWA sid uses a network-specific suffix ("nwon") rather
# than the numeric ACIS network code.
STATION_ID = "ny_geng nwon"

# hrlyFields returned by the API, in order.
# Types beyond what we explicitly use are preserved as strings.
FIELDS = ["date", "flags", "prcp", "temp", "rhum", "dwpt", "lwet", "wspd", "wdir", "srad"]


class NEWAAPIError(RuntimeError):
    pass


@dataclass
class NEWAClient:
    sid: str = STATION_ID
    timeout: int = DEFAULT_TIMEOUT

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(
            ENDPOINT,
            json=body,
            headers={"content-type": "application/json"},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise NEWAAPIError(f"{r.status_code} {r.reason}: {r.text[:300]}")
        text = r.text.strip()
        if text.startswith("Invalid") or not text.startswith("{"):
            raise NEWAAPIError(f"NEWA returned: {text[:300]}")
        return r.json()

    def fetch_hourly(self, sdate: datetime, edate: datetime | str = "now") -> dict[str, Any]:
        """
        Fetch hourly data for the station.

        sdate / edate: tz-aware datetime objects, or "now" for edate.
        Date format sent to API is YYYYMMDDHH in the station's local time.
        """
        body = {
            "sid": self.sid,
            "sdate": sdate.strftime("%Y%m%d%H"),
            "edate": "now" if edate == "now" else edate.strftime("%Y%m%d%H"),
            "extraelems": "",
        }
        return self._post(body)


def _safe_float(v: str) -> float | None:
    if v in ("", "M", "T", "S", None):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def f_to_c(f: float | None) -> float | None:
    if f is None:
        return None
    return (f - 32.0) * 5.0 / 9.0


def in_to_mm(inches: float | None) -> float | None:
    if inches is None:
        return None
    return inches * 25.4


def mph_to_ms(mph: float | None) -> float | None:
    if mph is None:
        return None
    return mph * 0.44704


# Canonical output: long-format rows with converted values, variable names
# matching the tower data ("Temperature", "RH", "Dew Point") plus NEWA-only
# extras ("Wind Speed", "Wind Direction", "Solar Radiation", "Precipitation",
# "Leaf Wetness").
OUTPUT_UNITS = {
    "Temperature":       "°C",
    "RH":                "%",
    "Dew Point":         "°C",
    "Wind Speed":        "m/s",
    "Wind Direction":    "deg",
    "Solar Radiation":   "W/m²",   # NEWA reports solar in W/m² already
    "Precipitation":     "mm",
    "Leaf Wetness":      "min/h",
}


def parse_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert raw hrlyData into long rows with °C and metric units."""
    fields = payload.get("hrlyFields", FIELDS)
    rows: list[dict[str, Any]] = []
    for record in payload.get("hrlyData", []):
        rec = dict(zip(fields, record))
        ts = rec.get("date")
        if not ts:
            continue

        # Temperature: °F -> °C
        t_c = f_to_c(_safe_float(rec.get("temp")))
        rh = _safe_float(rec.get("rhum"))
        dp_c = f_to_c(_safe_float(rec.get("dwpt")))
        wspd = mph_to_ms(_safe_float(rec.get("wspd")))
        wdir = _safe_float(rec.get("wdir"))
        srad = _safe_float(rec.get("srad"))
        prcp = in_to_mm(_safe_float(rec.get("prcp")))
        lwet = _safe_float(rec.get("lwet"))

        for var, val in [
            ("Temperature",     t_c),
            ("RH",              rh),
            ("Dew Point",       dp_c),
            ("Wind Speed",      wspd),
            ("Wind Direction",  wdir),
            ("Solar Radiation", srad),
            ("Precipitation",   prcp),
            ("Leaf Wetness",    lwet),
        ]:
            if val is None:
                continue
            rows.append(
                {
                    "timestamp_local": ts,      # keep original with TZ offset
                    "variable": var,
                    "value": val,
                    "units": OUTPUT_UNITS[var],
                }
            )
    return rows
