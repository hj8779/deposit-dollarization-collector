"""Belgium: National Bank of Belgium(NBB) 공식 SDMX-JSON REST API.

dataflow BE2,DF_BSIMFI,1.0 (MFI Balance Sheet Items). MBSI_ITEM 코드 체계(자체 검증):
    L2BE   = Deposits, Belgium(거주자) 전체 통화 합계  -> TD
    L2BEEU = Deposits, Belgium, Euro
    L2BEFC = Deposits, Belgium, Foreign currencies      -> FCD
    (검증: 한 시점에서 L2BEEU + L2BEFC == L2BE 정확히 일치함을 실측으로 확인)

SDMX-JSON 응답은 observations가 "{freq_idx}:{mbsi_idx}:{time_idx}": [value, ...] 형태의
희소 딕셔너리이고, structure.dimensions.observation에 각 차원의 코드 배열이 순서대로 있어
인덱스로 역참조해야 한다. 쿼리 키에 'M.L2BE+L2BEFC'처럼 필요한 두 시리즈만 지정하면
전체 79개 항목이 아니라 이 둘만 응답에 포함되어 훨씬 가볍다.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR

# base.download()의 기본 Accept 헤더(text/html 위주)로는 이 API가 JSON을 주지 않고
# 빈 응답/XML을 준다. Accept: application/json을 명시한 자체 요청이 필요해 __RENDER__로 처리.
FILE_URL = "__RENDER__"

QUERY_URL = (
    "https://nsidisseminate-stat.nbb.be/rest/data/BE2,DF_BSIMFI,1.0/"
    "M.L2BE+L2BEFC?startPeriod=1990-01&dimensionAtObservation=AllDimensions"
)
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BEL은 render()를 통해 처리한다 (Accept: application/json 헤더 필요)")


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    response = requests.get(QUERY_URL, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()

    dims = payload["structure"]["dimensions"]["observation"]
    mbsi_ids = [v["id"] for v in next(d for d in dims if d["id"] == "MBSI_ITEM")["values"]]
    time_ids = [v["id"] for v in next(d for d in dims if d["id"] == "TIME_PERIOD")["values"]]

    try:
        idx_td = mbsi_ids.index("L2BE")
        idx_fcd = mbsi_ids.index("L2BEFC")
    except ValueError:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    observations = payload["dataSets"][0]["observations"]

    rows = []
    for t_idx, period in enumerate(time_ids):
        year = int(period[:4])
        td_obs = observations.get(f"0:{idx_td}:{t_idx}")
        fcd_obs = observations.get(f"0:{idx_fcd}:{t_idx}")
        if td_obs is not None:
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": "TD", "value": round(float(td_obs[0]), 2), "updated_at": now,
            })
        if fcd_obs is not None:
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": INDICATOR, "value": round(float(fcd_obs[0]), 2), "updated_at": now,
            })

    return pd.DataFrame(rows)
