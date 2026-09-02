"""Yemen: Central Bank of Yemen (Aden, internationally-recognized) research page,
two families of PDF: "Annual Report" (연 1회) + "Monetary and Financial
Developments" 월간 소식지(+ 일부 "CBY Quarterly Bulletin") — 둘 다 같은
'Table 1: Monetary Survey of Yemen' 표를 싣는다.

https://english.cby-ye.com/researchandstatistics 페이지에서 두 종류 링크를 모두 스크레이핑.

1) Annual Report (확인 시점 기준 3개뿐: 2020/2024/2025, 2021~2023년치는 별도 연차보고서가
   없음 - CBY가 그 기간을 건너뜀), 각 보고서의 Table 1이 9~12개년 롤링 윈도우라 셋을 합치면
   2014~2025 연간 데이터가 커버됨:
     - Annual Report 2020: ~2016-2020 (billion rials)
     - Annual Report 2024: ~2020-2024 (million rials)
     - Annual Report 2025: ~2021-2025 (million rials, 2022년부터 시장환율 기준이라는 각주 있음)
   겹치는 연도는 최신 보고서 값으로 덮어쓴다. → period="YYYY-Annual".

2) "Monetary and Financial Developments" 월간지(2021-12부터 매월 발행, 제목 표기가
   "Monetary and Financial Developments - December 2023"/"...development July 2022"/
   "...Developments Dec - 2025"처럼 들쭉날쭉함 - 월/연도를 자유 검색으로 추출) + 일부
   "CBY Quarterly Bulletin"(2020-12부터). 이 소식지들의 Table 1도 동일한 'Items' 헤더 +
   연도별 롤링 컬럼 구조지만, 마지막 1~2개 컬럼만 그 호가 다루는 실제 월(예: Nov/Dec 2023)이고
   나머지는 과거 연말 스냅샷 재수록이라 겹친다. 그래서 이 소식지들은 **가장 오른쪽(마지막)
   컬럼만** 그 호 자신의 보고월로 채택하고(월/연도는 제목에서 파싱), 나머지 컬럼은 버린다
   (Annual Report 트랙과 값이 겹쳐도 상관없게 period 네임스페이스가 "YYYY-MM"으로 분리됨).
   → period="YYYY-MM". 실측 검증: 2023-12호 Table 1 마지막 컬럼 FCD=5,818.6/
   TD(Quasi+Demand)=8,153.6 billion rials — 같은 값이 Annual Report 2025의 "2023-Annual"
   행에도 million 단위(5,818,560 / 8,153,651.2)로 실려있어 일치 확인함.

표 헤더는 'Items' 로 시작하는 행에 연도가 나열되는데, 문서 안에 'Items' 헤더를 쓰는
표가 여러 개(부문별 통계표 등) 있어 연도가 가장 많이 나열된 헤더부터 순서대로 시도해
'Foreign currency deposits'/'Quasi-money'/'Demand deposits' 세 행이 모두 매칭되는
첫 번째 표를 채택한다.

TD = Quasi-money + Demand deposits (표에 있는 'Foreign currency deposits to total
deposits' 비율로 역산한 값과 거의 일치함을 확인). FCD = Foreign currency deposits.
단위는 보고서마다 billion/million rials로 다르게 표기되어 있어 보고서에 실린 그대로
저장한다(연도 사이 스케일 불연속 있음, FCD_TD_RATIO는 영향 없음)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.fcd_series import pdf_text
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_RESEARCH_PAGE = "https://english.cby-ye.com/researchandstatistics"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

_ANNUAL_REPORT_LINK_RE = re.compile(r'<a[^>]*href="(/files/[^"]+\.pdf)"[^>]*>\s*[^<]*[Aa]nnual\s+[Rr]eport[^<]*</a>')
_MONTHLY_LINK_RE = re.compile(
    r'<a[^>]*href="(/files/[^"]+\.pdf)"[^>]*>\s*([^<]*(?:[Mm]onetary\s+and\s+[Ff]inancial\s+[Dd]evelopment|[Qq]uarterly\s+[Bb]ulletin)[^<]*)</a>'
)
_ITEMS_HEADER_RE = re.compile(r"^Items\b")
_YEAR_TOKEN_RE = re.compile(r"\*?(\d{4})")

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_TITLE_MONTH_YEAR_RE = re.compile(
    r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")[a-z]*\W*(\d{4})",
    re.I,
)


def _parse_period_from_title(title: str) -> str | None:
    m = _TITLE_MONTH_YEAR_RE.search(title)
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    year = int(m.group(2))
    return f"{year}-{month:02d}"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("YEM은 render()로 연차보고서 목록을 순회한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _list_annual_report_urls() -> list[str]:
    resp = requests.get(_RESEARCH_PAGE, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return sorted({urljoin(_RESEARCH_PAGE, m) for m in _ANNUAL_REPORT_LINK_RE.findall(resp.text)})


def _list_monthly_bulletin_urls() -> list[tuple[str, str]]:
    """Return [(url, title)] for 'Monetary and Financial Developments' / 'CBY
    Quarterly Bulletin' issues (excludes Annual Report, matched separately)."""
    resp = requests.get(_RESEARCH_PAGE, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    out = []
    seen = set()
    for href, title in _MONTHLY_LINK_RE.findall(resp.text):
        url = urljoin(_RESEARCH_PAGE, href)
        if url not in seen:
            seen.add(url)
            out.append((url, title.strip()))
    return out


def _row_values(lines: list[str], header_idx: int, label: str, n: int) -> list[float] | None:
    for line in lines[header_idx: header_idx + 40]:
        low = line.lower()
        if label.lower() not in low:
            continue
        if "change" in low or "to broad" in low or "to total" in low:
            continue
        nums = re.findall(r"-?[\d,]+\.\d+", line)
        if len(nums) >= n:
            return [float(x.replace(",", "")) for x in nums[-n:]]
    return None


def _extract_monetary_survey(text: str) -> tuple[list[str], list[float], list[float], list[float]] | None:
    lines = text.splitlines()
    candidates = []
    for i, line in enumerate(lines):
        if not _ITEMS_HEADER_RE.match(line.strip()):
            continue
        years = _YEAR_TOKEN_RE.findall(line)
        if len(years) >= 2:
            candidates.append((i, years))

    for i, years in sorted(candidates, key=lambda c: -len(c[1])):
        n = len(years)
        fcd = _row_values(lines, i, "Foreign currency deposits", n)
        quasi = _row_values(lines, i, "Quasi-money", n)
        demand = _row_values(lines, i, "Demand deposits", n)
        if fcd and quasi and demand:
            return years, fcd, quasi, demand
    return None


def _extract_latest_column(text: str) -> tuple[float, float, float] | None:
    """Same Table 1 lookup as _extract_monetary_survey, but only the rightmost
    (this issue's own reporting month) column — used for monthly/quarterly
    bulletins where earlier columns just re-print prior year-end snapshots."""
    lines = text.splitlines()
    candidates = []
    for i, line in enumerate(lines):
        if not _ITEMS_HEADER_RE.match(line.strip()):
            continue
        years = _YEAR_TOKEN_RE.findall(line)
        if len(years) >= 2:
            candidates.append((i, len(years)))

    for i, n in sorted(candidates, key=lambda c: -c[1]):
        fcd = _row_values(lines, i, "Foreign currency deposits", n)
        quasi = _row_values(lines, i, "Quasi-money", n)
        demand = _row_values(lines, i, "Demand deposits", n)
        if fcd and quasi and demand:
            return fcd[-1], quasi[-1], demand[-1]
    return None


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()
    combined: dict[str, tuple[float, float]] = {}

    try:
        urls = _list_annual_report_urls()
    except Exception:
        urls = []
        logger.exception("[%s] 연차보고서 목록 조회 실패", country_code)

    logger.info("[%s] 연차보고서 %d건 발견", country_code, len(urls))

    for url in urls:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=120)
            resp.raise_for_status()
            text = pdf_text(resp.content)
            found = _extract_monetary_survey(text)
            if not found:
                logger.warning("[%s] Monetary Survey 표를 못 찾음: %s", country_code, url.rsplit("/", 1)[-1])
                continue
            years, fcd, quasi, demand = found
            for year, f, q, d in zip(years, fcd, quasi, demand):
                td = q + d
                if td > 0:
                    combined[f"{year}-Annual"] = (f, td)
            logger.info("[%s] %s -> %d개 연도", country_code, url.rsplit("/", 1)[-1], len(years))
        except Exception:
            logger.warning("[%s] %s 처리 실패", country_code, url, exc_info=True)

    try:
        monthly_urls = _list_monthly_bulletin_urls()
    except Exception:
        monthly_urls = []
        logger.exception("[%s] 월간 소식지 목록 조회 실패", country_code)

    logger.info("[%s] 월간/분기 소식지 %d건 발견", country_code, len(monthly_urls))

    def _one(item: tuple[str, str]) -> tuple[str, float, float] | None:
        url, title = item
        period = _parse_period_from_title(title)
        if period is None:
            logger.debug("[%s] 제목에서 연월 파싱 실패: %s", country_code, title)
            return None
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=120)
            resp.raise_for_status()
            text = pdf_text(resp.content)
            found = _extract_latest_column(text)
            if not found:
                logger.warning("[%s] Monetary Survey 표를 못 찾음: %s", country_code, title)
                return None
            f, q, d = found
            td = q + d
            if td > 0:
                return period, f, td
        except Exception:
            logger.warning("[%s] %s 처리 실패", country_code, url, exc_info=True)
        return None

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_one, item): item for item in monthly_urls}
        for fut in as_completed(futs):
            result = fut.result()
            if result:
                period, f, td = result
                combined[period] = (f, td)

    if not combined:
        return _empty()

    rows = []
    for period, (fcd, td) in combined.items():
        year = int(period[:4])
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
