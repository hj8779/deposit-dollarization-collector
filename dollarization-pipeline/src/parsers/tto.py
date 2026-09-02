"""Trinidad and Tobago: Central Bank of T&T "Economic DataPack" xlsm.

목록 페이지(economic-datapack-report/)에서 가장 최근 게시물의 링크를 찾고, 그 게시물
페이지 하단의 "... Data Downloadable Version" .xlsm 다운로드 링크를 스크레이핑한다
(파일명이 매달 바뀜, 예: edp-download-june-2026.xlsm).

'PAGE 14_MonAggs_Monthly' 시트, 헤더는 10~11행(2행에 걸쳐 있고 F/G열만 하위 라벨
'Commercial Banks'/'NFIs'로 나뉨), 데이터는 12행부터. 열 구성:
B=Currency in Active Circulation, C=Demand Deposits, D=Savings Deposits,
E=Time Deposits, F=Foreign Currency Deposits(Commercial Banks), G=Foreign Currency
Deposits(NFIs).

FCD = F + G. TD(총예금, 통화 유통고 제외) = C + D + E + F + G.
1991-01부터 최신월까지 매달 갱신되는 단일 시트라 결측 없이 전체 시리즈를 매번 새로 받는다."""

import re
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = "__RENDER__"

_LIST_URL = "https://www.central-bank.org.tt/resources-category/publications-and-research/all-reports/economic-datapack-report/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_ARTICLE_RE = re.compile(r"https://www\.central-bank\.org\.tt/resources/economic-datapack[^\"'\s]+/")
_XLSM_RE = re.compile(r"https://www\.central-bank\.org\.tt/wp-content/uploads/[^\"'\s]+\.xlsm")

_SHEET_NAME = "PAGE 14_MonAggs_Monthly"
_FIRST_DATA_ROW = 12


def _find_latest_xlsx_url() -> str | None:
    resp = requests.get(_LIST_URL, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    article_match = _ARTICLE_RE.search(resp.text)
    if not article_match:
        return None

    article_resp = requests.get(article_match.group(0), headers=_HEADERS, timeout=30)
    article_resp.raise_for_status()
    xlsx_match = _XLSM_RE.search(article_resp.text)
    return xlsx_match.group(0) if xlsx_match else None


def render(target: dict) -> pd.DataFrame:
    url = _find_latest_xlsx_url()
    if not url:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    resp = requests.get(url, headers=_HEADERS, timeout=60)
    resp.raise_for_status()
    return parse(resp.content, target["country_code"])


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    ws = wb[_SHEET_NAME]
    now = datetime.now(timezone.utc).isoformat()
    rows = []

    for r in range(_FIRST_DATA_ROW, ws.max_row + 1):
        date = ws.cell(row=r, column=1).value
        if not isinstance(date, datetime):
            continue
        demand = ws.cell(row=r, column=3).value
        savings = ws.cell(row=r, column=4).value
        time_dep = ws.cell(row=r, column=5).value
        fcd_banks = ws.cell(row=r, column=6).value
        fcd_nfis = ws.cell(row=r, column=7).value

        fcd_banks = float(fcd_banks) if isinstance(fcd_banks, (int, float)) else 0.0
        fcd_nfis = float(fcd_nfis) if isinstance(fcd_nfis, (int, float)) else 0.0
        fcd = fcd_banks + fcd_nfis
        if fcd <= 0:
            continue

        period = f"{date.year}-{date.month:02d}"
        rows.append({
            "country_code": country_code, "year": date.year, "period": period,
            "indicator": INDICATOR, "value": round(fcd, 4), "updated_at": now,
        })

        if all(isinstance(v, (int, float)) for v in (demand, savings, time_dep)):
            td = float(demand) + float(savings) + float(time_dep) + fcd
            rows.append({
                "country_code": country_code, "year": date.year, "period": period,
                "indicator": INDICATOR_TD, "value": round(td, 4), "updated_at": now,
            })

    return pd.DataFrame(rows)
