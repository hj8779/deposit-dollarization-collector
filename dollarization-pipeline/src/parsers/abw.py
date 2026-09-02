"""Aruba: Centrale Bank van Aruba(CBA) Monthly Bulletin PDF, 'TABLE 2: COMPONENTS OF BROAD MONEY'.

표는 벡터 罫線이 없어 pdfplumber의 기본 extract_tables()로는 셀이 잡히지 않는다.
대신 페이지 텍스트를 줄 단위로 읽어 연간(예: '2022 ...') 및 월간(예: '2025 January ...',
'February ...') 행을 정규식으로 파싱한다. 열 구성은 PDF 표 각주의 컬럼 정의를 따른다:

    (1) Currency issued            (2) Currency at banks
    (3=1-2) Currency outside banks (4) Demand deposits Afl.
    (5) Demand deposits Foreign currency        (6=4+5) Demand deposits Total
    (7=3+6) Money
    (8) Other deposits Savings Afl.             (9) Other deposits Savings Foreign currency
    (10) Other deposits Time Afl.               (11) Other deposits Time Foreign currency
    (12=8+9+10+11) Other deposits Total
    (13) Treasury bills and cash certificates
    (14=12+13) Quasi-money
    (15=7+14) Broad money

FCD(거주자 외화예금) = col(5) + col(9) + col(11)
TD(총예금)          = col(6) + col(12)

과거 이력(2010~) 수집: CBA는 연도별 아카이브 페이지(/document/monthly-tables-{YYYY}/)에서
`readBlob.do?id=NNNNN` 형태로 각 월 PDF를 노출한다. 각 PDF의 TABLE 2 자체가 최근 약 18개월치
월별 데이터 + 과거 4개년 연간 데이터를 롤링 윈도우로 담고 있으므로, 연도마다 1개(가급적 12월,
없으면 그 해 마지막으로 발행된 월)만 받아도 그 해의 월별 데이터 대부분을 재구성할 수 있다.
일부 PDF(2010, 2011, 2013, 2014년 다수 + 2018/2021 일부 월)는 pdfplumber.extract_text()로
읽으면 글자 단위로 뒤집힌 텍스트가 나온다. 실제로는 렌더링된 페이지 자체가 180도 회전되어 있는
것으로 확인되어(육안/비전 모델로는 인지하기 어렵지만 실제 픽셀은 뒤집혀 있음), 해당 페이지를
이미지로 렌더링 후 180도 회전해 OCR을 돌리면 정상적으로 읽힌다. 이를 이 프로젝트의 표준
OCR 폴백 절차로 사용한다: 일반 텍스트 추출 실패 시
`src.collectors.base.find_page_text_via_ocr()`로 페이지를 찾아 재시도한다
(자세한 내용은 README.md의 'PDF 텍스트 추출 실패 시 표준 폴백' 절 참고).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber

from src.collectors.base import download, find_page_text_via_ocr
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # 연도별 아카이브를 순회해야 하므로 단일 파일 다운로드가 아니다.

ARCHIVE_URL_TMPL = "https://www.cbaruba.org/document/monthly-tables-{year}/"
FIRST_ARCHIVE_YEAR = 2010

# "MonthlyTablesDec2010.pdf" (구형) / "June 2026 Monthly Tables ..." (신형) 두 라벨 형식을 모두 처리
_LABEL_OLD_RE = re.compile(r"MonthlyTables([A-Za-z]{3})(\d{4})\.pdf", re.I)
_LABEL_NEW_RE = re.compile(r"^([A-Za-z]+)\s+(\d{4})\s+Monthly Tables", re.I)
_ARCHIVE_LINK_RE = re.compile(
    r'<span class="text">([^<]*)</span>.*?readBlob\.do\?id=(\d+)', re.S
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_ABBR = {name[:3]: num for name, num in _MONTHS.items()}
_NUM_RE = r"-?[\d,]+\.\d+"
_ROW_RE = re.compile(
    rf"^(?:(?P<year>\d{{4}})\s+)?(?:(?P<month>[A-Za-z]+)\s+)?(?P<values>(?:{_NUM_RE}\s*){{15}})$"
)


_TABLE2_MARKER = "TABLE 2: COMPONENTS OF BROAD MONEY"
# OCR은 "TABLE 2:"의 숫자/구두점을 종종 놓치므로(예: "TABLE\n\n: COMPONENTS..."),
# OCR 마커 탐지에는 더 관대한 부분 문자열을 쓴다.
_TABLE2_OCR_MARKER = "COMPONENTS OF BROAD MONEY"


def _find_table2_page(pdf: pdfplumber.PDF):
    for page in pdf.pages:
        text = page.extract_text() or ""
        if text.startswith(_TABLE2_MARKER) or _TABLE2_MARKER in text.splitlines()[0:1]:
            return page
    for page in pdf.pages:
        text = page.extract_text() or ""
        if _TABLE2_MARKER in text:
            return page
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    with pdfplumber.open(BytesIO(content)) as pdf:
        page = _find_table2_page(pdf)
        text = page.extract_text() if page is not None else None

        if not text:
            # 표준 OCR 폴백: 일반 텍스트 추출로 TABLE 2를 못 찾으면(글자 인코딩 손상 등)
            # 페이지를 이미지로 렌더링해 회전별로 OCR을 시도한다. 회전이 틀리면 제목만 얼추
            # 인식되고 본문 숫자는 뒤죽박죽인 경우가 있어, 실제 파싱되는 행 수로 최적 회전을 고른다.
            logger.info("[%s] 텍스트 추출 실패, OCR 폴백 시도", country_code)
            text = find_page_text_via_ocr(
                pdf, _TABLE2_OCR_MARKER,
                scorer=lambda t: len(_parse_table2_text(t, country_code)),
            )

    if not text:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    return _parse_table2_text(text, country_code)


def _parse_table2_text(text: str, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    current_year = None
    for raw_line in text.splitlines():
        # OCR 결과에는 표 각주의 밑줄/등호 같은 잡음 토큰(예: '=')이 섞여 들어오는 경우가 있어 제거한다.
        line = " ".join(tok for tok in raw_line.split() if tok not in ("=", "-", "|"))
        m = _ROW_RE.match(line)
        if not m:
            continue

        if m.group("year"):
            current_year = int(m.group("year"))
        if current_year is None:
            continue

        values = [float(v.replace(",", "")) for v in m.group("values").split()]
        if len(values) != 15:
            continue

        month_name = m.group("month")
        if month_name:
            month = _MONTHS.get(month_name.lower())
            if month is None:
                continue
            period = f"{current_year}-{month:02d}"
            year = current_year
        else:
            # 연간 합계 행(예: '2022 336.6 ...')
            year = current_year
            period = f"{year}-Annual"

        demand_fcy, savings_fcy, time_fcy = values[4], values[8], values[10]
        demand_total, other_total = values[5], values[11]

        fcd = round(demand_fcy + savings_fcy + time_fcy, 2)
        td = round(demand_total + other_total, 2)
        ratio = round((fcd / td) * 100, 2) if td else None

        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    return pd.DataFrame(rows)


def _month_from_label(label: str) -> tuple[int, int] | None:
    """아카이브 링크의 라벨 텍스트에서 (year, month)를 추출한다."""
    m = _LABEL_OLD_RE.search(label)
    if m:
        month = _MONTH_ABBR.get(m.group(1).lower()[:3])
        return (int(m.group(2)), month) if month else None

    m = _LABEL_NEW_RE.search(label)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        return (int(m.group(2)), month) if month else None

    return None


def _candidates_per_year(archive_html: str) -> dict[int, list[tuple[int, str]]]:
    """연도별 아카이브 페이지 HTML에서 year -> [(month, doc_id), ...] 목록을 월 내림차순으로 정리한다.
    일부 PDF는 텍스트가 글자 단위로 뒤집혀 추출되는 손상본이라 최선(12월/최신월) 후보가 실패할 수 있으므로,
    render()에서 실패 시 다음 후보로 순차 재시도할 수 있도록 전체 목록을 반환한다."""
    by_year: dict[int, list[tuple[int, str]]] = {}
    for label, doc_id in _ARCHIVE_LINK_RE.findall(archive_html):
        parsed = _month_from_label(label.strip())
        if parsed is None:
            continue
        year, month = parsed
        by_year.setdefault(year, []).append((month, doc_id))
    for year in by_year:
        by_year[year].sort(key=lambda pair: pair[0], reverse=True)
    return by_year


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now_year = datetime.now(timezone.utc).year

    frames = []
    for year in range(FIRST_ARCHIVE_YEAR, now_year + 1):
        archive_url = ARCHIVE_URL_TMPL.format(year=year)
        try:
            html = download(archive_url).decode("utf-8", errors="ignore")
        except Exception:
            logger.warning("[%s] %s 아카이브 접근 실패, 스킵", country_code, year)
            continue

        candidates = _candidates_per_year(html).get(year, [])
        if not candidates:
            logger.info("[%s] %s 연도 아카이브에 유효한 PDF 링크 없음, 스킵", country_code, year)
            continue

        df = pd.DataFrame()
        for _, doc_id in candidates:
            pdf_url = f"https://www.cbaruba.org/readBlob.do?id={doc_id}"
            try:
                content = download(pdf_url, referer=archive_url)
            except Exception:
                continue
            df = parse(content, country_code)
            if not df.empty:
                break
            logger.info(
                "[%s] %s PDF(id=%s) 파싱 결과 없음(텍스트 손상 PDF 추정), 그 해 다른 월로 재시도",
                country_code, year, doc_id,
            )

        if df.empty:
            logger.warning("[%s] %s 연도의 모든 후보 PDF 파싱 실패, 스킵", country_code, year)
            continue
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    merged = pd.concat(frames, ignore_index=True)
    # 연도별 아카이브가 겹치는 기간(롤링 윈도우)을 다룰 수 있어 (period, indicator) 기준 중복 제거,
    # 더 최근에 발행된 PDF(리스트 뒤쪽, 즉 연도가 늦은 쪽)의 값을 우선한다.
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="last")
    merged = merged.sort_values(["period", "indicator"]).reset_index(drop=True)
    return merged
