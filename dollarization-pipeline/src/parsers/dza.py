"""Algeria: Banque d'Algérie (Bank of Algeria) Bulletin Statistique Trimestriel.

bank-of-algeria.dz/bulletins-statistiques/ 에서 연도별 분기통계Bulletin PDF를 수집한다.
각 PDF의 "G 3.4 Structure des dépôts" 표에서 "DEPÔTS EN DEVISES" (외화예금) 열을 추출한다.

TD(총예금) = col0(DEPÔTS A VUE 계) + col4(DEPÔTS A TERME 계). 표 자체가 'Structure des
dépôts'(예금 구조) 전체를 요구불(A VUE)+정기(A TERME) 두 축으로 나눈 것이라 이 둘의 합이
곧 전체 예금이다(DEVISES/DINARS는 A TERME만의 통화별 하위 분해라 A VUE에는 통화 구분이
없음 - 실측: col4 = col5(DINARS)+col6(DEVISES), col0 = col1+col2+col3(예치기관별 분해)).

파일 구조:
- URL 패턴: https://www.bank-of-algeria.dz/bulletins-statistiques-{YYYY}/
- PDF 패턴: stoodroa/YYYY/MM/Bulletin_NN_Month_YYYY.pdf
- 표 G 3.4: 월별 예금 구조 (DINARS vs DEVISES 열 구분)
- 단위: 10억 디나르 (milliards de DZD)

사이트 TLS 인증서 체인 문제로 verify=False 사용.
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FILE_URL = "__RENDER__"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# 연도별 bulletin 페이지 목록 (2007~2021 확인됨)
_YEAR_RANGE = range(2007, 2026)

_MONTHS_FR = {
    "janv": 1, "jan": 1, "févr": 2, "fév": 2, "feb": 2, "mars": 3, "mar": 3,
    "avr": 4, "apr": 4, "mai": 5, "may": 5, "juin": 6, "jun": 6,
    "juil": 7, "jul": 7, "août": 8, "aou": 8, "aug": 8,
    "sept": 9, "sep": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12,
}

# G 3.4 표 헤더 패턴
_TABLE_TITLE_RE = re.compile(r"G\s*3\.4|Structure\s+des\s+d[ée]p[ôo]ts", re.I)
_DEVISES_RE = re.compile(r"D[ÉE]P[ÔO]TS\s+EN\s+DEVISES", re.I)
# 표 마지막 두 열('DEPOTS EN DINARS'/'DEPOTS EN DEVISES') 헤더가 폭이 좁아 pdfplumber가
# 글자 단위로 뒤섞어 추출하는 경우가 있어(예: 'DEP D Ô E T V S IS E E N S'), 온전한
# 'DEVISES' 문자열 존재 여부로 페이지를 거르지 않는다 - 표 제목만으로 충분히 특정된다.
_VARIATION_SECTION_RE = re.compile(r"variation\s+en\s*%", re.I)
# 프랑스어 숫자 표기(천단위 공백 구분)를 관대하게 매칭: '167,4'(공백 없음),
# '2 949,1'(공백 1개), '1531,5'(공백이 아예 빠진 경우, 역추적으로 '1'+'531'+',5'로 재구성됨) 모두 처리.
_NUMBER_RE = re.compile(r"\d{1,3}(?:\s?\d{3})*,\d+")
# 일부 문서(예: Bulletin_48_Dec_2019)는 3자리 숫자 중간에 가짜 공백이 끼어 렌더링된다
# (예: '8 60,2'가 실제로는 860,2). 정상적인 프랑스어 천단위 구분은 콤마 앞 그룹이 항상
# 정확히 3자리이므로, 콤마 앞이 1~2자리뿐인 공백만 골라 제거해 원래 숫자로 복원한다
# (예: '8 60,2'->'860,2'는 제거, '3 537,5'는 콤마 앞이 3자리라 정상적인 천단위 구분으로 보존).
_SPURIOUS_SPACE_RE = re.compile(r"(?<=\d)\s(?=\d{1,2},)")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("DZA는 render()를 통해 처리한다 (여러 PDF를 순회해야 함)")


def _collect_pdf_links() -> list[str]:
    """연도별 페이지를 순회하며 PDF 링크 수집."""
    links: set[str] = set()

    for year in _YEAR_RANGE:
        url = f"https://www.bank-of-algeria.dz/bulletins-statistiques-{year}/"
        try:
            r = requests.get(url, headers=_HEADERS, timeout=30, verify=False)
            if r.status_code != 200:
                continue
            pdfs = re.findall(r'href=["\']([^"\']+\.pdf)', r.text, re.I)
            for pdf in pdfs:
                if "bulletin" in pdf.lower():
                    links.add(pdf)
        except Exception as e:
            logger.warning("[DZA] 연도 페이지 %d 수집 실패: %s", year, e)

    return sorted(links)


def _parse_period(text: str) -> tuple[int, int] | None:
    """'2021janv.' 또는 '2014 déc.' 형식에서 연도/월 추출."""
    # 연도 + 월 패턴
    m = re.match(r"(\d{4})\s*([a-zéûô]+)", text.strip(), re.I)
    if m:
        year = int(m.group(1))
        month_key = m.group(2).lower()[:4].rstrip(".")
        month = _MONTHS_FR.get(month_key)
        if month:
            return year, month
    return None


def _extract_devises_from_page(text: str) -> list[tuple[str, float, float | None]]:
    """페이지 텍스트에서 기간별 (period, FCD, TD) 값 추출.

    표는 연도가 그 해 첫 달에만 나오고(예: '2008 sept. ...'), 같은 해의 나머지 달은
    연도 없이 월만 나온다(예: 'oct. ...', 'nov. ...') - 연도를 forward-fill한다.
    표는 항상 7개 열(DEPOTS A VUE 계 / DANS LES BANQUES / AU TRESOR / AU CCP /
    DEPOTS A TERME 계 / EN DINARS / EN DEVISES) 순서라 마지막 숫자가 DEVISES 열(FCD),
    col0+col4가 TD(전체 예금)다.
    데이터 블록 뒤에는 같은 연/월 포맷으로 'Variation en %'(전월/전년 대비 변동률) 섹션이
    이어지는데 절대값이 아니므로, 그 섹션 표제가 나오면 더 이상 읽지 않는다.
    """
    results = []
    current_year: int | None = None
    prev_month: int | None = None

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if _VARIATION_SECTION_RE.search(line):
            break

        # 연도(4자리) + 월 이름, 또는 연도 없이 월 이름만(전년도 이어받기). 월 이름 뒤에
        # '*'(잠정치 표시, 예: 'Juin*')가 붙기도 해 '.'/'*' 모두 허용한다.
        m = re.match(r"(?:(\d{4})\s*)?([a-zéûô]+)[.*]?\s+(.*)", line, re.I)
        if not m:
            continue

        year_str, month_str, rest = m.groups()
        month = _MONTHS_FR.get(month_str.lower()[:4].rstrip(".")) or _MONTHS_FR.get(month_str.lower()[:3])
        if month is None:
            continue
        if year_str:
            current_year = int(year_str)
        elif current_year is not None and prev_month is not None and month <= prev_month:
            # 연도 표기가 없는데 월이 이전 달보다 같거나 작아지면(예: déc.->sept.) 해가 넘어간 것.
            # 표 안에서 일부 달(예: 2010년 1~8월)이 통째로 생략된 채 다음 12월 값만 다시
            # 연도와 함께 나오는 경우도 있어, 그 시점에 year_str이 다시 채워지며 정정된다.
            current_year += 1
        if current_year is None:
            continue
        prev_month = month

        rest = _SPURIOUS_SPACE_RE.sub("", rest)
        numbers = _NUMBER_RE.findall(rest)
        if len(numbers) < 2:  # 최소 2개 열 이상 있어야 함(오탐 방지)
            continue

        values = [float(n.replace(" ", "").replace(",", ".")) for n in numbers]
        fcd = values[-1]
        td = values[0] + values[4] if len(values) >= 5 else None
        results.append((f"{current_year}-{month:02d}", fcd, td))

    return results


def _parse_bulletin(content: bytes, country_code: str) -> pd.DataFrame:
    """단일 PDF에서 외화예금 데이터 추출."""
    now = datetime.now(timezone.utc).isoformat()

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            # G 3.4 표가 있는 페이지 찾기. 목차(TOC) 페이지도 표 제목 텍스트를 포함해
            # _TABLE_TITLE_RE에 걸리지만, 실제 데이터 행이 없어 _extract_devises_from_page가
            # 빈 결과를 반환하므로 아래 'if data:'에서 자연히 다음 페이지로 넘어간다.
            for page in pdf.pages:
                text = page.extract_text() or ""
                if _TABLE_TITLE_RE.search(text):
                    data = _extract_devises_from_page(text)
                    if data:
                        rows = []
                        for period, fcd, td in data:
                            year = int(period[:4])
                            rows.append({
                                "country_code": country_code,
                                "year": year,
                                "period": period,
                                "indicator": INDICATOR,
                                "value": round(fcd, 2),
                                "updated_at": now,
                            })
                            if td is not None:
                                rows.append({
                                    "country_code": country_code,
                                    "year": year,
                                    "period": period,
                                    "indicator": INDICATOR_TD,
                                    "value": round(td, 2),
                                    "updated_at": now,
                                })
                        if rows:
                            return pd.DataFrame(rows)
    except Exception as e:
        logger.warning("[%s] PDF 파싱 실패: %s", country_code, e)

    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    links = _collect_pdf_links()
    logger.info("[%s] Bulletin PDF %d개 발견", country_code, len(links))

    if not links:
        logger.warning("[%s] PDF 링크를 찾을 수 없음", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    all_data: dict[tuple[str, str], float] = {}  # (period, indicator) -> value (최신 값 우선)

    for url in links:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=60, verify=False)
            r.raise_for_status()
        except Exception as e:
            logger.warning("[%s] PDF 다운로드 실패, 스킵: %s (%s)", country_code, url, e)
            continue

        df = _parse_bulletin(r.content, country_code)
        if df.empty:
            continue

        for _, row in df.iterrows():
            key = (row["period"], row["indicator"])
            # 이미 있는 기간은 덮어쓰지 않음 (나중에 정렬 후 최신 PDF 우선)
            if key not in all_data:
                all_data[key] = row["value"]

    if not all_data:
        logger.warning("[%s] 외화예금 데이터를 찾을 수 없음", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for (period, indicator), value in sorted(all_data.items()):
        year = int(period[:4])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": indicator,
            "value": value,
            "updated_at": now,
        })

    result = pd.DataFrame(rows)
    logger.info("[%s] 외화예금 데이터 %d행 추출 (%s ~ %s)",
                country_code, len(result), result["period"].min(), result["period"].max())
    return result
