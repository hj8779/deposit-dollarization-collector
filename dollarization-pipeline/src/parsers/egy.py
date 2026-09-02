"""Egypt: Central Bank of Egypt(CBE), Table "Banking Survey: Deposits (Except CBE)".

이전 조사(targets.json notes)는 cbe.org.eg가 WAF로 "Request Rejected"를 반환한다고 되어
있었으나, 실제로는 특정 경로(예: /robots.txt)만 그렇고 브라우저 UA 헤더를 붙인 일반 GET으로
/en/economic-research/time-series, /en/economic-research/economic-reports/monthly-statistical-bulletin
등 대부분의 페이지와 첨부 xlsx는 정상 다운로드된다(Playwright 불필요).

데이터는 두 소스를 합쳐서 만든다.

1. Time Series 페이지(카테고리 'Banking Surveys' -> 'Deposits in Local and Foreign Currency')의
   단일 xlsx('deposits-in-local-and-foreign-currency-monthly-june-2023.xlsx')에 회계연도별
   (Jul~Jun) 시트가 2004-2005부터 2022-2023까지 들어있어 2004-07~2023-06 월별 데이터를 한 번에 얻는다.
2. 그 이후(2023-07~)는 Monthly Statistical Bulletin의 각 호(issue)별 xlsx
   ('financial-and-monetary-sector-{issue}.xlsx', 시트 'جدول3')에서 얻는다. 각 호는
   최근 5개 회계연도 6월말 스냅샷 + 최근 약 7~13개월 롤링 윈도우를 담고 있고, 호(issue) 번호가
   1 증가할 때마다 롤링 윈도우가 정확히 1개월씩 이동한다(issue 297의 최신월=2021-10,
   issue 349의 최신월=2026-02로 실측 확인, 52 issue 차이 = 52개월 차이). 이 성질을 이용해
   과거 참조점(REFERENCE_ISSUE/YEAR/MONTH)으로 "현재 시점에 맞는 최신 issue 번호"를 역산한 뒤
   앞뒤로 탐색해 실제 최신 issue를 찾고, 거기서부터 issue 번호를 낮춰가며(각 호 -1개월씩) Time
   Series 파일이 커버하는 기간(2023-06)과 겹치는 지점까지만 내려받는다(사이트가 최근 ~50여개
   호만 보관하므로 오래된 issue는 어차피 404).

두 표는 행 구조가 동일하다(단 정부/비정부, 통화별 라벨의 대소문자가 달라 구분 가능).
    Total Deposits (Including Gov.Deposits)
    Government Deposits
        In local currency / In foreign currencies
    Non-Government Deposits
        In Local Currency
            Public/Private business sector, Household sector,
            Non-resident (external sector), Minus purchased cheques & drafts
        In Foreign Currencies
            (위와 동일한 하위 항목)

거주자 외화예금(FCD) = "In Foreign Currencies" 총계 - "Non-resident (external sector)"
                     (= Public+Private business+Household 합 - 매입수표/환어음 차감분,
                        실측으로 두 계산식이 소수점까지 일치함을 확인)
거주자 총예금(TD)   = FCD + ("In Local Currency" 총계 - "Non-resident (external sector)")

정부예금과 비거주자(외부부문) 예금은 모두 제외(거주자 예금만 집계하는 것이 이 프로젝트의
"resident foreign currency deposits" 정의에 부합).
"""

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # 두 개 이상의 파일(과거 아카이브 + 최신 호 여러 개)을 합쳐야 한다.

_TS_URL = (
    "https://www.cbe.org.eg/-/media/project/cbe/listing/time-series/banking-survey/"
    "deposits-in-local-and-foreign-currency/deposits-in-local-and-foreign-currency-monthly-june-2023.xlsx"
)
_BULLETIN_URL_TMPL = (
    "https://www.cbe.org.eg/-/media/project/cbe/listing/monthly-statistical-bulletin/"
    "financial/financial-and-monetary-sector-{n}.xlsx"
)
_BULLETIN_SHEET = "جدول3"

# 실측 기준점: issue 297의 롤링 윈도우 최신월 = 2021-10 (issue 349 = 2026-02로 검증, 52issue=52개월 일치)
_REF_ISSUE = 297
_REF_YEAR, _REF_MONTH = 2021, 10

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month_num(text) -> int | None:
    if not isinstance(text, str):
        return None
    key = text.strip().rstrip("#").rstrip(".").strip().lower()[:3]
    return _MONTHS.get(key)


def _find_row(df: pd.DataFrame, col: int, needle: str, start: int = 0) -> int | None:
    for i in range(start, len(df)):
        v = df.iat[i, col]
        if isinstance(v, str) and needle in v:
            return i
    return None


