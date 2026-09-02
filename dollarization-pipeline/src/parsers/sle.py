"""Sierra Leone: Bank of Sierra Leone(BSL) Monetary Policy Report(분기) PDF, 'Monetary Survey' 부록 표.

bsl.gov.sl은 저장돼 있던 www.bsl.gov.sl(DNS 오류) 대신 www. 없는 https://bsl.gov.sl 로
접속해야 한다(200 OK 확인됨). 요청 시 기본 requests User-Agent로는 커넥션이 리셋되지만
(브라우저처럼 보이는 UA를 요구하는 방화벽/CDN 설정으로 추정) src.collectors.base.download()가
쓰는 브라우저 UA 헤더면 정상 응답한다.

BSL은 'Statistics Data Warehouse'(app.datawarehousepro.com)와 Open Data for Africa
포털(cb-sierraleone.opendataforafrica.org)을 통계 허브로 안내하지만, 후자는 Cloudflare
봇 챌린지("Just a moment...")로 막혀 있어 requests는 물론 Playwright 헤드리스 브라우저로도
통과하지 못했다(2026-08 확인) - 이 경로는 자동화 불가.

대신 BSL이 직접 호스팅하는 분기별 Monetary Policy Report(MPR) PDF의 부록에 있는
'Table 4: Monetary Survey'(구 명칭 'Table 3/4: Money Supply and Components')에
거주자 외화예금 항목이 명시적으로 존재한다:

    Demand deposit                          <- 요구불예금
    Quasi money                             <- 준화폐성예금 합계
      o.w. Foreign currency deposit         <- 그 중 외화예금 (FCD)
      Time and saving deposit               <- 정기/저축성예금(자국통화)

    FCD = "o.w. Foreign currency deposit" 행
    TD  = "Demand deposit" + "Quasi money" 행 (= 은행에 대한 총 예금성 부채, 정부/은행간 제외)

단위는 표마다 'Billions of Leones'(2022년 8월 리디노미네이션 이전, 구 SLL) 또는
'Millions of Leones'(리디노미네이션 이후, 신 SLE)로 표기되지만 두 단위는 수치적으로
동일하다(신 1 SLE = 구 1,000 SLL 이므로 구 SLL 십억 단위 = 신 SLE 백만 단위) - 실제로
2022Q1 Broad Money(M2)=15,163.12가 리디노미네이션 전후 보고서 모두에서 동일하게 나타나는
것으로 교차 확인했다. 따라서 별도 환산 없이 원자료 값을 그대로 사용한다.

모든 MPR이 이 부록 표를 포함하지는 않는다(약 절반은 서술형 %변화만 있고 절대값 표가 없음).
render()는 Publications.html에서 'Monetary Policy Report' 링크를 모두 찾아 각 PDF를
내려받고, 표가 있는 PDF에서만 데이터를 뽑는다.

MPR은 2021년부터만 있어(확인 시점 최고 16분기), 2026-08-19 사용자 제보로 'Annual Report
and Statement of Accounts'(2013~2024년치가 Publications.html에 정적 <a href> 링크로
그대로 있음 - hover 메뉴처럼 보여도 실제로는 JS 없이도 바로 파싱 가능) PDF도 함께 수집하도록
확장했다. 이 연차보고서들도 부록에 'Table N: Monetary Survey (Million/Billion Leones)'
표를 싣는데, 헤더가 분기번호(2025Q1)가 아니라 월-연도('Dec-12 Mar-13 Jun-13 ...') 형식이고
행 라벨도 'o.w. Foreign currency deposit'가 아니라 그냥 'Foreign Currency Deposits'다.
Dec/Mar/Jun/Sep 월말 스냅샷은 각각 Q4/Q1/Q2/Q3에 대응하므로 동일한 'YYYY-QN' 포맷으로
변환해 MPR 데이터와 병합한다. 모든 연차보고서가 이 표를 텍스트로 담고 있진 않다(예: 2017년판은
스캔 이미지라 텍스트 추출 불가 - 자동 스킵).
FCD = 'Foreign Currency Deposits' 행 (o.w. 접두어 없음). TD = 'Demand Deposits' + 'Quasi Money'
(MPR 쪽과 동일 정의).

표 헤더 행(예: 'Millions of Leones 2025Q1 2025Q4 2026Q1 2025Q4 2026Q1 2025Q4 2026Q1')은
분기 라벨을 실제 레벨 컬럼 수만큼 나열한 뒤, 분기증감/전년동기증감 컬럼에서 재사용(뒤쪽
컬럼일수록 라벨이 반복)한다. 레벨 컬럼 개수는 라벨이 처음 반복되기 시작하는 지점까지로
판별한다(예: 3개 레벨 컬럼 뒤 2개 분기증감 + 2개 전년동기증감 = 총 7개 토큰).

일부 최신 보고서(예: 2025년 12월호)는 pdfplumber 텍스트 추출 순서가 뒤바뀌어 레벨 값이
담긴 숫자만 있는 줄이 라벨 줄보다 먼저 나온다('8,527.04 9,564.94 10,116.74' 다음 줄에
'Reserve money (0.001) 5.77 19.87 18.64'). 이 경우 라벨 줄 자체의 숫자 개수가 레벨
컬럼 수보다 적으면(증감 컬럼 수만 있으면) 바로 앞 줄에서 레벨 값을 가져온다.
"""

