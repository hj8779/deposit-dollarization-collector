"""Armenia: the 'Export all' button on the Central Bank of Armenia 'Monetary Aggregates'
page actually returns an XLSX file (not the JSON one might expect — the response has an
application/...spreadsheetml Content-Type). It's a static file served directly on a single
GET, so no Playwright is needed.

Sheet 'value, month', header is row 2 (row 1 is the sheet title), data starts at row 3.
    col1 Activity value                              -> period (YYYY-MM-DD, end of month)
    col3 Demand deposits in drams mln, AMD
    col5 Time deposits in drams mln, AMD
    col7 Deposits in foreign currency mln, AMD        -> FCD
TD = col3 + col5 + col7 (dram demand deposits + dram time deposits + foreign currency deposits)
"""

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd

from src.collectors.base import INDICATOR

FILE_URL = "https://www.cba.am/en/statistics/monetary-aggregates/50/export-all/"

_SHEET_NAME = "value, month"
_HEADER_ROW = 2
_FIRST_DATA_ROW = 3
_DATE_COL = 1
_DEMAND_DRAM_COL = 3
_TIME_DRAM_COL = 5
_FCD_COL = 7


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    ws = wb[_SHEET_NAME]

    rows = []
    for r in range(_FIRST_DATA_ROW, ws.max_row + 1):
        date_val = ws.cell(row=r, column=_DATE_COL).value
        demand = ws.cell(row=r, column=_DEMAND_DRAM_COL).value
        time_dep = ws.cell(row=r, column=_TIME_DRAM_COL).value
        fcd = ws.cell(row=r, column=_FCD_COL).value

        if isinstance(date_val, str):
            try:
                date_val = datetime.strptime(date_val, "%Y-%m-%d")
            except ValueError:
                continue
        if not isinstance(date_val, datetime):
            continue
        if not all(isinstance(v, (int, float)) for v in (demand, time_dep, fcd)):
            continue

        period = f"{date_val.year}-{date_val.month:02d}"
        td = demand + time_dep + fcd

        rows.append({
            "country_code": country_code, "year": date_val.year, "period": period,
            "indicator": INDICATOR, "value": round(fcd, 2), "updated_at": now,
        })
        rows.append({
            "country_code": country_code, "year": date_val.year, "period": period,
            "indicator": "TD", "value": round(td, 2), "updated_at": now,
        })

    return pd.DataFrame(rows)
