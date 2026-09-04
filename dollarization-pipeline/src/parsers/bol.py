"""Bolivia: among BCB (Banco Central de Bolivia)'s 'sector-monetario' page individual statistics
Excel listings, uses 'Créditos y Depósitos > OSD > 17. Depósitos totales por monedas
serie.xlsx' (a time series of deposits across the whole financial system (banks + Pyme +
savings banks + cooperatives, etc.) broken down by currency, monthly, from 2017-12 to present).

Initially the '2. Base Monetaria...' file's row 31 'Moneda Extranjera', which the user pointed
out, was examined, but that turned out to be only the foreign-currency-denominated portion of
central bank reserve requirements (Encaje Legal, etc.), not customer foreign-currency deposits
held at commercial banks (and the amounts were much smaller), so it wasn't used. The same
listing's '17. Depósitos totales por monedas serie.xlsx' is a genuine time series aggregating
deposits across the entire financial system by currency (MN/ME/UFV/MVDOL), so that is used
instead (confirmed with the user).

The workbook has sheets split into 'Total'/'MN'/'ME'/'UFV'/'MVDOL'; each sheet lists rows by
financial institution group (banks/Pyme/savings banks/cooperatives, etc.), with a 'TOTAL'
subtotal row at the end of each group, and a 'TOTAL SISTEMA' row summing everything at the very
end. TD = the 'TOTAL SISTEMA' row of the 'Total' sheet (dates are listed in row 5, on a
month-end basis).

2026-08-19 bug fix (important): the 'ME' sheet's 'TOTAL SISTEMA' row is not a Boliviano-converted
amount but is instead recorded **directly in the original currency (USD)** — the sheet's title
is "POR ENTIDADES FINANCIERAS DE MONEDA DÓLARES", but the 'MN'/'UFV'/'MVDOL' sheets are all in
Bolivianos, so dividing FCD (=raw ME) / TD (=Total, in Bolivianos) directly to compute the ratio,
as had been done up to this point, was in fact a unit mismatch equivalent to "USD deposits ÷
Bs total deposits" (discovered while cross-checking against the Pasivo tab of '3. Sistema
Monetario.xlsx' after a tip from the user). Verification: for 2026-06, Total(Bs)=255,956,216.02,
MN(Bs)=227,326,162.06, UFV=1,460,453.86, MVDOL=226,029.27, but adding ME(2,557,741.23) directly
leaves 24.4M Bs unaccounted for; multiplying by the BCB's official exchange rate at that time
(9.76, the TCO rate right after the 2026-06-26 switch to a floating regime) gives
2,557,741.23×9.76≈24,963,571, and the sum comes out to 255.98M Bs, matching to within 0.8% —
meaning the actual dollarization ratio was several times higher (around 9.4~9.8% as of 2026-06)
than what had previously been computed (~1.0%).

Exchange rate: Bolivia maintained a fixed exchange rate (buy rate 6.96 Bs/USD) from November
2011 until the switch to a floating regime on 2026-06-26 (this period covers most of the
2017-12~2026-06 history handled by this file). After the switch to floating, the BCB publishes
daily per-bank 'TCO (Tipo de Cambio Oficial)' detail as CSV
(tco_tcreferencial_descargar_csv.php?desde=&hasta=), and the weighted-average TCO value from the
'TOTAL BANCOS' column is used for each cut-off date. The month-end value is used as the
representative rate for that month."""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from io import BytesIO, StringIO

import openpyxl
import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_DEPOSITS_URL = "https://www.bcb.gob.bo/webdocs/sector_monetario/Cr%C3%A9ditos%20y%20Dep%C3%B3sitos/OSD/17.%20Dep%C3%B3sitos%20totales%20por%20monedas%20serie.xlsx"
_TCO_CSV_URL = "https://www.bcb.gob.bo/tco_tcreferencial_descargar_csv.php"
_FLOAT_START = date(2026, 6, 26)
_FIXED_RATE = 6.96  # official peg, Nov 2011 - 2026-06-26