import re
from datetime import datetime, timezone

import pandas as pd
import pdfplumber
from io import BytesIO

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

PUBLICATIONS_URL = "https://bsl.gov.sl/Publications.html"
BASE_URL = "https://bsl.gov.sl/"

_MPR_LINK_RE = re.compile(
    r'href="\.?/?([^"?#]*monetary\s*policy\s*report[^"?#]*\.pdf)"', re.I
)
_ANNUAL_LINK_RE = re.compile(
    r'href="\.?/?([^"?#]*annual\s*report[^"?#]*\.pdf)"', re.I
)

_PERIOD_TOKEN_RE = re.compile(r"\b(20\d{2})\s*Q\s*([1-4])\b", re.I)
_MONTH_YEAR_TOKEN_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{2})\b", re.I
)
_MONTH_TO_QUARTER = {
    "dec": 4, "mar": 1, "jun": 2, "sep": 3,
    # non-quarter-end months occasionally appear too; map to nearest quarter-end
    "jan": 4, "feb": 1, "apr": 1, "may": 2, "jul": 2, "aug": 3, "oct": 3, "nov": 4,
}
_NUM_RE = re.compile(r"\(?-?\d[\d,]*\.\d+\)?|\(?-?\d[\d,]*\)?")

_FCD_LABEL_RE = re.compile(r"^o\.?w\.?\s*foreign\s+currency\s+deposit", re.I)
_FCD_LABEL_PLAIN_RE = re.compile(r"^foreign\s+currency\s+deposit", re.I)
_DEMAND_LABEL_RE = re.compile(r"^demand\s+deposit", re.I)
_QUASI_LABEL_RE = re.compile(r"^quasi[\s-]*money", re.I)
_TABLE_MARKER_RE = re.compile(r"foreign currency deposit", re.I)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SLE는 render()를 통해 처리한다 (여러 MPR PDF를 순회해야 함)")


def _clean_number(tok: str) -> float:
    neg = tok.startswith("(") and tok.endswith(")")
    tok = tok.strip("()").replace(",", "")
    val = float(tok)
    return -val if neg else val


def _period_columns(header_line: str) -> list[str]:
    """헤더 줄에서 분기 라벨 토큰들을 뽑아 '레벨 컬럼' 구간만 반환한다(첫 반복 직전까지).

    'YYYYQN' 형식(MPR)과 'Mon-YY' 월말 스냅샷 형식(Annual Report — Dec/Mar/Jun/Sep
    분기말이 대부분) 둘 다 지원하며, 후자는 대응하는 분기로 변환해 동일한 'YYYYQN'
    라벨 네임스페이스로 합친다."""
    tokens = [f"{y}Q{q}" for y, q in _PERIOD_TOKEN_RE.findall(header_line)]
    if not tokens:
        for mon, yy in _MONTH_YEAR_TOKEN_RE.findall(header_line):
            q = _MONTH_TO_QUARTER.get(mon.lower())
            if q is None:
                continue
            year = 2000 + int(yy)
            tokens.append(f"{year}Q{q}")
    seen: list[str] = []
    for tok in tokens:
        if tok in seen:
            break
        seen.append(tok)
    return seen


_PURE_NUMERIC_LINE_RE = re.compile(r"^[\d,.\s()-]+$")


def _row_numbers(lines: list[str], idx: int, n: int) -> list[float] | None:
    """lines[idx]가 목표 라벨을 담은 줄일 때, 레벨 값 n개를 찾는다.

    일부 보고서는 pdfplumber가 레벨 값 줄과 라벨(+증감값) 줄의 순서를 뒤바꿔 추출한다
    (레벨 값만 있는 숫자 전용 줄이 라벨 줄보다 먼저 나옴). 이 경우 라벨 줄 자체의 숫자는
    증감값(레벨이 아님)이므로, 숫자만으로 구성된 바로 앞 줄을 우선 확인한다.
    """
    if idx > 0:
        prev = lines[idx - 1].strip()
        if _PURE_NUMERIC_LINE_RE.match(prev):
            prev_nums = _NUM_RE.findall(prev)
            if len(prev_nums) == n:
                return [_clean_number(t) for t in prev_nums]

    this_nums = _NUM_RE.findall(lines[idx])
    if len(this_nums) >= n:
        return [_clean_number(t) for t in this_nums[:n]]

    return None


