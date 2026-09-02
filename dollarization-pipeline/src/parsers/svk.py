"""Slovakia: Národná banka Slovenska(NBS) 'Deposits and loans received – sector break-down'
(v5-12a 통계양식) 월별 xls/xlsx 시계열.
https://nbs.sk/en/statistics/financial-institutions/banks/statistical-data-of-monetary-financial-institutions/deposits/

페이지 자체가 순수 HTML로 서버 렌더링되어 있어(JS 렌더링 불필요, requests로 바로 파싱 가능;
targets.json의 requires_js=true는 부정확했다) 페이지를 받아 "Deposits and loans received –
sector break-down" 섹션의 표에서 연도(row) x 월(로마 숫자 I~XII, 각각 개별 파일 링크) 격자를
파싱한다. 링크는 두 형태가 섞여 있다: 최근 파일은 `https://nbs.sk/dokument/{uuid}/stiahnut/?force=true`
(UUID 기반 CMS 다운로드), 과거 파일(~2022년경까지)은 `https://nbs.sk/_img/Documents/STATIST/ZSU/
v5-12/v5-12a@YYYYMM.xls(x)` 직접 경로다. 두 형태 모두 페이지 HTML에서 직접 추출되므로 URL 패턴을
추측할 필요가 없다.

파일 포맷은 시기에 따라 3세대로 나뉜다(실측 확인):
    1) 2005~2008 연간 아카이브(`v5-12a@YYYY.xls`, 연 1개 파일에 월별 시트): 유로 도입 전
       SKK/EUR/OFC 3통화 체계로 완전히 다른 레이아웃. 이 파서는 다루지 않는다(아래 '알려진 공백' 참고).
    2) 2009-01~2011-12: "SECTORS"/"Currency" 헤더의 행 기반 레이아웃. 섹터가 행, 통화(EUR/CM)가
       섹터마다 2행 1쌍으로 반복된다. "EURO area - Domestic" 행 그룹의 바로 다음 TOTAL(EUR)/
       (CM) 행 쌍이 거주자 전체 섹터 합계다. DEPOSITS TOTAL 값은 열 C(0-idx 2)에 있다(헤더 텍스트로
       'DEPOSITS'+'TOTAL' 확인). TD = EUR값+CM값, FCD = CM값(외화 전체를 하나로 묶은 값).
    3) 2012-01~현재: "row no." 헤더가 있는 라벨 기반 레이아웃('Total deposits'/'Deposits in EUR'/
       'Deposits in foreign currency' 등 행 라벨이 그대로 지표를 알려준다). 열 구성은 왼쪽부터
       TOTAL(전세계 전체) -> [2016년경부터 삽입된 'Euro area'(유로존 전체)] -> Domestic(거주자
       전체, 이후 열들은 이 거주자 합계를 섹터별로 쪼갠 하위 열) 순서다. 'Euro area' 열 유무로
       "Domestic" 합계 열의 위치가 밀리므로(2012~2015경: TOTAL 바로 다음 열, 2016~: TOTAL, Euro
       area 다음 열), 헤더 텍스트에서 'all sectors'/'euro area' 문자열을 검색해 매 파일마다
       동적으로 위치를 찾는다. TD = 'Total deposits' 행의 Domestic 열, FCD = 'Deposits in foreign
       currency' 행의 Domestic 열. 안전장치로 'Deposits in EUR' 행 값 + FCD가 TD와 (반올림 오차
       이내로) 일치하는지 매 파일 검증하고, 불일치하면(Domestic 열을 잘못 짚었다는 뜻) 그 달은
       조용히 스킵한다(틀린 값보다 결측이 안전하다는 이 프로젝트의 원칙).

알려진 공백: 2005~2008(유로 도입 전, SKK 기준)은 통화 정의 자체가 다르고(SKK가 자국통화, EUR도
'외화'로 잡힘) 레이아웃도 완전히 다른 3번째 포맷이라 이번 구현 범위에서 제외했다. 2009-01부터는
이미 유로가 자국통화이므로 FCD/TD 정의가 현재와 일관된다(불연속 없음).

ECB SDMX BSI API 검토 결과: 슬로바키아(SK)의 거주자 총예금 성격 시리즈(BS_COUNT_SECTOR=2000,
Non-MFIs, COUNT_AREA=U6 Domestic)는 CURRENCY_TRANS=Z01(All currencies combined) 한 종류만
존재하고 EUR/외화 통화별 분해가 없다(실측: `M.SK.N.A.L20.A.1.U6.2000..` 조회 시 Z01만 반환).
NFC(2240) 등 좁은 하위 섹터에서는 통화별 분해가 있지만 일반 거주자 전체 섹터 기준은 아니므로
이번 구현에서는 NBS 원본 파일을 직접 사용한다.

xlrd 2.x는 이 사이트의 구형 .xls 일부에서 NAME 정의(매크로/워크북 이름 범위)에 포함된 특정
토큰(0x2d AreaN)을 만나면 파싱을 포기하고 예외를 던진다(실제 셀 데이터와는 무관한 워크북
메타데이터 파싱 실패). `xlrd.book.evaluate_name_formula`를 이 모듈 내에서만 일시적으로
no-op으로 바꿔치기해 우회한다(호출 직후 원복).
"""