_DATE_ROW = 5
_TOTAL_SISTEMA_LABEL = "total sistema"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BOL fetches the deposits xlsx and exchange-rate CSV together via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _find_total_row(ws) -> int | None:
    for r in range(1, ws.max_row + 1):
        label = ws.cell(row=r, column=1).value
        if isinstance(label, str) and label.strip().lower() == _TOTAL_SISTEMA_LABEL:
            return r
    return None


def _extract_series(ws) -> dict[str, float]:
    total_row = _find_total_row(ws)
    if total_row is None:
        return {}

    series = {}
    for c in range(2, ws.max_column + 1):
        date_val = ws.cell(row=_DATE_ROW, column=c).value
        value = ws.cell(row=total_row, column=c).value
        if isinstance(date_val, datetime) and isinstance(value, (int, float)):
            series[f"{date_val.year}-{date_val.month:02d}"] = float(value)
    return series


def _fetch_post_float_rates() -> dict[str, float]:
    """{'YYYY-MM': rate} for month-end cut-off dates from the float onward, using
    the 'TOTAL BANCOS' weighted-average TCO. Returns {} on any failure (caller
    then just skips periods it has no rate for rather than guessing)."""
    try:
        resp = requests.get(
            _TCO_CSV_URL,
            params={"desde": _FLOAT_START.isoformat(), "hasta": date.today().isoformat()},
            headers=_HEADERS,
            timeout=60,
            verify=False,
        )
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig")
    except Exception as e:
        logger.warning("[BOL] Failed to fetch TCO exchange-rate CSV: %s", e)
        return {}

    rates: dict[str, float] = {}  # date -> rate, keep last (month-end) per YYYY-MM
    reader = csv.reader(StringIO(text), delimiter=";")
    for row in reader:
        if len(row) < 3 or row[2] != "TCO":
            continue
        cutoff = row[0].strip()
        # row ends with a trailing ';' (empty last field) followed by the
        # "TOTAL BANCOS" TCO value, so the value is the second-to-last field.
        total_rate_str = row[-2].strip() if len(row) >= 2 and row[-2].strip() else None
        if not total_rate_str:
            continue
        try:
            d = datetime.strptime(cutoff, "%Y-%m-%d").date()
            rate = float(total_rate_str.replace(",", "."))
        except ValueError:
            continue
        period = f"{d.year}-{d.month:02d}"
        # keep the latest cutoff date seen per period (rows are chronological)
        rates[period] = rate
    return rates


def _rate_for_period(period: str, post_float_rates: dict[str, float]) -> float | None:
    year, month = int(period[:4]), int(period[5:7])
    # crude but adequate: anything at/after the float's own month uses the
    # published TCO for that month; everything earlier used the fixed peg.
    if (year, month) < (_FLOAT_START.year, _FLOAT_START.month):
        return _FIXED_RATE
    return post_float_rates.get(period)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        resp = requests.get(_DEPOSITS_URL, headers=_HEADERS, timeout=90, verify=False)
        resp.raise_for_status()
        wb = openpyxl.load_workbook(BytesIO(resp.content), data_only=True)
    except Exception as e:
        logger.exception("[%s] Deposits xlsx download/parse failed: %s", country_code, e)
        return _empty()

    fcd_usd_series = _extract_series(wb["ME"])  # raw USD thousands, needs FX conversion
    td_series = _extract_series(wb["Total"])  # already Bs thousands

    post_float_rates = _fetch_post_float_rates()

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period, td in td_series.items():
        fcd_usd = fcd_usd_series.get(period)
        if fcd_usd is None or td <= 0:
            continue
        rate = _rate_for_period(period, post_float_rates)
        if rate is None:
            logger.warning("[%s] Could not find an exchange rate for %s, skipping", country_code, period)
            continue
        fcd = fcd_usd * rate
        if fcd > td:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

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
