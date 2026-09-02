"""Spain: Banco de España(BdE) 공식 통계 페이지, Statistics Bulletin Table 8.25
('Main assets and liabilities of OMFIs, by currency' / 통화별 OIFM 주요 자산부채) CSV.

BdE 통계 포털(bde.es/webbe/.../estadis/...) 자체는 링크가 408개나 있고 지표명이 페이지
텍스트에 노출되지 않는 것처럼 보이지만, 실제로는 순수 정적 HTML이다(JS 렌더링 아님) -
각 링크 앵커 주변에 <strong>제목</strong>과 'Table X.Y of the Statistics Bulletin' 툴팁이
바로 붙어 있어서 curl만으로도 표 제목 -> csv 코드(beXXYY) 매핑을 뽑아낼 수 있었다.

CSV 자체는 SDMX 스타일 코드를 컬럼 헤더로 쓰는 '가로로 넓은' 시계열 포맷이다(1행=시리즈
코드, 4행=스페인어 설명, 7행부터 'MAR 1992' 같은 분기 라벨이 첫 컬럼에 오고 그 뒤로 각
시리즈의 값이 옆으로 이어짐). 코드 예시: DF_QESNAL20A1U62000Z01E
    L20    = Deposit liabilities (예금부채)
    U62000 = 카운터파트: 스페인 거주 non-MFI(U6=domestic/거주자, 2000=Non-MFIs)
             -> 은행간이 아닌 '고객 예금'만 잡는다(U61000=거주 MFI끼리의 예금은 제외)
    Z01    = All currencies combined -> TD
    EUR    = Euro만 -> 자국통화
    (Z03/USD/JPY/CHF/Z05 등 개별 외화 컬럼도 있으나, 굳이 다 더할 필요 없이
     FCD = Z01 - EUR 로 계산 가능함을 실측으로 확인: 예) 2003Q1 EUR 619,719 +
     (Z03 345 + USD 2,742 + JPY 88 + CHF 97 + Z05 133) = 623,124 = Z01과 정확히 일치)

고정 컬럼 인덱스 대신 4행(DESCRIPCIÓN DE LA SERIE)의 텍스트에서 'Depósitos'+'no IFM
residentes en España'가 모두 들어간(그리고 '[discontinuada]' 아닌) 열을 찾고, 그 중
통화 표시가 없는 것(Z01=총액)과 'En euros'가 들어간 것(EUR)을 각각 골라 열 인덱스로
사용한다 - 이 프로젝트의 표준 관례(bgr.py/bgd.py)대로 텍스트 기반 동적 탐색.

분기별(TRIMESTRAL) 데이터가 1997년 3분기(SEP 1997)부터 최신 분기까지 존재한다(그 이전
컬럼은 값이 전부 '_' placeholder). period 표기는 'YYYY-QN'.
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
    """4행(시리즈 설명)에서 '거주 non-MFI 대상 예금' 계열 중 총액(Z01, 통화 표기 없음)과
    유로(EUR, 'En euros' 포함) 컬럼 인덱스를 찾는다."""
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
        logger.warning("[%s] Table 8.25에서 예금(Z01/EUR) 컬럼을 찾지 못함", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for row in reader[6:]:
        if not row or not row[0]:
            continue
        m = _PERIOD_RE.match(row[0].strip())
        if not m:
            continue  # 'NOTAS' 같은 꼬리 행

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
