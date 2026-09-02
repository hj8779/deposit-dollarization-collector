"""Venezuela: BCV "Balances monetarios" — Bancos Universales/Comerciales y de
Desarrollo, "Resumen del Balance Monetario Consolidado" xls.

https://www.bcv.org.ve/estadisticas/balances-monetarios 페이지에서 해당 xls 링크를
스크레이핑(문서 경로가 개편될 수 있어 매번 재탐색).

이 xls는 시트 하나당 반년치(예: 'I Semestre 2026', 'II Semestre 1999') 월별 데이터를
담고 있고 1999년부터 현재까지 전체 시트가 누적되어 있음(2021년만 통화 재표시 시점 때문에
'Ene - Sep 2021'/'Oct - Dic 2021'로 예외적으로 3+3개월 분할). 5행이 월 헤더(예: 'Ene
2026'), 라벨 열(A열)에서 'DEPOSITOS EN MONEDA NACIONAL'(자국통화 예금) /
'DEPOSITOS EN MONEDA EXTRANJERA'(외화예금=FCD) 행을 찾는다 - 이 두 라벨의 실제 행
번호는 연도별로 계속 바뀌어서(예: 1999년 40/65행, 2010년 44/68행, 2026년 45/70행)
라벨 텍스트로 매번 검색한다.

TD = 자국통화예금 + 외화예금(비거주자예금/양도성예금증서 등은 제외, 다른 국가 파서들의
'핵심 예금'만 합산하는 관행과 동일). FCD = 외화예금.

베네수엘라는 2008년(볼리바르 푸에르떼), 2018년(볼리바르 소베라노), 2021년(볼리바르
디지털, 6자리 제거) 세 차례 화폐개혁을 거쳐 절대값 스케일이 시기마다 완전히 다르다(파일
자체에도 '2021-10-01부터 새 통화 표시 적용, 6자리 삭제' 각주가 있음). FCD_TD_RATIO는
같은 시점 내 비율이라 화폐개혁과 무관하게 유효하지만, FCD/TD 절대값(단위: 천 볼리바르
또는 볼리바르, 시기별로 다름)은 시계열로 그대로 이어붙이면 안 되므로 그래프에서 절대값
비교 시 주의가 필요함(비율 축은 문제 없음)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3
import xlrd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_LIST_PAGE = "https://www.bcv.org.ve/estadisticas/balances-monetarios"
_XLS_LINK_RE = re.compile(
    r'href="([^"]*bcos\._com\._univ\._y_de_desarrollo\._resumen_bal\._monetario_consolidado_mensual\.xls)"',
    re.I,
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}
_MONTH_HEADER_RE = re.compile(r"([A-Za-z]{3})\.?\s*(\d{4})")
_NATIONAL_LABEL = "deposit"  # 뒤에서 'moneda nacional'/'moneda extranjera' 조합으로 재확인
_ACCENTS = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("VEN은 render()로 xls를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _find_xls_url() -> str | None:
    resp = requests.get(_LIST_PAGE, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    match = _XLS_LINK_RE.search(resp.text)
    if not match:
        return None
    href = match.group(1)
    return href if href.startswith("http") else "https://www.bcv.org.ve" + href


def _normalize(s: str) -> str:
    return s.translate(_ACCENTS).strip().upper()


def _find_row(sh, label: str) -> int | None:
    for r in range(sh.nrows):
        cell = sh.cell_value(r, 0)
        if isinstance(cell, str) and _normalize(cell) == label:
            return r
    return None


def _header_periods(sh, header_row: int) -> dict[int, str]:
    periods = {}
    for c in range(1, sh.ncols):
        v = sh.cell_value(header_row, c)
        if not isinstance(v, str):
            continue
        m = _MONTH_HEADER_RE.search(_normalize(v).lower())
        if not m:
            continue
        month = _MONTHS.get(m.group(1).lower())
        if month:
            periods[c] = f"{int(m.group(2))}-{month:02d}"
    return periods


def _parse_sheet(sh, country_code: str, now: str) -> list[dict]:
    header_row = None
    for r in range(min(10, sh.nrows)):
        if _header_periods(sh, r):
            header_row = r
            break
    if header_row is None:
        return []
    periods = _header_periods(sh, header_row)
    if not periods:
        return []

    national_row = _find_row(sh, "DEPOSITOS EN MONEDA NACIONAL")
    fx_row = _find_row(sh, "DEPOSITOS EN MONEDA EXTRANJERA")
    if national_row is None or fx_row is None:
        return []

    rows = []
    for col, period in periods.items():
        national = sh.cell_value(national_row, col)
        fx = sh.cell_value(fx_row, col)
        if not isinstance(national, (int, float)) or not isinstance(fx, (int, float)):
            continue
        fcd = float(fx)
        td = float(national) + fcd
        if td <= 0:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })
    return rows


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    xls_url = _find_xls_url()
    if not xls_url:
        logger.warning("[%s] 목록 페이지에서 xls 링크를 찾지 못함", country_code)
        return _empty()

    resp = requests.get(xls_url, headers=_HEADERS, timeout=60, verify=False)
    resp.raise_for_status()
    wb = xlrd.open_workbook(file_contents=resp.content)

    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for sheet_name in wb.sheet_names():
        sh = wb.sheet_by_name(sheet_name)
        try:
            rows.extend(_parse_sheet(sh, country_code, now))
        except Exception:
            logger.warning("[%s] 시트 파싱 실패: %s", country_code, sheet_name, exc_info=True)

    if not rows:
        return _empty()

    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
