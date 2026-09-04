"""Chile: Banco Central de Chile 'Statistics Database (BDE)' query view (si3.bcentral.cl/Siete).
Officially there is an API (GetSeries/SearchSeries), but it requires applying by email to
obtain credentials (user/pass), which makes it impractical to use immediately from outside.
Instead, the query view itself (si3.bcentral.cl/Siete/.../Cuadro/.../E32) is server-rendered
and returns an HTML table containing the entire time series via a plain GET, with no
login/JS needed (confirmed with Playwright too — there is no separate XHR call, the table is
already present on the initial page load). So instead of the API, this query view is fetched
directly with GET and the table is parsed.

Under the table titled 'Deposits in foreign currency, balances (millions of dollars)', the
'Serie' column has three rows: 'Total deposits' / 'Transferable deposits and sight deposits'
/ 'Time deposits, savings deposits and debt securities', and the remaining columns hold
monthly values from 'Jan.2009' to the present. FCD = the 'Total deposits' row (since this
table is already a foreign-currency-deposit table, it equals the sum of the other two rows).

TD (total deposits) calculation: the 'Total deposits' row of the local-currency (peso)
deposit table (E31, 'Local currency deposits, balances (billions of pesos)', same site,
CAP_DYB/MN_ESTAD_MON55/EM_DEP_MN/E31) + FCD. Since E31 is in 'billions of pesos' and E32
(FCD) is in 'millions of dollars', the two cannot simply be added, so the BCC monthly nominal
exchange-rate table (TC_HIST, CAP_TIPO_CAMBIO/MN_TIPO_CAMBIO4/TC_HIST/TC_HIST, 'Exchange rate
(pesos/dollar)', Jan.1960-present) is used to convert the peso-denominated portion to
dollars:
    TD_usd = (E31_billions_pesos * 1000 / fx_rate) + E32_usd
(Verified example: as of Jan.2009, E31=6,164.0 billion pesos, FX=623.01, E32=15,650.92 ->
TD ~= 114,590 million dollars)
"""

import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = "https://si3.bcentral.cl/Siete/en/Siete/Cuadro/CAP_DYB/MN_ESTAD_MON55/EM_DEP_ME/E32"

_LOCAL_DEPOSITS_URL = "https://si3.bcentral.cl/Siete/en/Siete/Cuadro/CAP_DYB/MN_ESTAD_MON55/EM_DEP_MN/E31"
_FX_RATE_URL = "https://si3.bcentral.cl/Siete/en/Siete/Cuadro/CAP_TIPO_CAMBIO/MN_TIPO_CAMBIO4/TC_HIST/TC_HIST"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

_COL_RE = re.compile(r"^([A-Za-z]{3})\.(\d{4})$")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _row_by_period(table: pd.DataFrame, serie_label: str) -> dict[str, float]:
    matched = table[table["Serie"].str.strip() == serie_label]
    if matched.empty:
        return {}
    row = matched.iloc[0]
    out: dict[str, float] = {}
    for col in table.columns:
        m = _COL_RE.match(str(col).strip())
        if not m:
            continue
        month = _MONTHS.get(m.group(1).lower())
        if month is None:
            continue
        year = int(m.group(2))
        value = row[col]
        if pd.isna(value):
            continue
        out[f"{year}-{month:02d}"] = float(value)
    return out


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    html = content.decode("utf-8")

    table = pd.read_html(StringIO(html))[0]
    fcd_by_period = _row_by_period(table, "Total deposits")
    if not fcd_by_period:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for period, value in fcd_by_period.items():
        year = int(period[:4])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR,
            "value": round(value, 2),
            "updated_at": now,
        })

    from concurrent.futures import ThreadPoolExecutor

    def _fetch(url: str) -> pd.DataFrame:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        return pd.read_html(StringIO(resp.content.decode("utf-8")))[0]

    # si3.bcentral.cl responses each take several seconds (~5-6s per request), so fetching
    # sequentially would be slow — fetch in parallel instead.
    with ThreadPoolExecutor(max_workers=2) as executor:
        local_future = executor.submit(_fetch, _LOCAL_DEPOSITS_URL)
        fx_future = executor.submit(_fetch, _FX_RATE_URL)
        local_table = local_future.result()
        fx_table = fx_future.result()

    local_by_period = _row_by_period(local_table, "Total deposits")
    fx_by_period = _row_by_period(fx_table, "Exchange rate (pesos/dollar)")

    for period, fcd_value in fcd_by_period.items():
        local_pesos_billions = local_by_period.get(period)
        fx_rate = fx_by_period.get(period)
        if local_pesos_billions is None or not fx_rate:
            continue
        year = int(period[:4])
        td_value = local_pesos_billions * 1000 / fx_rate + fcd_value
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR_TD,
            "value": round(td_value, 2),
            "updated_at": now,
        })

    return pd.DataFrame(rows)
