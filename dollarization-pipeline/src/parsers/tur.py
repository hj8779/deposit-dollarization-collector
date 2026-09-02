"""Turkey: Central Bank of the Republic of Turkey (TCMB/CBRT) "Weekly Money and Banking
Statistics" bulletin (Money_Bank.pdf).

TCMB의 EVDS(evds2.tcmb.gov.tr) REST API는 무료지만 반드시 가입 후 발급받는 API 키가
필요해(사람 인증 없는 셀프 발급 경로가 없음) 이 환경에서는 사용할 수 없다. 대신 TCMB가
매주 발행하는 'Weekly Money and Banking Statistics' PDF(Money_Bank.pdf)를 사용한다.
이 PDF는 Table 2 (신 포맷) / Table 7 (구 포맷)에 "거주자(Residents)" 예금을 TRY/FX로
나눠 표시하므로 FCD(거주자 외화예금), TD(거주자 총예금)를 직접 얻을 수 있다.

    FCD = 거주자 예금 중 FX(외화) 부분
    TD  = 거주자 예금 합계(TRY + FX)

실측(2026-07-24, 신 포맷 Table 2): FX(거주자)=10,499,925,050천 TRY,
거주자 총예금=28,416,399,833천 TRY -> ratio=36.95%. 사전 조사 수치(FX 10.500조,
총예금 28.416조, ratio≈36.95%)와 정확히 일치.

포맷은 시기에 따라 두 가지다(같은 asset URL이 매주 덮어써지므로 과거본은
web.archive.org의 CDX 스냅샷을 통해서만 구할 수 있다):

1. 신 포맷 (대략 2025-02~현재, 9페이지): "Table 2. Banking Sector Selected Balance
   Sheet Items"에 "A. DEPOSITS -> 1. Residents -> a. TRY / b. FX"가 5개 주간 컬럼으로
   나온다. 페이지 안에 "1. Residents"~"2. Resident Banks" 사이 구간에서 값을 뽑는다
   (그 밖에도 "2. Resident Banks", "3. Non-Residents" 등에도 동일한 "a. TRY"/"b. FX"
   레이블이 반복되므로 반드시 이 구간으로 한정해야 한다).

2. 구 포맷 (~2024-09까지, 11페이지): "Table 7. Deposits With Banks"에 TRY/FX가 완전히
   분리된 두 섹션(I.TRY DEPOSITS, II.FX DEPOSITS)으로 나뉘고 각각 "I.I.DEPOSIT MONEY
   BANKS"/"I.II.PARTICIPATION BANKS" 하위에 "A.Residents"가 반복된다(총 4회 등장:
   TRY-예금은행, TRY-참여은행, FX-예금은행, FX-참여은행). 4개 참조 시점(당주/전주/전년말/
   전년동주) 컬럼이 있다. TD = 앞의 두 A.Residents 합, FCD = 뒤의 두 A.Residents 합.

숫자 포맷(천단위 구분자)도 스냅샷마다 영어식(1,234,567) 또는 튀르키예식(1.234.567)이
뒤섞여 있다(같은 문서 자산이 CMS에서 재게시될 때마다 로케일이 바뀐 것으로 보임). 이
표의 금액 컬럼은 항상 정수(천 TRY 단위)라 소수점이 없으므로, 토큰에서 '.'와 ',' 를
전부 제거하고 정수로 파싱하면 로케일에 관계없이 안전하다(퍼센트 성장률 컬럼은 컬럼 개수를
정확히 세어서 그 뒤는 아예 읽지 않으므로 문제되지 않는다).

과거 이력 확보: 이 PDF는 매주 같은 URL(wps/wcm/connect/122c325c-.../Money_Bank.pdf)에
덮어써지므로 사이트 자체에는 아카이브가 없다. 대신 Wayback Machine이 이 고정 URL을
2018년부터 반복적으로 스냅샷했고(CDX API로 조회), 각 PDF 한 장이 4~5개 주간 컬럼을
담고 있어(구 포맷은 참조 시점 4개, 신 포맷은 최근 5주) 스냅샷을 전부 모으면 2018~현재
구간을 (완전하진 않지만) 상당히 조밀하게 재구성할 수 있다. 스냅샷 간 공백이 큰 구간
(예: 2019-07~2020-08, 2023-04~2024-02)은 자연히 비어 있다.
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_HEADERS = {"User-Agent": "Mozilla/5.0"}

# 매주 같은 자산 ID에 덮어써지는 "현재" 발행본 (라이브 최신 데이터).
_CURRENT_URL = (
    "https://www.tcmb.gov.tr/wps/wcm/connect/"
    "122c325c-6afd-4718-8573-49f75964ff34/Money_Bank.pdf?MOD=AJPERES"
)

# 위 고정 URL에 대한 Wayback Machine 스냅샷 전체 목록(콘텐츠 다이제스트 기준 중복 제거).
_CDX_URL = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=tcmb.gov.tr/wps/wcm/connect/122c325c-6afd-4718-8573-49f75964ff34/Money_Bank.pdf"
    "&matchType=prefix&collapse=digest&filter=statuscode:200&output=json&limit=1000"
)

_DATE_RE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")
_NUM = r"-?[\d.,]+"


def _num(token: str) -> int:
    """'1,234,567' / '1.234.567' / '1234567' 모두 정수로 안전하게 파싱(천단위 구분자만
    쓰이고 소수점은 없는 컬럼이라 '.'와 ','를 그냥 다 지워도 된다)."""
    return int(token.replace(",", "").replace(".", ""))


def _row_values(text: str, label: str, ncols: int) -> list[int] | None:
    pattern = re.compile(
        rf"^{re.escape(label)}\s+((?:{_NUM}\s+){{{ncols - 1}}}{_NUM})", re.MULTILINE
    )
    m = pattern.search(text)
    if not m:
        return None
    tokens = m.group(1).split()
    if len(tokens) != ncols:
        return None
    return [_num(t) for t in tokens]


def _header_dates(text: str, ncols: int) -> list[str] | None:
    lines = text.splitlines()
    for line in lines[:3]:
        dates = _DATE_RE.findall(line)
        if len(dates) >= ncols:
            out = []
            for d in dates[:ncols]:
                day, month, year = d.split(".")
                out.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
            return out
    return None


def _parse_new_format(pdf: pdfplumber.PDF) -> dict[str, tuple[int, int]]:
    """신 포맷(Table 2, 'A. DEPOSITS' -> '1. Residents' -> a.TRY/b.FX). 반환: {period: (fcd, td)}."""
    for page in pdf.pages:
        text = page.extract_text() or ""
        lines = text.splitlines()
        if not lines or "Table 2." not in lines[0]:
            continue
        if "1. Residents" not in text or "A. DEPOSITS" not in text:
            continue

        # "2. Resident Banks" 이전까지로 한정해 'a. TRY'/'b. FX' 레이블 중복(Resident Banks,
        # Non-Residents 구간에도 같은 레이블이 있음)을 피한다.
        scoped = text.split("\n2. Resident Banks")[0]

        ncols = len(_DATE_RE.findall(text.splitlines()[1])) if len(text.splitlines()) > 1 else 0
        if ncols == 0:
            continue

        td_vals = _row_values(scoped, "1. Residents", ncols)
        fcd_vals = _row_values(scoped, "b. FX", ncols)
        dates = _header_dates(text, ncols)
        if not (td_vals and fcd_vals and dates):
            continue

        return {date: (fcd, td) for date, fcd, td in zip(dates, fcd_vals, td_vals)}

    return {}


def _parse_old_format(pdf: pdfplumber.PDF) -> dict[str, tuple[int, int]]:
    """구 포맷(Table 7. Deposits With Banks). 'A.Residents'가 순서대로
    TRY-예금은행, TRY-참여은행, FX-예금은행, FX-참여은행 4번 등장."""
    for page in pdf.pages:
        text = page.extract_text() or ""
        first_line = text.splitlines()[0] if text.splitlines() else ""
        if "Table 7." not in first_line or "Deposits With Banks" not in first_line:
            continue

        scoped = text.split("III.TOTAL DEPOSITS")[0]
        ncols = len(_DATE_RE.findall(text.splitlines()[1])) if len(text.splitlines()) > 1 else 0
        if ncols == 0:
            continue

        matches = list(
            re.finditer(
                rf"^A\.Residents\s+((?:{_NUM}\s+){{{ncols - 1}}}{_NUM})", scoped, re.MULTILINE
            )
        )
        if len(matches) < 4:
            continue

        def vals(m):
            tokens = m.group(1).split()
            return [_num(t) for t in tokens] if len(tokens) == ncols else None

        try_deposit_banks = vals(matches[0])
        try_participation = vals(matches[1])
        fx_deposit_banks = vals(matches[2])
        fx_participation = vals(matches[3])
        dates = _header_dates(text, ncols)
        if not (try_deposit_banks and try_participation and fx_deposit_banks and fx_participation and dates):
            continue

        result = {}
        for i, date in enumerate(dates):
            fcd = fx_deposit_banks[i] + fx_participation[i]
            td_try = try_deposit_banks[i] + try_participation[i]
            result[date] = (fcd, td_try + fcd)
        return result

    return {}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    columns = ["country_code", "year", "period", "indicator", "value", "updated_at"]

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            by_period = _parse_new_format(pdf)
            if not by_period:
                by_period = _parse_old_format(pdf)
    except Exception as exc:
        logger.info("[%s] PDF 파싱 실패(손상된 아카이브본 추정), 스킵: %s", country_code, exc)
        return pd.DataFrame(columns=columns)

    if not by_period:
        return pd.DataFrame(columns=columns)

    rows = []
    for period, (fcd, td) in by_period.items():
        year = int(period[:4])
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


def _wayback_urls() -> list[str]:
    try:
        response = requests.get(_CDX_URL, headers=_HEADERS, timeout=30)
        response.raise_for_status()
        rows = response.json()
    except Exception as exc:
        logger.warning("TUR: Wayback CDX 조회 실패, 현재 발행본만 사용: %s", exc)
        return []

    if not rows or len(rows) < 2:
        return []

    urls = []
    for ts, original in ((r[1], r[2]) for r in rows[1:]):
        urls.append(f"https://web.archive.org/web/{ts}if_/{original}")
    return urls


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    frames = []

    urls = [_CURRENT_URL] + _wayback_urls()
    logger.info("[%s] Weekly Money and Banking Statistics PDF %d개(현재+아카이브) 순회", country_code, len(urls))

    for url in urls:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=60)
            response.raise_for_status()
            content = response.content
        except Exception as exc:
            logger.info("[%s] 다운로드 실패, 스킵: %s (%s)", country_code, url, exc)
            continue

        df = parse(content, country_code)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="first")
    merged = merged.sort_values(["period", "indicator"]).reset_index(drop=True)
    return merged