import re
import time
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # 페이지 내 여러 월별 파일을 순회해야 하므로 단일 파일 다운로드가 아니다.

DEPOSITS_PAGE_URL = (
    "https://nbs.sk/en/statistics/financial-institutions/banks/"
    "statistical-data-of-monetary-financial-institutions/deposits/"
)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_SECTION_START = "Deposits and loans received – sector break-down"
_SECTION_END = "Deposits and loans received – break-down by economic activity"

_ROMAN = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_YEAR_CELL_RE = re.compile(r"^\s*<t[hd][^>]*>\s*(\d{4})\s*</t[hd]>")
_LINK_CELL_RE = re.compile(r'<a href="([^"]+)"[^>]*>\s*([IVX]+)\s*<')

_REL_TOL = 0.02  # Domestic 열 판정 정합성 검증 허용 오차(반올림/천단위 차이 흡수)

_OLE_SIG = b"\xd0\xcf\x11\xe0"  # 구형 .xls(OLE) 시그니처
_ZIP_SIG = b"PK"  # 신형 .xlsx(ZIP) 시그니처


def _download_file(url: str, retries: int = 4, backoff: float = 1.5) -> bytes | None:
    """nbs.sk의 WAF가 간헐적으로 정상 요청도 403(HTML 에러 페이지)으로 막는 현상이 실측 확인됨
    (동일 URL을 연속 재시도하면 성공하는 경우가 대부분 -> 일시적 레이트리밋으로 판단).
    응답이 실제 xls/xlsx 시그니처로 시작하지 않으면(= WAF 차단 페이지 등) 재시도한다."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            if resp.status_code == 200 and resp.content[:2] == _ZIP_SIG:
                return resp.content
            if resp.status_code == 200 and resp.content[:4] == _OLE_SIG:
                return resp.content
        except requests.RequestException:
            pass
        time.sleep(backoff * (attempt + 1))
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SVK는 render()를 통해 처리한다 (여러 월별 파일을 순회해야 함)")


def _extract_month_links(html: str) -> dict[tuple[int, int], str]:
    """'sector break-down' 섹션의 (year, month) -> 파일 URL 매핑을 추출한다.
    2005~2008 연간 아카이브(별도 표, 완전히 다른 레이아웃)는 의도적으로 제외한다."""
    import html as htmlmod

    i0 = html.find(_SECTION_START)
    i1 = html.find(_SECTION_END)
    if i0 == -1 or i1 == -1 or i1 <= i0:
        return {}
    section = htmlmod.unescape(html[i0:i1])

    tables = re.findall(r"<table.*?</table>", section, re.S)
    if not tables:
        return {}

    result: dict[tuple[int, int], str] = {}
    for row_html in _ROW_RE.findall(tables[0]):
        year_m = _YEAR_CELL_RE.match(row_html)
        if not year_m:
            continue
        year = int(year_m.group(1))
        for href, roman in _LINK_CELL_RE.findall(row_html):
            month = _ROMAN.get(roman)
            if month:
                result[(year, month)] = href
    return result


def _matrix_from_bytes(content: bytes) -> list[list]:
    """xlsx/xls 바이트를 셀 값의 2차원 리스트로 변환한다."""
    if content[:2] == b"PK":
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
        ws = wb.worksheets[0]
        return [[cell for cell in row] for row in ws.iter_rows(values_only=True)]

    import xlrd
    import xlrd.book as xlrd_book

    original = xlrd_book.evaluate_name_formula
    xlrd_book.evaluate_name_formula = lambda *a, **k: None
    try:
        wb = xlrd.open_workbook(file_contents=content, ignore_workbook_corruption=True)
    finally:
        xlrd_book.evaluate_name_formula = original
    ws = wb.sheet_by_index(0)
    return [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]


def _norm(v) -> str:
    return " ".join(str(v).split()).strip().lower() if isinstance(v, str) else ""


def _find_header_end(matrix: list[list]) -> int | None:
    """'a', 'b', 1, 2, 3 ... 형태의 열 번호 행(신형 포맷 마커)의 인덱스를 찾는다."""
    for r, row in enumerate(matrix):
        if len(row) >= 2 and _norm(row[0]) == "a" and _norm(row[1]) == "b":
            return r
    return None


def _find_domestic_column(matrix: list[list], header_end: int) -> tuple[int | None, int | None]:
    """헤더 텍스트에서 'all sectors'(TOTAL 열)과 'euro area'(있으면) 열을 찾아
    거주자(Domestic) 합계 열 위치를 동적으로 계산한다. (domestic_col, total_col) 반환."""
    ncols = max((len(r) for r in matrix[:header_end]), default=0)
    col_text = []
    for c in range(ncols):
        parts = [_norm(matrix[r][c]) for r in range(header_end) if c < len(matrix[r])]
        col_text.append(" ".join(p for p in parts if p))

    col_total = next((c for c in range(2, ncols) if "all sectors" in col_text[c]), None)
    if col_total is None:
        return None, None

    col_ea = next((c for c in range(col_total + 1, ncols) if "euro area" in col_text[c]), None)
    domestic_col = (col_ea + 1) if col_ea is not None else (col_total + 1)
    if domestic_col >= ncols:
        return None, col_total
    return domestic_col, col_total


def _parse_new_format(matrix: list[list], year: int, month: int, country_code: str, now: str) -> list[dict]:
    header_end = _find_header_end(matrix)
    if header_end is None:
        return []

    domestic_col, _ = _find_domestic_column(matrix, header_end)
    if domestic_col is None:
        logger.warning("[%s] %04d-%02d: Domestic 열을 찾지 못함, 스킵", country_code, year, month)
        return []

    td_val = fcd_val = eur_val = None
    for row in matrix[header_end + 1:]:
        if not row or domestic_col >= len(row):
            continue
        label = _norm(row[0])
        if label == "total deposits" and td_val is None:
            td_val = row[domestic_col]
        elif label == "deposits in eur" and eur_val is None:
            eur_val = row[domestic_col]
        elif label == "deposits in foreign currency" and fcd_val is None:
            fcd_val = row[domestic_col]

    if not all(isinstance(v, (int, float)) for v in (td_val, fcd_val, eur_val)):
        logger.warning("[%s] %04d-%02d: 필요한 행(Total/EUR/foreign currency)을 찾지 못함, 스킵",
                        country_code, year, month)
        return []

    # 정합성 검증: EUR + 외화 == 전체 (Domestic 열을 잘못 짚었으면 어긋난다)
    if abs((eur_val + fcd_val) - td_val) > max(1.0, abs(td_val) * _REL_TOL):
        logger.warning("[%s] %04d-%02d: EUR+FCD != TD (Domestic 열 오판 추정), 스킵",
                        country_code, year, month)
        return []

    return _rows(country_code, year, month, td_val, fcd_val, now)


def _parse_old_format(matrix: list[list], year: int, month: int, country_code: str, now: str) -> list[dict]:
    # "SECTORS" / "Currency" / "DEPOSITS" 헤더가 있는지 먼저 확인(형식 오탐 방지)
    has_marker = any(
        any(_norm(v) == "deposits" for v in row) and any(_norm(v) == "sectors" for v in row)
        for row in matrix[:15]
    )
    if not has_marker:
        return []

    section_row = next(
        (r for r, row in enumerate(matrix) if row and _norm(row[0]) == "euro area - domestic"),
        None,
    )
    if section_row is None or section_row + 2 >= len(matrix):
        logger.warning("[%s] %04d-%02d: 'EURO area - Domestic' 섹션을 찾지 못함, 스킵",
                        country_code, year, month)
        return []

    eur_row = matrix[section_row + 1]
    cm_row = matrix[section_row + 2]
    if _norm(eur_row[1]) != "eur" or _norm(cm_row[1]) != "cm":
        logger.warning("[%s] %04d-%02d: Domestic TOTAL 행 쌍(EUR/CM)을 찾지 못함, 스킵",
                        country_code, year, month)
        return []

    eur_val, cm_val = eur_row[2], cm_row[2]
    if not all(isinstance(v, (int, float)) for v in (eur_val, cm_val)):
        return []

    td_val = eur_val + cm_val
    fcd_val = cm_val
    return _rows(country_code, year, month, td_val, fcd_val, now)


def _rows(country_code: str, year: int, month: int, td: float, fcd: float, now: str) -> list[dict]:
    period = f"{year}-{month:02d}"
    td = round(float(td), 2)
    fcd = round(float(fcd), 2)
    ratio = round((fcd / td) * 100, 2) if td else None
    out = []
    for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
        if value is None:
            continue
        out.append({
            "country_code": country_code, "year": year, "period": period,
            "indicator": indicator, "value": value, "updated_at": now,
        })
    return out


def _parse_month(content: bytes, year: int, month: int, country_code: str, now: str) -> list[dict]:
    try:
        matrix = _matrix_from_bytes(content)
    except Exception:
        logger.exception("[%s] %04d-%02d 파일 파싱 실패(워크북 열기 오류), 스킵", country_code, year, month)
        return []

    rows = _parse_new_format(matrix, year, month, country_code, now)
    if rows:
        return rows
    return _parse_old_format(matrix, year, month, country_code, now)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    page_html = None
    for attempt in range(5):
        try:
            resp = requests.get(DEPOSITS_PAGE_URL, headers=_HEADERS, timeout=30)
            if resp.status_code == 200:
                page_html = resp.text
                break
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    if page_html is None:
        logger.warning("[%s] deposits 페이지 요청 실패(WAF 일시 차단 추정, 재시도 소진)", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    links = _extract_month_links(page_html)
    if not links:
        logger.warning("[%s] deposits 페이지에서 월별 파일 링크를 하나도 찾지 못함", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    all_rows: list[dict] = []
    for (year, month), url in sorted(links.items()):
        content = _download_file(url)
        if content is None:
            logger.warning("[%s] %04d-%02d 파일 다운로드 실패(재시도 소진), 스킵", country_code, year, month)
            continue
        all_rows.extend(_parse_month(content, year, month, country_code, now))

    if not all_rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    df = df.sort_values(["period", "indicator"]).reset_index(drop=True)
    return df
