"""Estonia: Eesti Pank(Bank of Estonia) statistics portal(statistika.eestipank.ee).

원래 targets.json에 저장된 URL(#/en/p/1009/r/1015, andmestikId=873, 'Analytical accounts of
monetary financial intitutions')은 사실 'Archives'(nodeID=891) 하위의 옛 보고서라 원천 데이터
자체가 2004-01~2010-12로 끝나 있다(위젯 인터랙션 문제가 아니라 그 report가 실제로 2010년에
멈춘 것). 같은 포털의 'Credit institutions statistics > Deposits'(nodeID=900) 아래
'Stock of deposits by customer group, residence, currency and maturity'(nodeID=936,
andmestikId=806)가 현재까지(1997-01~) 이어지는 후속 보고서이며 거주성(Residence)×통화
(Currency: EUR/EEK/USD/Other) 축을 모두 갖고 있어 이걸 사용한다.

Playwright로 위젯을 조작하는 대신, 브라우저 네트워크 탭에서 위젯이 실제로 호출하는
`/spring/getReadSumma`(값) + `/spring/getVeerud`(기간 헤더) REST 엔드포인트를 직접
넓은 날짜 범위로 GET한다(단일 요청, JS 불필요). 단, 기본 브라우저형 헤더(Accept: text/html...)로
요청하면 서버가 JSON 대신 XML을 반환하므로 Accept: application/json을 명시해야 한다
(BEL 파서와 동일한 함정) -> FILE_URL="__RENDER__" + render()로 처리.

쿼리 파라미터:
    VALIK1=RESIDENT (거주자만), VALIK2=KOKKU (전체 고객군 합계), VALIK4=KOKKU (전체 만기 합계)
    VALIK3을 생략하면(display all) 통화별로 행이 분리되어 나온다: TOTAL/EUR/EEK/USD/Other.

TD = "Residents/TOTAL" 행(전체 통화 합계).
FCD = TD - 그 시점의 '자국통화' 열. 에스토니아는 2011-01에 크룬(EEK)에서 유로(EUR)로 전환했으므로
    2011-01 이전은 자국통화=EEK(그 열을 제외), 2011-01부터는 자국통화=EUR(그 열을 제외)로 계산한다.
    (EUR+EEK+USD+Other의 합이 TOTAL과 소수점 반올림 오차 이내로 일치함을 실측 확인함.)
FCD_TD_RATIO = FCD/TD*100.
"""

import re
from datetime import datetime, timezone

import pandas as pd
import requests

FILE_URL = "__RENDER__"

_ANDMESTIK_ID = 806  # 'Stock of deposits by customer group, residence, currency and maturity'
_BASE = "https://statistika.eestipank.ee/spring"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
}
_START_DATE = "31.01.1997"  # 소스 데이터 시작일(포털의 'Data available' 표시 기준)
_EURO_ADOPTION_PERIOD = "2011-01"  # 이전=EEK가 자국통화, 이후=EUR가 자국통화

_TAG_RE = re.compile(r"<[^>]+>")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("EST는 render()를 통해 처리한다 (Accept: application/json 헤더 + 2개 엔드포인트 필요)")


def _num(text: str) -> float:
    text = text.strip()
    return 0.0 if not text else float(text.replace(",", ""))


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()
    end_date = datetime.now().strftime("%d.%m.%Y")

    common_params = [
        ("andmestikId", _ANDMESTIK_ID),
        ("parameetrid", "kuupaevAlg"), ("parameetrid", _START_DATE),
        ("parameetrid", "kuupaevLopp"), ("parameetrid", end_date),
        ("parameetrid", "VALIK1"), ("parameetrid", "RESIDENT"),
        ("parameetrid", "VALIK2"), ("parameetrid", "KOKKU"),
        ("parameetrid", "VALIK4"), ("parameetrid", "KOKKU"),
        ("lang", "eng"),
    ]

    resp_values = requests.get(
        f"{_BASE}/getReadSumma", params=common_params + [("sectionId", "null")],
        headers=_HEADERS, timeout=30,
    )
    resp_values.raise_for_status()
    rows = resp_values.json()

    resp_cols = requests.get(
        f"{_BASE}/getVeerud", params=common_params + [("fullDataMode", "true")],
        headers=_HEADERS, timeout=30,
    )
    resp_cols.raise_for_status()
    header_cells = resp_cols.json()["upperRows"][0]["cellList"]
    periods = []
    for cell in header_cells:
        date_text = _TAG_RE.sub("", cell["cellText"]).strip()  # DD/MM/YYYY
        day, month, year = date_text.split("/")
        periods.append((int(year), f"{year}-{month}"))

    series = {(row[0], row[1]): row[2:] for row in rows}
    total = series.get(("Residents", "TOTAL"))
    eur = series.get(("Residents", "EUR"))
    eek = series.get(("Residents", "EEK"))
    usd = series.get(("Residents", "USD"))
    other = series.get(("Residents", "Other"))
    if not all([total, eur, eek, usd, other]):
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    out = []
    for i, (year, period) in enumerate(periods):
        td = _num(total[i])
        domestic = _num(eek[i]) if period < _EURO_ADOPTION_PERIOD else _num(eur[i])
        fcd = round(td - domestic, 2)
        td = round(td, 2)
        ratio = round((fcd / td) * 100, 2) if td else None

        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            out.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    return pd.DataFrame(out)
