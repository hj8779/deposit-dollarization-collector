"""Japan: BOJ Time-Series Data Search API — MD10 deposits by depositor.

API (published 2026-02, no key required):
  https://www.stat-search.boj.or.jp/api/v1/getDataCode
  Manual: https://www.stat-search.boj.or.jp/info/api_manual_en.pdf
  Portal: https://www.stat-search.boj.or.jp/

Statistics DB: MD10 — Amounts Outstanding of Deposits by Depositor
(Domestically Licensed Banks, Total Value, Total of All Depositors)

  FCD  DLDDLKY45090_DLDD3DBTTL12
       Total Value / Foreign Currency Deposits / Total of All Depositors
  TD   DLDDLKY45090_DLDD3DBTTL
       Total Value / Total Value / Total of All Depositors
       (= sum of yen + foreign-currency + nonresident yen deposits; the
       dollarization-ratio denominator)

Note: the item some sources refer to, 「定期預金・据置貯金」(Time Deposits and
Fixed Savings, code ...TTL8), is a subcategory of time deposits, so using it
as the denominator would overstate FCD/TD. To match the pipeline convention
(foreign-currency deposits over total deposits), Total Value is used as TD.

Unit: 100 million yen (億円)
Frequency: recorded in quarterly slots, but recent data is FH (semiannual) —
observations where Q2/Q4 values are 0 are excluded.
period: quarter-end month (Q1->03, Q2->06, Q3->09, Q4->12).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
_PORTAL = "https://www.stat-search.boj.or.jp/"
_DB = "MD10"

# Domestically Licensed Banks / Total of All Depositors / Total Value
_CODE_FCD = "DLDDLKY45090_DLDD3DBTTL12"  # Foreign Currency Deposits
_CODE_TD = "DLDDLKY45090_DLDD3DBTTL"  # Total deposits

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*",
    "Accept-Encoding": "gzip",
    "Referer": _PORTAL,
}

# SURVEY_DATES YYYYQQ → quarter-end month
_Q_TO_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("JPN calls the BOJ API via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _survey_to_period(survey) -> str | None:
    """199802 / '199802' / 202601 → '1998-06' / '2026-03'."""
    try:
        s = str(int(survey)).zfill(6)
    except (TypeError, ValueError):
        return None
    if len(s) != 6:
        return None
    year = int(s[:4])
    q = int(s[4:6])
    month = _Q_TO_MONTH.get(q)
    if month is None or year < 1960 or year > 2100:
        return None
    return f"{year}-{month:02d}"


def _fetch_series() -> dict[str, dict]:
    """code -> {period: value}."""
    codes = f"{_CODE_FCD},{_CODE_TD}"
    params = {
        "format": "json",
        "lang": "en",
        "db": _DB,
        "code": codes,
    }
    resp = requests.get(_API, params=params, headers=_HEADERS, timeout=120, verify=False)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("STATUS") != 200:
        raise RuntimeError(
            f"BOJ API error: {payload.get('MESSAGEID')} {payload.get('MESSAGE')}"
        )

    out: dict[str, dict] = {}
    for item in payload.get("RESULTSET") or []:
        code = item.get("SERIES_CODE")
        vals = item.get("VALUES") or {}
        dates = vals.get("SURVEY_DATES") or []
        numbers = vals.get("VALUES") or []
        if not code or len(dates) != len(numbers):
            logger.warning("[JPN] skip malformed series %s", code)
            continue
        series: dict[str, float] = {}
        for d, v in zip(dates, numbers):
            if v is None:
                continue
            try:
                num = float(v)
            except (TypeError, ValueError):
                continue
            # exclude empty quarters (0) in FH slots — an actual zero balance is extremely unlikely
            if num <= 0:
                continue
            period = _survey_to_period(d)
            if not period:
                continue
            series[period] = num
        out[code] = series
        logger.info(
            "[JPN] %s: %d obs %s~%s unit=%s",
            code,
            len(series),
            min(series) if series else "-",
            max(series) if series else "-",
            item.get("UNIT"),
        )
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        series = _fetch_series()
    except Exception as e:
        logger.exception("[%s] BOJ API failed: %s", country_code, e)
        return _empty()

    fcd_map = series.get(_CODE_FCD) or {}
    td_map = series.get(_CODE_TD) or {}
    if not fcd_map or not td_map:
        logger.error("[%s] missing series keys %s", country_code, list(series))
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    periods = sorted(set(fcd_map) & set(td_map))
    rows = []
    for period in periods:
        fcd = fcd_map[period]
        td = td_map[period]
        if td <= 0:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in (
            ("FCD", round(fcd, 4)),
            ("TD", round(td, 4)),
            ("FCD_TD_RATIO", ratio),
        ):
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    if not rows:
        return _empty()
    df = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] merged %d rows (%s~%s)",
        country_code, len(df), df["period"].min(), df["period"].max(),
    )
    return df
