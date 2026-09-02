"""Belize: Central Bank of Belize 'Statistical Digest'(연 1회 발간, 1977~최신년까지 전체
시계열이 한 PDF에 누적) 안의 두 표를 조합한다.
    TABLE 7: DOMESTIC BANKS: SUMMARY OF LIABILITIES  -> 'Deposits Total'(전체 통화 합계)
    TABLE 8: DOMESTIC BANKS: BREAKDOWN OF LOCAL CURRENCY DEPOSITS -> 'Total Local Currency Deposits'
FCD = Table7의 Deposits Total - Table8의 Total Local Currency Deposits

두 함정을 실측으로 발견해 처리했다:
1) 이 PDF는 페이지가 실제로 180도 뒤집혀 렌더링되어 있어 pdfplumber.extract_text()가
   글자 단위로 역순인 텍스트를 준다(ABW/BHR 등에서 본 것과 같은 유형의 문제). 게다가 이
   문서는 회전된 표라 extract_text()가 셀 하나당 한 줄씩 쪼개 버려서 좌표 기반 재조립도
   까다로웠다 - 표준 OCR 폴백(페이지를 이미지로 렌더링 후 180도 회전, pytesseract)을 쓰는
   편이 훨씬 안정적이었다.
2) TABLE 7의 'Deposits' 하위 컬럼 개수가 연도에 따라 다르다(예: 1977년은 Demand/Savings/
   Time 3개+Total, 2025년은 Demand/Savings·Chequing/Savings/Time 4개+Total로 늘어남).
   그래서 몇 번째 값이 'Total'인지 컬럼 인덱스로 고정할 수 없다 - 대신 누적합이 자기 자신과
   일치하는 지점(즉 앞선 값들의 합)을 'Total'로 자기검증 방식으로 찾는다.
   TABLE 8은 구조가 안 바뀌어서 마지막 값이 항상 Total Local Currency Deposits이다.

TABLE 7/8은 이 문서에서 각각 11페이지, 10페이지에 걸쳐 있고(연속), 첫 페이지 제목에
'TABLE 7'/'TABLE 8'이, 이후 페이지에는 'continued'가 붙는다. 각 표의 페이지 범위는
문서 앞부분 목차가 아니라 실제 페이지를 순회하며 제목으로 찾는다(발간 연도가 바뀌면
페이지 수도 바뀌므로 매번 동적으로 탐색).
"""

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "https://www.centralbank.org.bz/docs/default-source/4.2.5-statistical-digest/statistical-digest-2025c640da5a-dd75-4fc3-a3bc-3a431d52c202.pdf?sfvrsn=6342168f_1"

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_ROW_RE = re.compile(r"^(?P<label>[A-Za-z]+)\.?\s+(?P<rest>.*\d.*)$")
_NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")
_STRAY_O_RE = re.compile(r"(?<=[\d,\s])O(?=[\d,\s]|$)")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _to_float(token: str) -> float | None:
    token = token.replace(",", "").strip()
    if not token or token == "-":
        return None
    try:
        return float(token)
    except ValueError:
        return None


_OCR_RESOLUTIONS = (240, 250, 260, 275, 300)


def _score_ocr_text(text: str) -> int:
    """월 라벨을 가진 데이터 행이 몇 줄이나 정상적으로 잡히는지로 품질을 매긴다."""
    score = 0
    for line in text.splitlines():
        m = _ROW_RE.match(line.strip())
        if m and _MONTHS.get(m.group("label").strip().lower()[:3]) is not None:
            score += 1
    return score


def _ocr_page(page) -> str:
    """해상도에 따라 tesseract가 표를 행 단위 대신 열 단위로 잘못 읽는 경우가 있어(원인
    불명, 200/300/400dpi 등에서 산발적으로 재현됨), 여러 해상도로 시도해 보고 정상적인
    '라벨+숫자' 행이 가장 많이 잡히는 결과를 채택한다(ABW 등에서 쓰던 회전값 선택과 같은
    자기검증 방식)."""
    import pytesseract

    best_text, best_score = "", -1
    for resolution in _OCR_RESOLUTIONS:
        image = page.to_image(resolution=resolution).original.rotate(180, expand=True)
        text = pytesseract.image_to_string(image)
        score = _score_ocr_text(text)
        if score > best_score:
            best_text, best_score = text, score
    return best_text


def _find_table_pages(pdf, marker: str) -> list[int]:
    """제목에 marker(예: 'SUMMARY OF LIABILITIES')가 포함된 연속 페이지 인덱스를 찾는다.
    'continued' 후속 페이지는 'TABLE 7:' 없이 본문 제목만 반복되므로 marker는 표 본문
    제목(모든 페이지에 공통으로 등장)으로 준다."""
    hits = []
    in_block = False
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        # 180도 회전된 페이지라 줄 순서와 각 줄의 문자 순서가 모두 뒤집혀 있다.
        head_lines = text.splitlines()[:8]
        first_lines = " ".join(line[::-1] for line in reversed(head_lines))
        if marker in first_lines:
            hits.append(i)
            in_block = True
        elif in_block:
            break
    return hits


def _extract_period_rows(pages, value_count_min: int) -> dict[str, list[float]]:
    """OCR 텍스트에서 {period: [numbers...]}를 뽑는다. period는 'YYYY-MM'."""
    result: dict[str, list[float]] = {}
    current_year = None
    for page in pages:
        text = _ocr_page(page)
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if _YEAR_RE.match(line):
                current_year = int(line)
                continue

            m = _ROW_RE.match(line)
            if not m or current_year is None:
                continue
            month = _MONTHS.get(m.group("label").strip().lower()[:3])
            if month is None:
                continue

            rest = _STRAY_O_RE.sub("0", m.group("rest"))
            values = [_to_float(t) for t in _NUM_RE.findall(rest)]
            values = [v for v in values if v is not None]
            if len(values) < value_count_min:
                continue

            result[f"{current_year}-{month:02d}"] = values
    return result


def _deposits_total(values: list[float]) -> float | None:
    """앞선 값들의 누적합과 일치하는 첫 지점을 'Total'로 본다(컬럼 수가 연도별로 달라 인덱스 고정 불가)."""
    cum = 0.0
    for i, v in enumerate(values):
        if i >= 2 and abs(v - cum) < 1.0:
            return v
        cum += v
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber
    from io import BytesIO

    now = datetime.now(timezone.utc).isoformat()

    with pdfplumber.open(BytesIO(content)) as pdf:
        t7_pages = [pdf.pages[i] for i in _find_table_pages(pdf, "DOMESTIC BANKS: SUMMARY OF LIABILITIES")]
        t8_pages = [pdf.pages[i] for i in _find_table_pages(pdf, "BREAKDOWN OF LOCAL CURRENCY DEPOSITS")]

        logger.info("[%s] TABLE 7 %d페이지, TABLE 8 %d페이지 OCR 처리", country_code, len(t7_pages), len(t8_pages))

        t7 = _extract_period_rows(t7_pages, value_count_min=4)
        t8 = _extract_period_rows(t8_pages, value_count_min=10)

    rows = []
    for period, values in t7.items():
        if period not in t8:
            continue
        deposits_total = _deposits_total(values)
        local_total = t8[period][-1]
        if deposits_total is None:
            continue

        fcd = deposits_total - local_total
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
            "value": round(deposits_total, 2),
            "updated_at": now,
        })

    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True) if rows else pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )
