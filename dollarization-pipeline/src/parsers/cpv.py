"""Cabo Verde: Banco de Cabo Verde(BCV) 'Sector Bancário' 통계 페이지의 'Síntese Monetária'
(통화종합표) xls 다운로드(옛 바이너리 .xls 포맷이라 xlrd로 읽음). 파일 하나가 2010-12부터
현재까지 전체 시계열을 담고 있어(매번 갱신되어 재게시됨) 크롤링 없이 이 파일 하나만 받으면
된다.

'Depósitos em Divisas de Residentes'(거주자 외화예금) 행이 정확히 FCD. 바로 아래
'Depósitos de Emigrantes'(이민자/교포 예금)는 별개 카테고리라 FCD에 합산하지 않는다
(거주자 명목이 아니고, 한국은행식 FCD 정의(거주자 외화예금)와도 다름).

TD(총예금) = 'Depósitos a ordem em Moeda Nacional'(국내통화 요구불예금) + 'Depósitos de
Poupança'(저축예금) + 'Depósitos a Prazo em Moeda Nacional'(국내통화 정기예금) + FCD.
'Depósitos de Emigrantes'/'Cheques e Ordens a Pagar'/'Depósitos de Caução'/'Acordos de
Recompra' 등은 거주자 핵심 예금이 아니거나 FCD와 마찬가지로 제외 대상이라 TD에서도 뺀다.
(Massa Monetária = Passivos Monetários + Passivos Quase Monetários 항등식으로 각 행 값을
실측 검증함.)

2행에 연도(병합 셀이라 각 연도 블록의 첫 컬럼에만 값이 있고 나머지는 빈칸 -> forward-fill),
3행에 월 이름(포르투갈어 3글자 약어: Jan/Fev/Mar/Abr/Mai/Jun/Jul/Ago/Set/Out/Nov/Dez).
2010년만 분기별(Dez/Mar/Jun/Set/Dez), 2011년부터는 매월.

bcv.cv는 TLS 인증서 체인이 불완전해(중간 인증서 누락으로 추정) Python 기본 인증서 번들로
검증에 실패한다(curl은 시스템 신뢰 저장소가 달라 통과함) - 그래서 verify=False로 받는다.
"""

from datetime import datetime, timezone

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = "__RENDER__"  # bcv.cv 인증서 체인 문제로 verify=False가 필요해 render()에서 직접 처리

_DOWNLOAD_URL = (
    "https://www.bcv.cv/pt/Estatisticas/Quadros%20Estatisticos/AnaliseEstatica/"
    "sectorbancario2/Documents/2026/Agosto/S%c3%adntese%20Monet%c3%a1ria%20"
    "%28Estat%c3%adsticas%20de%20Dezembro%20de%202010%20a%20Junho%20de%202026%29.xls"
)

_SHEET_INDEX = 0
_YEAR_ROW = 1
_MONTH_ROW = 2
_DATA_START_ROW = 3
_FCD_LABEL = "depósitos em divisas de residentes"
_TD_COMPONENT_LABELS = (
    "depósitos a ordem em moeda nacional",
    "depósitos de poupança",
    "depósitos a prazo em moeda nacional",
)

_MONTHS = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    import xlrd

    now = datetime.now(timezone.utc).isoformat()
    wb = xlrd.open_workbook(file_contents=content)
    ws = wb.sheet_by_index(_SHEET_INDEX)

    fcd_row = None
    td_component_rows: list[int] = []
    for r in range(ws.nrows):
        label = ws.cell_value(r, 0)
        if not isinstance(label, str):
            continue
        stripped = label.strip().lower()
        if stripped == _FCD_LABEL:
            fcd_row = r
        elif stripped in _TD_COMPONENT_LABELS:
            td_component_rows.append(r)
    if fcd_row is None:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    current_year = None
    for c in range(1, ws.ncols):
        year_val = ws.cell_value(_YEAR_ROW, c)
        if isinstance(year_val, float):
            current_year = int(year_val)
        elif isinstance(year_val, str) and year_val.strip():
            # 최근 연도는 '2026P'처럼 잠정치(Provisório) 표시가 붙어 문자열로 나온다.
            digits = "".join(ch for ch in year_val if ch.isdigit())
            if digits:
                current_year = int(digits)
        month_val = ws.cell_value(_MONTH_ROW, c)
        if not isinstance(month_val, str):
            continue
        month = _MONTHS.get(month_val.strip().lower()[:3])
        if month is None or current_year is None:
            continue
        period = f"{current_year}-{month:02d}"

        fcd_value = ws.cell_value(fcd_row, c)
        if isinstance(fcd_value, float):
            rows.append({
                "country_code": country_code,
                "year": current_year,
                "period": period,
                "indicator": INDICATOR,
                "value": round(fcd_value, 4),
                "updated_at": now,
            })

        if len(td_component_rows) == len(_TD_COMPONENT_LABELS) and isinstance(fcd_value, float):
            component_values = [ws.cell_value(r, c) for r in td_component_rows]
            if all(isinstance(v, float) for v in component_values):
                td_value = sum(component_values) + fcd_value
                rows.append({
                    "country_code": country_code,
                    "year": current_year,
                    "period": period,
                    "indicator": INDICATOR_TD,
                    "value": round(td_value, 4),
                    "updated_at": now,
                })

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    response = requests.get(
        _DOWNLOAD_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
        timeout=60,
        verify=False,
    )
    response.raise_for_status()
    return parse(response.content, target["country_code"])
