"""Costa Rica: combines two individual statistical tables (CodCuadro) from the BCCR
(Banco Central de Costa Rica) 'Indicadores Económicos' data portal (gee.bccr.fi.cr).
    CodCuadro=167: Depósitos de ahorro en moneda extranjera mantenidos en el sistema financiero
                   (FX savings deposits, 1997-present)
    CodCuadro=147: Depósitos en cuenta corriente en moneda extranjera mantenidos en el sistema
                   bancario (FX current/checking accounts, 1987-present)
FCD = 167 + 147. Searched the BCCR catalog (frmBusquedas.aspx) for a separate table
corresponding to 'FX time deposits (depósito a plazo en moneda extranjera)', but none exists -
the two categories above are all that BCCR publishes.

Each table's own page is a UI widget (date-range inputs, etc.) so the table can't be seen
without JS, but the page's embedded 'Exportar datos a Excel' button (js_doExport()) actually
opens a plain URL of the form '...frmVerCatCuadro.aspx?CodCuadro={code}&Idioma=1&Exportar=True',
which can be GET'd directly with requests. The response only has a .xls extension - it's
actually an HTML table, so pandas.read_html reads it directly.

The exported table is a year(row) x month(column) matrix, with values scaled as integers
(e.g. the raw January 1998 savings-deposit value 22104846115 -> actual value is
221.048... million USD). Cross-checked against the value shown on the page (Spanish
thousands-separator '.'/decimal-comma ',' notation, e.g. '5.176,9') to confirm the scale
factor is exactly 1e8 (517690172446 / 1e8 = 5176.90, matching the displayed '5.176,9').

TD (total deposits) calculation: the corresponding domestic-currency (colón) tables
    CodCuadro=172: Depósitos de ahorro en moneda nacional mantenidos en el sistema financiero
                   (same scope as FCD's 167: sistema financiero)
    CodCuadro=138: Depósitos en cuenta corriente en moneda nacional mantenidos en el sistema
                   bancario (same scope as FCD's 147: sistema bancario)
+ FCD(167+147). The colón tables are in 'millones de colones' while the dollar table (FCD) is
in 'millones de dólares', so the units differ; CodCuadro=748 'Tipo de cambio promedio MONEX'
(daily, colones/dollar, 2006-present) is aggregated to a monthly average and used for
conversion: TD_usd = (172+138)_colones / fx_avg + FCD_usd. Since the MONEX FX table only
starts in 2006, TD is only computed from 2006-01 onward; the earlier period (1987-2005) has
FCD values only.
"""

from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = "__RENDER__"

_EXPORT_URL = "https://gee.bccr.fi.cr/indicadoreseconomicos/Cuadros/frmVerCatCuadro.aspx?CodCuadro={code}&Idioma=1&Exportar=True"
_SAVINGS_CODE = 167
_CURRENT_ACCOUNT_CODE = 147
_SAVINGS_MN_CODE = 172
_CURRENT_ACCOUNT_MN_CODE = 138
_FX_CODE = 748
_SCALE = 1e8

_MONTH_COL_TO_NUM = {i: i for i in range(1, 13)}  # col1=Enero..col12=Diciembre
_MONTHS_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("CRI is handled via render() (needs to sum two statistical tables)")


def _fetch_series(code: int) -> dict[str, float]:
    response = requests.get(
        _EXPORT_URL.format(code=code),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
        timeout=60,
    )
    response.raise_for_status()

    table = pd.read_html(StringIO(response.text))[0]

    series: dict[str, float] = {}
    for _, row in table.iterrows():
        year_str = str(row[0]).strip()
        if not year_str.isdigit():
            continue
        year = int(year_str)
        for col, month in _MONTH_COL_TO_NUM.items():
            value_str = str(row[col]).strip()
            if value_str and value_str.lower() != "nan" and value_str.lstrip("-").isdigit():
                series[f"{year}-{month:02d}"] = float(value_str) / _SCALE
    return series


def _fetch_monthly_fx_avg(code: int) -> dict[str, float]:
    """Aggregates the daily (day-row x year-col) MONEX FX table into monthly averages."""
    response = requests.get(
        _EXPORT_URL.format(code=code),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
        timeout=60,
    )
    response.raise_for_status()
    table = pd.read_html(StringIO(response.text))[0]

    year_row = table.iloc[4]
    years: dict[int, int] = {}
    for c in range(1, table.shape[1]):
        v = year_row[c]
        if pd.notna(v):
            try:
                years[c] = int(float(v))
            except ValueError:
                continue

    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for r in range(5, table.shape[0]):
        label = str(table.iloc[r, 0]).strip()
        parts = label.split()
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        month = _MONTHS_ES.get(parts[1].lower()[:3])
        if month is None:
            continue
        for c, year in years.items():
            raw = table.iloc[r, c]
            if pd.isna(raw):
                continue
            raw_s = str(raw).strip()
            if not raw_s:
                continue
            try:
                value = float(raw_s) / _SCALE
            except ValueError:
                continue
            if value == 0:
                continue
            period = f"{year}-{month:02d}"
            sums[period] = sums.get(period, 0.0) + value
            counts[period] = counts.get(period, 0) + 1

    return {period: sums[period] / counts[period] for period in sums}


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    savings = _fetch_series(_SAVINGS_CODE)
    current_account = _fetch_series(_CURRENT_ACCOUNT_CODE)

    rows = []
    fcd_by_period: dict[str, float] = {}
    for period in set(savings) | set(current_account):
        value = savings.get(period, 0.0) + current_account.get(period, 0.0)
        if period not in savings and period not in current_account:
            continue
        fcd_by_period[period] = value
        rows.append({
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": INDICATOR,
            "value": round(value, 4),
            "updated_at": now,
        })

    savings_mn = _fetch_series(_SAVINGS_MN_CODE)
    current_account_mn = _fetch_series(_CURRENT_ACCOUNT_MN_CODE)
    fx_avg = _fetch_monthly_fx_avg(_FX_CODE)

    for period, fcd_value in fcd_by_period.items():
        rate = fx_avg.get(period)
        mn_savings = savings_mn.get(period)
        mn_current = current_account_mn.get(period)
        if rate is None or mn_savings is None or mn_current is None:
            continue
        td_value = (mn_savings + mn_current) / rate + fcd_value
        rows.append({
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": INDICATOR_TD,
            "value": round(td_value, 4),
            "updated_at": now,
        })

    return pd.DataFrame(rows).sort_values(["period", "indicator"]).reset_index(drop=True)
