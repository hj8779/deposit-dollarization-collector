"""Sweden: Statistics Sweden(SCB) Statistical Database, PxWebApi v2 (api.scb.se).

targets.json에 저장돼 있던 SCB 'FM5001 Financial Market Statistics' 페이지
(scb.se/fm5001-en)에는 다운로드 가능한 PDF/파일 링크가 없다(통계 포털 랜딩 페이지일 뿐).
실제 데이터는 SCB Statistical Database(statistikdatabasen.scb.se)의 PxWeb 테이블에
있고, PxWeb 소프트웨어는 2025-10에 신형 PxWebApi v2(REST, GET 기반)를 공개했다
(구형 v1 POST/JSON-stat 방식 대신). Eesti Pank(EST)와 같은 PxWeb 계열이지만 SCB는
자체 공식 API 문서(scb.se/en/services/open-data-api/pxwebapi/pxwebapi-2.0)를 제공한다.

베이스 URL: https://api.scb.se/OV0104/v2beta/api/v2
    (statistikdatabasen.scb.se/api/v2 에도 동일 데이터가 미러링돼 있음을 확인)
테이블 탐색: GET /tables?lang=en&query=<keyword> 로 키워드 검색 가능(테이블 ID를 몰라도 됨).
    "monetary financial institutions" 검색 결과 1순위로 다음 테이블을 확인:
    TAB2824 "Monetary Financial Institutions (MFI), assets and liabilities by MFI,
    item and currency. Monthly 1998M01-", source: Swedish FSA(집계), 월간, 1998-01~현재.

TAB2824 차원(변수):
    Institut(institutions): S21 = "1. Monetary Financial Institutions (MFI)"(집계 전체)
    Kontopost(item, 부채 항목): 예금 세부 항목 다수. 거주자(Sweden 소재 예금주) 예금 합계는
        하나의 코드로 안 나오고 다음 두 항목의 합이다(실측으로 검증, 아래 참고):
            K20500 "201011 Deposits, Swe, MFI"      (스웨덴 소재 MFI가 예치한 예금)
            K21400 "201012A Deposits, Swe, Non-MFI"  (스웨덴 소재 비MFI가 예치한 예금)
        검증: K20500(v0)+K21400(v0)+K22600(EU제외 스웨덴 Total, v0)+K23800(Rest of world
        Total, v0) == K20400 "201 Deposits, Total"(v0) 가 한 시점(2026M06)에서 정확히
        일치함을 실측 확인(11,246,916 SEK백만). 즉 K20400은 거주자+비거주자 전체 예금이므로
        거주자만 필요하면 K20500+K21400을 써야 한다.
    Valuta(currency): v0=Total currency, v1=Foreign currency, v2=SEK
        (EUR/USD 등 세부 통화별 분리는 이 테이블에 없고 SEK vs 외화의 2분류만 존재.
        v1+v2 == v0가 각 항목에서 정확히 일치함을 실측 확인.)
    ContentsCode: FM0401XX (유일값, "SEK million", 월말 잔액 스톡)
    Tid(month): 1998M01 ~ 현재, 월간.

TD(총예금, 거주자) = K20500(v1+v2) + K21400(v1+v2)  [= K20500(v0)+K21400(v0)]
FCD(외화예금, 거주자) = K20500(v1) + K21400(v1)
FCD_TD_RATIO = FCD/TD*100

값 단위는 SEK million(원본 그대로 사용, 환산 없음).

PxWebApi v2는 GET 쿼리로 값을 직접 받을 수 있어(v1처럼 POST 바디 불필요) 단일 요청으로 처리
가능하지만, 파라미터 키가 `valueCodes[Institut]=...` 형태의 대괄호 표기라 requests의 기본
params 인코딩(리스트/딕셔너리)과 충돌 없이 처리하려면 직접 쿼리스트링을 구성하는 편이 안전하다.
또한 fmt=json-stat2 응답이 기본 Accept 헤더로도 오지만(BEL/EST와 달리 특별한 Accept 불필요),
다른 파서와의 일관성을 위해 명시적으로 지정한다. 단일 GET이 아니라 여러 파라미터를 조합해
구성해야 하므로 FILE_URL="__RENDER__" + render()로 처리한다.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

FILE_URL = "__RENDER__"

_BASE = "https://api.scb.se/OV0104/v2beta/api/v2/tables/TAB2824/data"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# 거주자(Sweden 소재) 예금 항목 = MFI 카운터파티 + Non-MFI 카운터파티
_RESIDENT_ITEMS = ["K20500", "K21400"]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SWE는 render()를 통해 처리한다 (PxWebApi v2 GET 쿼리 파라미터 구성 필요)")


def _query_params() -> list[tuple[str, str]]:
    return [
        ("lang", "en"),
        ("valueCodes[Institut]", "S21"),
        ("valueCodes[Kontopost]", ",".join(_RESIDENT_ITEMS)),
        ("valueCodes[Valuta]", "v1,v2"),
        ("valueCodes[ContentsCode]", "FM0401XX"),
        ("valueCodes[Tid]", "*"),
        ("outputFormat", "json-stat2"),
    ]


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    response = requests.get(_BASE, params=_query_params(), headers=_HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()

    dims = payload["dimension"]
    kontopost_ids = list(dims["Kontopost"]["category"]["index"].keys())
    valuta_ids = list(dims["Valuta"]["category"]["index"].keys())
    tid_index = dims["Tid"]["category"]["index"]  # "1998M01" -> 0, 순서대로 오름차순
    periods = sorted(tid_index.keys(), key=lambda k: tid_index[k])
    n_tid = len(periods)

    try:
        idx_v1 = valuta_ids.index("v1")  # Foreign currency
        idx_v2 = valuta_ids.index("v2")  # SEK
    except ValueError:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    values = payload["value"]
    n_valuta = len(valuta_ids)

    def block(kontopost_idx: int, valuta_idx: int) -> list[float]:
        # 차원 순서 [Institut(1), Kontopost, Valuta, ContentsCode(1), Tid], Tid가 가장 빠르게 변한다.
        offset = (kontopost_idx * n_valuta + valuta_idx) * n_tid
        return values[offset: offset + n_tid]

    fcd_total = [0.0] * n_tid
    td_total = [0.0] * n_tid
    for kp_idx, kp in enumerate(kontopost_ids):
        if kp not in _RESIDENT_ITEMS:
            continue
        fcy = block(kp_idx, idx_v1)
        sek = block(kp_idx, idx_v2)
        for i in range(n_tid):
            fcy_v = fcy[i] if fcy[i] is not None else 0.0
            sek_v = sek[i] if sek[i] is not None else 0.0
            fcd_total[i] += fcy_v
            td_total[i] += fcy_v + sek_v

    rows = []
    for i, tid in enumerate(periods):
        year_str, month_str = tid.split("M")
        year = int(year_str)
        period = f"{year_str}-{month_str}"

        fcd = round(fcd_total[i], 2)
        td = round(td_total[i], 2)
        if td == 0.0 and fcd == 0.0:
            continue
        ratio = round((fcd / td) * 100, 2) if td else None

        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    return pd.DataFrame(rows)