def _find_indices(df: pd.DataFrame, label_col: int):
    """'Non-Government Deposits' 이하에서 통화별/거주지별 합계 행 인덱스를 문서 순서대로 찾는다.
    라벨에 붙는 각주 기호(+, ++)가 있어 부분 문자열 매칭을 쓴다."""
    ng = _find_row(df, label_col, "Non-Government Deposits")
    if ng is None:
        return None
    local_total = _find_row(df, label_col, "In Local Currency", ng + 1)
    if local_total is None:
        return None
    local_nonres = _find_row(df, label_col, "Non-resident (external sector)", local_total + 1)
    if local_nonres is None:
        return None
    fc_total = _find_row(df, label_col, "In Foreign Currencies", local_nonres + 1)
    if fc_total is None:
        return None
    fc_nonres = _find_row(df, label_col, "Non-resident (external sector)", fc_total + 1)
    if fc_nonres is None:
        return None
    return local_total, local_nonres, fc_total, fc_nonres


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _build_rows(country_code: str, periods_values: list[tuple[str, float, float]]) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period, fcd, td in periods_values:
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4) if td else None
        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": round(value, 2) if indicator != "FCD_TD_RATIO" else value,
                "updated_at": now,
            })
    return pd.DataFrame(rows)


def _parse_timeseries(content: bytes, country_code: str) -> pd.DataFrame:
    xl = pd.ExcelFile(BytesIO(content))
    periods_values = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, header=None)
        title_row = _find_row(df, 0, "Banking Survey")
        if title_row is None:
            continue
        month_row = title_row + 1
        idx = _find_indices(df, 0)
        if idx is None:
            continue
        local_total, local_nonres, fc_total, fc_nonres = idx

        last_year = None
        for col in range(2, df.shape[1]):
            y = df.iat[title_row, col]
            if pd.notna(y):
                try:
                    last_year = int(y)
                except (TypeError, ValueError):
                    pass
            month = _month_num(df.iat[month_row, col])
            if month is None or last_year is None:
                continue
            try:
                fcd = df.iat[fc_total, col] - df.iat[fc_nonres, col]
                td_fc_part = fcd
                td = (df.iat[local_total, col] - df.iat[local_nonres, col]) + td_fc_part
            except TypeError:
                continue
            if pd.isna(fcd) or pd.isna(td):
                continue
            periods_values.append((f"{last_year}-{month:02d}", float(fcd), float(td)))

    if not periods_values:
        return _empty()
    return _build_rows(country_code, periods_values)


def _parse_bulletin(content: bytes, country_code: str) -> tuple[pd.DataFrame, set[str]]:
    """반환값: (롱폼 DataFrame, 롤링 윈도우 구간의 period 집합).

    표는 앞쪽에 최근 5개 회계연도의 6월말 스냅샷(연간 앵커, 모두 'June')이 나오고 그 뒤에
    최근 몇 개월 롤링 윈도우가 이어진다. 앵커 구간은 항상 과거 5개년 6월로 고정돼 있어(즉,
    issue가 바뀌어도 커버리지가 거의 늘지 않음) render()에서 "Time Series 아카이브와 겹치는
    지점까지 왔는지" 판단할 때 앵커 구간을 쓰면 첫 호에서부터 오탐으로 멈춰버린다. 그래서 앵커
    구간과 롤링 윈도우 구간을 구분해, 겹침 판정에는 롤링 윈도우 구간의 period만 쓴다(앵커 구간
    이후 처음 등장하는 'June이 아닌 월' 컬럼부터를 롤링 윈도우로 간주)."""
    try:
        xl = pd.ExcelFile(BytesIO(content))
    except Exception:
        return _empty(), set()
    if _BULLETIN_SHEET not in xl.sheet_names:
        return _empty(), set()
    df = xl.parse(_BULLETIN_SHEET, header=None)

    unit_row = _find_row(df, 2, "LE mn")
    if unit_row is None:
        return _empty(), set()
    year_row = unit_row + 1
    month_row = unit_row + 3

    idx = _find_indices(df, 1)
    if idx is None:
        return _empty(), set()
    local_total, local_nonres, fc_total, fc_nonres = idx

    periods_values = []
    rolling_periods = set()
    last_year = None
    in_annual_anchor = True
    for col in range(2, df.shape[1]):
        y = df.iat[year_row, col]
        if pd.notna(y):
            try:
                last_year = int(y)
            except (TypeError, ValueError):
                pass
        month = _month_num(df.iat[month_row, col])
        if month is None or last_year is None:
            continue
        if in_annual_anchor and month != 6:
            in_annual_anchor = False
        try:
            fcd = df.iat[fc_total, col] - df.iat[fc_nonres, col]
            td = (df.iat[local_total, col] - df.iat[local_nonres, col]) + fcd
        except TypeError:
            continue
        if pd.isna(fcd) or pd.isna(td):
            continue
        period = f"{last_year}-{month:02d}"
        periods_values.append((period, float(fcd), float(td)))
        if not in_annual_anchor:
            rolling_periods.add(period)

    if not periods_values:
        return _empty(), set()
    return _build_rows(country_code, periods_values), rolling_periods


