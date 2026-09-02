"""Bulgaria: BNB(Bulgarian National Bank) 'Short Monetary Survey' XLSX, 시트 'MS_short'(첫 번째 탭).
가로로 확장되는 시계열(row2=날짜, col2~=월별). 통화별(BGN/외화) 분해가 'in BGN'/
'in foreign currency' 두 줄짜리 하위 행으로 여러 카테고리에 반복해서 나온다(자산 항목에도,
부채/예금 항목에도 똑같은 라벨로 나옴).

FCD/TD는 '예금'에 해당하는 카테고리만 골라야 한다(자산 측 FOREIGN ASSETS, DOMESTIC CREDIT,
CLAIMS ON... 등에도 'in foreign currency' 하위 행이 있어 전부 더하면 안 됨). 규칙: 바로 위
상위(비들여쓰기) 카테고리 라벨에 'deposit'이 포함된 경우만 집계한다. 이 조건으로 걸리는
카테고리는 정확히 4개:
    Overnight deposits
    Deposits with agreed maturity up to 2 years
    Deposits redeemable at notice up to 3 months
    Deposits with agreed maturity over 2 years and deposits redeemable at notice over 3 months
FCD = 이 4개 카테고리의 'in foreign currency' 값 합
TD  = 이 4개 카테고리의 'in BGN' + 'in foreign currency' 값 합 (= 카테고리 총액 합과 동일)
"""

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd

from src.collectors.base import INDICATOR

FILE_URL = "https://www.bnb.bg/bnbweb/groups/public/documents/bnb_download/s_ms_monetarystatistics_all_en.xlsx"

_SHEET_NAME = "MS_short"
_HEADER_ROW = 2
_FIRST_DATA_COL = 2


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    ws = wb[_SHEET_NAME]

    # 1) 'deposit' 카테고리 아래의 'in BGN'/'in foreign currency' 행 번호를 찾는다.
    bgn_rows, fc_rows = [], []
    current_parent = ""
    for r in range(3, ws.max_row + 1):
        label = ws.cell(row=r, column=1).value
        if not isinstance(label, str) or not label.strip():
            continue
        stripped = label.strip().lower()
        if stripped == "in bgn":
            if "deposit" in current_parent:
                bgn_rows.append(r)
        elif stripped == "in foreign currency":
            if "deposit" in current_parent:
                fc_rows.append(r)
        else:
            current_parent = stripped

    if not fc_rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    # 2) 날짜 컬럼별로 위 행들의 값을 합산.
    rows = []
    for c in range(_FIRST_DATA_COL, ws.max_column + 1):
        date_val = ws.cell(row=_HEADER_ROW, column=c).value
        if not isinstance(date_val, datetime):
            continue

        fc_values = [ws.cell(row=r, column=c).value for r in fc_rows]
        bgn_values = [ws.cell(row=r, column=c).value for r in bgn_rows]
        if not all(isinstance(v, (int, float)) for v in fc_values + bgn_values):
            continue

        fcd = sum(fc_values)
        td = fcd + sum(bgn_values)
        period = f"{date_val.year}-{date_val.month:02d}"

        rows.append({
            "country_code": country_code, "year": date_val.year, "period": period,
            "indicator": INDICATOR, "value": round(fcd, 2), "updated_at": now,
        })
        rows.append({
            "country_code": country_code, "year": date_val.year, "period": period,
            "indicator": "TD", "value": round(td, 2), "updated_at": now,
        })

    return pd.DataFrame(rows)
