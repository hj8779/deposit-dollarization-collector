"""Guatemala: source_url(agregados-monetarios 페이지) 내부의 pim10.xls 링크에서 다운로드.
legacy .xls, 연간 데이터. col0=연도, col4(0-idx)='MEDIOS DE PAGO (M2) - MONEDA EXTRANJERA'
(M2 중 외화 표시 부분, 예금성 광의통화의 외화 비중 프록시).

TD(총예금) = col5(0-idx) 'MEDIOS DE PAGO TOTALES' = M2 전체(MONEDA NACIONAL col3 + MONEDA
EXTRANJERA col4, 실측으로 두 열 합이 col5와 정확히 일치함을 확인, 예: 2001년
45173.3+2054.9=47228.2)."""

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
