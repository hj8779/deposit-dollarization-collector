"""Argentina: BCRA(Banco Central de la República Argentina) official statistics REST API.

The originally suggested idVariable=14 actually turned out to be 'Tasa de interés de
préstamos personales' (personal loan interest rate, annualized %) — unrelated to deposits.
The right ID was found by pulling the full variable catalog (/estadisticas/v4.0/Monetarias)
and searching its descriptions (descripcion) directly:

    idVariable 1414: 'Depósitos totales del total de sectores' (total deposits across all
                      sectors, denominated in foreign currency (USD)),
                      categoria='Depósitos por cuenta', unidadExpresion='En millones de USD'

In BCRA's data, deposits reported in USD are by definition foreign-currency (dollar) deposits,
so this is the one that corresponds to FCD. Also, the API had already moved from v3.0 to v4.0
(calling v3/v2 returns HTTP 410 Gone with the message "Método correspondiente a la v3 ha sido
deprecado").

Computing TD (total deposits, all currencies combined): the peso (ARS) counterpart is
'idVariable 1369', the same 'Depósitos totales del total de sectores' series but denominated
in ARS (unidadExpresion='En millones de ARS', moneda='ML'). Since 1369 (ARS) and 1414 (USD)
are in different currency units, they can't just be added together — the peso figure is
converted to dollars using 'idVariable 5' (Tipo de cambio mayorista de referencia, Pesos por
USD) before summing:
    TD_usd = (1369_ars / fx_rate) + 1414_usd
Since FCD is already stored in USD, converting TD to USD as well keeps the two on a common
basis for ratio calculations.

Since the series is daily (Saldos, periodicidad=D), the last observation of each month is
used as the month-end value for monthly aggregation. The server returns at most ~3000 records
per call (requesting too much, e.g. limit=7000, returns an empty response), so pagination is
done by incrementing offset. The SSL certificate validates normally (verify=False isn't
needed), so requests use default settings.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

API_BASE = "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias"
_ID_FCD_USD = 1414
_ID_TD_ARS = 1369
_ID_FX_RATE = 5
_PAGE_LIMIT = 3000
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("ARG is handled via render() (REST API requiring pagination)")


def _fetch_monthly_series(id_variable: int) -> dict[str, float]:
    """Fetch the daily Saldos series and aggregate to monthly (last observation of the month),
    returning {period: value}."""
    all_records = []
    offset = 0
    while True:
        response = requests.get(
            f"{API_BASE}/{id_variable}", headers=_HEADERS,
            params={"limit": _PAGE_LIMIT, "offset": offset}, timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        if not results:
            break

        detalle = results[0].get("detalle", [])
        all_records.extend(detalle)

        total = payload.get("metadata", {}).get("resultset", {}).get("count", 0)
        offset += _PAGE_LIMIT
        if offset >= total:
            break

    by_month: dict[str, tuple[str, float]] = {}
    for rec in all_records:
        fecha = rec["fecha"]  # 'YYYY-MM-DD'

        period = fecha[:7]
        if period not in by_month or fecha > by_month[period][0]:
            by_month[period] = (fecha, rec["valor"])

    return {period: value for period, (_, value) in by_month.items()}


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    fcd_usd = _fetch_monthly_series(_ID_FCD_USD)
    if not fcd_usd:
        logger.warning("[%s] No data received from BCRA API", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    td_ars = _fetch_monthly_series(_ID_TD_ARS)
    fx_rate = _fetch_monthly_series(_ID_FX_RATE)

    rows = []
    for period, value in fcd_usd.items():
        year = int(period[:4])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR,
            "value": round(float(value), 2),
            "updated_at": now,
        })

    for period, ars_value in td_ars.items():
        rate = fx_rate.get(period)
        usd_value = fcd_usd.get(period)
        if rate is None or usd_value is None:
            continue
        year = int(period[:4])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR_TD,
            "value": round(ars_value / rate + usd_value, 2),
            "updated_at": now,
        })

    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True)
