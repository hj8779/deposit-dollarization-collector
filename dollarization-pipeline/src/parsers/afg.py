"""Afghanistan: Da Afghanistan Bank(DAB) Annual/Quarterly Economic Bulletin PDF들,
'Table 2.1' 계열 표('Monetary Aggregates' / "...Analytical Balance Sheet and Monetary
Aggregate...")의 'In Foreign currency' 행(Other Deposits/Quasi Money의 외화 구성분).

수집 절차:
1. 랜딩 페이지(Annual/Quarterly Bulletins 목록) 진입, 페이지 내 a[href$=".pdf"] 전부 수집
   (DAB 사이트는 별도 게시물 상세페이지 없이 목록 페이지에 PDF가 직접 링크되어 있음).
2. 각 PDF를 다운로드해 pdfplumber로 'In Foreign currency' 행을 정규식으로 추출.
   표는 항상 [기간1 금액, 기간2 금액, YoY%, YoY증감, 기간3(최신) 금액, YoY%, YoY증감]
   7개 숫자 토큰으로 구성되고, 마지막에서 3번째 토큰(기간3 금액)이 그 회보 발행 시점의
   최신 값이다.

TD(총예금) = 'Demand Deposits' 행 + 'Other Deposits (Quasi Money)' 행(같은 표, 같은 7토큰
구조). 'In Foreign currency'는 'Other Deposits (Quasi Money)'의 하위 구성분(In Afghani +
In Foreign currency = Other Deposits)이므로, Demand Deposits + Other Deposits 전체가
곧 광의통화(M2)에 포함되는 예금 총액이다(실측: 2020-12 Demand 252,219 + Other 40,373.93 =
292,592.93; Other 40,373.93 = In Afghani 9,191.67 + In Foreign currency 31,182.26 일치).
3. 기간 라벨은 PDF 내부 텍스트(문서마다 아프간력/그레고리력이 뒤섞여 있고 표 헤더 자체가
   pdfplumber에서 글자 단위로 뒤섞여 나옴)가 아니라 훨씬 안정적인 **링크 텍스트(파일명)**에서
   분기/연도를 추출한다. 파일명의 연도가 1500 미만이면 아프간 태양력(SH)으로 보고 +621해
   그레고리력으로 정규화한다(예: FY1399 -> 2020).
"""

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import unquote, urljoin

import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

from src.collectors.base import INDICATOR, INDICATOR_TD, download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

LANDING_URLS = [
    "https://dab.gov.af/Annual-Economic-and-Statistical-Bulletins",
    "https://dab.gov.af/quarterly-economic-and-statistical-bulletins",
]

_NUM_TOKENS = r"([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+(-?[\d.]+%)\s+(-?[\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+(-?[\d.]+%)\s+(-?[\d,]+\.?\d*)"
_ROW_RE = re.compile(r"In Foreign currency\s+" + _NUM_TOKENS)
_DEMAND_ROW_RE = re.compile(r"Demand Deposits\s+" + _NUM_TOKENS)
_OTHER_DEPOSITS_ROW_RE = re.compile(r"Other Deposits \(Quasi Money\)\s+" + _NUM_TOKENS)

_QUARTER_PATTERNS = [
    re.compile(r"(\d)(?:st|nd|rd|th)\s*Quarter\s*of\s*FY\s*(\d{4})", re.I),
    re.compile(r"Q(\d)\s*[-–,_]\s*(\d{4})", re.I),
]
_ANNUAL_PATTERN = re.compile(r"Annual.*?(\d{4})", re.I)


def _normalize_year(year: int) -> int:
    """파일명의 연도가 아프간 태양력(SH)이면 그레고리력으로 환산한다."""
    return year + 621 if year < 1500 else year


def _period_from_label(label: str) -> str | None:
    for pattern in _QUARTER_PATTERNS:
        m = pattern.search(label)
        if m:
            quarter, year = int(m.group(1)), _normalize_year(int(m.group(2)))
            return f"{year}-Q{quarter}"
    m = _ANNUAL_PATTERN.search(label)
    if m:
        return f"{_normalize_year(int(m.group(1)))}-Annual"
    return None


def _collect_pdf_links() -> list[tuple[str, str]]:
    """(period, absolute_pdf_url) 목록. 기간 라벨을 못 만들면 건너뛴다."""
    links: dict[str, str] = {}
    for landing_url in LANDING_URLS:
        try:
            html = download(landing_url).decode("utf-8", errors="ignore")
        except Exception:
            logger.warning("[AFG] 랜딩 페이지 접근 실패: %s", landing_url)
            continue

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.lower().endswith(".pdf"):
                continue
            filename = unquote(href.split("/")[-1])
            period = _period_from_label(filename)
            if period is None:
                continue
            # 같은 기간에 파일이 여러 개면(재게시 등) 나중에 발견된 것으로 덮어써
            # 랜딩 페이지 하단(대개 더 최신 재게시본)의 값을 우선한다.
            links[period] = urljoin(landing_url, href)

    return list(links.items())


def _extract_fcd_td(content: bytes) -> tuple[str | None, str | None]:
    """PDF에서 'In Foreign currency'(FCD)와 'Demand Deposits'+'Other Deposits (Quasi Money)'
    (TD) 행의 최신(가장 오른쪽) 금액을 문자열로 반환."""
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            fcd_m = _ROW_RE.search(text)
            if not fcd_m:
                continue
            fcd = fcd_m.group(5)  # [amt1, amt2, pct, diff, amt3(최신), pct, diff]

            demand_m = _DEMAND_ROW_RE.search(text)
            other_m = _OTHER_DEPOSITS_ROW_RE.search(text)
            td = None
            if demand_m and other_m:
                try:
                    td = str(
                        float(demand_m.group(5).replace(",", ""))
                        + float(other_m.group(5).replace(",", ""))
                    )
                except ValueError:
                    td = None
            return fcd, td
    return None, None


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    pdf_links = _collect_pdf_links()
    logger.info("[%s] 라벨링 가능한 PDF %d개 발견", country_code, len(pdf_links))

    rows = []
    for period, pdf_url in pdf_links:
        try:
            content = download(pdf_url)
        except Exception:
            logger.warning("[%s] %s(%s) 다운로드 실패, 스킵", country_code, period, pdf_url)
            continue

        try:
            amount, td_amount = _extract_fcd_td(content)
        except Exception:
            logger.warning("[%s] %s PDF 파싱 실패, 스킵", country_code, period)
            continue

        if amount is None:
            logger.info("[%s] %s PDF에 'In Foreign currency' 행 없음, 스킵", country_code, period)
            continue

        year = int(period.split("-")[0])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR,
            "value": float(amount.replace(",", "")),
            "updated_at": now,
        })
        if td_amount is not None:
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": INDICATOR_TD,
                "value": round(float(td_amount), 2),
                "updated_at": now,
            })

    if not rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last").sort_values(["period", "indicator"]).reset_index(drop=True)
    return df
