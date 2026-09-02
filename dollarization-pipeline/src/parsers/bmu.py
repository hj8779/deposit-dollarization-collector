"""Bermuda: BMA(Bermuda Monetary Authority) 'Annual Report' PDF 시리즈(2000~현재, 연 1회).
목록 페이지(documents-centre/document-annual-reports/general-all-sectors)는 페이지네이션이
서버사이드 fetch가 아니라 클라이언트 JS(HTML을 그대로 스왑)라 requests로 두 번째 페이지를
못 받는다(fetchdata?page=2를 직접 GET하면 404) - Playwright로 실제 '2' 페이지네이션 링크를
클릭해야 두 번째 목록(2000~2006년치)이 로드된다.

각 연차보고서 안의 'Combined Balance Sheet of Bermuda Banks and Deposit Companies
(Consolidated)' 표에서 부채(Liabilities) 섹션의 'Sub(-)Total (-) Deposits' 행 -> Total/BD$/Other
세 컬럼 중 Other(=BD$ 외 통화, 즉 외화)가 FCD.

한 표는 분기 3개씩 묶어서 나오고(예: Q4-2025/Q3-2025/Q2-2025), 보고서 안에 이 표가
1~2번 등장한다(최근 보고서는 PDF 페이지 2장에 나눠 6개 분기, 2000년대 초 보고서는
PDF 페이지 1장에 두 블록으로 나눠 같은 6개 분기). 분기 표기 형식도 연도별로 다르다:
    'Q4-2025' (최근), '2010-Q4' (2010년대), '1998 - Q4' (2000년 보고서, 공백 포함)
그래서 페이지 텍스트에서 분기 헤더 줄을 정규식으로 찾아 블록을 나누고, 각 블록 안에서
'Sub Total Deposits'류 행(연도별로 'Sub - Total Deposits' / 'sub total - Deposits' /
'Subtotal — Deposits' 등 대소문자/공백/대시 표기가 제각각)을 찾아 9개 숫자(3분기 x
Total/BD$/Other)를 그 블록의 분기 3개에 순서대로 매핑한다.

여러 보고서에 걸쳐 겹치는 분기가 나오면(예: 2025년 보고서의 Q3-2024도, 2024년 보고서의
Q3-2024도 있음) 더 최근에 발간된 보고서 쪽 수치를 우선한다(연차보고서가 나올 때마다 직전
분기 수치가 소폭 수정(restated)되는 경우가 있어 최신판이 더 정확하다고 보고 채택).

2005년 보고서 등 일부 파일은 제목/헤더처럼 굵게(bold) 렌더링된 줄만 글자가 전부 두 번씩
찍혀 추출된다('CCoommbbiinneedd BBaallaannccee...') - 폰트가 볼드체를 굵게 흉내내려고 획을 살짝
겹쳐 그린 걸 pdfplumber가 글자 두 개로 잡아내는 것으로 보인다. 반면 일반 굵기인 데이터 행은
멀쩡하므로 전체를 일괄 반정규화하면 '16,200' 같은 숫자가 '16,20'으로 뭉개진다. 그래서 줄
단위로 '공백 제거 후 문자열을 반으로 나눴을 때 앞뒤가 완전히 같은지'로 이중찍힘 여부를
판별해(_maybe_undouble) 해당하는 줄에만 문자 중복 제거 정규식을 적용한다.

컬럼 구성도 연도에 따라 Total/BD$/Other 3열과 Total/BD$/US$/Other 4열이 섞여 있다(4열
형식은 Other가 'USD를 제외한' 기타통화만 가리켜 3열 형식과 의미가 다름). 컬럼 이름을
파싱하는 대신 FCD = Total - BD$ 로 계산하면 두 형식 모두에서 그대로 성립해 열 개수를
신경 쓸 필요가 없다.

알려진 결측 구간(소스 자체 문제, 다른 보고서로도 못 메움):
    2003-Q1, 2003-Q2 : 2003년 보고서(PDF) 전체가 텍스트 레이어 없는 스캔 이미지라 추출 불가.
                        2003-Q3/Q4는 2004년 보고서에 재수록되어 있어 그걸로 채워짐.
    2020-Q1, 2020-Q2 : '50th Anniversary' 특별판(2020년 발간)에는 통계 부록 자체가 없음.
                        2020-Q3/Q4는 2021년 보고서에 재수록되어 있어 그걸로 채워짐.
"""

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

