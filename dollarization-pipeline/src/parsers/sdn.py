"""Sudan: Central Bank of Sudan (CBOS) annual reports, "Deposits in Local/Foreign
Currency" tables.

목록: https://cbos.gov.sd/en/publication-type/annual-reports 에서
/en/content/annual-report-YYYY 링크들을 모음(2002~2018만 존재, 2019년 이후 발행본 없음 -
CBOS 사이트 자체에 게시된 마지막 연차보고서가 2018년임). 각 연차보고서 페이지에는 영문
PDF 링크(및 모든 연도 페이지에 공통으로 걸려 있는 무관한 아랍어 조직도 PDF 링크)가 있어,
아랍어(%D8로 시작하는 percent-encoded) 링크는 제외하고 첫 PDF를 쓴다.

각 보고서는 해당 연도와 전년도 2개년 표를 담고 있어("Deposits in Local Currency by the
end of 2017 and 2018" 등, 연도별 표 제목 문구가 조금씩 다름 - "Total deposits in Local
Currency by the end of the years 2013 and 2014"처럼 접두어/'the years'가 붙기도 함,
그래서 정확한 문구 대신 '숫자 4자리 두 개 + Local/Foreign Currency + Deposit' 조합으로
느슨하게 찾는다), 2002~2018년 보고서를 전부 훑으면 겹치는 연도는 최신 보고서 값으로
덮어써 2002~2018 전체 연간 시계열이 만들어진다.

표는 예금주체별(정부/공기업/민간)로 나뉜 뒤 'Grand Total' 행에 두 해의 합계가 있고, 이
합계를 그대로 쓴다: FCD = Foreign Currency 표의 Grand Total, TD = Local Grand Total +
Foreign Grand Total. 단위 SDG million(단, 2007년 이전은 수단이 화폐개혁 전 구 디나르
표시라 절대값 스케일이 다름 - 보고서에 실린 그대로 저장).

pdftotext -layout이 이 PDF들의 폰트 인코딩을 pdfplumber보다 훨씬 안정적으로 읽어서(구형
보고서의 임베디드 폰트가 pdfplumber에서는 전부 (cid:NN) 깨짐 문자로 나옴) pdftotext를
우선 쓴다.

--- 분기 공보(추가) ---
목록: https://cbos.gov.sd/en/periodicals-publications?field_publication_type_tid_i18n=44
(2003~2025 분기, 연차보고서보다 최신까지 커버). 게시물 슬러그가 'Nth-quarter-YYYY',
'quarter-N-YYYY', 'first-quarter-YYYY', 'NYYYY'(오타로 보이는 형태, 예: '32020-0'=
2020-Q3) 등 제각각이라 여러 정규식으로 시도한다. 공보 제목/링크 텍스트도 국문 표기라
PDF 링크는 아랍어 파일명인 경우가 대부분인데, PDF 안의 'Table No.(20) Money Supply'
표(제목 번호는 호수마다 바뀔 수 있어 'Money Supply'와 'Foreign Currency Deposits'가
같이 나오는 표로 찾음)는 아랍어 보고서 안에서도 영문 라벨+로마숫자로 되어 있어 그대로
파싱 가능하다.

이 표는 매 호마다 최근 9개 기간(과거 연말들 + 최근 분기들)을 나란히 보여주는 롤링
윈도우라 헤더 정렬을 파싱하는 대신 각 행의 '마지막 숫자'(=해당 호 자신의 분기, 표의
가장 오른쪽 열)만 취하고, 그 분기는 게시물 슬러그에서 이미 알고 있으므로 헤더 매칭이
필요 없다. TD = Demand Deposits + Local Currency Deposits + Foreign Currency Deposits
(= Money Supply M2 - Currency with the Public, 두 방식이 정확히 일치함을 확인함).
FCD = Foreign Currency Deposits."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.fcd_series import pdf_text
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_ARCHIVE_URL = "https://cbos.gov.sd/en/publication-type/annual-reports"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

_REPORT_LINK_RE = re.compile(r'href="(/en/content/annual-report-[^"]*)"')
_PDF_LINK_RE = re.compile(r'href="(https://cbos\.gov\.sd/sites/default/files/[^"]+\.pdf)"', re.I)
_TITLE_RE = re.compile(
    r"[Dd]eposits?[^\n]{0,40}(Local|Foreign) Currency[^\n]{0,40}?(\d{4})\s+and\s*(?:the\s+year[s]?\s+)?(\d{4})",
)
_GRAND_TOTAL_RE = re.compile(r"Grand [Tt]otal\s*\n*\s*([\d,]+\.?\d*)\s+([\d,]+\.?\d*)")
_GRAND_TOTAL_FALLBACK_RE = re.compile(r"Grand [Tt]otal[^\n]*\n?[^\n]*?([\d,]+\.?\d*)[^\n]*?([\d,]+\.?\d*)")

_QUARTERLY_LIST_URL = "https://cbos.gov.sd/en/periodicals-publications?field_publication_type_tid_i18n=44"
_QUARTER_LINK_RE = re.compile(r'href="(/en/content/[^"]*)"')
_QUARTER_SLUG_PATTERNS = [
    re.compile(r"(\d)(?:st|nd|rd|th)-quarter-(\d{4})"),
    re.compile(r"quarter-(\d)-(\d{4})"),
    re.compile(r"(first|second|third|fourth)-quarter-(\d{4})"),
    re.compile(r"^(\d)(\d{4})(?:-\d+)?$"),
]
_QUARTER_WORD_MAP = {"first": "1", "second": "2", "third": "3", "fourth": "4"}


def _period_from_slug(slug: str) -> str | None:
    for pat in _QUARTER_SLUG_PATTERNS:
        m = pat.search(slug)
        if not m:
            continue
        q, year = m.group(1), m.group(2)
        q = _QUARTER_WORD_MAP.get(q, q)
        if q in ("1", "2", "3", "4"):
            return f"{year}-Q{q}"
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SDN은 render()로 연차보고서 목록을 순회한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _list_report_pages() -> list[str]:
    resp = requests.get(_ARCHIVE_URL, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    return sorted({urljoin(_ARCHIVE_URL, m) for m in _REPORT_LINK_RE.findall(resp.text)})


def _find_pdf_url(report_page_url: str) -> str | None:
    """공보 PDF 링크를 찾는다. 분기 공보는 아랍어 파일명뿐인 경우가 많지만(표 안 라벨은
    영문이라 그대로 파싱 가능) 모든 연도 페이지에 공통으로 걸려 있는 무관한 조직도 PDF
    ('...82%5D.pdf')만 제외하고, 그 외 첫 PDF를 쓴다."""
    resp = requests.get(report_page_url, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    for url in _PDF_LINK_RE.findall(resp.text):
        if "82%5D.pdf" in url:
            continue
        return url
    return None


def _extract_deposits(text: str) -> dict[tuple[str, int], float]:
    results: dict[tuple[str, int], float] = {}
    for m in _TITLE_RE.finditer(text):
        kind = m.group(1).lower()
        y1, y2 = int(m.group(2)), int(m.group(3))
        window = text[m.end(): m.end() + 3000]
        gt = _GRAND_TOTAL_RE.search(window) or _GRAND_TOTAL_FALLBACK_RE.search(window)
        if not gt:
            continue
        try:
            v1 = float(gt.group(1).replace(",", ""))
            v2 = float(gt.group(2).replace(",", ""))
        except ValueError:
            continue
        results[(kind, y1)] = v1
        results[(kind, y2)] = v2
    return results


def _render_annual(country_code: str) -> pd.DataFrame:
    try:
        report_pages = _list_report_pages()
    except Exception:
        logger.exception("[%s] 연차보고서 목록 조회 실패", country_code)
        return _empty()

    logger.info("[%s] 연차보고서 %d건 발견", country_code, len(report_pages))

    combined: dict[tuple[str, int], float] = {}
    for page_url in report_pages:
        try:
            pdf_url = _find_pdf_url(page_url)
            if not pdf_url:
                logger.warning("[%s] PDF 링크 없음: %s", country_code, page_url)
                continue
            resp = requests.get(pdf_url, headers=_HEADERS, timeout=120, verify=False)
            resp.raise_for_status()
            text = pdf_text(resp.content)
            found = _extract_deposits(text)
            if found:
                combined.update(found)  # 최신(연도 오름차순 순회) 보고서 값으로 덮어씀
                logger.info("[%s] %s -> %d개 항목", country_code, pdf_url.rsplit("/", 1)[-1][:50], len(found))
            else:
                logger.warning("[%s] 표를 못 찾음: %s", country_code, pdf_url.rsplit("/", 1)[-1][:50])
        except Exception:
            logger.warning("[%s] %s 처리 실패", country_code, page_url, exc_info=True)

    years = sorted({y for _, y in combined})
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for year in years:
        local = combined.get(("local", year))
        fx = combined.get(("foreign", year))
        if local is None or fx is None:
            continue
        td = local + fx
        if td <= 0:
            continue
        period = f"{year}-Annual"
        ratio = round((fx / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fx, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })
    return pd.DataFrame(rows) if rows else _empty()


def _last_number(line: str) -> float | None:
    nums = re.findall(r"[\d,]+\.?\d*", line)
    nums = [n for n in nums if re.search(r"\d", n)]
    if not nums:
        return None
    try:
        return float(nums[-1].replace(",", ""))
    except ValueError:
        return None


def _extract_money_supply_last_col(text: str) -> tuple[float, float, float] | None:
    """(fcd, local, demand) — 'Money Supply' 표의 가장 오른쪽(=이 공보 자신의 분기) 값."""
    if "Money Supply" not in text or "Foreign Currency Deposits" not in text:
        return None
    fcd = local = demand = None
    for line in text.splitlines():
        if "Foreign Currency Deposits" in line and fcd is None:
            fcd = _last_number(line)
        elif "Local Currency Deposits" in line and local is None:
            local = _last_number(line)
        elif "Demand Deposits" in line and demand is None:
            demand = _last_number(line)
    if fcd is None or local is None or demand is None:
        return None
    return fcd, local, demand


def _list_quarterly_pages() -> list[tuple[str, str]]:
    """[(period, page_url), ...]"""
    resp = requests.get(_QUARTERLY_LIST_URL, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    out = []
    for href in set(_QUARTER_LINK_RE.findall(resp.text)):
        slug = href.rsplit("/", 2)[-1] if href.endswith("/") else href.rsplit("/", 1)[-1]
        period = _period_from_slug(slug)
        if period:
            out.append((period, urljoin(_QUARTERLY_LIST_URL, href)))
    return sorted(set(out))


def _render_quarterly(country_code: str) -> pd.DataFrame:
    try:
        pages = _list_quarterly_pages()
    except Exception:
        logger.exception("[%s] 분기 공보 목록 조회 실패", country_code)
        return _empty()

    logger.info("[%s] 분기 공보 %d건 발견", country_code, len(pages))

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period, page_url in pages:
        try:
            pdf_url = _find_pdf_url(page_url)
            if not pdf_url:
                logger.warning("[%s] PDF 링크 없음: %s", country_code, page_url)
                continue
            resp = requests.get(pdf_url, headers=_HEADERS, timeout=120, verify=False)
            resp.raise_for_status()
            text = pdf_text(resp.content)
            found = _extract_money_supply_last_col(text)
            if not found:
                logger.warning("[%s] Money Supply 표를 못 찾음: %s (%s)", country_code, period, pdf_url.rsplit("/", 1)[-1][:50])
                continue
            fcd, local, demand = found
            td = local + demand + fcd
            if td <= 0:
                continue
            year = int(period[:4])
            ratio = round((fcd / td) * 100, 4)
            for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
                rows.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": indicator, "value": value, "updated_at": now,
                })
            logger.info("[%s] %s -> FCD=%.1f TD=%.1f", country_code, period, fcd, td)
        except Exception:
            logger.warning("[%s] %s 처리 실패", country_code, page_url, exc_info=True)

    return pd.DataFrame(rows) if rows else _empty()


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    annual = _render_annual(country_code)
    quarterly = _render_quarterly(country_code)

    frames = [df for df in (annual, quarterly) if not df.empty]
    if not frames:
        return _empty()

    out = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] %d rows total (annual=%d, quarterly=%d)",
        country_code, len(out), len(annual), len(quarterly),
    )
    return out
