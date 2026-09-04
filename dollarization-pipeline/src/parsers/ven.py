"""Venezuela: BCV "Balances monetarios" — Bancos Universales/Comerciales y de
Desarrollo, "Resumen del Balance Monetario Consolidado" xls.

The xls link is scraped from https://www.bcv.org.ve/estadisticas/balances-monetarios
(re-discovered on every run since the document path can be restructured).

This xls holds one sheet per half-year (e.g. 'I Semestre 2026', 'II Semestre 1999') of
monthly data, and sheets accumulate continuously from 1999 to the present (2021 is a
special case, split into 3+3 months as 'Ene - Sep 2021'/'Oct - Dic 2021' due to the
currency redenomination). Row 5 is the month header (e.g. 'Ene 2026'); the label column
(column A) is searched for the rows 'DEPOSITOS EN MONEDA NACIONAL' (national-currency
deposits) and 'DEPOSITOS EN MONEDA EXTRANJERA' (foreign-currency deposits = FCD) - the
actual row numbers for these two labels keep shifting year to year (e.g. rows 40/65 in
1999, 44/68 in 2010, 45/70 in 2026), so they are looked up by label text every time.

TD = national-currency deposits + foreign-currency deposits (non-resident deposits,
certificates of deposit, etc. are excluded, matching the same convention other country
parsers use of summing only 'core deposits'). FCD = foreign-currency deposits.

Venezuela underwent three currency redenominations - 2008 (Bolívar Fuerte), 2018 (Bolívar
Soberano), and 2021 (Bolívar Digital, dropping 6 zeros) - so the absolute-value scale is
completely different across periods (the file itself carries a footnote: 'new currency
notation applied from 2021-10-01, 6 digits removed'). FCD_TD_RATIO is a within-period ratio
so it remains valid across redenominations, but the absolute FCD/TD values (unit: thousand
bolívares or bolívares, depending on the period) should not be concatenated as-is into a
single time series - caution is needed when comparing absolute values on a chart (the ratio
axis is unaffected)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3
import xlrd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_LIST_PAGE = "https://www.bcv.org.ve/estadisticas/balances-monetarios"
_XLS_LINK_RE = re.compile(
    r'href="([^"]*bcos\._com\._univ\._y_de_desarrollo\._resumen_bal\._monetario_consolidado_mensual\.xls)"',
    re.I,
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}
_MONTH_HEADER_RE = re.compile(r"([A-Za-z]{3})\.?\s*(\d{4})")
_NATIONAL_LABEL = "deposit"  # re-confirmed below against the 'moneda nacional'/'moneda extranjera' combination
_ACCENTS = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("VEN fetches the xls via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _find_xls_url() -> str | None:
    resp = requests.get(_LIST_PAGE, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    match = _XLS_LINK_RE.search(resp.text)
    if not match:
        return None
    href = match.group(1)
    return href if href.startswith("http") else "https://www.bcv.org.ve" + href


def _normalize(s: str) -> str:
    return s.translate(_ACCENTS).strip().upper()


def _find_row(sh, label: str) -> int | None:
    for r in range(sh.nrows):
        cell = sh.cell_value(r, 0)
        if isinstance(cell, str) and _normalize(cell) == label:
            return r
    return None


def _header_periods(sh, header_row: int) -> dict[int, str]:
    periods = {}
    for c in range(1, sh.ncols):
        v = sh.cell_value(header_row, c)
        if not isinstance(v, str):
            continue
        m = _MONTH_HEADER_RE.search(_normalize(v).lower())
        if not m:
            continue
        month = _MONTHS.get(m.group(1).lower())
        if month:
            periods[c] = f"{int(m.group(2))}-{month:02d}"
    return periods


def _parse_sheet(sh, country_code: str, now: str) -> list[dict]:
    header_row = None
    for r in range(min(10, sh.nrows)):
        if _header_periods(sh, r):
            header_row = r
            break
    if header_row is None:
        return []
    periods = _header_periods(sh, header_row)
    if not periods:
        return []

    national_row = _find_row(sh, "DEPOSITOS EN MONEDA NACIONAL")
    fx_row = _find_row(sh, "DEPOSITOS EN MONEDA EXTRANJERA")
    if national_row is None or fx_row is None:
        return []

    rows = []
    for col, period in periods.items():
        national = sh.cell_value(national_row, col)
        fx = sh.cell_value(fx_row, col)
        if not isinstance(national, (int, float)) or not isinstance(fx, (int, float)):
            continue
        fcd = float(fx)
        td = float(national) + fcd
        if td <= 0:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })
    return rows


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    xls_url = _find_xls_url()
    if not xls_url:
        logger.warning("[%s] xls link not found on listing page", country_code)
        return _empty()

    resp = requests.get(xls_url, headers=_HEADERS, timeout=60, verify=False)
    resp.raise_for_status()
    wb = xlrd.open_workbook(file_contents=resp.content)

    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for sheet_name in wb.sheet_names():
        sh = wb.sheet_by_name(sheet_name)
        try:
            rows.extend(_parse_sheet(sh, country_code, now))
        except Exception:
            logger.warning("[%s] sheet parse failed: %s", country_code, sheet_name, exc_info=True)

    if not rows:
        return _empty()

    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
