"""Samoa: Central Bank of Samoa "Money and Banking" statistics, Table A-4
"Structure of Money Supply" (cbs.gov.ws/money-and-banking → 정적 xlsx 다운로드,
차단 없음).

이 표는 '광의통화(Broad Money) 대비 구성비(%)' 표라 FCD/TD를 직접 주지 않지만, 17행에
그 분기의 광의통화 절대값(단위: Tala million)이 별도로 있어 비율×절대값으로 역산 가능:
  FCD_tala = FCD%(11행) × BroadMoney_tala(17행) / 100
  TD_tala  = BroadMoney_tala × (1 − Currency%(8행)/100)   (통화발행고만 제외한 전체 예금)

분기 데이터, 사모아 회계연도(7월~6월) 기준 컬럼 헤더가 두 가지로 섞여 있다: 초기엔 로마
숫자(I~IV, I=9월말/II=12월말/III=익년3월말/IV=익년6월말), 이후엔 월 이름(Mar/June/
Sep/Dec)으로 바뀐다 - 둘 다 같은 의미라 통합 매핑.

가장 최근 분기(2026-03) 데이터는 원본 스프레드시트 자체에 오류가 있음(11행 FCD%가
7행 M1% 전체와 동일한 값으로 찍혀 있어, FCD가 M1의 부분집합이라는 정의에 모순) - 이런
명백히 불가능한 값(FCD% > M1%가 되는 경우, 즉 FCD가 그 상위 집합인 M1보다 커지는 경우)은
소스 자체의 오류로 보고 건너뛴다."""

from __future__ import annotations

from datetime import datetime, timezone

import openpyxl
import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_XLSX_URL = "https://cbs.gov.ws/media/A4-Structure-of-Money-Supply-7.xlsx"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("WSM은 render()로 xlsx를 받는다")

_QUARTER_END_MONTH = {"I": 9, "II": 12, "III": 3, "IV": 6, "Sep": 9, "Dec": 12, "Mar": 3, "June": 6}
_ROLLOVER_MONTHS = {3, 6}  # III/Mar, IV/June는 회계연도 표기연도의 다음 해

_M1_ROW = 7
_CURRENCY_ROW = 8
_FCD_ROW = 11
_BROAD_MONEY_ROW = 17


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    resp = requests.get(_XLSX_URL, headers=_HEADERS, timeout=60)
    resp.raise_for_status()

    from io import BytesIO
    wb = openpyxl.load_workbook(BytesIO(resp.content), data_only=True)
    ws = wb["A4"]

    fiscal_year = None
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for c in range(2, ws.max_column + 1):
        year_cell = ws.cell(row=5, column=c).value
        if isinstance(year_cell, str) and "/" in year_cell:
            fiscal_year = int(year_cell.split("/")[0])
        quarter_cell = ws.cell(row=6, column=c).value
        month = _QUARTER_END_MONTH.get(str(quarter_cell).strip()) if quarter_cell else None
        if fiscal_year is None or month is None:
            continue
        year = fiscal_year + 1 if month in _ROLLOVER_MONTHS else fiscal_year

        currency_pct = ws.cell(row=_CURRENCY_ROW, column=c).value
        fcd_pct = ws.cell(row=_FCD_ROW, column=c).value
        m1_pct = ws.cell(row=_M1_ROW, column=c).value
        broad_money = ws.cell(row=_BROAD_MONEY_ROW, column=c).value
        if not all(isinstance(v, (int, float)) for v in (currency_pct, fcd_pct, m1_pct, broad_money)):
            continue
        if fcd_pct > m1_pct:
            continue  # 소스 데이터 오류로 보이는 불가능한 값(FCD는 M1의 부분집합인데 M1 전체보다 큼)

        fcd = fcd_pct * broad_money / 100
        td = broad_money * (1 - currency_pct / 100)
        if td <= 0 or fcd <= 0 or fcd > td:
            continue

        period = f"{year}-{month:02d}"
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    if not rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
