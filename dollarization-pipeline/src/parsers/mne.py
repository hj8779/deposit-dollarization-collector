"""Montenegro: CBCG Monetary Financial Institutions statistics zip.

페이지:
  https://www.cbcg.me/en/statistics/statistical-data/monetary-and-financial-statistics/monetary-financial-institutions
파일:
  /slike_i_fajlovi/fajlovi/fajlovi_publikacije/statistika/statistika_monetarnih_finansijskih_institucija_{mon}_{year}.zip

xlsx 시트 'Ukupni depoziti -Total deposits':
  연도 행 × 월 열 (I..XII) → TD (EUR 000)

FCD (other currencies, 유로 제외):
  월별 통화분해가 zip에 없어, CBCG 연차/안정보고서에서 확인된
  year-end other-currency share를 TD에 적용해 연말 관측을 보강한다.
  (2021=5.75%, 2022=5.12%, 2023=4.93% — batch1/CBCG AR)

월별 TD는 전 기간, FCD/RATIO는 연말(12월) 및 문서 기반 share가 있는 해만.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_PAGE = (
    "https://www.cbcg.me/en/statistics/statistical-data/"
    "monetary-and-financial-statistics/monetary-financial-institutions"
)
_BASE = "https://www.cbcg.me"
_FALLBACK_ZIP = (
    "https://www.cbcg.me/slike_i_fajlovi/fajlovi/fajlovi_publikacije/statistika/"
    "statistika_monetarnih_finansijskih_institucija_jun_2026.zip"
)

# Year-end other-currency share of total deposits (CBCG Annual Report 각 연도판,
# "deposits in other currencies made up X% of total deposits" 문장에서 직접 확인).
# 2026-08-20 사용자가 짚어준 publications 목록 페이지에서 cbm_annual_report_2003~2012.pdf +
# cbcg_annual_report_2014~2024.pdf 15개를 전부 훑어 확장(2013, 2020 보고서는 미게시/해당
# 문장 없음 확인 — 2020-2024판부터는 이 상세 표 자체가 사라졌다는 사용자 확인과 일치).
# 2003-2008은 문장형 요약이 없고 옛 포맷 표(예: 2003년 'Table 21 Deposits by Private
# Citizens'는 전체가 아니라 거주자 중 개인 부문만의 통화별 분해라 범위가 달라 보류 —
# 추후 시간 날 때 재조사 필요.
_YEAR_END_OTHER_CCY_SHARE = {
    2009: 3.4,
    2010: 3.32,
    2011: 3.5,
    2012: 4.0,
    2014: 4.08,
    2015: 6.9,
    2016: 6.6,
    2017: 7.06,
    2018: 6.92,
    2019: 7.10,
    2021: 5.75,
    2022: 5.12,
    2023: 4.93,
    2024: 4.76,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MNE는 render()로 zip을 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _resolve_zip() -> str:
    try:
        resp = requests.get(_PAGE, headers=_HEADERS, timeout=60, verify=False)
        resp.raise_for_status()
        hrefs = re.findall(
            r'href=["\']([^"\']*statistika_monetarnih_finansijskih_institucija[^"\']*\.zip)["\']',
            resp.text,
            re.I,
        )
        if hrefs:
            # pick last (often newest) or max by name
            hrefs = sorted(set(hrefs))
            url = urljoin(_BASE, hrefs[-1])
            logger.info("[MNE] resolved %s", url)
            return url
    except Exception as e:
        logger.warning("[MNE] page scrape: %s", e)
    return _FALLBACK_ZIP


def _parse_td_sheet(xlsx_bytes: bytes) -> dict[str, float]:
    xl = pd.ExcelFile(BytesIO(xlsx_bytes))
    sheet = None
    for s in xl.sheet_names:
        if re.search(r"total deposits|ukupni depoziti", s, re.I):
            sheet = s
            break
    if sheet is None:
        return {}
    df = xl.parse(sheet, header=None)
    # header row with I II III ... or 1..12
    month_row = None
    month_cols: dict[int, int] = {}
    for i in range(min(8, len(df))):
        hits = {}
        for j in range(1, df.shape[1]):
            v = df.iat[i, j]
            if isinstance(v, str):
                rom = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                       "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
                key = v.strip().upper()
                if key in rom:
                    hits[j] = rom[key]
            elif isinstance(v, (int, float)) and not pd.isna(v) and 1 <= int(v) <= 12:
                hits[j] = int(v)
        if len(hits) >= 6:
            month_row = i
            month_cols = hits
            break
    if not month_cols:
        return {}

    out: dict[str, float] = {}
    for i in range((month_row or 0) + 1, len(df)):
        yv = df.iat[i, 0]
        try:
            year = int(float(str(yv).replace("*", "").strip()[:4]))
        except (TypeError, ValueError):
            continue
        if year < 1990 or year > 2100:
            continue
        for j, mon in month_cols.items():
            val = df.iat[i, j]
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            try:
                td = float(val)
            except (TypeError, ValueError):
                continue
            if td <= 0:
                continue
            out[f"{year}-{mon:02d}"] = td
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        url = _resolve_zip()
        resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
        resp.raise_for_status()
        if not resp.content.startswith(b"PK"):
            raise RuntimeError("not zip")
        with zipfile.ZipFile(BytesIO(resp.content)) as zf:
            name = next(
                (n for n in zf.namelist() if n.lower().endswith((".xlsx", ".xls"))),
                None,
            )
            if not name:
                raise RuntimeError("no xlsx in zip")
            xlsx_bytes = zf.read(name)

        td_map = _parse_td_sheet(xlsx_bytes)
        if not td_map:
            logger.error("[%s] no TD periods", country_code)
            return _empty()

        now = datetime.now(timezone.utc).isoformat()
        # Apply year-end other-currency share to every month of that year
        # (CBCG monthly FX breakdown not published; share is annual).
        rows = []
        for period, td in sorted(td_map.items()):
            year = int(period[:4])
            share = _YEAR_END_OTHER_CCY_SHARE.get(year)
            if share is None or td <= 0:
                continue
            fcd = td * share / 100.0
            ratio = round(share, 4)
            for indicator, value in (
                ("FCD", round(fcd, 4)),
                ("TD", round(td, 4)),
                ("FCD_TD_RATIO", ratio),
            ):
                rows.append({
                    "country_code": country_code,
                    "year": year,
                    "period": period,
                    "indicator": indicator,
                    "value": value,
                    "updated_at": now,
                })

        if not rows:
            logger.error(
                "[%s] no months overlapped year-end FCD shares %s (TD months=%d)",
                country_code,
                sorted(_YEAR_END_OTHER_CCY_SHARE),
                len(td_map),
            )
            return _empty()

        out = (
            pd.DataFrame(rows)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] %d rows (%s~%s) note: monthly TD × year-end other-currency share",
            country_code, len(out), out["period"].min(), out["period"].max(),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
