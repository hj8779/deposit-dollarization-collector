"""Israel: Bank of Israel Fusion Edge SDMX — Monetary Aggregates deposits.

Portal: https://edge.boi.gov.il/FusionDataBrowser/
Path: Money and Debt aggregates -> Public's Assets Portfolio -> Monetary Aggregates

SDMX dataflow: BOI.STATISTICS / MAG / 1.0
Example CSV:
  https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/BOI.STATISTICS/MAG/1.0/{SERIES}?locale=en&format=csv

FCD (foreign-currency deposits, million NIS):
  MAG_TRANS_OTH_DEP_FC_INCLUDED_2SR_M_E  DATA_ITEM=DD1YF
    Broad money: FC denominated current accounts + deposits <=1y
  MAG_OTH_DEP_FC_EXCLUDED_2SR_M          DATA_ITEM=OTBDF
    Deposits outside broad money (foreign currency)
  FCD = DD1YF + OTBDF

TD (total deposits, million NIS) — dollarization-ratio denominator:
  The total deposit balance is built by also summing the local-currency (NC)
  counterpart series.
  MAG_TRANS_DEP_NC_INCLUDED_2SR_M_E      DATA_ITEM=DDI   (NC transferable deposits within BM)
  MAG_OTH_DEP_NC_INCLUDED_2SR_M_E        DATA_ITEM=D1Y   (NC other deposits within BM)
  MAG_OTH_DEP_NC_EXCLUDED_2SR_M          DATA_ITEM=OTBDI (NC deposits outside BM)
  + the two FCD component series
  TD = DDI + D1Y + OTBDI + DD1YF + OTBDF

Note: MAG_A028_MA DATA_ITEM=TD is "M2: time deposits" (time deposits only),
not total deposits. Using it as the denominator inflates FCD/TD above the 50%
range. To match the dollarization-pipeline convention (foreign-currency
deposits over total deposits), we use the summation above instead.

Frequency: monthly. Unit: million NIS (UNIT_MULT=6). The non-BM series
(OTBDF/OTBDI) are available starting 2007-03, so the common period range is
roughly 2007-03 to the latest (observed OTBDF/OTBDI lag is possible).
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PORTAL = "https://edge.boi.gov.il/FusionDataBrowser/"
_SDMX = (
    "https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/"
    "BOI.STATISTICS/MAG/1.0"
)

# series_code -> role group
_SERIES = {
    # FCD components
    "MAG_TRANS_OTH_DEP_FC_INCLUDED_2SR_M_E": "fcd",  # DD1YF
    "MAG_OTH_DEP_FC_EXCLUDED_2SR_M": "fcd",  # OTBDF
    # Local-currency deposits (for total TD)
    "MAG_TRANS_DEP_NC_INCLUDED_2SR_M_E": "lcd",  # DDI
    "MAG_OTH_DEP_NC_INCLUDED_2SR_M_E": "lcd",  # D1Y
    "MAG_OTH_DEP_NC_EXCLUDED_2SR_M": "lcd",  # OTBDI
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/xml,*/*",
    "Referer": _PORTAL,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("ISR fetches BOI SDMX CSV via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _fetch_series(series_code: str) -> pd.Series:
    url = f"{_SDMX}/{series_code}?locale=en&format=csv"
    resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
    resp.raise_for_status()
    if "OBS_VALUE" not in resp.text[:500]:
        raise RuntimeError(f"unexpected SDMX CSV for {series_code}: {resp.text[:120]!r}")
    df = pd.read_csv(StringIO(resp.text))
    if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
        raise RuntimeError(f"missing columns in {series_code}: {list(df.columns)}")
    s = (
        df.assign(
            TIME_PERIOD=df["TIME_PERIOD"].astype(str).str.strip(),
            OBS_VALUE=pd.to_numeric(df["OBS_VALUE"], errors="coerce"),
        )
        .dropna(subset=["OBS_VALUE"])
        .drop_duplicates(subset=["TIME_PERIOD"], keep="last")
        .set_index("TIME_PERIOD")["OBS_VALUE"]
        .sort_index()
    )
    # keep YYYY-MM monthly only
    s = s[s.index.str.match(r"^\d{4}-\d{2}$")]
    return s


def _build_frame(country_code: str, fcd: pd.Series, td: pd.Series) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    periods = sorted(set(fcd.index) & set(td.index))
    rows = []
    for period in periods:
        fv = float(fcd[period])
        tv = float(td[period])
        if tv <= 0 or fv < 0:
            continue
        year = int(period[:4])
        ratio = round((fv / tv) * 100, 4)
        for indicator, value in (
            ("FCD", round(fv, 4)),
            ("TD", round(tv, 4)),
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
    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    loaded: dict[str, pd.Series] = {}

    for code in _SERIES:
        try:
            s = _fetch_series(code)
            loaded[code] = s
            logger.info(
                "[%s] %s: %d months %s~%s",
                country_code, code, len(s), s.index.min(), s.index.max(),
            )
        except Exception as e:
            logger.exception("[%s] fetch failed %s: %s", country_code, code, e)

    needed = list(_SERIES)
    missing = [c for c in needed if c not in loaded]
    if missing:
        logger.error("[%s] missing series: %s", country_code, missing)
        return _empty()

    # align on intersection of all components
    common = None
    for s in loaded.values():
        common = set(s.index) if common is None else (common & set(s.index))
    if not common:
        logger.error("[%s] no common periods across series", country_code)
        return _empty()

    periods = sorted(common)
    fcd_parts = [loaded[c] for c, role in _SERIES.items() if role == "fcd"]
    all_parts = list(loaded.values())

    fcd = sum(s.reindex(periods) for s in fcd_parts)
    td = sum(s.reindex(periods) for s in all_parts)

    df = _build_frame(country_code, fcd, td)
    if not df.empty:
        logger.info(
            "[%s] merged %d rows (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    return df