def _extract_table(text: str) -> dict[str, tuple[float, float]]:
    """페이지 텍스트에서 period -> (FCD, TD) 매핑을 뽑는다."""
    lines = text.splitlines()

    header_idx = None
    periods: list[str] = []
    for i, line in enumerate(lines):
        cols = _period_columns(line)
        if len(cols) >= 2:
            header_idx = i
            periods = cols
            break
    if header_idx is None:
        return {}

    n = len(periods)
    fcd_vals = demand_vals = quasi_vals = None

    for i in range(header_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if (_FCD_LABEL_RE.match(stripped) or _FCD_LABEL_PLAIN_RE.match(stripped)) and fcd_vals is None:
            fcd_vals = _row_numbers(lines, i, n)
        elif _DEMAND_LABEL_RE.match(stripped) and demand_vals is None:
            demand_vals = _row_numbers(lines, i, n)
        elif _QUASI_LABEL_RE.match(stripped) and quasi_vals is None:
            quasi_vals = _row_numbers(lines, i, n)
        if fcd_vals is not None and demand_vals is not None and quasi_vals is not None:
            break

    if fcd_vals is None or demand_vals is None or quasi_vals is None:
        return {}

    result = {}
    for period, fcd, demand, quasi in zip(periods, fcd_vals, demand_vals, quasi_vals):
        td = round(demand + quasi, 2)
        result[period] = (round(fcd, 2), td)
    return result


def _parse_mpr_pdf(content: bytes) -> dict[str, tuple[float, float]]:
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if _TABLE_MARKER_RE.search(text):
                    data = _extract_table(text)
                    if data:
                        return data
    except Exception as e:
        logger.warning("[SLE] PDF 파싱 실패: %s", e)
    return {}


def _collect_mpr_links() -> list[str]:
    try:
        html = download(PUBLICATIONS_URL).decode("utf-8", errors="ignore")
    except Exception as e:
        logger.warning("[SLE] Publications.html 접근 실패: %s", e)
        return []

    links = set()
    for path in _MPR_LINK_RE.findall(html):
        if "statement" in path.lower():
            continue
        links.add(BASE_URL + path)
    return sorted(links)


def _collect_annual_links() -> list[str]:
    """'Annual Report and Statement of Accounts' PDFs — Publications.html serves
    these as plain static <a href> links (no JS needed despite the hover-menu
    look), so a normal GET + regex is enough."""
    try:
        html = download(PUBLICATIONS_URL).decode("utf-8", errors="ignore")
    except Exception as e:
        logger.warning("[SLE] Publications.html 접근 실패: %s", e)
        return []

    from urllib.parse import quote

    links = set()
    for path in _ANNUAL_LINK_RE.findall(html):
        links.add(BASE_URL + quote(path))
    return sorted(links)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    links = _collect_mpr_links()
    logger.info("[%s] Monetary Policy Report PDF %d개 발견", country_code, len(links))

    annual_links = _collect_annual_links()
    logger.info("[%s] Annual Report PDF %d개 발견", country_code, len(annual_links))

    all_data: dict[str, tuple[float, float]] = {}
    # Annual reports first (older, spans further back) so MPR's more precise
    # recent-quarter figures win on any overlap.
    for url in annual_links:
        try:
            content = download(url, referer=PUBLICATIONS_URL)
        except Exception as e:
            logger.warning("[%s] Annual Report 다운로드 실패, 스킵: %s (%s)", country_code, url, e)
            continue
        data = _parse_mpr_pdf(content)
        if data:
            logger.info("[%s] %s -> %s", country_code, url.rsplit("/", 1)[-1][:50], sorted(data))
        for period, values in data.items():
            all_data[period] = values

    for url in links:
        try:
            content = download(url, referer=PUBLICATIONS_URL)
        except Exception as e:
            logger.warning("[%s] PDF 다운로드 실패, 스킵: %s (%s)", country_code, url, e)
            continue

        data = _parse_mpr_pdf(content)
        for period, values in data.items():
            all_data[period] = values

    if not all_data:
        logger.warning("[%s] Monetary Survey 표를 찾을 수 없음", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for period in sorted(all_data.keys()):
        fcd, td = all_data[period]
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 2) if td else None
        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period.replace("Q", "-Q"),
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    return pd.DataFrame(rows)
