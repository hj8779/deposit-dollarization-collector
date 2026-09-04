"""Spain: Banco de España (BdE) official statistics page, Statistics Bulletin Table 8.25
('Main assets and liabilities of OMFIs, by currency') CSV.

The BdE statistics portal (bde.es/webbe/.../estadis/...) itself has as many as 408
links, and the indicator names appear not to be exposed in the page text, but it
is actually pure static HTML (not JS-rendered) - each link anchor is immediately
followed by a <strong>title</strong> and a 'Table X.Y of the Statistics Bulletin'
tooltip, so a plain curl was enough to extract the table-title -> csv-code
(beXXYY) mapping.

The CSV itself is a "wide" time-series format that uses SDMX-style codes as
column headers (row 1 = series code, row 4 = Spanish description, and from row 7
onward each row starts with a quarter label like 'MAR 1992' in the first column
followed by each series' value across the row). Example code:
DF_QESNAL20A1U62000Z01E
    L20    = Deposit liabilities
    U62000 = counterparty: Spain-resident non-MFI (U6=domestic/resident,
             2000=Non-MFIs) -> captures only 'customer deposits', not
             interbank deposits (U61000=deposits between resident MFIs is
             excluded)
    Z01    = All currencies combined -> TD
    EUR    = Euro only -> domestic currency
    (Individual foreign-currency columns like Z03/USD/JPY/CHF/Z05 also exist,
     but there's no need to sum them all - empirically confirmed that
     FCD = Z01 - EUR works: e.g. 2003Q1 EUR 619,719 +
     (Z03 345 + USD 2,742 + JPY 88 + CHF 97 + Z05 133) = 623,124, which exactly
     matches Z01)

Instead of fixed column indices, we search row 4 (DESCRIPCIÓN DE LA SERIE) for
columns whose text contains both 'Depósitos' and 'no IFM residentes en España'
(and does not contain '[discontinuada]'), then among those pick the one with no
currency designation (Z01=total) and the one containing 'En euros' (EUR) as the
respective column indices - following this project's standard convention
(bgr.py/bgd.py) of text-based dynamic column discovery.

Quarterly (TRIMESTRAL) data exists from Q3 1997 (SEP 1997) through the most
recent quarter (columns before that are all '_' placeholders). Period is
formatted as 'YYYY-QN'.
"""

import csv
import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "https://www.bde.es/webbe/es/estadisticas/compartido/datos/csv/be0825.csv"

_MONTH_TO_Q = {"MAR": 1, "JUN": 2, "SEP": 3, "DIC": 4}
_PERIOD_RE = re.compile(r"^([A-ZÁÉÍÓÚ]{3})\s+(\d{4})$")

_TARGET_DESC_MARKERS = ("Depósitos", "no IFM residentes en España")


def _find_columns(desc_row: list[str]) -> tuple[int, int]:
    """Finds, among the 'deposits held by resident non-MFIs' series in row 4 (series
    description), the column indices for the total (Z01, no currency designation)
    and the euro (EUR, contains 'En euros')."""
    total_col, eur_col = None, None
    for idx, desc in enumerate(desc_row):
        if not desc or "[discontinuada]" in desc:
            continue
        if not all(marker in desc for marker in _TARGET_DESC_MARKERS):
            continue
        if "En euros" in desc:
            eur_col = idx
        elif "En dólares" not in desc and "En yenes" not in desc and "En francos suizos" not in desc \
                and "Monedas UE no UEM" not in desc and "otras monedas" not in desc:
            total_col = idx
    return total_col, eur_col


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()

    text = content.decode("latin-1")
    reader = list(csv.reader(StringIO(text)))
    if len(reader) < 8:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    desc_row = reader[3]
    total_col, eur_col = _find_columns(desc_row)
    if total_col is None or eur_col is None:
        logger.warning("[%s] Could not find deposit (Z01/EUR) columns in Table 8.25", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for row in reader[6:]:
        if not row or not row[0]:
            continue
        m = _PERIOD_RE.match(row[0].strip())
        if not m:
            continue  # trailing rows like 'NOTAS'

        month_abbr, year_str = m.groups()
        quarter = _MONTH_TO_Q.get(month_abbr)
        if quarter is None:
            continue
        year = int(year_str)

        raw_total = row[total_col] if total_col < len(row) else None
        raw_eur = row[eur_col] if eur_col < len(row) else None
        if raw_total in (None, "", "_") or raw_eur in (None, "", "_"):
            continue

        try:
            td = float(raw_total.replace(",", ""))
            eur = float(raw_eur.replace(",", ""))
        except ValueError:
            continue

        fcd = td - eur
        period = f"{year}-Q{quarter}"

        for indicator, value in (
            ("FCD", round(fcd, 2)),
            ("TD", round(td, 2)),
            ("FCD_TD_RATIO", round((fcd / td) * 100, 2) if td else None),
        ):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    return pd.DataFrame(rows)
