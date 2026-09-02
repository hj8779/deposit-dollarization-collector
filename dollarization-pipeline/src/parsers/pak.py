"""Pakistan: SBP "Broad Money (M2)" archive xls.

https://www.sbp.org.pk/economic-data 의
https://www.sbp.org.pk/assets/document/BroadMoney_M2_Arch.xls — 시대별 시트
(M2_FY70-FY90, ..., M2_(FY23 to onwards))에 1969-06부터 현재까지 전체 시계열이 있다.
sbp.org.pk가 기본 requests 헤더를 403으로 막아 브라우저형 User-Agent/Referer가 필요.

시트마다 헤더 행/라벨 열 위치가 조금씩 다르지만(구형 시트는 헤더가 2행·라벨이 A열,
신형 시트는 헤더가 4행·라벨이 B/C열 등) 공통 앵커로 파싱한다: 'Currency in Circulation'
행을 먼저 찾고, 그 위로 올라가며 처음 만나는 '숫자(엑셀 날짜 시리얼)가 많은 행'을 헤더로
쓰고, 'Currency in Circulation' 아래 15행 내에서 'Demand Deposit'/'Time Deposit'/
'Resident...Foreign Currency'(RFCDs) 라벨이 있는 행을 찾는다.

TD = Demand Deposits + Time Deposits + RFCDs (= 'Total Deposits with Banks'와 정확히
일치함을 확인). FCD = RFCDs. 1998년 이전 시트는 RFCD 값이 아예 비어 있어(항목은 있으나
공백) 그 구간은 자동 제외됨(FX 거주자예금 제도가 그때부터 생겼거나 그 이전엔 분리
집계되지 않았던 것으로 보임).

최근 시트는 주간(금/토 마감) 빈도라 그대로 쓰면 과밀하므로, (연,월)별로 그 달의 마지막
관측치만 남겨 월간으로 리샘플링한다. 단위 PKR million."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pandas as pd
import requests
import xlrd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_XLS_URL = "https://www.sbp.org.pk/assets/document/BroadMoney_M2_Arch.xls"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.sbp.org.pk/economic-data",
}

_CURRENCY_LABEL_RE = re.compile(r"currency in circulation", re.I)
_DEMAND_LABEL_RE = re.compile(r"demand deposit", re.I)
_TIME_LABEL_RE = re.compile(r"time deposit", re.I)
_RFCD_LABEL_RE = re.compile(r"resident.*foreign currency|rfcd", re.I)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("PAK은 render()로 xls를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _find_row(sh, pattern: re.Pattern, start: int = 0, end: int | None = None) -> int | None:
    end = sh.nrows if end is None else min(end, sh.nrows)
    for r in range(start, end):
        for c in range(sh.ncols):
            v = sh.cell_value(r, c)
            if isinstance(v, str) and pattern.search(v):
                return r
    return None


def _find_header_row(sh, before: int) -> int | None:
    for r in range(before - 1, -1, -1):
        floats = sum(1 for c in range(sh.ncols) if isinstance(sh.cell_value(r, c), float))
        if floats >= sh.ncols * 0.3:
            return r
    return None


def _excel_date(serial: float, datemode: int) -> date | None:
    try:
        y, m, d, *_ = xlrd.xldate_as_tuple(serial, datemode)
        return date(y, m, d)
    except Exception:
        return None


def _parse_sheet(sh, datemode: int) -> list[tuple[date, float, float]]:
    """[(date, fcd, td), ...]"""
    currency_row = _find_row(sh, _CURRENCY_LABEL_RE)
    if currency_row is None:
        return []
    header_row = _find_header_row(sh, currency_row)
    if header_row is None:
        return []
    demand_row = _find_row(sh, _DEMAND_LABEL_RE, currency_row, currency_row + 15)
    time_row = _find_row(sh, _TIME_LABEL_RE, currency_row, currency_row + 15)
    rfcd_row = _find_row(sh, _RFCD_LABEL_RE, currency_row, currency_row + 15)
    if demand_row is None or time_row is None or rfcd_row is None:
        return []

    columns = []
    for c in range(sh.ncols):
        v = sh.cell_value(header_row, c)
        if isinstance(v, float) and v > 1000:
            d = _excel_date(v, datemode)
            if d:
                columns.append(c)

    out = []
    for c in columns:
        demand = sh.cell_value(demand_row, c)
        time_dep = sh.cell_value(time_row, c)
        rfcd = sh.cell_value(rfcd_row, c)
        if not all(isinstance(v, (int, float)) for v in (demand, time_dep, rfcd)):
            continue
        d = _excel_date(sh.cell_value(header_row, c), datemode)
        if not d:
            continue
        fcd = float(rfcd)
        td = float(demand) + float(time_dep) + fcd
        if td <= 0:
            continue
        out.append((d, fcd, td))
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    resp = requests.get(_XLS_URL, headers=_HEADERS, timeout=60)
    resp.raise_for_status()
    wb = xlrd.open_workbook(file_contents=resp.content)

    observations: list[tuple[date, float, float]] = []
    for sheet_name in wb.sheet_names():
        sh = wb.sheet_by_name(sheet_name)
        try:
            found = _parse_sheet(sh, wb.datemode)
            observations.extend(found)
            logger.info("[%s] %s -> %d개 관측치", country_code, sheet_name, len(found))
        except Exception:
            logger.warning("[%s] 시트 파싱 실패: %s", country_code, sheet_name, exc_info=True)

    if not observations:
        return _empty()

    # (year, month)별 그 달의 마지막 관측치만 남겨 월간으로 리샘플링
    monthly: dict[tuple[int, int], tuple[date, float, float]] = {}
    for d, fcd, td in observations:
        key = (d.year, d.month)
        prev = monthly.get(key)
        if prev is None or d > prev[0]:
            monthly[key] = (d, fcd, td)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for (year, month), (d, fcd, td) in monthly.items():
        period = f"{year}-{month:02d}"
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
