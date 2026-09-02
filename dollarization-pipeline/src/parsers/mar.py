"""Morocco: Bank Al-Maghrib "Séries statistiques monétaires" — 'AGRÉGATS DE MONNAIE' xlsx.

페이지: https://www.bkam.ma/Statistiques/Statistiques-monetaires/Series-statistiques-monetaires
다운로드 링크(예: /content/download/632818/7098245/6-AgregatsDeMonnaie.xlsx)의 문서ID가
개정마다 바뀔 수 있어 매번 페이지를 스크레이핑해 현재 링크를 찾는다.

'Feuil1' 시트: 3행이 월말 날짜 헤더(2001-12부터), 이후 각 행이 지표. 필요한 행(라벨로
탐색, 행 번호가 아니라):
  'Dépôts en devises' — 각주(3) "Dépôts à vue et à terme en devises auprès des banques"
      = 은행 예치 요구불+정기 외화예금 = FCD.
  'Monnaie scripturale' — BAM/은행/우체국(CCP)/재무부 예치 요구불예금 합계 (M1의 통화발행고
      제외 부분) = 자국통화 요구불예금.
  'Placements à vue' — 저축성 즉시인출예금(quasi-money 유동성 예치).
  'Comptes à terme et bons de caisse auprès des banques' — 은행 정기예금.
  'Autres dépôts' — 기타예금.

TD = Monnaie scripturale + Placements à vue + Comptes à terme... + Dépôts en devises
   + Autres dépôts. 'Titres OPCVM monétaires'(MMF 지분), 'Valeurs données en pension'(레포),
   'Certificats de dépôts'(NCD), 'Dépôts à terme auprès du Trésor'는 순수 예금이 아니거나
   자료 부재(ND)가 잦아 제외 — 다른 국가 파서들의 NID/repo 제외 관행과 동일.
   검산: 'Autres actifs Monétaires' 행 = 위 제외 항목들 + Dépôts en devises + Comptes à
   terme + Autres dépôts 의 합과 정확히 일치함을 확인(구조 검증됨).

월간, 2001-12~현재. 단위: MDH(백만 디르함)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_LIST_PAGE = "https://www.bkam.ma/Statistiques/Statistiques-monetaires/Series-statistiques-monetaires"
_BASE = "https://www.bkam.ma"
_XLSX_LINK_RE = re.compile(r'href="([^"]*AgregatsDeMonnaie\.xlsx)"', re.I)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}

_SCRIPTURAL_LABEL = "monnaie scripturale"
_SIGHT_SAVINGS_LABEL = "placements à vue"
_TERM_LABEL = "comptes à terme et bons de caisse"
_FCD_LABEL = "dépôts en devises"
_OTHER_LABEL = "autres dépôts"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MAR는 render()로 xlsx를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _find_xlsx_url() -> str | None:
    resp = requests.get(_LIST_PAGE, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    match = _XLSX_LINK_RE.search(resp.text)
    if not match:
        return None
    href = match.group(1)
    return href if href.startswith("http") else _BASE + href


def _find_row(ws, label: str) -> int | None:
    for r in range(1, ws.max_row + 1):
        cell = ws.cell(row=r, column=1).value
        if isinstance(cell, str) and cell.strip().lower().startswith(label):
            return r
    return None


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    xlsx_url = _find_xlsx_url()
    if not xlsx_url:
        logger.warning("[%s] 목록 페이지에서 AgregatsDeMonnaie.xlsx 링크를 찾지 못함", country_code)
        return _empty()

    resp = requests.get(xlsx_url, headers=_HEADERS, timeout=60, verify=False)
    resp.raise_for_status()
    return _parse_workbook(resp.content, country_code)


def _parse_workbook(content: bytes, country_code: str) -> pd.DataFrame:
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    ws = wb["Feuil1"]

    scriptural_row = _find_row(ws, _SCRIPTURAL_LABEL)
    sight_savings_row = _find_row(ws, _SIGHT_SAVINGS_LABEL)
    term_row = _find_row(ws, _TERM_LABEL)
    fcd_row = _find_row(ws, _FCD_LABEL)
    other_row = _find_row(ws, _OTHER_LABEL)
    if not all([scriptural_row, sight_savings_row, term_row, fcd_row, other_row]):
        logger.error(
            "[%s] 필요한 행을 못 찾음: scriptural=%s sight_savings=%s term=%s fcd=%s other=%s",
            country_code, scriptural_row, sight_savings_row, term_row, fcd_row, other_row,
        )
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for c in range(2, ws.max_column + 1):
        date = ws.cell(row=3, column=c).value
        if not isinstance(date, datetime):
            continue

        fcd = ws.cell(row=fcd_row, column=c).value
        scriptural = ws.cell(row=scriptural_row, column=c).value
        sight_savings = ws.cell(row=sight_savings_row, column=c).value
        term = ws.cell(row=term_row, column=c).value
        other = ws.cell(row=other_row, column=c).value
        parts = (fcd, scriptural, sight_savings, term, other)
        if any(not isinstance(v, (int, float)) for v in parts):
            continue

        fcd = float(fcd)
        td = sum(float(v) for v in parts)
        if td <= 0:
            continue

        period = f"{date.year}-{date.month:02d}"
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
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
