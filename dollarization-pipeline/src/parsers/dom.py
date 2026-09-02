"""Dominican Republic: BCRD(Banco Central de la República Dominicana) 통화·금융통계.

BCRD 통계포털(bancentral.gov.do/a/CustomView/2536-sector-monetario-y-financiero)에서
"Balance sectorial de las OSD: Instrumentos y sectores institucionales (Pasivos en ME)"
파일을 다운로드하여 거주자 외화예금(Foreign Currency Deposits, FCD)을 추출한다.

파일 구조:
- 시트: II.3.b.OSD-Pasivos ME
- 행 9-11: 헤더 (카테고리/부문/열번호)
- 행 12~: 월별 데이터 (2001-12부터)
- 열 0: 연도 (Año)
- 열 1: 월 (Mes - Ene/Feb/.../Dic)
- 열 2: 비거주자 예금 (No residentes) - FCD 계산에서 제외
- 열 3-9: 거주자 외화예금 (부문별 합산 = FCD)
  - 3: 기타 예금기관, 4: 기타 금융회사, 5: 중앙정부
  - 6: 지방정부, 7: 공공 비금융회사, 8: 기타 비금융회사
  - 9: 가계 및 ISFLSH
- 열 17: 총 외화 부채 (Total pasivos)

단위: 백만 페소 (Pesos Dominicanos, DOP) - FCD도 이미 페소 환산액으로 게시되므로 통화
환산 없이 그대로 국내통화 예금과 더할 수 있다.

TD(총예금) = 위 FCD(ME 파일 열3-9 합)와 짝을 이루는 'Pasivos en MN'(국내통화, balance_osd_
pasivos_mn.xlsx, 시트 'II.3.a.OSD-Pasivos MN') 파일의 동일 열(열3-9, 부문 구성이 완전히
동일: Otras sociedades de depósito/financieras, Gobierno central, Gobiernos estatales y
locales, Sociedades públicas/otras no financieras, Hogares e ISFLSH)을 합한 값 + FCD.
두 파일 모두 '백만 페소'로 단위가 이미 같아 환율 환산이 필요 없다.
"""

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "https://cdn.bancentral.gov.do/documents/estadisticas/sector-monetario-y-financiero/documents/balance_osd_pasivos_me.xlsx"
_MN_FILE_URL = "https://cdn.bancentral.gov.do/documents/estadisticas/sector-monetario-y-financiero/documents/balance_osd_pasivos_mn.xlsx"
_MN_SHEET_NAME = "II.3.a.OSD-Pasivos MN"

_MONTHS_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# 거주자 외화예금 열 인덱스 (비거주자 열2 제외)
_FCD_COLUMNS = [3, 4, 5, 6, 7, 8, 9]  # 열 3~9 합산


def _sector_sum_by_period(df: pd.DataFrame, country_code: str, indicator: str, now: str) -> list[dict]:
    """열3-9(거주자 부문별 예금) 합산 시계열을 (country_code, year, period, indicator, value) 행으로 만든다."""
    data_start = None
    for i in range(df.shape[0]):
        cell = df.iloc[i, 0]
        try:
            year_check = int(cell)
            if 1990 <= year_check <= 2100:
                data_start = i
                break
        except (ValueError, TypeError):
            continue

    if data_start is None:
        logger.error("[%s] 데이터 시작 행을 찾을 수 없음", country_code)
        return []

    rows = []
    for i in range(data_start, df.shape[0]):
        row = df.iloc[i]
        year_val = row.iloc[0]
        month_val = row.iloc[1]

        if pd.isna(year_val):
            continue
        try:
            year = int(year_val)
        except (ValueError, TypeError):
            continue

        if pd.isna(month_val):
            continue
        month_str = str(month_val).strip().lower()[:3]
        month = _MONTHS_ES.get(month_str)
        if month is None:
            continue

        value = 0.0
        for col_idx in _FCD_COLUMNS:
            val = row.iloc[col_idx]
            if pd.notna(val):
                try:
                    value += float(val)
                except (ValueError, TypeError):
                    pass

        if value == 0.0:
            continue

        period = f"{year}-{month:02d}"
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": indicator,
            "value": round(value, 2),
            "updated_at": now,
        })
    return rows


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Balance sectorial OSD Pasivos en ME/MN 엑셀 파일에서 FCD와 TD를 추출한다."""
    from io import BytesIO

    now = datetime.now(timezone.utc).isoformat()

    try:
        me_df = pd.read_excel(BytesIO(content), sheet_name="II.3.b.OSD-Pasivos ME", header=None)
    except Exception as e:
        logger.error("[%s] 엑셀 파일 읽기 실패: %s", country_code, e)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    fcd_rows = _sector_sum_by_period(me_df, country_code, INDICATOR, now)
    if not fcd_rows:
        logger.warning("[%s] 외화예금 데이터를 찾을 수 없음", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    fcd_by_period = {r["period"]: r["value"] for r in fcd_rows}

    td_rows: list[dict] = []
    try:
        mn_content = requests.get(
            _MN_FILE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60
        ).content
        mn_df = pd.read_excel(BytesIO(mn_content), sheet_name=_MN_SHEET_NAME, header=None)
        mn_rows = _sector_sum_by_period(mn_df, country_code, INDICATOR_TD, now)
        for r in mn_rows:
            fcd_value = fcd_by_period.get(r["period"])
            if fcd_value is None:
                continue
            td_rows.append({**r, "value": round(r["value"] + fcd_value, 2)})
    except Exception as e:
        logger.warning("[%s] MN(국내통화) 파일 처리 실패, TD 없이 진행: %s", country_code, e)

    result = pd.DataFrame(fcd_rows + td_rows).sort_values(["period", "indicator"]).reset_index(drop=True)
    logger.info("[%s] 외화예금 데이터 %d개월 추출 (%s ~ %s)",
                country_code, len(fcd_rows), min(fcd_by_period), max(fcd_by_period))
    return result
