"""Cabo Verde: Banco de Cabo Verde (BCV) 'Sector Bancário' statistics page, 'Síntese
Monetária' (monetary summary table) xls download (old binary .xls format, read with xlrd).
A single file covers the entire time series from 2010-12 to the present (it is updated and
re-published each time), so no crawling is needed — just fetching this one file is enough.

The 'Depósitos em Divisas de Residentes' (resident foreign-currency deposits) row is exactly
FCD. The row directly below it, 'Depósitos de Emigrantes' (emigrant deposits), is a separate
category and is not added to FCD (it is not resident-denominated, and also differs from the
Bank of Korea-style FCD definition of resident foreign-currency deposits).

TD (total deposits) = 'Depósitos a ordem em Moeda Nacional' (domestic-currency demand
deposits) + 'Depósitos de Poupança' (savings deposits) + 'Depósitos a Prazo em Moeda
Nacional' (domestic-currency term deposits) + FCD. Items like 'Depósitos de Emigrantes' /
'Cheques e Ordens a Pagar' / 'Depósitos de Caução' / 'Acordos de Recompra' are either not
core resident deposits or are excluded for the same reason as FCD, so they are also left out
of TD. (Each row's values were verified against the identity Massa Monetária = Passivos
Monetários + Passivos Quase Monetários.)

Row 2 holds the year (merged cells, so only the first column of each year block has a value
and the rest are blank -> forward-fill), and row 3 holds the month name (3-letter Portuguese
abbreviations: Jan/Fev/Mar/Abr/Mai/Jun/Jul/Ago/Set/Out/Nov/Dez). Only 2010 is quarterly
(Dez/Mar/Jun/Set/Dez); from 2011 onward it is monthly.

bcv.cv has an incomplete TLS certificate chain (presumably a missing intermediate
certificate), which fails verification against Python's default certificate bundle (curl
succeeds because it uses a different system trust store) — so it is fetched with
verify=False.
"""

from datetime import datetime, timezone

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = "__RENDER__"  # handled directly in render() because bcv.cv's certificate chain issue requires verify=False

_DOWNLOAD_URL = (
    "https://www.bcv.cv/pt/Estatisticas/Quadros%20Estatisticos/AnaliseEstatica/"
    "sectorbancario2/Documents/2026/Agosto/S%c3%adntese%20Monet%c3%a1ria%20"
    "%28Estat%c3%adsticas%20de%20Dezembro%20de%202010%20a%20Junho%20de%202026%29.xls"
)

_SHEET_INDEX = 0
_YEAR_ROW = 1
_MONTH_ROW = 2
_DATA_START_ROW = 3
_FCD_LABEL = "depósitos em divisas de residentes"
_TD_COMPONENT_LABELS = (
    "depósitos a ordem em moeda nacional",
    "depósitos de poupança",
    "depósitos a prazo em moeda nacional",
)

_MONTHS = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    import xlrd

    now = datetime.now(timezone.utc).isoformat()
    wb = xlrd.open_workbook(file_contents=content)
    ws = wb.sheet_by_index(_SHEET_INDEX)

    fcd_row = None
    td_component_rows: list[int] = []
    for r in range(ws.nrows):
        label = ws.cell_value(r, 0)
        if not isinstance(label, str):
            continue
        stripped = label.strip().lower()
        if stripped == _FCD_LABEL:
            fcd_row = r
        elif stripped in _TD_COMPONENT_LABELS:
            td_component_rows.append(r)
    if fcd_row is None:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    current_year = None
    for c in range(1, ws.ncols):
        year_val = ws.cell_value(_YEAR_ROW, c)
        if isinstance(year_val, float):
            current_year = int(year_val)
        elif isinstance(year_val, str) and year_val.strip():
            # Recent years appear as strings with a provisional ("Provisório") marker, e.g. '2026P'.
            digits = "".join(ch for ch in year_val if ch.isdigit())
            if digits:
                current_year = int(digits)
        month_val = ws.cell_value(_MONTH_ROW, c)
        if not isinstance(month_val, str):
            continue
        month = _MONTHS.get(month_val.strip().lower()[:3])
        if month is None or current_year is None:
            continue
        period = f"{current_year}-{month:02d}"

        fcd_value = ws.cell_value(fcd_row, c)
        if isinstance(fcd_value, float):
            rows.append({
                "country_code": country_code,
                "year": current_year,
                "period": period,
                "indicator": INDICATOR,
                "value": round(fcd_value, 4),
                "updated_at": now,
            })

        if len(td_component_rows) == len(_TD_COMPONENT_LABELS) and isinstance(fcd_value, float):
            component_values = [ws.cell_value(r, c) for r in td_component_rows]
            if all(isinstance(v, float) for v in component_values):
                td_value = sum(component_values) + fcd_value
                rows.append({
                    "country_code": country_code,
                    "year": current_year,
                    "period": period,
                    "indicator": INDICATOR_TD,
                    "value": round(td_value, 4),
                    "updated_at": now,
                })

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    response = requests.get(
        _DOWNLOAD_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
        timeout=60,
        verify=False,
    )
    response.raise_for_status()
    return parse(response.content, target["country_code"])
