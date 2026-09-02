"""Maldives: MMA Statistics API — ODC deposit liabilities by currency.

API (Bearer token required):
  https://database.mma.gov.mv/api/docs
  GET https://database.mma.gov.mv/api/series?ids={id1},{id2},...
  Header: Authorization: Bearer $MMA_API_TOKEN

Register token: https://database.mma.gov.mv/api/register

Series (Financial Sector → Assets And Liabilities of Other Depository Corporations
→ Liabilities → Deposits):
  2414 Transferable deposits (total)
  2415   Local currency
  2416   Foreign currency          → part of FCD
  2417 Other deposits (total)
  2418   Local currency
  2419   Foreign currency          → part of FCD

  FCD = 2416 + 2419
  TD  = 2414 + 2417   (= all ODC customer deposits)
  FCD_TD_RATIO = FCD/TD*100

Note: series 2307 "Dollarization ratio" is FC quasi-money / broad money (includes
currency) and is *not* used — we recompute deposit-only FCD/TD.

API amounts are in Rufiyaa (MVR); we store **million MVR**.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import requests
import urllib3

from src.utils.fcd_series import empty_frame, long_rows
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_API = "https://database.mma.gov.mv/api/series"
_DOCS = "https://database.mma.gov.mv/api/docs"

# ODC deposit liability series
_ID_TRF = 2414  # transferable total
_ID_TRF_LC = 2415
_ID_TRF_FC = 2416
_ID_OTH = 2417  # other deposits total
_ID_OTH_LC = 2418
_ID_OTH_FC = 2419

_SERIES_IDS = f"{_ID_TRF},{_ID_TRF_FC},{_ID_OTH},{_ID_OTH_FC}"

_HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MDV uses render() + MMA Statistics API")


def _empty() -> pd.DataFrame:
    return empty_frame()


def _token() -> str | None:
    t = (os.environ.get("MMA_API_TOKEN") or os.environ.get("MDV_API_TOKEN") or "").strip()
    return t or None


def _fetch_series(ids: str, token: str) -> list[dict]:
    headers = {**_HEADERS_BASE, "Authorization": f"Bearer {token}"}
    r = requests.get(
        _API,
        params={"ids": ids},
        headers=headers,
        timeout=120,
        verify=False,
    )
    r.raise_for_status()
    payload = r.json()
    data = payload.get("data") or []
    if not data:
        raise RuntimeError(f"empty API data for ids={ids}: {payload.get('meta')}")
    return data


def _to_period_map(series: dict) -> dict[str, float]:
    """date → amount (raw MVR)."""
    out: dict[str, float] = {}
    for pt in series.get("data") or []:
        d = str(pt.get("date") or "")[:10]
        if len(d) < 7:
            continue
        period = d[:7]  # YYYY-MM
        try:
            out[period] = float(pt["amount"])
        except (TypeError, ValueError, KeyError):
            continue
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        token = _token()
        if not token:
            logger.error(
                "[MDV] MMA_API_TOKEN not set. Register at %s and put token in .env",
                "https://database.mma.gov.mv/api/register",
            )
            return _empty()

        series_list = _fetch_series(_SERIES_IDS, token)
        by_id = {int(s["id"]): s for s in series_list}
        need = {_ID_TRF, _ID_TRF_FC, _ID_OTH, _ID_OTH_FC}
        missing = need - set(by_id)
        if missing:
            logger.error("[MDV] missing series ids %s", sorted(missing))
            return _empty()

        trf = _to_period_map(by_id[_ID_TRF])
        trf_fc = _to_period_map(by_id[_ID_TRF_FC])
        oth = _to_period_map(by_id[_ID_OTH])
        oth_fc = _to_period_map(by_id[_ID_OTH_FC])

        periods = sorted(set(trf) & set(trf_fc) & set(oth) & set(oth_fc))
        obs: list[tuple[str, float, float]] = []
        for p in periods:
            fcd_raw = trf_fc[p] + oth_fc[p]
            td_raw = trf[p] + oth[p]
            if td_raw <= 0 or fcd_raw < 0:
                continue
            # MVR → million MVR
            fcd = fcd_raw / 1_000_000.0
            td = td_raw / 1_000_000.0
            if fcd > td * 1.05:
                continue
            if td < 100 or td > 50_000_000:
                continue
            ratio = fcd / td
            if ratio > 0.95 or ratio < 0.05:
                continue
            obs.append((p, fcd, td))

        if not obs:
            logger.error("[%s] no overlapping periods from API", country_code)
            return _empty()

        out = long_rows(country_code, obs)
        logger.info(
            "[MDV] MMA API → %d rows (%s~%s) unit=MVR million",
            len(out),
            out["period"].min(),
            out["period"].max(),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
