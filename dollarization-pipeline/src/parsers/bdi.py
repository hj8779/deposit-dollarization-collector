"""Burundi: sheet 'Mensuelle', col A=날짜, col D='Dépôts en devises des résidents'.

TD(총예금) = col B(Dépôts à vue, 요구불예금) + col C(Dépôts à terme et d'épargne, 정기/저축예금)
+ col D(Dépôts en devises des résidents, FCD). 거주자 예금 전체(통화 무관)에 해당하며,
col E~K(Etablissements de Microfinances/기관간 예금, 중앙은행/정부 부채 등)는 제외한다."""

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = None  # target['source_url']를 그대로 사용


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    ws = wb["Mensuelle"]
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for r in range(8, ws.max_row + 1):
        date = ws.cell(row=r, column=1).value
        demand = ws.cell(row=r, column=2).value
        term_savings = ws.cell(row=r, column=3).value
        fcd = ws.cell(row=r, column=4).value
        if not isinstance(date, datetime) or fcd is None:
            continue
        period = f"{date.year}-{date.month:02d}"
        rows.append({
            "country_code": country_code,
            "year": date.year,
            "period": period,
            "indicator": INDICATOR,
            "value": float(fcd),
            "updated_at": now,
        })
        if demand is not None and term_savings is not None:
            rows.append({
                "country_code": country_code,
                "year": date.year,
                "period": period,
                "indicator": INDICATOR_TD,
                "value": round(float(demand) + float(term_savings) + float(fcd), 2),
                "updated_at": now,
            })
    return pd.DataFrame(rows)
