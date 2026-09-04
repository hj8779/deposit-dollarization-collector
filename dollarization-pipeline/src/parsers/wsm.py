"""Samoa: Central Bank of Samoa "Money and Banking" statistics, Table A-4
"Structure of Money Supply" (cbs.gov.ws/money-and-banking → static xlsx download,
no blocking).

This table reports composition as a share of Broad Money (%), so it doesn't give FCD/TD
directly, but row 17 separately has the quarter's absolute Broad Money value (unit: Tala
million), so the absolute values can be recovered by multiplying share × total:
  FCD_tala = FCD%(row 11) × BroadMoney_tala(row 17) / 100
  TD_tala  = BroadMoney_tala × (1 − Currency%(row 8)/100)   (all deposits, i.e. everything
                                                              except currency in circulation)

Quarterly data, based on Samoa's fiscal year (July-June); the column headers mix two
formats: early on, Roman numerals (I-IV, where I=end of September/II=end of December/
III=end of March next year/IV=end of June next year), later switching to month names
(Mar/June/Sep/Dec) - both mean the same thing, so they're mapped to a unified scheme.

The most recent quarter (2026-03) has an error in the source spreadsheet itself (row 11's
FCD% is identical to row 7's M1% total, which contradicts the definition that FCD is a
subset of M1) - such an evidently impossible value (FCD% > M1%, i.e. FCD exceeding its own
superset M1) is treated as a source-data error and skipped."""

from __future__ import annotations

from datetime import datetime, timezone

import openpyxl
import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_XLSX_URL = "https://cbs.gov.ws/media/A4-Structure-of-Money-Supply-7.xlsx"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("WSM fetches the xlsx via render()")

_QUARTER_END_MONTH = {"I": 9, "II": 12, "III": 3, "IV": 6, "Sep": 9, "Dec": 12, "Mar": 3, "June": 6}
_ROLLOVER_MONTHS = {3, 6}  # III/Mar, IV/June fall in the year after the fiscal-year label

_M1_ROW = 7
_CURRENCY_ROW = 8
_FCD_ROW = 11
_BROAD_MONEY_ROW = 17


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    resp = requests.get(_XLSX_URL, headers=_HEADERS, timeout=60)
    resp.raise_for_status()

    from io import BytesIO
    wb = openpyxl.load_workbook(BytesIO(resp.content), data_only=True)
    ws = wb["A4"]

    fiscal_year = None
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for c in range(2, ws.max_column + 1):
        year_cell = ws.cell(row=5, column=c).value
        if isinstance(year_cell, str) and "/" in year_cell:
            fiscal_year = int(year_cell.split("/")[0])
        quarter_cell = ws.cell(row=6, column=c).value
        month = _QUARTER_END_MONTH.get(str(quarter_cell).strip()) if quarter_cell else None
        if fiscal_year is None or month is None:
            continue
        year = fiscal_year + 1 if month in _ROLLOVER_MONTHS else fiscal_year

        currency_pct = ws.cell(row=_CURRENCY_ROW, column=c).value
        fcd_pct = ws.cell(row=_FCD_ROW, column=c).value
        m1_pct = ws.cell(row=_M1_ROW, column=c).value
        broad_money = ws.cell(row=_BROAD_MONEY_ROW, column=c).value
        if not all(isinstance(v, (int, float)) for v in (currency_pct, fcd_pct, m1_pct, broad_money)):
            continue
        if fcd_pct > m1_pct:
            continue  # impossible value that looks like a source-data error (FCD is a subset of M1 but exceeds the whole of M1)

        fcd = fcd_pct * broad_money / 100
        td = broad_money * (1 - currency_pct / 100)
        if td <= 0 or fcd <= 0 or fcd > td:
            continue

        period = f"{year}-{month:02d}"
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    if not rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
