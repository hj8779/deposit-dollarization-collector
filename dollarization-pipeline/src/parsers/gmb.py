"""Gambia: CBG Macroeconomic Data Warehouse (DataWarehousePro).

Portal: https://app.datawarehousepro.com/go/cbg
(Central Bank of The Gambia Macroeconomic Data Warehouse)

The Monetary Survey (MON)'s Quasi money / deposit items only distinguish
private/public and have no currency (foreign-currency) breakdown. Balance of
Payments' Currency and deposits is an external-sector item and differs from
resident FCD. The most directly relevant public time series for resident
foreign-currency exposure is the following indicator under Financial Sector
(FIN) > Commercial Banks > Financial soundness indicators.

    mnemonic  fcdlttlcb
    name      19. Foreign-currency-denominated liabilities to total liabilities
    API       GET /guest/getMnemonicData/cbg/FIN/fcdlttlcb
    frequency Quarterly (Q); observed data 2007Q3~2023Q3 (metadata says
              first_observation=2000Q1, but the actual data array starts at
              2007Q3)
    unit meta labeled as "mill. Of GMD" but the values are actually a ratio
              (%) — consistent with the title "liabilities to total
              liabilities" and sample values (e.g. 2022Q4=34.62)

The related category 18 (fcdlttlocb, FC-denominated loans/total loans) is a
loan-side supplementary indicator and is excluded from the default collection
target (can be added later if needed).

This pipeline has no numerator/denominator available to reconstruct absolute
FCD/TD balances, so only indicator=FCD_TD_RATIO is loaded (a liabilities-based
dollarization-ratio proxy). Adapter notes state explicitly that this may
differ in definition from a pure deposit-based dollarization ratio.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_ACCOUNT = "cbg"
_DATABANK = "FIN"
_MNEMONIC = "fcdlttlcb"  # FC-denominated liabilities / total liabilities (%)
_API = (
    f"https://app.datawarehousepro.com/guest/getMnemonicData/"
    f"{_ACCOUNT}/{_DATABANK}/{_MNEMONIC}"
)
_PORTAL = "https://app.datawarehousepro.com/go/cbg"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": _PORTAL,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("GMB calls the Data Warehouse API via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _period_from_label(label: str) -> tuple[int, str] | None:
    """'2007Q3' / '2007-Q3' / '2007 Q3' -> (2007, '2007-Q3')."""
    text = str(label).strip().upper().replace(" ", "")
    m = re.fullmatch(r"(\d{4})-?Q([1-4])", text)
    if not m:
        return None
    year, q = int(m.group(1)), int(m.group(2))
    return year, f"{year}-Q{q}"


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    try:
        resp = requests.get(_API, headers=_HEADERS, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.exception("[%s] Data Warehouse API failed: %s", country_code, e)
        return _empty()

    if not isinstance(payload, dict) or "data" not in payload:
        logger.error("[%s] Unexpected response: %s", country_code, str(payload)[:200])
        return _empty()

    rows = []
    for point in payload.get("data") or []:
        label = point.get("description")
        parsed = _period_from_label(label) if label else None
        if parsed is None:
            continue
        year, period = parsed
        try:
            value = float(point.get("value"))
        except (TypeError, ValueError):
            continue
        if value != value:  # NaN
            continue
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": "FCD_TD_RATIO",
            "value": round(value, 4),
            "updated_at": now,
        })

    if not rows:
        logger.warning("[%s] No observations (mnemonic=%s)", country_code, _MNEMONIC)
        return _empty()

    df = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] %s (%s): %d quarters %s~%s (unit meta=%s; values are a ratio%%)",
        country_code,
        payload.get("name_of_series"),
        _MNEMONIC,
        len(df),
        df["period"].min(),
        df["period"].max(),
        payload.get("unit_of_measure"),
    )
    return df
