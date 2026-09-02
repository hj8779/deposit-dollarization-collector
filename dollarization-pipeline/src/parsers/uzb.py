"""Uzbekistan: CBU "Monetary aggregates" xlsx.

https://cbu.uz/en/statistics/dks/4320467/ (Monetary and financial statistics >
Monetary aggregates) 페이지에서 xlsx 링크를 스크레이핑(문서 경로가 바뀔 수 있음).

영어/러시아어("Денежные агрегаты")/우즈베크어("Pul agregatlari") 페이지가 언어별로
서로 다른 콘텐츠 ID를 쓰지만 데이터는 전부 동일하게 2013-02부터 시작함(직접 세 언어
버전 다 받아서 대조 확인함) - 이 CBU 통계 자체가 2013년 이전 시계열을 갖고 있지 않은
것으로 보임(2016 IMF Monetary and Financial Statistics Manual 기준 통화별 M2 분해를
2013년부터 소급 적용한 것으로 추정).

'Broad money' 시트, 7행이 열 인덱스 헤더(2=3+8 등 수식으로 열 구성을 알려줌), 8행부터
월별 데이터. B열(2)=Broad money M2 총계=TD. H열(8)='Foreign currency deposits in
national currency equivalent'=FCD. 단위 billion UZS."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_LIST_PAGE = "https://cbu.uz/en/statistics/dks/4320467/"
_XLSX_LINK_RE = re.compile(r'href="([^"]*\.xlsx)"', re.I)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

_TD_COL = 2  # Broad money (M2)
_FCD_COL = 8  # Foreign currency deposits in national currency equivalent
_FIRST_DATA_ROW = 8


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("UZB는 render()로 xlsx를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _find_xlsx_url() -> str | None:
    resp = requests.get(_LIST_PAGE, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    match = _XLSX_LINK_RE.search(resp.text)
    if not match:
        return None
    href = match.group(1)
    return href if href.startswith("http") else "https://cbu.uz" + href


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    xlsx_url = _find_xlsx_url()
    if not xlsx_url:
        logger.warning("[%s] 목록 페이지에서 xlsx 링크를 찾지 못함", country_code)
        return _empty()

    resp = requests.get(xlsx_url, headers=_HEADERS, timeout=60)
    resp.raise_for_status()
    wb = openpyxl.load_workbook(BytesIO(resp.content), data_only=True)
    ws = wb[wb.sheetnames[0]]

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for r in range(_FIRST_DATA_ROW, ws.max_row + 1):
        date = ws.cell(row=r, column=1).value
        if not isinstance(date, datetime):
            continue
        td = ws.cell(row=r, column=_TD_COL).value
        fcd = ws.cell(row=r, column=_FCD_COL).value
        if not isinstance(td, (int, float)) or not isinstance(fcd, (int, float)) or td <= 0:
            continue

        period = f"{date.year}-{date.month:02d}"
        ratio = round((float(fcd) / float(td)) * 100, 4)
        for indicator, value in ((INDICATOR, round(float(fcd), 4)), (INDICATOR_TD, round(float(td), 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": date.year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

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
