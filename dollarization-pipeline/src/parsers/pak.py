"""Pakistan: SBP "Broad Money (M2)" archive xls.

On https://www.sbp.org.pk/economic-data,
https://www.sbp.org.pk/assets/document/BroadMoney_M2_Arch.xls contains one sheet per
era (M2_FY70-FY90, ..., M2_(FY23 to onwards)) covering the full time series from
1969-06 to the present. sbp.org.pk returns 403 for default requests headers, so a
browser-style User-Agent/Referer is required.

The header row / label column position varies slightly by sheet (older sheets have
the header on row 2 with labels in column A; newer sheets have the header on row 4
with labels in column B/C, etc.), so parsing uses a common anchor: first locate the
'Currency in Circulation' row, then scan upward for the first row with many numeric
values (Excel date serials) and treat it as the header, then within 15 rows below
'Currency in Circulation' look for rows labeled 'Demand Deposit'/'Time Deposit'/
'Resident...Foreign Currency' (RFCDs).

TD = Demand Deposits + Time Deposits + RFCDs (confirmed to match 'Total Deposits
with Banks' exactly). FCD = RFCDs. Sheets before 1998 have RFCD values entirely
blank (the line item exists but is empty), so that period is automatically excluded
(it appears the FX resident-deposit scheme either started then, or wasn't tracked
separately before that).

Recent sheets are weekly (Fri/Sat close) frequency, which is too dense to use as-is,
so we resample to monthly by keeping only the last observation of each month for
each (year, month). Unit: PKR million."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pandas as pd
import requests
import xlrd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_XLS_URL = "https://www.sbp.org.pk/assets/document/BroadMoney_M2_Arch.xls"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.sbp.org.pk/economic-data",
}

_CURRENCY_LABEL_RE = re.compile(r"currency in circulation", re.I)
_DEMAND_LABEL_RE = re.compile(r"demand deposit", re.I)
_TIME_LABEL_RE = re.compile(r"time deposit", re.I)
_RFCD_LABEL_RE = re.compile(r"resident.*foreign currency|rfcd", re.I)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("PAK fetches the xls via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _find_row(sh, pattern: re.Pattern, start: int = 0, end: int | None = None) -> int | None:
    end = sh.nrows if end is None else min(end, sh.nrows)
    for r in range(start, end):
        for c in range(sh.ncols):
            v = sh.cell_value(r, c)
            if isinstance(v, str) and pattern.search(v):
                return r
    return None


def _find_header_row(sh, before: int) -> int | None:
    for r in range(before - 1, -1, -1):
        floats = sum(1 for c in range(sh.ncols) if isinstance(sh.cell_value(r, c), float))
        if floats >= sh.ncols * 0.3:
            return r
    return None


def _excel_date(serial: float, datemode: int) -> date | None:
    try:
        y, m, d, *_ = xlrd.xldate_as_tuple(serial, datemode)
        return date(y, m, d)
    except Exception:
        return None


def _parse_sheet(sh, datemode: int) -> list[tuple[date, float, float]]:
    """[(date, fcd, td), ...]"""
    currency_row = _find_row(sh, _CURRENCY_LABEL_RE)
    if currency_row is None:
        return []
    header_row = _find_header_row(sh, currency_row)
    if header_row is None:
        return []
    demand_row = _find_row(sh, _DEMAND_LABEL_RE, currency_row, currency_row + 15)
    time_row = _find_row(sh, _TIME_LABEL_RE, currency_row, currency_row + 15)
    rfcd_row = _find_row(sh, _RFCD_LABEL_RE, currency_row, currency_row + 15)
    if demand_row is None or time_row is None or rfcd_row is None:
        return []

    columns = []
    for c in range(sh.ncols):
        v = sh.cell_value(header_row, c)
        if isinstance(v, float) and v > 1000:
            d = _excel_date(v, datemode)
            if d:
                columns.append(c)

    out = []
    for c in columns:
        demand = sh.cell_value(demand_row, c)
        time_dep = sh.cell_value(time_row, c)
        rfcd = sh.cell_value(rfcd_row, c)
        if not all(isinstance(v, (int, float)) for v in (demand, time_dep, rfcd)):
            continue
        d = _excel_date(sh.cell_value(header_row, c), datemode)
        if not d:
            continue
        fcd = float(rfcd)
        td = float(demand) + float(time_dep) + fcd
        if td <= 0:
            continue
        out.append((d, fcd, td))
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    resp = requests.get(_XLS_URL, headers=_HEADERS, timeout=60)
    resp.raise_for_status()
    wb = xlrd.open_workbook(file_contents=resp.content)

    observations: list[tuple[date, float, float]] = []
    for sheet_name in wb.sheet_names():
        sh = wb.sheet_by_name(sheet_name)
        try:
            found = _parse_sheet(sh, wb.datemode)
            observations.extend(found)
            logger.info("[%s] %s -> %d observations", country_code, sheet_name, len(found))
        except Exception:
            logger.warning("[%s] sheet parse failed: %s", country_code, sheet_name, exc_info=True)

    if not observations:
        return _empty()

    # Resample to monthly by keeping only the last observation of each (year, month)
    monthly: dict[tuple[int, int], tuple[date, float, float]] = {}
    for d, fcd, td in observations:
        key = (d.year, d.month)
        prev = monthly.get(key)
        if prev is None or d > prev[0]:
            monthly[key] = (d, fcd, td)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for (year, month), (d, fcd, td) in monthly.items():
        period = f"{year}-{month:02d}"
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
