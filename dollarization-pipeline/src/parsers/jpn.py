"""Japan: BOJ Time-Series Data Search API — MD10 deposits by depositor.

API (2026-02 공개, 키 불필요):
  https://www.stat-search.boj.or.jp/api/v1/getDataCode
  매뉴얼: https://www.stat-search.boj.or.jp/info/api_manual_en.pdf
  포털:   https://www.stat-search.boj.or.jp/

통계 DB: MD10 — Amounts Outstanding of Deposits by Depositor
(Domestically Licensed Banks, Total Value, Total of All Depositors)

  FCD  DLDDLKY45090_DLDD3DBTTL12
       Total Value / Foreign Currency Deposits / Total of All Depositors
  TD   DLDDLKY45090_DLDD3DBTTL
       Total Value / Total Value / Total of All Depositors
       (= 엔화+외화+비거주자 엔 예금 합계; 달러화율 분모)

참고: 사용자가 언급한 「定期預金・据置貯金」(Time Deposits and Fixed Savings,
코드 …TTL8)은 시간성 예금 하위항목이라 분모로 쓰면 FCD/TD가 과대 계상된다.
파이프라인 관례(총예금 대비 외화예금)에 맞게 Total Value를 TD로 사용한다.

단위: 100 million yen (億円)
빈도: 분기 슬롯에 수록되나 최근은 FH(반기) — Q2·Q4 값이 0인 관측은 제외.
period: 분기말 월 (Q1→03, Q2→06, Q3→09, Q4→12).
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
    raise NotImplementedError("JPN는 render()로 BOJ API를 호출한다")


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
            # FH 슬롯의 빈 분기(0) 제외 — 실제 0 잔액 가능성은 극히 낮음
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
