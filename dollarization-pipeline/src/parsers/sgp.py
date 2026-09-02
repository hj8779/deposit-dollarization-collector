"""Singapore: Monetary Authority of Singapore(MAS) Monthly Statistical Bulletin(MSB)
Table 'I.4 Commercial Banks: Deposits and Balances (excluding S$NCDs) by Types of
Non-bank Customers'.

이 표의 최상위 합계 행이 정확히 필요한 지표다:
    TOTAL DEPOSITS - TOTAL            -> TD  (총예금, 거주자+비거주자 전체)
    TOTAL DEPOSITS - IN FOREIGN CURRENCIES -> FCD (외화예금 전체)
    TOTAL DEPOSITS - IN S$            -> (미사용, SGD 예금)

주의: 이 FCD는 거주자(resident)뿐 아니라 비거주자(residents outside Singapore, 즉
아시아 통화 단위/ACU 역외 예금 포함)까지 합산된 상업은행 전체 외화예금이다. 싱가포르는
국제금융센터라 비거주자 예금 비중이 크지만, MAS 자신이 'Deposits and Balances'로
공표하는 은행권 전체 수치를 그대로 쓰는 것은 이 파이프라인의 다른 국가(중앙은행이 발표하는
'외화예금' 원자료를 그대로 채택)와 일관된 처리 방식이다.

데이터 소스는 두 곳을 이어붙여야 전체 이력을 구성할 수 있다:

1. MSB Historical Summary(discontinued/과거 데이터, ~1991-01 ~ 2021-06):
   https://www.mas.gov.sg/-/media/mas-media-library/statistics/monthly-statistical-bulletin/msb-historical/money-and-banking--i4--monthly.csv
   컬럼 순서가 현재 라이브 API와 동일(TOTAL/IN S$/IN FOREIGN CURRENCIES)하다.

2. 현재 라이브 MSB 페이지가 내부적으로 호출하는 JSON API(최근 약 5년 롤링 윈도우만 제공,
   2021-07부터 현재까지):
   https://www.mas.gov.sg/api/v1/MAS/chart/table_i_4_commercial_banks_deposits_and_balances_excluding_s_ncds_by_types_of_non_bank_customers
   필드: dpst_bal_tot(=TD), dpst_bal_in_sgd, dpst_bal_in_forg_cur(=FCD).
   이 엔드포인트는 해당 표의 사람이 보는 페이지
   (/statistics/monthly-statistical-bulletin/i-4-commercial-banks-deposits-and-balances-excluding-s$ncds)
   안에 `injectMasChartData(...)` 스크립트로 URL이 하드코딩되어 있어 찾아냈다.

주의: mas.gov.sg의 일부 인터랙티브 페이지(예: /statistics/monthly-statistical-bulletin/money-and-banking
같은 구 URL)는 Referer 헤더 없이 접근하면 "Maintenance" WAF 페이지를 반환하지만, 실제 데이터
엔드포인트(위 CSV/API 두 곳)는 일반 브라우저 User-Agent만으로도 정상적으로 200을 반환했다
(WAF는 특정 경로에만 적용되는 것으로 보임). 안전을 위해 Referer는 계속 넣어준다.

두 소스 모두 결측월 없이 이어진다(과거 1991-01~2021-06, 현재 API 2021-07~). 검증:
2023-12 FCD=974,745.8 / TD=1,789,239.4 (비율 54.5%), 2024-03 FCD=1,007,555.3 -
사전 조사에서 언급된 표본값(FCD~936bn Dec 2023, ~1,008.2bn Mar 2024, 비율~55%)과
근사치가 대체로 일치해 같은 표/같은 정의임을 확인했다(사전 조사 수치는 근사/역산값이었다).
"""

import csv
import json
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # 단일 파일이 아니라 과거 CSV + 현재 API 두 소스를 이어붙여야 한다.

_HIST_CSV_URL = (
    "https://www.mas.gov.sg/-/media/mas-media-library/statistics/monthly-statistical-bulletin/"
    "msb-historical/money-and-banking--i4--monthly.csv"
)
_HIST_REFERER = "https://www.mas.gov.sg/statistics/monthly-statistical-bulletin/msb-historical-summary"

_LIVE_API_URL = (
    "https://www.mas.gov.sg/api/v1/MAS/chart/"
    "table_i_4_commercial_banks_deposits_and_balances_excluding_s_ncds_by_types_of_non_bank_customers"
)
_LIVE_REFERER = (
    "https://www.mas.gov.sg/statistics/monthly-statistical-bulletin/"
    "i-4-commercial-banks-deposits-and-balances-excluding-s$ncds"
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_COLUMNS = ["country_code", "year", "period", "indicator", "value", "updated_at"]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SGP는 render()를 통해 처리한다 (과거 CSV + 현재 API 2개 소스 병합)")


def _emit(country_code: str, year: int, month: int, fcd: float, td: float, now: str) -> list[dict]:
    period = f"{year}-{month:02d}"
    rows = [
        {"country_code": country_code, "year": year, "period": period,
         "indicator": "FCD", "value": round(fcd, 2), "updated_at": now},
        {"country_code": country_code, "year": year, "period": period,
         "indicator": "TD", "value": round(td, 2), "updated_at": now},
    ]
    if td:
        rows.append({"country_code": country_code, "year": year, "period": period,
                      "indicator": "FCD_TD_RATIO", "value": round(fcd / td * 100, 2), "updated_at": now})
    return rows


def _parse_historical(content: bytes, country_code: str, now: str) -> list[dict]:
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(StringIO(text))
    rows = []
    for cells in reader:
        if not cells:
            continue
        period_label = cells[0].strip()
        parts = period_label.split()
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        month = _MONTHS.get(parts[1].strip().lower()[:3])
        if month is None:
            continue
        year = int(parts[0])
        try:
            td = float(cells[1])
            fcd = float(cells[3])
        except (ValueError, IndexError):
            continue
        rows.extend(_emit(country_code, year, month, fcd, td, now))
    return rows


def _parse_live(content: bytes, country_code: str, now: str) -> list[dict]:
    payload = json.loads(content.decode("utf-8"))
    rows = []
    for el in payload.get("elements", []):
        year, month = el.get("year"), el.get("month")
        fcd, td = el.get("dpst_bal_in_forg_cur"), el.get("dpst_bal_tot")
        if year is None or month is None or fcd is None or td is None:
            continue
        rows.extend(_emit(country_code, int(year), int(month), float(fcd), float(td), now))
    return rows


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    rows: list[dict] = []
    try:
        hist_content = download(_HIST_CSV_URL, referer=_HIST_REFERER)
        rows.extend(_parse_historical(hist_content, country_code, now))
    except Exception:
        logger.warning("[%s] 과거 이력 CSV 수집 실패, 라이브 API만으로 진행", country_code)

    try:
        live_content = download(_LIVE_API_URL, referer=_LIVE_REFERER)
        rows.extend(_parse_live(live_content, country_code, now))
    except Exception:
        logger.warning("[%s] 라이브 API 수집 실패", country_code)

    if not rows:
        return pd.DataFrame(columns=_COLUMNS)

    df = pd.DataFrame(rows)
    # 과거 CSV(~2021-06)와 라이브 API(2021-07~)가 겹치는 경우 라이브 값을 우선한다.
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    return df.sort_values(["period", "indicator"]).reset_index(drop=True)
