"""Bhutan: Royal Monetary Authority(RMA) 'Financial Sector Performance Review'
분기 보고서 PDF 시리즈(publication/41/ 페이지, media/Publication/Financial%20Sector%20
Performance%20Review/{Month}%20{Year}.pdf, 월=Mar/Jun/Sep/Dec, 2012~2022).

이전 조사 때는 RMA 사이트 자체가 SSL/연결 오류로 접속 불가였으나(사이트 리뉴얼 중이었던
것으로 추정), 지금은 정상 접속되고 목록 페이지에 예측 가능한 URL 패턴으로 분기 보고서가
쭉 나열되어 있다. 다만 여전히 인증서 체인이 불완전한지 기본 검증(verify=True)로는 SSL
실패가 나서 requests 호출 시 verify=False가 필요하다(다른 여러 국가 파서와 동일한 패턴).

각 보고서의 'ANNEXURE I a) Deposit by Customer'(또는 구형: 'Table 5. Deposits by
Customer') 표에 'Foreign Currency'(=FCD, 소매예금 중 외화 표시분) 행과 'Total'(=TD, 전체
예금) 행이 있고, 같은 표에 당해 분기(예: Sep-22)와 전년 동분기(Sep-21) 두 기간 값이 함께
나온다(1개 PDF당 2개 분기 확보 가능).

주의(실측으로 발견한 함정들):
  - 단위가 시기별로 다르다: 최근(~2017년경부터) 표는 'figures in million Nu.'로 백만
    단위, 오래된 표(예: 2015년)는 'Table 5. Deposits by Customer(Nu. in Billion)'로
    십억 단위다. 표 제목/부제 텍스트에서 'billion' 포함 여부로 단위를 판별해 십억이면
    1000을 곱해 백만 단위로 통일한다.
  - 두 기간 값의 좌우 순서가 보고서마다 다르다(예: Sep-22 보고서는 [당분기, 전년동분기]
    순, Dec-18 보고서는 [전년동분기, 당분기] 순으로 뒤바뀌어 있음). 컬럼 인덱스를 고정해서
    쓰면 안 되고, 헤더 줄의 'Mon-YY' 토큰 순서를 그대로 따라가야 한다.
  - 'Total' 행 위쪽에 'Total Deposits % Holding'처럼 실제 데이터가 아닌 컬럼그룹
    헤더 문구가 먼저 나온다(같은 단어 'Total'로 시작). 데이터 행은 'Total' 뒤에 바로
    숫자가 오는 줄만 인정한다(정규식 anchor).
  - 'Total' 행 자체가 소스에서 가끔 틀린다(실측: 2022년 3월호와 6월호 둘 다 Total이
    188,845.48로 동일 - Foreign Currency/Corporate deposits 등 다른 행은 분기마다 정상
    변화. Corporate deposits+Retail deposits 합으로 검산하면 Mar-22는 일치(188,845.49
    ≈188,845.48)하지만 Jun-22는 193,198.94로 전혀 다름 -> Jun-22의 'Total' 라벨 값이
    스테일 카피 오류로 판단). 그래서 TD는 'Total' 라벨을 그대로 믿지 않고 'Corporate
    deposits'+'Retail deposits' 두 행의 합으로 직접 계산한다(모든 정상 케이스에서
    'Total' 라벨과 정확히 일치함을 확인했고, 이 방식이 스테일 카피 오류에 강건하다).

2022년 9월호 이후로는 이 분기 보고서 시리즈 자체가 발간되지 않는 것으로 보인다(후속 발간물인
'Core Financial Indicators'/'Annual Supervision Report'는 확인 결과 예금 통화별 분해 표가
없음 - CAR/NPL 등 건전성 지표 위주). 그래서 2022-Q3 이후 최신 데이터는 이 파서로 자동
수집이 안 되고, 대시보드의 수동 입력 테이블로 채워야 한다(MANUAL_UPDATE_COUNTRIES).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_BASE_URL = (
    "https://www.rma.org.bt/media/Publication/"
    "Financial%20Sector%20Performance%20Review/{month}%20{year}.pdf"
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

# 분기 말 월 이름(URL에 그대로 쓰임) -> 분기 번호
_QUARTER_MONTHS = {"March": 1, "June": 2, "September": 3, "December": 4}
_FIRST_YEAR = 2012
_LAST_YEAR = 2022  # 2022-09(Q3)를 마지막으로 이 보고서 시리즈 자체가 끊김

# 본문 서술 중 'customer deposits...' 같은 문장을 표 제목으로 오인하지 않도록, 줄 맨 앞이
# 'a)'나 'Table N.' 형태인 실제 표 제목만 매칭한다(실측: 'Analysis on the deposit data
# reveals that customer deposits...' 같은 서술문에 낚였던 적이 있음).
_TITLE_RE = re.compile(r"^(?:[a-z]\)|table\s*\d+\.?)\s*deposits?\s+by\s+customer", re.I | re.M)
_FOREIGN_CURRENCY_ROW_RE = re.compile(r"^Foreign Currency\s+(?P<rest>[\d,.\s%()-]+)$", re.I)
_CORPORATE_ROW_RE = re.compile(r"^Corporate deposits\s+(?P<rest>[\d,.][\d,.\s%()-]*)$", re.I)
_RETAIL_ROW_RE = re.compile(r"^Retail deposits\s+(?P<rest>[\d,.][\d,.\s%()-]*)$", re.I)
_PERIOD_TOKEN_RE = re.compile(r"\b([A-Za-z]{3})-(\d{2})\b")
_NUM_RE = re.compile(r"-?[\d,]+\.\d+")

_MONTHS_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_TO_QUARTER = {3: 1, 6: 2, 9: 3, 12: 4}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BTN은 render()를 통해 처리한다 (여러 분기 PDF를 순회해야 함)")


def _candidate_urls() -> list[str]:
    urls = []
    for year in range(_FIRST_YEAR, _LAST_YEAR + 1):
        for month in _QUARTER_MONTHS:
            if year == _LAST_YEAR and _QUARTER_MONTHS[month] > 3:
                continue  # 2022-Q3(September)가 마지막 발간호
            urls.append(_BASE_URL.format(month=month, year=year))
    return urls


def _parse_pdf(content: bytes, country_code: str) -> list[dict]:
    import pdfplumber

    now = datetime.now(timezone.utc).isoformat()

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not _TITLE_RE.search(text):
                continue

            lines = text.splitlines()
            title_idx = next((i for i, ln in enumerate(lines) if _TITLE_RE.search(ln)), None)
            if title_idx is None:
                continue

            # 표 제목 근방에 'billion'이 있으면 십억 단위(-> 백만으로 환산), 없으면 기본 백만.
            window = "\n".join(lines[max(0, title_idx - 2):title_idx + 20])
            scale = 1000.0 if re.search(r"\bbillion\b", window, re.I) else 1.0

            # 표 헤더의 두 기간(Mon-YY) 토큰을 컬럼 순서 그대로 찾는다.
            periods: list[tuple[int, int]] | None = None
            for ln in lines[title_idx:title_idx + 10]:
                tokens = _PERIOD_TOKEN_RE.findall(ln)
                if len(tokens) >= 2:
                    parsed = []
                    for mon_str, yy_str in tokens[:2]:
                        month = _MONTHS_ABBR.get(mon_str.lower())
                        if month is None or month not in _MONTH_TO_QUARTER:
                            parsed = []
                            break
                        parsed.append((2000 + int(yy_str), month))
                    if len(parsed) == 2:
                        periods = parsed
                        break
            if periods is None:
                logger.warning("[%s] 기간 헤더(Mon-YY)를 찾지 못함, 스킵", country_code)
                continue

            fcd_values: list[float] | None = None
            corporate_values: list[float] | None = None
            retail_values: list[float] | None = None
            for ln in lines[title_idx:title_idx + 25]:
                stripped = ln.strip()
                if fcd_values is None:
                    m = _FOREIGN_CURRENCY_ROW_RE.match(stripped)
                    if m:
                        nums = [float(t.replace(",", "")) for t in _NUM_RE.findall(m.group("rest"))]
                        if len(nums) >= 2:
                            fcd_values = nums[:2]
                if corporate_values is None:
                    m = _CORPORATE_ROW_RE.match(stripped)
                    if m:
                        nums = [float(t.replace(",", "")) for t in _NUM_RE.findall(m.group("rest"))]
                        if len(nums) >= 2:
                            corporate_values = nums[:2]
                if retail_values is None:
                    m = _RETAIL_ROW_RE.match(stripped)
                    if m:
                        nums = [float(t.replace(",", "")) for t in _NUM_RE.findall(m.group("rest"))]
                        if len(nums) >= 2:
                            retail_values = nums[:2]
                if fcd_values is not None and corporate_values is not None and retail_values is not None:
                    break

            if fcd_values is None or corporate_values is None or retail_values is None:
                logger.warning(
                    "[%s] Foreign Currency/Corporate deposits/Retail deposits 행을 찾지 못함, 스킵",
                    country_code,
                )
                continue
            total_values = [corporate_values[i] + retail_values[i] for i in range(2)]

            rows = []
            for i, (year, month) in enumerate(periods):
                quarter = _MONTH_TO_QUARTER[month]
                period = f"{year}-Q{quarter}"
                rows.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": INDICATOR, "value": round(fcd_values[i] * scale, 2), "updated_at": now,
                })
                rows.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": INDICATOR_TD, "value": round(total_values[i] * scale, 2), "updated_at": now,
                })
            return rows

    return []


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    urls = _candidate_urls()
    logger.info("[%s] Financial Sector Performance Review 후보 %d개(2012~2022-Q3)", country_code, len(urls))

    all_data: dict[tuple[str, str], float] = {}  # (period, indicator) -> value, 최신 발간호 값 우선
    found = 0
    for url in urls:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=60, verify=False)
        except Exception:
            continue
        if response.status_code != 200 or response.content[:4] != b"%PDF":
            continue  # 목록에 없는 연도/분기 조합(404 등), 조용히 스킵

        rows = _parse_pdf(response.content, country_code)
        if not rows:
            continue
        found += 1
        for row in rows:
            all_data[(row["period"], row["indicator"])] = row["value"]

    logger.info("[%s] 실제 발간된 PDF %d개 파싱, %d개 (period,indicator) 확보", country_code, found, len(all_data))

    if not all_data:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": indicator,
            "value": value,
            "updated_at": now,
        }
        for (period, indicator), value in sorted(all_data.items())
    ]
    return pd.DataFrame(rows)
