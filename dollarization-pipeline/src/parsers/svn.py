"""Slovenia: Banka Slovenije(BSI) PxWeb 통계 데이터베이스(px.bsi.si), PxWeb API v1(POST/JSON-stat2).

targets.json에 저장돼 있던 월간회보(Monthly Bulletin) PDF 경로는 이전 조사에서 169페이지의
"Selected Liabilities of Other MFIs by Sector" 표에 거주지x상품유형x통화 3단 중첩 헤더가 있어
단순 텍스트/표 파싱이 어렵다고 기록돼 있었으나, 같은 데이터가 BSI 자체 PxWeb 통계 포털
(bsi.si/en/statistics/data-series -> "Money and Monetary Financial Institutions")에 훨씬 다루기
쉬운 flat PxWeb 테이블로 공개돼 있어 PDF 경로를 쓸 필요가 없다.

테이블: I1_6AAE "Selected obligations of other Monetary Financial Institutions - by sector (Total)"
    경로: /pxweb/en/serije_ang/serije_ang__10_denar_mfi__70_OBVEZ_MFI/i1_6aae.px
    (형제 국가 SWE와 마찬가지로 PxWeb 계열이지만 BSI는 신형 PxWebApi v2가 아니라 구형 v1을 쓰므로
    GET 쿼리스트링이 아니라 POST + JSON 쿼리 바디가 필요하다 -> FILE_URL="__RENDER__")

테이블 변수(차원):
    Date: 2004M12 ~ 현재, 월간
    Currency: 0=SIT(톨라르, 2007-01 이전 값만 존재), 1=EUR(2007-01 이후 값만 존재)
        -> 두 계열은 날짜상 정확히 겹치지 않고(2006M12까지 SIT만, 2007M01부터 EUR만 값이 채워짐)
           깔끔하게 이어붙일 수 있음을 실측 확인. 이는 BSI가 "국내통화"를 유로 전환 시점 기준으로
           재정의했기 때문(2007 이전: 국내통화=SIT, 외화=SIT 제외 전체 / 2007 이후:
           국내통화=EUR, 외화=EUR 제외 전체) - 과제에서 요구한 정의와 정확히 일치한다.
    Frequency: 0=Monthly, 1=Annual (Monthly만 사용)
    Items: "All domestic sectors"(거주자 부문 합계)의 예금 8종류가 국내통화/외화로 나뉘어 있음:
        0 overnight(국내통화)       4 overnight(외화)
        1 short-term(국내통화)      5 short-term(외화)
        2 long-term(국내통화)       6 long-term(외화)
        3 redeemable at notice(국내통화)  7 redeemable at notice(외화)
        (8,9번 항목은 채무증권 발행분이라 예금이 아니므로 제외. 10번 "Liabilities to all domestic
        sectors" 합계도 채무증권을 포함하므로 TD로 쓰지 않고 0~7을 직접 합산한다.)

    TD(총예금, 거주자) = items[0..7] 합
    FCD(외화예금, 거주자) = items[4..7] 합
    FCD_TD_RATIO = FCD/TD*100

값 단위는 원본 그대로(2006-12 이전은 Mio SIT, 2007-01 이후는 Mio EUR) 사용한다. 유로 전환 시점에
단위가 바뀌므로 절대값 레벨 자체는 그 시점에서 불연속이지만(실제 통화 재표시이므로 불가피),
FCD_TD_RATIO는 각 시점 내에서 동일 통화 단위로 계산되므로 영향받지 않는다.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

FILE_URL = "__RENDER__"

_URL = (
    "https://px.bsi.si/api/v1/en/serije_ang/10_denar_mfi/70_OBVEZ_MFI/i1_6aae.px"
)
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Content-Type": "application/json"}

_DOMESTIC_ITEMS = ["0", "1", "2", "3"]
_FOREIGN_ITEMS = ["4", "5", "6", "7"]
_ALL_ITEMS = _DOMESTIC_ITEMS + _FOREIGN_ITEMS

_QUERY = {
    "query": [
        {"code": "Currency", "selection": {"filter": "item", "values": ["0", "1"]}},
        {"code": "Frequency", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Items", "selection": {"filter": "item", "values": _ALL_ITEMS}},
    ],
    "response": {"format": "json-stat2"},
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SVN은 render()를 통해 처리한다 (PxWeb v1 POST 쿼리 바디 필요)")


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    response = requests.post(_URL, headers=_HEADERS, json=_QUERY, timeout=30)
    response.raise_for_status()
    payload = response.json()

    dims = payload["dimension"]
    date_index = dims["Date"]["category"]["index"]  # "2004M12" -> 0, 오름차순
    dates = sorted(date_index.keys(), key=lambda k: date_index[k])
    n_dates = len(dates)

    currency_ids = list(dims["Currency"]["category"]["index"].keys())
    item_ids = list(dims["Items"]["category"]["index"].keys())
    n_currency = len(currency_ids)
    n_items = len(item_ids)

    values = payload["value"]

    # 차원 순서 [Date, Currency, Frequency(=1), Items], Items가 가장 빠르게 변한다.
    def cell(date_idx: int, currency_idx: int, item_idx: int) -> float | None:
        offset = (date_idx * n_currency + currency_idx) * n_items + item_idx
        return values[offset]

    item_pos = {item_id: idx for idx, item_id in enumerate(item_ids)}

    rows = []
    for date_idx, date in enumerate(dates):
        year_str, month_str = date.split("M")
        year = int(year_str)
        period = f"{year_str}-{month_str}"

        # SIT(0)/EUR(1) 두 통화 표시 계열 중 그 시점에 실제 값이 채워진 쪽을 쓴다
        # (둘 다 채워진 시점은 없고, 둘 다 비어 있으면 이 날짜는 건너뛴다).
        domestic_total = None
        foreign_total = None
        for currency_idx in range(n_currency):
            probe = cell(date_idx, currency_idx, item_pos[_DOMESTIC_ITEMS[0]])
            if probe is None:
                continue
            domestic_total = sum(
                cell(date_idx, currency_idx, item_pos[item]) or 0.0 for item in _DOMESTIC_ITEMS
            )
            foreign_total = sum(
                cell(date_idx, currency_idx, item_pos[item]) or 0.0 for item in _FOREIGN_ITEMS
            )
            break

        if domestic_total is None:
            continue

        td = round(domestic_total + foreign_total, 2)
        fcd = round(foreign_total, 2)
        if td == 0.0:
            continue
        ratio = round((fcd / td) * 100, 2)

        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    return pd.DataFrame(rows)
