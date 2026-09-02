"""Tanzania: Bank of Tanzania(BoT) 'Monthly Economic Review'(MER) PDF 시리즈.

목록 페이지 https://www.bot.go.tz/Publications/Filter/1 (필터 카테고리 1 = Monthly Economic
Review; /Publications/Filter/16은 결제시스템/무역 통계용으로 통화 통계와 무관하다는 사실을
재확인했다) 한 페이지에 전체 발간호(2002~현재, 약 280개)가 페이지네이션 없이 테이블로 노출된다.
각 행은 `<a href=".../Monthly Economic Review/en/{token}.pdf">{Mon YY} - Monthly Economic
Review</a>` 형태다. 파일명의 숫자 token은 업로드 타임스탬프일 뿐 실제 대상 기간과 무관하므로
사용하지 않고, 링크 텍스트의 "Mon YY" 라벨도 참고용일 뿐 실제 파싱은 표 내부의 열 헤더
("Mon-YY")에서 직접 기간을 읽어온다.

각 호는 "Money Supply and Its Main Components"류 표(제목이 호마다 조금씩 다름: "Table 2.1:
Money Supply and Components" / "...and its Main Components" / "Sources and Uses of Money
Supply" / "Table 2.2.1"/"Table 2.3.1" 등 번호도 다름)에 최근 3개월(전전월 동월 작년, 전월,
당월 -- 예: 'Nov-24 Oct-25 Nov-25')의 Outstanding stock(단위: Billion TZS)을 롤링 윈도우로
싣는다. 표 안에 다음 행이 있다:

    Extended broad money (M3)        -> M3
    Foreign currency deposits        -> FCD (거주자 외화예금)
    Other deposits
    Currency in circulation
    Transferable deposits

TD(총예금, monetary-survey 정의) = Transferable deposits + Other deposits + FCD
                                 (= M3 - Currency in circulation, 검증됨)
FCD_TD_RATIO = FCD / TD * 100

2026-02-18 발행 "Jan 26" 호(파일 2026021821282158.pdf)의 최신 열 Dec-25로 직접 검증:
FCD=13,381.1, Other=17,944.2, Currency=8,492.3, M3=61,524.3
-> TD = 61,524.3 - 8,492.3 = 53,032.0 (Transferable 21,706.7 + Other 17,944.2 + FCD 13,381.1
   = 53,032.0, 일치) -> FCD_TD_RATIO = 25.23%. 사전 조사에서 제시된 수치와 일치한다.

표는 벡터 罫線이 없는 텍스트 표라 pdfplumber.extract_tables()로는 못 읽는다. 대신
extract_text()로 줄 단위 파싱한다. 오래된 호(대략 2014~2017년경)는 특정 글자(대문자 다음)
뒤에 스퓨리어스 공백이 삽입되어 나오는 폰트 트래킹 문제가 있는데("M 3", "O ther deposits",
"Extended broad m oney supply"), extract_text()의 x_tolerance 기본값(3) 대신 4를 쓰면
이 스퓨리어스 공백이 사라지고 최신 호와 동일한 포맷으로 파싱된다(실측 확인됨). 그래도 실패하는
극히 오래된 호(2013년 일부 등, 해당 표 자체가 없거나 이미지로 삽입된 것으로 추정)는 조용히
건너뛴다 -- 표준 OCR 폴백은 이 케이스에는 해당하지 않는다(텍스트 자체가 존재하고 손상된 게
아니라, 표가 아예 없거나 열 순서가 완전히 뒤섞인 벡터 레이아웃 문제라 OCR로도 해결되지 않음).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # 발간호 전체(약 280개)를 순회해야 하므로 단일 파일 다운로드가 아니다.

BASE_URL = "https://www.bot.go.tz"
LIST_URL = f"{BASE_URL}/Publications/Filter/1"  # Category 1 = Monthly Economic Review

# 목록 페이지의 각 발간호 행: <td>Sn.</td><td>업로드일</td><td>카테고리</td>
# <td class="text-left"><a href="{pdf 경로}">{Mon YY} - Monthly Economic Review</a></td>
_ROW_RE = re.compile(
    r'<tr>\s*<td>\d+\.</td>\s*<td>\s*([^<]+?)\s*</td>\s*<td>\s*([^<]+?)\s*</td>\s*'
    r'<td class="text-left">\s*<a href="([^"]+\.pdf)"[^>]*>\s*([^<]+?)\s*</a>',
    re.S,
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_HEADER_TOKEN_RE = re.compile(r"\b([A-Za-z]{3})-(\d{2})\b")
# 표의 값은 전부 소수점 이하 정확히 1자리(예: '13,543.4')다. 일부 호(예: 2026년 6월호)는
# 인접한 두 열 사이에 공백이 아예 없어("14,553.513,308.6") '\d+'로 탐욕적으로 매칭하면
# 두 숫자가 하나로 합쳐진다. 소수점 이하를 '\d' 1자리로 고정하고 숫자 사이 구분자를 '\s*'
# (0칸도 허용)로 두면, 공백이 없어도 소수점 자리에서 자연스럽게 다음 숫자로 끊어 읽힌다.
# 첫 글자는 반드시 숫자여야 한다('\d[\d,]*'): 일부 2010년 전후 호는 정반대로 천 단위 콤마
# 앞에 스퓨리어스 공백이 들어간다(예: "2 ,060.0"). 콤마로 시작하는 것도 허용하면(예:
# 옛 '[\d,]+') 이런 줄에서 ",060.0"이 "60.0"이라는 가짜 숫자로 오매칭되어 값이 크게
# 틀어진다(실제 발견 사례: 2010년 4월호에서 FCD가 2,060.0 대신 60.0으로 잘못 파싱됨).
# 숫자가 선행 공백으로 쪼개진 행은 이 조건 때문에 아예 매칭되지 않고 조용히 스킵되는데,
# 틀린 값을 만드는 것보다 그 달을 결측으로 두는 편이 안전하다.
_NUM = r"-?\d[\d,]*\.\d"
_ROW_VALUES_RE = re.compile(
    rf"^(?P<label>[A-Za-z][A-Za-z0-9 /().%-]*?)\s+(?P<v1>{_NUM})\s*(?P<v2>{_NUM})\s*(?P<v3>{_NUM})"
    rf"(?:\s*{_NUM}){{0,6}}\s*$"
)

_TARGETS = {
    "M3": "extended broad money",
    "FCD": "foreign currency deposits",
    "OTHER": "other deposits",
    "CURRENCY": "currency in circulation",
    "TRANSFERABLE": "transferable deposits",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("TZA는 render()를 통해 처리한다 (발간호 목록을 전부 순회)")


def _collect_pdf_links() -> list[tuple[str, str]]:
    """(라벨, 절대 PDF URL) 목록을 반환한다. 목록 페이지 자체에 페이지네이션이 없다(전체 노출)."""
    html = download(LIST_URL).decode("utf-8", errors="ignore")
    links = []
    for _upload_date, _category, href, label in _ROW_RE.findall(html):
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        url = url.replace(" ", "%20")
        label = " ".join(label.split())
        links.append((label, url))
    return links


def _period_from_header_token(month_abbr: str, year_2digit: str) -> tuple[int, int] | None:
    month = _MONTHS.get(month_abbr.lower())
    if month is None:
        return None
    year = 2000 + int(year_2digit)
    return year, month


def _extract_table_periods_and_row(text: str) -> tuple[list[tuple[int, int]], dict[str, dict[tuple[int, int], float]]] | None:
    """페이지 텍스트에서 열 기간(최대 3개)과 타깃 행별 {기간: 값} 매핑을 추출한다."""
    lines = text.splitlines()

    periods: list[tuple[int, int]] | None = None
    for line in lines:
        tokens = _HEADER_TOKEN_RE.findall(line)
        if len(tokens) >= 3:
            candidate = [_period_from_header_token(m, y) for m, y in tokens[:3]]
            if all(candidate):
                periods = candidate  # type: ignore[assignment]
                break
    if periods is None:
        return None

    values: dict[str, dict[tuple[int, int], float]] = {key: {} for key in _TARGETS}
    for line in lines:
        m = _ROW_VALUES_RE.match(line.strip())
        if not m:
            continue
        label_lc = " ".join(m.group("label").lower().split())
        if "million" in label_lc or "usd" in label_lc:
            continue  # "...(Millions of USD)" 보조 행은 제외

        matched_key = None
        if label_lc.startswith(_TARGETS["OTHER"]):
            matched_key = "OTHER"
        elif "outside" not in label_lc and label_lc.startswith(_TARGETS["CURRENCY"]):
            matched_key = "CURRENCY"
        elif label_lc.startswith(_TARGETS["TRANSFERABLE"]):
            matched_key = "TRANSFERABLE"
        elif _TARGETS["FCD"] in label_lc:
            matched_key = "FCD"
        elif label_lc.startswith(_TARGETS["M3"]):
            matched_key = "M3"
        if matched_key is None:
            continue

        try:
            v1, v2, v3 = (float(m.group(g).replace(",", "")) for g in ("v1", "v2", "v3"))
        except ValueError:
            continue
        for period, value in zip(periods, (v1, v2, v3)):
            values[matched_key].setdefault(period, value)

    return periods, values


def _parse_pdf(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages[:12]:  # 통화 통계 표는 항상 앞부분(2~7페이지)에 있음
            text = page.extract_text(x_tolerance=4) or ""
            if "foreign currency deposits" not in text.lower():
                continue
            result = _extract_table_periods_and_row(text)
            if result is None:
                continue
            periods, values = result
            if not values["FCD"]:
                continue

            for period in periods:
                fcd = values["FCD"].get(period)
                if fcd is None:
                    continue

                td = None
                transferable = values["TRANSFERABLE"].get(period)
                other = values["OTHER"].get(period)
                if transferable is not None and other is not None:
                    td = round(transferable + other + fcd, 2)
                else:
                    m3 = values["M3"].get(period)
                    currency = values["CURRENCY"].get(period)
                    if m3 is not None and currency is not None:
                        td = round(m3 - currency, 2)

                year, month = period
                period_str = f"{year}-{month:02d}"
                indicator_values = [("FCD", round(fcd, 2))]
                if td:
                    indicator_values.append(("TD", td))
                    indicator_values.append(("FCD_TD_RATIO", round(fcd / td * 100, 2)))

                for indicator, value in indicator_values:
                    rows.append({
                        "country_code": country_code,
                        "year": year,
                        "period": period_str,
                        "indicator": indicator,
                        "value": value,
                        "updated_at": now,
                    })
            break  # 표를 찾아 파싱했으면 이 PDF의 나머지 페이지는 볼 필요 없음

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    links = _collect_pdf_links()
    logger.info("[%s] Monthly Economic Review 발간호 %d개 발견", country_code, len(links))

    frames = []
    for label, url in links:
        try:
            content = download(url, referer=LIST_URL)
        except Exception:
            logger.warning("[%s] 다운로드 실패, 스킵: %s (%s)", country_code, label, url)
            continue

        try:
            df = _parse_pdf(content, country_code)
        except Exception:
            logger.warning("[%s] 파싱 실패, 스킵: %s (%s)", country_code, label, url)
            continue

        if not df.empty:
            frames.append(df)
        else:
            logger.info("[%s] 통화 통계 표를 찾지 못함, 스킵: %s", country_code, label)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    merged = pd.concat(frames, ignore_index=True)
    # 발간호가 최근 3개월치를 롤링 윈도우로 중복 보고하므로 (period, indicator) 기준 중복 제거.
    # links는 최신순(목록 페이지 노출 순서)이므로 keep="first"가 가장 최근 발간호(더 정확한
    # 확정치일 가능성이 높음)의 값을 우선한다.
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="first")
    merged = merged.sort_values(["period", "indicator"]).reset_index(drop=True)
    return merged
