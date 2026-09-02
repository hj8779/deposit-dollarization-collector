"""Finland: Suomen Pankki(Bank of Finland) open data portal(portal.boffsaopendata.fi, Azure API
Management 기반) 'Timeseries API v4'.

targets.json에 저장돼 있던 구 URL(mfi-balance-sheet/tables/)은 사이트 개편으로 404. 현재
suomenpankki.fi의 통계 대시보드(dashboards/loans-and-deposits2)는 Power BI 임베드라 직접
스크래핑이 사실상 불가능해서, 같은 데이터를 제공하는 공개 REST API(api.boffsaopendata.fi,
API 키 불필요)를 대신 사용한다. ECB SDMX(data-api.ecb.europa.eu) BSI 데이터플로우도 검토했으나
FI의 통화별(CURRENCY_TRANS=Z06 'all currencies except EUR') 분해는 227A/227B/227C(OFI 하위
섹터)에만 존재하고 가계+기업을 포함하는 일반 거주자 예금 총계(BS_COUNT_SECTOR=2000)에는
없어서(실측 확인: 여러 BS_ITEM/COUNT_AREA 조합 모두 빈 결과) 사용하지 않았다.

MFI_PUBL 데이터셋의 시리즈 이름은 점(.)으로 구분된 17개 차원 코드로 구성된다. 아래 두 시리즈는
포털의 'Series' 엔드포인트(GET /v4/series/MFI_PUBL)로 전체 1382개 시리즈 목록을 받아 제목
텍스트에서 검증한 것이다:

    TD  = M.A.0.A.L20.A.A.U6.2000.ZZ.Z01.A.A.0.A.0.A.0
          (Monthly, MFIs excl. Bank of Finland, Volume, Stock, Deposit liabilities,
           Domestic(home/reference area), Non-MFIs, All currencies combined)
    FCD = 위와 동일하되 마지막에서 세 번째 코드만 Z06(All currencies except EUR)

둘 다 'Deposit liabilities'(L20, 만기 구분 없는 예금 총계) x 'Non-MFIs'(거주 비MFI 부문 전체,
가계+기업+정부 등) x 'Domestic'(거주자) 조합이라 FCD/TD 정의에 정확히 부합한다.
TD는 1998-01부터, FCD는 2003-01부터 월별로 존재(2026-06까지, 즉 최신월 기준 약 2개월 시차).

Observations 엔드포인트(GET /v4/observations/{dataset}?seriesName=...)는 시리즈 하나당 전체
관측치를 한 번에 반환하므로(페이지네이션은 시리즈 목록 쪽에만 적용) 페이지 처리가 불필요하다.
기본 브라우저형 Accept 헤더로도 JSON을 반환하지만(BEL/EST와 달리 이 API는 Accept: text/html에도
JSON을 줌), 명시적으로 application/json을 요청해 안전하게 처리한다. 단일 파일 다운로드가 아니라
API를 두 번 호출해야 하므로 FILE_URL="__RENDER__"로 처리한다.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

FILE_URL = "__RENDER__"

_DATASET = "MFI_PUBL"
_BASE = "https://api.boffsaopendata.fi/v4/observations"
_TD_SERIES = "M.A.0.A.L20.A.A.U6.2000.ZZ.Z01.A.A.0.A.0.A.0"
_FCD_SERIES = "M.A.0.A.L20.A.A.U6.2000.ZZ.Z06.A.A.0.A.0.A.0"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("FIN은 render()를 통해 처리한다 (단일 파일이 아니라 API 2회 호출)")


def _fetch_series(series_name: str) -> dict[str, float]:
    """periodCode('YYYYMnn') -> value 매핑을 반환한다."""
    response = requests.get(
        f"{_BASE}/{_DATASET}",
        params={"seriesName": series_name, "pageSize": 1000},
        headers=_HEADERS, timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items") or []
    if not items:
        return {}
    out = {}
    for obs in items[0].get("observations", []):
        year_str, month_str = obs["periodCode"].split("M")
        period = f"{year_str}-{int(month_str):02d}"
        out[period] = obs["value"]
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    td_by_period = _fetch_series(_TD_SERIES)
    fcd_by_period = _fetch_series(_FCD_SERIES)

    rows = []
    for period in sorted(td_by_period):
        td = round(td_by_period[period], 2)
        year = int(period[:4])
        rows.append({
            "country_code": country_code, "year": year, "period": period,
            "indicator": "TD", "value": td, "updated_at": now,
        })

        fcd_raw = fcd_by_period.get(period)
        if fcd_raw is None:
            continue
        fcd = round(fcd_raw, 2)
        ratio = round((fcd / td) * 100, 2) if td else None
        rows.append({
            "country_code": country_code, "year": year, "period": period,
            "indicator": "FCD", "value": fcd, "updated_at": now,
        })
        if ratio is not None:
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": "FCD_TD_RATIO", "value": ratio, "updated_at": now,
            })

    return pd.DataFrame(rows)
