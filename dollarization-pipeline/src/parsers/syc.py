"""Seychelles: Central Bank of Seychelles(CBS) 'Monetary Survey.xlsx' (Statistics > Statistics Data
페이지의 StaExcel 직접 링크), 시트 'Depository Corporation Survey'.

사전 조사 노트는 SSL/연결 오류로 접속 실패한다고 기록했으나 재시도 결과 사이트 자체는 살아있고
(curl은 기본 검증으로도 통과), Python 기본 verify=True 경로에서만 인증서 체인 결함으로
SSLCertVerificationError가 난다(아래 참고, verify=False로 우회). 페이지 자체는 다수의 xlsx
직링크를 나열하고 있을 뿐 JS 렌더링이 필요 없어 requires_js=false로 정정.

'Deposit Distribution.xlsx'(사전 조사가 주목했던 파일)는 실제로는 부문별(Private/Public)
분해만 제공하고 통화별(자국통화 vs 외화) 분해가 없어 FCD 산출에 쓸 수 없다 -> 기각.
대신 'Monetary Survey.xlsx'의 'Depository Corporation Survey' 시트가 정확히 필요한 4개 행을
담고 있다:
    row 'Transferable Deposits'      (자국통화, M1 구성)
    row 'Fixed Term Deposits'        (자국통화, Quasi Money 구성)
    row 'Savings Deposits'           (자국통화, Quasi Money 구성)
    row 'Foreign Currency Deposits'  (외화예금, M3 구성) -> FCD

TD(총예금) = Transferable + Fixed Term + Savings + Foreign Currency
(연구 단계에서 검증한 값과 실측 일치: 2025-01 Transferable=8112.81, Fixed Term=1837.92,
Savings=5239.72, FCD=10268.96 -> TD=25459.4≈25460, FCD/TD≈40.33%).

이 시트에는 더 넓은 개념의 'Broad Money(M3)' 관련 부채 항목들도 있지만 예금이 아닌 항목
(Pipeline deposits, Other Items Net 등)이 섞여 있어 TD 분모로 쓰지 않는다 - 위 4개 예금성
행만 합산.

행 라벨과 열(날짜) 모두 헤더 텍스트로 동적 탐색한다(고정 인덱스 미사용, 시트 레이아웃이
바뀌어도 견고하도록).

cbs.sc는 인증서 체인에 결함이 있어 Python 기본 verify=True 경로에서 SSLCertVerificationError가
발생한다(curl은 관대하게 통과, kor.py/jpn.py/twn.py와 동일한 우회 패턴). `src.collectors.base.
download()`는 verify 옵션이 없으므로 단일 파일임에도 `__RENDER__` + 자체 requests 세션으로
처리한다.
"""

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_XLSX_URL = "https://www.cbs.sc/Downloads/StaExcel/Monetary%20Survey.xlsx"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

_SHEET_NAME = "Depository Corporation Survey"
_HEADER_ROW = 2
_FIRST_DATA_COL = 2

_ROW_LABELS = {
    "transferable deposits": "transferable",
    "fixed term deposits": "fixed_term",
    "savings deposits": "savings",
    "foreign currency deposits": "fcd",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    ws = wb[_SHEET_NAME]

    # 1) 라벨 텍스트로 필요한 4개 행 번호를 동적으로 찾는다.
    row_nums: dict[str, int] = {}
    for r in range(1, ws.max_row + 1):
        label = ws.cell(row=r, column=1).value
        if not isinstance(label, str):
            continue
        key = _ROW_LABELS.get(label.strip().lower())
        if key:
            row_nums[key] = r

    if set(row_nums) != set(_ROW_LABELS.values()):
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for c in range(_FIRST_DATA_COL, ws.max_column + 1):
        date_val = ws.cell(row=_HEADER_ROW, column=c).value
        if not isinstance(date_val, datetime):
            continue

        values = {
            key: ws.cell(row=row_nums[key], column=c).value
            for key in _ROW_LABELS.values()
        }
        if not all(isinstance(v, (int, float)) for v in values.values()):
            continue

        fcd = values["fcd"]
        td = values["transferable"] + values["fixed_term"] + values["savings"] + values["fcd"]
        ratio = round((fcd / td) * 100, 2) if td else None

        year, period = date_val.year, f"{date_val.year}-{date_val.month:02d}"
        for indicator, value in (("FCD", round(fcd, 2)), ("TD", round(td, 2)), ("FCD_TD_RATIO", ratio)):
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


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    response = requests.get(_XLSX_URL, headers=_HEADERS, timeout=30, verify=False)
    response.raise_for_status()
    return parse(response.content, country_code)
