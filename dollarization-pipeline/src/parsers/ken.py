"""Kenya: Central Bank of Kenya "Depository Corporation Survey" CSV
(centralbank.go.ke/uploads/monetary_and_finance_statistics/...).

CBK가 두 CSV를 게시한다:
  ..._Depository%20Corporation%20Survey%20Old%20-%20CSV.csv   ("1996-todate" — 실측 결과
    실제로는 1995-12부터 최신월(확인 시점 2026-05)까지 매달 갱신되고 있어, 이름과 달리
    가장 넓은 범위를 갖는 메인 소스)
  ..._Depository%20Corporation%20Survey%20-%20CSV.csv          ("current exchange rate"
    버전, A.CBK/B.기관별 섹션으로 재구성돼 FCD 절대값 행이 없고 M3-M2로만 역산 가능 — 검증용)

Old CSV 레이아웃: 라벨이 0열, 연도 헤더가 2행(연 첫 컬럼에만 값, forward-fill), 월 헤더가
4행(Dec, Jan, Feb, ... 문자열). 필요한 행(0-idx, 라벨 매칭으로 찾음):
  'Foreign currency deposits (of residents in Money) (FCDs)'  → FCD
  'Broad money supply ( M2 )'                                  → M2
  'i) Money ( M0 )'                                            → M0 (통화발행잔액, 은행시재금
                                                                  등 제외한 유통현금)
TD(총예금, 자국통화+외화) = M2 − M0 + FCD
  (M2−M0 = 자국통화 예금 전체[요구불+준화폐], 여기에 거주자 외화예금(FCD)을 더하면 전체
  예금이 됨 — "current" CSV의 M3(=M2+FCD)에서 M0을 뺀 것과 동일).

실측 검증: 2026-05 FCD=1,397,034 / M2=4,959,184 / M0=323,871 → TD=6,032,347,
ratio≈23.16% (KNBS Chapter 4 교차 방식으로 얻은 이전 실측 2024-12 ratio≈22.24%와 근접,
같은 자릿수/단위대라 정합적). 단위 KSh Million."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from io import StringIO

import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_OLD_CSV_URL = (
    "https://www.centralbank.go.ke/uploads/monetary_and_finance_statistics/"
    "18143394_Depository%20Corporation%20Survey%20Old%20-%20CSV.csv"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("KEN는 render()로 CBK CSV를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _num(v: str) -> float | None:
    t = v.strip().replace(",", "")
    if t in {"", "-", "–", "—"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _find_row(rows: list[list[str]], label_pattern: str) -> list[str] | None:
    pat = re.compile(label_pattern, re.I)
    for row in rows:
        if row and pat.search(row[0] or ""):
            return row
    return None


def _period_columns(rows: list[list[str]]) -> dict[int, str]:
    """col index -> 'YYYY-MM', from the year row (idx 2, sparse) + month row (idx 4)."""
    year_row = rows[2]
    month_row = rows[4]
    n = max(len(year_row), len(month_row))
    years: dict[int, int] = {}
    last_year = None
    for j in range(1, n):
        v = year_row[j].strip() if j < len(year_row) else ""
        if v:
            m = re.search(r"\d{4}", v)
            if m:
                last_year = int(m.group())
        if last_year is not None:
            years[j] = last_year

    cols: dict[int, str] = {}
    for j in range(1, n):
        mon_s = month_row[j].strip().lower() if j < len(month_row) else ""
        mon = _MONTHS.get(mon_s)
        year = years.get(j)
        if mon is None or year is None:
            continue
        cols[j] = f"{year}-{mon:02d}"
    return cols


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        resp = requests.get(_OLD_CSV_URL, headers=_HEADERS, timeout=90, verify=False)
        resp.raise_for_status()
        text = resp.content.decode("latin-1")
        rows = list(csv.reader(StringIO(text)))
    except Exception as e:
        logger.exception("[%s] CSV 다운로드/파싱 실패: %s", country_code, e)
        return _empty()

    fcd_row = _find_row(rows, r"Foreign currency deposits.*\(FCDs\)")
    m2_row = _find_row(rows, r"Broad money supply\s*\(\s*M2\s*\)")
    m0_row = _find_row(rows, r"Money\s*\(\s*M0\s*\)")
    if fcd_row is None or m2_row is None or m0_row is None:
        logger.error(
            "[%s] 필요한 행을 못 찾음 (fcd=%s, m2=%s, m0=%s)",
            country_code, fcd_row is not None, m2_row is not None, m0_row is not None,
        )
        return _empty()

    cols = _period_columns(rows)

    now = datetime.now(timezone.utc).isoformat()
    out_rows = []
    for j, period in cols.items():
        fcd = _num(fcd_row[j]) if j < len(fcd_row) else None
        m2 = _num(m2_row[j]) if j < len(m2_row) else None
        m0 = _num(m0_row[j]) if j < len(m0_row) else None
        if fcd is None or m2 is None or m0 is None:
            continue
        td = m2 - m0 + fcd
        if td <= 0 or fcd < 0:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            out_rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    if not out_rows:
        return _empty()
    out = (
        pd.DataFrame(out_rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
