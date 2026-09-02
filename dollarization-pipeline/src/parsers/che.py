"""Switzerland: SNB(Swiss National Bank) 데이터 포털(data.snb.ch) cube 'babilpobm'
("Banks' balance sheet items by currency for selected bank categories – monthly").
data.snb.ch 자체는 SPA(필터 UI)라 페이지를 그냥 로드해서는 표/파일이 없지만, 뒤에 깔끔한
REST API(/api/cube/{cubeId}/data/csv/{lang})가 있어 requests로 바로 호출한다.

사용자가 처음 제안한 방식은 UI에서 통화를 EUR/USD로 개별 선택해 두 값을 더하는 것이었으나,
API의 통화(WAEHRUNG) 차원은 CHF/EUR/USD 개별 항목과 'T'(전체 통화 합계)만 제공하고 엔·파운드
등 나머지 통화는 개별 항목이 없다(사용자도 이 한계를 지적함). 대신 전체 합계(T)에서
CHF만 빼면 EUR+USD뿐 아니라 그 외 모든 외화까지 포함한 더 완전한 FCD를 얻을 수 있어 이
방식을 쓴다: FCD = Total(WAEHRUNG=T) - CHF(WAEHRUNG=CHF).

필터:
    D0(Balance sheet items) = VKE ('Amounts due in respect of customer deposits', 부채/고객예금)
    INLANDAUSLAND(Domestic and foreign) = I (Domestic, 거주자)
    BANKENGRUPPE(Bank category) = A40 (All banks)
    WAEHRUNG(Currency) = T, CHF

시계열은 1987-12부터 있지만, CHF 개별 통화 값 자체가 1996-11까지는 비어 있어(전체
합계만 존재하고 통화별 분해가 아직 없던 시기) FCD를 계산할 수 없다 - 그래서 CHF 값이
있는 1996-12부터만 수집한다(그 이전은 소스 자체에 통화별 분해가 없어 산출 불가).
"""

import csv
import io
from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import INDICATOR

FILE_URL = (
    "https://data.snb.ch/api/cube/babilpobm/data/csv/en"
    "?dimSel=D0(VKE),INLANDAUSLAND(I),WAEHRUNG(T,CHF),BANKENGRUPPE(A40)&fromDate=1987-01"
)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    text = content.decode("utf-8-sig")

    total_by_period: dict[str, float] = {}
    chf_by_period: dict[str, float] = {}

    reader = csv.reader(io.StringIO(text), delimiter=";", quotechar='"')
    header_seen = False
    for row in reader:
        if not row or not row[0]:
            continue
        if row[0] == "Date":
            header_seen = True
            continue
        if not header_seen:
            continue

        period, _d0, _inland, waehrung, _bank, value = row[:6]
        if not value.strip():
            continue

        if waehrung == "T":
            total_by_period[period] = float(value)
        elif waehrung == "CHF":
            chf_by_period[period] = float(value)

    rows = []
    for period, total in total_by_period.items():
        chf = chf_by_period.get(period)
        if chf is None:
            continue
        year = int(period[:4])
        rows.append({
            "country_code": country_code, "year": year, "period": period,
            "indicator": INDICATOR, "value": round(total - chf, 2), "updated_at": now,
        })
        rows.append({
            "country_code": country_code, "year": year, "period": period,
            "indicator": "TD", "value": round(total, 2), "updated_at": now,
        })

    return pd.DataFrame(rows)
