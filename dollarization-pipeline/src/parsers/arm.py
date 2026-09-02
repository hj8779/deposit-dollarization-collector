"""Armenia: Central Bank of Armenia 'Monetary Aggregates' 페이지의 'Export all' 버튼이
실제로는 XLSX 파일을 내려준다(사용자가 예상한 JSON이 아니라 application/...spreadsheetml
Content-Type). 단일 GET으로 바로 받아지는 정적 파일이라 Playwright 불필요.

시트 'value, month', 헤더는 2행(1행은 시트 제목), 데이터는 3행부터.
    col1 Activity value                              -> 기간(YYYY-MM-DD, 월말)
    col3 Demand deposits in drams mln, AMD
    col5 Time deposits in drams mln, AMD
    col7 Deposits in foreign currency mln, AMD        -> FCD
TD = col3 + col5 + col7 (드람 요구불예금 + 드람 정기예금 + 외화예금)
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
