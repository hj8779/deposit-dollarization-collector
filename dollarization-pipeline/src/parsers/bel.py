"""Belgium: National Bank of Belgium (NBB) official SDMX-JSON REST API.

dataflow BE2,DF_BSIMFI,1.0 (MFI Balance Sheet Items). MBSI_ITEM code scheme (verified
empirically):
    L2BE   = Deposits, Belgium (resident), all currencies combined  -> TD
    L2BEEU = Deposits, Belgium, Euro
    L2BEFC = Deposits, Belgium, Foreign currencies                  -> FCD
    (verified: at any given point in time, L2BEEU + L2BEFC == L2BE exactly, confirmed by
    direct measurement)

The SDMX-JSON response's observations is a sparse dict keyed like
"{freq_idx}:{mbsi_idx}:{time_idx}": [value, ...], and structure.dimensions.observation holds
each dimension's code array in order, so values must be looked up by index. Specifying only
the two needed series in the query key (e.g. 'M.L2BE+L2BEFC') keeps the response to just those
two instead of all 79 items, which is much lighter.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR

# With base.download()'s default Accept header (mostly text/html), this API doesn't return
# JSON — it gives an empty response or XML instead. An explicit Accept: application/json
# request is required, so this is handled via __RENDER__.
FILE_URL = "__RENDER__"

QUERY_URL = (
    "https://nsidisseminate-stat.nbb.be/rest/data/BE2,DF_BSIMFI,1.0/"
    "M.L2BE+L2BEFC?startPeriod=1990-01&dimensionAtObservation=AllDimensions"
)
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BEL is handled via render() (requires Accept: application/json header)")


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
