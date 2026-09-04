"""Finland: Suomen Pankki (Bank of Finland) open data portal (portal.boffsaopendata.fi, built
on Azure API Management) 'Timeseries API v4'.

The old URL saved in targets.json (mfi-balance-sheet/tables/) 404s after a site
redesign. The current suomenpankki.fi statistics dashboard
(dashboards/loans-and-deposits2) is a Power BI embed, which makes direct
scraping essentially impossible, so we use the public REST API that serves the
same data instead (api.boffsaopendata.fi, no API key required). We also
considered the ECB SDMX (data-api.ecb.europa.eu) BSI dataflow, but FI's
currency breakdown (CURRENCY_TRANS=Z06 'all currencies except EUR') only exists
for 227A/227B/227C (OFI subsectors), not for the general resident deposit total
including households + corporates (BS_COUNT_SECTOR=2000) — empirically
confirmed by trying several BS_ITEM/COUNT_AREA combinations, all of which
returned empty results — so we did not use it.

Series names in the MFI_PUBL dataset consist of 17 dot-separated dimension
codes. The two series below were verified against the title text after
fetching the full list of 1382 series from the portal's 'Series' endpoint
(GET /v4/series/MFI_PUBL):

    TD  = M.A.0.A.L20.A.A.U6.2000.ZZ.Z01.A.A.0.A.0.A.0
          (Monthly, MFIs excl. Bank of Finland, Volume, Stock, Deposit liabilities,
           Domestic (home/reference area), Non-MFIs, All currencies combined)
    FCD = same as above except the third-from-last code is Z06 (All currencies
          except EUR)

Both combine 'Deposit liabilities' (L20, total deposits regardless of maturity)
x 'Non-MFIs' (the entire resident non-MFI sector: households + corporates +
government, etc.) x 'Domestic' (residents), which matches the FCD/TD
definitions exactly.
TD is available monthly from 1998-01, FCD from 2003-01 (through 2026-06, i.e.
roughly a 2-month lag as of the latest month).

The Observations endpoint (GET /v4/observations/{dataset}?seriesName=...)
returns all observations for a series in a single response (pagination only
applies to the series-list endpoint), so no paging logic is needed. Default
browser-style Accept headers also return JSON (unlike BEL/EST, this API
returns JSON even for Accept: text/html), but we explicitly request
application/json to be safe. Since this requires two API calls rather than a
single file download, it's handled via FILE_URL="__RENDER__".
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
    raise NotImplementedError("FIN is handled via render() (two API calls instead of a single file)")


def _fetch_series(series_name: str) -> dict[str, float]:
    """Returns a mapping from periodCode ('YYYYMnn') to value."""
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
