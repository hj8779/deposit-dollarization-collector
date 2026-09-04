"""Dominican Republic: BCRD (Banco Central de la República Dominicana) monetary and financial
statistics.

Downloads the "Balance sectorial de las OSD: Instrumentos y sectores institucionales (Pasivos
en ME)" file from the BCRD statistics portal
(bancentral.gov.do/a/CustomView/2536-sector-monetario-y-financiero) and extracts resident
Foreign Currency Deposits (FCD).

File structure:
- Sheet: II.3.b.OSD-Pasivos ME
- Rows 9-11: headers (category/sector/column number)
- Rows 12+: monthly data (from 2001-12)
- Column 0: year (Año)
- Column 1: month (Mes - Ene/Feb/.../Dic)
- Column 2: non-resident deposits (No residentes) - excluded from the FCD calculation
- Columns 3-9: resident foreign-currency deposits (summed across sectors = FCD)
  - 3: other deposit-taking institutions, 4: other financial corporations, 5: central government
  - 6: local government, 7: public non-financial corporations, 8: other non-financial corporations
  - 9: households and ISFLSH
- Column 17: total foreign-currency liabilities (Total pasivos)

Units: million pesos (Pesos Dominicanos, DOP) - FCD is also already published as a peso amount,
so it can be added directly to domestic-currency deposits without any currency conversion.

TD (total deposits) = the value obtained by summing the same columns (columns 3-9, with an
identical sector composition: Otras sociedades de depósito/financieras, Gobierno central,
Gobiernos estatales y locales, Sociedades públicas/otras no financieras, Hogares e ISFLSH) from
the paired 'Pasivos en MN' (domestic currency, balance_osd_pasivos_mn.xlsx, sheet
'II.3.a.OSD-Pasivos MN') file, plus FCD (columns 3-9 sum from the ME file above).
Both files are already in the same units ('million pesos'), so no exchange-rate conversion is
needed.
"""

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "https://cdn.bancentral.gov.do/documents/estadisticas/sector-monetario-y-financiero/documents/balance_osd_pasivos_me.xlsx"
_MN_FILE_URL = "https://cdn.bancentral.gov.do/documents/estadisticas/sector-monetario-y-financiero/documents/balance_osd_pasivos_mn.xlsx"
_MN_SHEET_NAME = "II.3.a.OSD-Pasivos MN"

_MONTHS_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# Resident foreign-currency deposit column indices (excludes non-resident column 2)
_FCD_COLUMNS = [3, 4, 5, 6, 7, 8, 9]  # sum of columns 3-9


def _sector_sum_by_period(df: pd.DataFrame, country_code: str, indicator: str, now: str) -> list[dict]:
    """Builds the summed time series across columns 3-9 (deposits by resident sector) into
    (country_code, year, period, indicator, value) rows."""
    data_start = None
    for i in range(df.shape[0]):
        cell = df.iloc[i, 0]
        try:
            year_check = int(cell)
            if 1990 <= year_check <= 2100:
                data_start = i
                break
        except (ValueError, TypeError):
            continue

    if data_start is None:
        logger.error("[%s] Could not find data start row", country_code)
        return []

    rows = []
    for i in range(data_start, df.shape[0]):
        row = df.iloc[i]
        year_val = row.iloc[0]
        month_val = row.iloc[1]

        if pd.isna(year_val):
            continue
        try:
            year = int(year_val)
        except (ValueError, TypeError):
            continue

        if pd.isna(month_val):
            continue
        month_str = str(month_val).strip().lower()[:3]
        month = _MONTHS_ES.get(month_str)
        if month is None:
            continue

        value = 0.0
        for col_idx in _FCD_COLUMNS:
            val = row.iloc[col_idx]
            if pd.notna(val):
                try:
                    value += float(val)
                except (ValueError, TypeError):
                    pass

        if value == 0.0:
            continue

        period = f"{year}-{month:02d}"
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": indicator,
            "value": round(value, 2),
            "updated_at": now,
        })
    return rows


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Extracts FCD and TD from the Balance sectorial OSD Pasivos en ME/MN Excel files."""
    from io import BytesIO

    now = datetime.now(timezone.utc).isoformat()

    try:
        me_df = pd.read_excel(BytesIO(content), sheet_name="II.3.b.OSD-Pasivos ME", header=None)
    except Exception as e:
        logger.error("[%s] Failed to read Excel file: %s", country_code, e)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    fcd_rows = _sector_sum_by_period(me_df, country_code, INDICATOR, now)
    if not fcd_rows:
        logger.warning("[%s] Could not find foreign-currency deposit data", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    fcd_by_period = {r["period"]: r["value"] for r in fcd_rows}

    td_rows: list[dict] = []
    try:
        mn_content = requests.get(
            _MN_FILE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60
        ).content
        mn_df = pd.read_excel(BytesIO(mn_content), sheet_name=_MN_SHEET_NAME, header=None)
        mn_rows = _sector_sum_by_period(mn_df, country_code, INDICATOR_TD, now)
        for r in mn_rows:
            fcd_value = fcd_by_period.get(r["period"])
            if fcd_value is None:
                continue
            td_rows.append({**r, "value": round(r["value"] + fcd_value, 2)})
    except Exception as e:
        logger.warning("[%s] Failed to process MN (domestic currency) file, proceeding without TD: %s", country_code, e)

    result = pd.DataFrame(fcd_rows + td_rows).sort_values(["period", "indicator"]).reset_index(drop=True)
    logger.info("[%s] Extracted %d months of foreign-currency deposit data (%s to %s)",
                country_code, len(fcd_rows), min(fcd_by_period), max(fcd_by_period))
    return result
