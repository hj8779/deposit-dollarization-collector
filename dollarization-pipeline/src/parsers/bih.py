"""Bosnia and Herzegovina: legacy .xls, among the sub-items under row7 (0-idx6)='TOTAL DEPOSITS',
row12 (0-idx11)='in foreign currency' is the total foreign-currency deposits. The header
(row7/0-idx6) holds 'MM-YY' period labels.

TD (total deposits) = the row idx7 'TOTAL DEPOSITS' row itself. Verified against actual data
that TOTAL DEPOSITS = sum of 'in KM' (idx8) + 'in foreign currency' (idx11) (e.g. 01-06
6823.90 = 3648.52 + 3175.39)."""

from datetime import datetime, timezone

import pandas as pd
import xlrd

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = None  # use target['source_url'] as-is


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    wb = xlrd.open_workbook(file_contents=content)
    ws = wb.sheet_by_index(0)
    now = datetime.now(timezone.utc).isoformat()

    HEADER_ROW = 6
    TD_ROW = 7
    FCD_ROW = 11
    FIRST_DATA_COL = 6

    rows = []
    for c in range(FIRST_DATA_COL, ws.ncols):
        period_label = ws.cell_value(HEADER_ROW, c)
        if not period_label:
            continue
        month_str, yy_str = str(period_label).split("-")
        yy_str = "".join(ch for ch in yy_str if ch.isdigit())
        if not month_str.isdigit() or not yy_str:
            continue
        year = 2000 + int(yy_str)
        month = int(month_str)
        period = f"{year}-{month:02d}"

        fcd_value = ws.cell_value(FCD_ROW, c)
        if fcd_value != "":
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": INDICATOR,
                "value": float(fcd_value),
                "updated_at": now,
            })

        td_value = ws.cell_value(TD_ROW, c)
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
