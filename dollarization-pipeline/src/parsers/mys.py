"""Malaysia: data.gov.my Monetary Aggregates (BNM M1/M2/M3 components), 2013-01~현재.

CSV:
  https://storage.data.gov.my/finsector/money_aggregates.csv

FCD = m2_deposit_fx          (Foreign currency deposits, RM million)
TD  = m1_deposit_demand
    + m2_deposit_saving
    + m2_deposit_fixed
    + m2_deposit_fx
    + m2_deposit_other
      (은행시스템 예금 구성요소 합; currency/NID/repo 제외)

api.bnm.gov.my/public/msb/1.3(Open API)는 과거 조회가 안 되고 항상 최신 1개월 스냅샷만
반환해(경로/쿼리 파라미터로 연월을 지정해도 무시되거나 404) 과거 데이터 확장에 쓸 수 없다.

2013-01 이전(1998-01~2012-12)은 BNM 'Monthly Statistical Bulletin' 개별 발행본에 첨부된
표 '1.3 Monetary Aggregates: M1, M2 and M3' 구형 XLS(BIFF, xlrd로 읽음)로 보강한다. 이
표는 발행 시점까지의 전체 누적 시계열(연간 1969~, 월간 1998-01~)을 담고 있어, 2013-01
직전 발행본(2012년 12월호) 파일 단 하나만으로 1998-01~2012-12 전체 월간 구간이 커버된다
(발행본마다 매번 새로 긁을 필요 없음 - 여러 발행본을 대조해 표 레이아웃이 안정적임을
확인함). 열 구성(0-index): 0=연도(연 첫 행에만), 1=월(1~12, 월간 구간에서만; 문자열/숫자
혼재), 3=M3, 4=M2, 5=M1, 6=통화발행고, 7=요구불예금, 8=협의 준통화 합계, 9=저축예금,
10=정기예금, 11=NID, 12=Repo, 13=외화예금(FCD), 14=기타예금, 15=타 금융기관 예치금.
data.gov.my CSV와 동일하게 TD = 7+9+10+13+14 (NID/Repo/타행예치금 제외), FCD = 13.
FCD는 1998-01부터 전 기간 값이 채워져 있음(그 이전 연간 구간은 0으로 미분리 표기되어
제외). 발행본 URL의 첨부파일 CMS 문서ID가 바뀔 수 있어 매번 게시물 페이지를 스크레이핑해
현재 1.3.xls 링크를 찾는다.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO, StringIO

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_CSV = "https://storage.data.gov.my/finsector/money_aggregates.csv"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
}

_TD_PARTS = (
    "m1_deposit_demand",
    "m2_deposit_saving",
    "m2_deposit_fixed",
    "m2_deposit_fx",
    "m2_deposit_other",
)
_FCD = "m2_deposit_fx"

# 2013-01 직전 발행본(2012년 12월호) - 1998-01~2012-12 전체 월간 구간을 담고 있음.
_HISTORICAL_ISSUE_URL = "https://www.bnm.gov.my/-/monthly-statistical-bulletin-dec-2012"
_XLS_LINK_RE = re.compile(r'href="(/documents/20124/\d+/1\.3\.xls)"')
_HIST_TABLE_TITLE = "1.3"
# 이 발행본 시리즈가 커버하는 마지막 달(그 다음 달부터는 data.gov.my CSV가 담당) 이후는
# 중복 삽입하지 않는다.
_HISTORICAL_LAST_PERIOD = "2012-12"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MYS는 render()로 CSV를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _emit(country_code: str, period: str, fcd: float, td: float, now: str) -> list[dict]:
    if td <= 0:
        return []
    ratio = round((fcd / td) * 100, 4)
    year = int(period[:4])
    return [
        {"country_code": country_code, "year": year, "period": period, "indicator": ind, "value": val, "updated_at": now}
        for ind, val in (("FCD", round(fcd, 4)), ("TD", round(td, 4)), ("FCD_TD_RATIO", ratio))
    ]


def _render_historical(country_code: str) -> pd.DataFrame:
    """1998-01~2012-12 (2012년 12월호 'Monetary Aggregates' 구형 XLS).

    bnm.gov.my는 requests 기본 헤더 조합(Accept-Encoding/Connection 등)이 섞이면 403을
    돌려주는 봇 차단 규칙이 있는 듯해서(curl -A "Mozilla/5.0"는 항상 통과, requests 기본
    헤더셋은 항상 403), User-Agent 하나만 남긴 세션으로 우회한다."""
    import xlrd

    session = requests.Session()
    session.headers.clear()
    session.headers["User-Agent"] = "Mozilla/5.0"

    page = session.get(_HISTORICAL_ISSUE_URL, timeout=30)
    page.raise_for_status()
    match = _XLS_LINK_RE.search(page.text)
    if not match:
        logger.warning("[%s] 과거 발행본 페이지에서 1.3.xls 링크를 찾지 못함", country_code)
        return _empty()
    xls_url = "https://www.bnm.gov.my" + match.group(1)

    resp = session.get(xls_url, timeout=60)
    resp.raise_for_status()
    wb = xlrd.open_workbook(file_contents=resp.content)
    sh = wb.sheet_by_index(0)

    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    current_year: int | None = None
    for r in range(9, sh.nrows):
        year_cell = sh.cell_value(r, 0)
        month_cell = sh.cell_value(r, 1)
        if isinstance(year_cell, (int, float)) and year_cell:
            current_year = int(year_cell)
        elif isinstance(year_cell, str) and year_cell.strip().isdigit():
            current_year = int(year_cell.strip())

        month_str = str(month_cell).strip()
        if not month_str or not month_str.replace(".0", "").isdigit() or current_year is None:
            continue  # 월간 구간이 아닌 행(연간 합계 행, 구분용 빈 행 등)은 건너뜀
        month = int(float(month_str))
        if not (1 <= month <= 12):
            continue
        period = f"{current_year}-{month:02d}"
        if period > _HISTORICAL_LAST_PERIOD:
            continue

        try:
            demand = float(sh.cell_value(r, 7))
            saving = float(sh.cell_value(r, 9))
            fixed = float(sh.cell_value(r, 10))
            fcd = float(sh.cell_value(r, 13))
            other = float(sh.cell_value(r, 14))
        except (ValueError, TypeError):
            continue
        if fcd <= 0:
            continue  # FX예금 미분리 구간(1998년 이전 연간 데이터 등)

        td = demand + saving + fixed + fcd + other
        rows.extend(_emit(country_code, period, fcd, td, now))

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    frames = []
    try:
        historical = _render_historical(country_code)
        if not historical.empty:
            frames.append(historical)
            logger.info(
                "[%s] 과거(발행본) %d행 (%s~%s)", country_code, len(historical),
                historical["period"].min(), historical["period"].max(),
            )
    except Exception:
        logger.warning("[%s] 과거(발행본) 데이터 수집 실패, 2013- 이후만 사용", country_code, exc_info=True)

    try:
        resp = requests.get(_CSV, headers=_HEADERS, timeout=90, verify=False)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        if not {"date", "measure", "value"}.issubset(df.columns):
            logger.error("[%s] unexpected columns %s", country_code, df.columns.tolist())
        else:
            wide = (
                df.pivot_table(index="date", columns="measure", values="value", aggfunc="last")
                .sort_index()
            )
            missing = [c for c in (_FCD, *_TD_PARTS) if c not in wide.columns]
            if missing:
                logger.error("[%s] missing columns %s", country_code, missing)
            else:
                now = datetime.now(timezone.utc).isoformat()
                rows = []
                for date, row in wide.iterrows():
                    fcd = row[_FCD]
                    if pd.isna(fcd):
                        continue
                    td = sum(float(row[c]) for c in _TD_PARTS)
                    ts = pd.Timestamp(date)
                    period = f"{ts.year}-{ts.month:02d}"
                    rows.extend(_emit(country_code, period, float(fcd), td, now))
                if rows:
                    frames.append(pd.DataFrame(rows))
    except Exception:
        logger.exception("[%s] 2013- CSV 수집 실패", country_code)

    if not frames:
        return _empty()

    out = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] %d rows total (%s~%s)",
        country_code, len(out), out["period"].min(), out["period"].max(),
    )
    return out
