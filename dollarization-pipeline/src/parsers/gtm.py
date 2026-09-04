"""Guatemala: downloaded from the pim10.xls link found on the source_url (agregados-monetarios page).
Legacy .xls, annual data. col0=year, col4(0-idx)='MEDIOS DE PAGO (M2) - MONEDA EXTRANJERA'
(the foreign-currency-denominated portion of M2, used as a proxy for the foreign-currency
share of broad deposit money).

TD(total deposits) = col5(0-idx) 'MEDIOS DE PAGO TOTALES' = total M2 (MONEDA NACIONAL col3 +
MONEDA EXTRANJERA col4; empirically confirmed the sum of the two columns exactly matches
col5, e.g. for 2001: 45173.3+2054.9=47228.2)."""

from datetime import datetime, timezone

import pandas as pd
import xlrd

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = "https://banguat.gob.gt/sites/default/files/banguat/pim/pim10.xls"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    wb = xlrd.open_workbook(file_contents=content)
    ws = wb.sheet_by_index(0)
    now = datetime.now(timezone.utc).isoformat()

    FIRST_DATA_ROW = 5
    YEAR_COL = 0
    FCD_COL = 4
    TD_COL = 5

    rows = []
    for r in range(FIRST_DATA_ROW, ws.nrows):
        year = ws.cell_value(r, YEAR_COL)
        if not isinstance(year, (int, float)):
            continue
        year = int(year)
        period = f"{year}-Annual"

        value = ws.cell_value(r, FCD_COL)
        if value != "":
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": INDICATOR,
                "value": float(value),
                "updated_at": now,
            })

        td_value = ws.cell_value(r, TD_COL)
        if td_value != "":
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": INDICATOR_TD,
                "value": float(td_value),
                "updated_at": now,
            })
    return pd.DataFrame(rows)