LIST_URL = "https://www.bma.bm/documents-centre/document-annual-reports/general-all-sectors"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_TITLE_RE = re.compile(r"combined balance sheet of bermuda banks and deposit companies", re.I)
_SUBTOTAL_START_RE = re.compile(r"^sub\s*-?\s*total\b", re.I)
_SUBTOTAL_DEPOSITS_RE = re.compile(r"sub\s*-?\s*total\s*[-–—]?\s*deposits", re.I)
_NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")
_REPORT_YEAR_RE = re.compile(r"(19|20)\d{2}")

# 분기 헤더 토큰: 'Q4-2025' / 'Q4 2018'(대시 없음) / 'Q4-21'(두자리 연도) / '2010-Q4' /
# '1998 - Q4' / '2001 Year-end'(=Q4, 2001~2003년 보고서)
_QTR_TOKEN_RE = re.compile(
    r"Q(?P<q1>[1-4])\s*-?\s*(?P<y1>\d{2,4})\b"
    r"|(?P<y2>\d{4})\s*-\s*Q(?P<q2>[1-4])"
    r"|(?P<y3>\d{4})\s+Year[- ]end",
    re.I,
)


_DOUBLED_CHAR_RE = re.compile(r"(.)\1")


def _maybe_undouble(line: str) -> str:
    """볼드체 렌더링 때문에 글자가 전부 두 번씩 찍힌 줄이면 원래 글자로 복원한다."""
    stripped = line.replace(" ", "")
    if stripped and len(stripped) % 2 == 0 and stripped[0::2] == stripped[1::2]:
        return _DOUBLED_CHAR_RE.sub(r"\1", line)
    return line


def _full_year(token: str) -> int:
    year = int(token)
    return 2000 + year if year < 100 else year


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BMU는 render()를 통해 처리한다 (문서 목록이 JS 페이지네이션)")