def _estimate_latest_issue() -> int:
    now = datetime.now(timezone.utc)
    months_since_ref = (now.year - _REF_YEAR) * 12 + (now.month - _REF_MONTH)
    return _REF_ISSUE + months_since_ref


def _issue_exists(n: int) -> bytes | None:
    """존재하지 않는 issue 번호는 302로 /en/page-not-found로 리다이렉트되는데,
    그 페이지 자체는 HTTP 200 HTML을 반환해 requests가 성공으로 착각한다.
    실제 xlsx(zip, 'PK'로 시작)인지 매직바이트로 검증해야 오탐을 피할 수 있다."""
    try:
        content = download(_BULLETIN_URL_TMPL.format(n=n))
    except Exception:
        return None
    if not content.startswith(b"PK"):
        return None
    return content


def _find_actual_latest_issue(guess: int) -> tuple[int, bytes] | None:
    """추정 issue 번호(guess) 주변을 탐색해 실제로 존재하는 가장 큰 issue 번호를 찾는다.
    데이터 공개 지연/추정 오차를 흡수하기 위해 위아래로 몇 개씩 시도한다."""
    content = _issue_exists(guess)
    if content is not None:
        # guess보다 큰 번호가 있는지 몇 개 더 확인(추정치가 실제보다 작을 수 있음)
        n = guess
        best_n, best_content = n, content
        for candidate in range(guess + 1, guess + 6):
            c = _issue_exists(candidate)
            if c is None:
                break
            best_n, best_content = candidate, c
        return best_n, best_content

    # guess가 없으면 아래로 내려가며 탐색(추정치가 실제보다 큰 경우)
    for candidate in range(guess - 1, guess - 12, -1):
        c = _issue_exists(candidate)
        if c is not None:
            return candidate, c
    return None


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    frames = []

    try:
        ts_content = download(_TS_URL)
        ts_df = _parse_timeseries(ts_content, country_code)
    except Exception as e:
        logger.warning("[%s] Time Series 아카이브 다운로드/파싱 실패: %s", country_code, e)
        ts_df = _empty()

    if not ts_df.empty:
        frames.append(ts_df)
        logger.info(
            "[%s] Time Series 아카이브: %d행 (%s~%s)",
            country_code, len(ts_df), ts_df["period"].min(), ts_df["period"].max(),
        )
    covered_periods = set(ts_df["period"]) if not ts_df.empty else set()

    guess = _estimate_latest_issue()
    found = _find_actual_latest_issue(guess)
    if found is None:
        logger.warning("[%s] Monthly Statistical Bulletin 최신 호를 찾지 못함(추정 issue=%d)", country_code, guess)
    else:
        latest_issue, latest_content = found
        logger.info("[%s] Monthly Statistical Bulletin 최신 호 = issue %d", country_code, latest_issue)

        bulletin_frames = []
        n = latest_issue
        content = latest_content
        consecutive_fail = 0
        tries = 0
        reached_overlap = False
        while consecutive_fail < 3 and tries < 80 and not reached_overlap:
            tries += 1
            if content is None:
                content = _issue_exists(n)
            if content is None:
                consecutive_fail += 1
                n -= 1
                content = None
                continue
            consecutive_fail = 0
            df_b, rolling_periods = _parse_bulletin(content, country_code)
            content = None
            if not df_b.empty:
                bulletin_frames.append(df_b)
                # 겹침 판정은 롤링 윈도우 구간만 본다(연간 앵커 구간은 항상 과거 5개년 6월로
                # 고정돼 있어 첫 호부터 ts_df와 겹쳐 보여 조기 종료를 유발하기 때문).
                if rolling_periods and rolling_periods & covered_periods:
                    reached_overlap = True
            n -= 1

        if bulletin_frames:
            # issue 번호 내림차순(최신 호 우선)으로 이어붙였으므로, 이후 drop_duplicates(keep="first")가
            # 같은 기간에 대해 가장 최근에 개정된 값을 채택하게 된다.
            bulletin_df = pd.concat(bulletin_frames, ignore_index=True)
            frames.append(bulletin_df)
            logger.info(
                "[%s] Monthly Statistical Bulletin 호 %d개에서 %d행 추가 확보",
                country_code, len(bulletin_frames), len(bulletin_df),
            )

    if not frames:
        return _empty()

    merged = pd.concat(frames, ignore_index=True)
    # ts_df(회계연도 아카이브, 개정 완료된 값)가 먼저 붙었으므로 겹치는 기간은 ts_df 값을 우선한다.
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="first")
    merged = merged.sort_values(["period", "indicator"]).reset_index(drop=True)
    return merged