def _collect_report_links() -> list[str]:
    from playwright.sync_api import sync_playwright

    links: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(LIST_URL, timeout=60000)
        page.wait_for_timeout(2000)
        links.extend(page.eval_on_selector_all("a[href$='.pdf']", "els => els.map(e => e.href)"))

        try:
            page.click("a.page-link[title='2']", timeout=5000)
            page.wait_for_timeout(2000)
            links.extend(page.eval_on_selector_all("a[href$='.pdf']", "els => els.map(e => e.href)"))
        except Exception:
            logger.warning("BMU 목록 2페이지 클릭 실패 (1페이지 결과만 사용)")

        browser.close()

    urls = {url for url in links if "cdn.bma.bm" in url}

    def _report_year(url: str) -> int:
        # 파일명 맨 앞 업로드 타임스탬프(YYYY-MM-DD-HH-MM-SS-)는 실제 보고서 연도와
        # 무관(2018-12-28에 2000~2017년치가 일괄 업로드됨)하므로 먼저 잘라내고,
        # 남은 설명 부분에서 연도를 찾는다. 못 찾으면(예: 'BMA 50th Anniversary'
        # 보고서처럼 파일명에 연도가 없는 경우) 업로드 타임스탬프 연도로 대체한다.
        basename = url.rsplit("/", 1)[-1]
        stripped = re.sub(r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-", "", basename)
        years = [int(m.group()) for m in _REPORT_YEAR_RE.finditer(stripped)]
        if years:
            return max(years)
        prefix_years = [int(m.group()) for m in _REPORT_YEAR_RE.finditer(basename)]
        return max(prefix_years) if prefix_years else 0

    return sorted(urls, key=_report_year)


def _quarter_tokens(line: str) -> list[str]:
    """줄에서 'YYYY-QN' 형식 분기 라벨을 좌->우 순서 그대로 뽑는다."""
    tokens = []
    for m in _QTR_TOKEN_RE.finditer(line):
        if m.group("y1"):
            tokens.append(f"{_full_year(m.group('y1'))}-Q{m.group('q1')}")
        elif m.group("y2"):
            tokens.append(f"{m.group('y2')}-Q{m.group('q2')}")
        else:
            tokens.append(f"{m.group('y3')}-Q4")
    return tokens


def _normalize_text(text: str) -> str:
    return "\n".join(_maybe_undouble(line) for line in text.splitlines())


def _parse_page(text: str, country_code: str, now: str) -> list[dict]:
    lines = _normalize_text(text).splitlines()

    # 1) 분기 헤더가 있는 줄(3개 묶음)을 블록 시작점으로 삼는다.
    blocks: list[tuple[list[str], int]] = []  # (quarters, start_line_idx)
    for i, line in enumerate(lines):
        tokens = _quarter_tokens(line)
        if len(tokens) >= 3:
            blocks.append((tokens[:3], i))

    if not blocks:
        return []

    rows = []
    for b, (quarters, start) in enumerate(blocks):
        end = blocks[b + 1][1] if b + 1 < len(blocks) else len(lines)
        for i in range(start, end):
            line = lines[i].strip()
            if not _SUBTOTAL_START_RE.match(line):
                continue

            # 연도별로 컬럼 라벨이 'Deposits'로 끝나는데, 지면 폭이 좁은 몇몇 발간호(2016~2017 등)는
            # 'Sub Total -' 뒤에 숫자가 바로 오고 'Deposits' 라벨만 다음 줄로 넘어간다.
            # 숫자는 절대 다음 줄에서 가져오지 않는다(다음 줄은 그다음 항목의 데이터 행일 수 있어
            # 섞이면 개수가 어긋난다) - 다음 줄은 라벨 확인 용도로만 본다.
            if _SUBTOTAL_DEPOSITS_RE.search(line):
                row_text = line
            else:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if next_line.lower().rstrip(".") != "deposits":
                    continue
                row_text = line

            values = _NUM_RE.findall(row_text)
            # 3분기 x (Total/BD$/Other) 3컬럼 또는 (Total/BD$/US$/Other) 4컬럼 두 형식이 섞여 있다.
            # 컬럼 이름과 무관하게 FCD = Total - BD$ 로 계산하면 두 형식 모두에서 성립한다.
            per_quarter = len(values) // 3
            if per_quarter < 2 or len(values) % 3 != 0:
                continue
            values = [float(v.replace(",", "")) for v in values]

            for q_idx, period in enumerate(quarters):
                block = values[q_idx * per_quarter: (q_idx + 1) * per_quarter]
                total, bd = block[0], block[1]
                fcd = total - bd
                year = int(period[:4])
                rows.append({
                    "country_code": country_code,
                    "year": year,
                    "period": period,
                    "indicator": INDICATOR,
                    "value": round(fcd, 2),
                    "updated_at": now,
                })
                rows.append({
                    "country_code": country_code,
                    "year": year,
                    "period": period,
                    "indicator": INDICATOR_TD,
                    "value": round(total, 2),
                    "updated_at": now,
                })
            break  # 이 블록에서 subtotal 행은 하나만 사용

    return rows


def _parse_report(content: bytes, country_code: str, now: str) -> list[dict]:
    import pdfplumber
    from io import BytesIO

    rows = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not _TITLE_RE.search(_normalize_text(text)):
                continue
            rows.extend(_parse_page(text, country_code, now))
    return rows


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    links = _collect_report_links()
    logger.info("[%s] BMA Annual Report %d개 발견", country_code, len(links))

    all_rows: list[dict] = []
    for url in links:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=60)
            response.raise_for_status()
        except Exception:
            logger.warning("[%s] 다운로드 실패, 스킵: %s", country_code, url)
            continue

        rows = _parse_report(response.content, country_code, now)
        logger.info("[%s] %s -> %d개 분기", country_code, url.rsplit("/", 1)[-1], len(rows))
        all_rows.extend(rows)

    if not all_rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    df = pd.DataFrame(all_rows)
    # 보고서 발간 순서(파일명 정렬)로 처리했으므로 나중에 처리된(더 최근 보고서) 값이 남도록 keep='last'
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    return df.sort_values("period").reset_index(drop=True)
