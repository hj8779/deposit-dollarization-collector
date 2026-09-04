"""Sweden: Statistics Sweden(SCB) Statistical Database, PxWebApi v2 (api.scb.se).

The SCB 'FM5001 Financial Market Statistics' page stored in targets.json (scb.se/fm5001-en) has
no downloadable PDF/file links (it's just a statistics-portal landing page). The actual data
lives in a PxWeb table on the SCB Statistical Database (statistikdatabasen.scb.se), and the
PxWeb software released the new PxWebApi v2 (REST, GET-based) in 2025-10 (replacing the older
v1 POST/JSON-stat approach). This is on the same PxWeb family as Eesti Pank (EST), but SCB
provides its own official API documentation
(scb.se/en/services/open-data-api/pxwebapi/pxwebapi-2.0).

Base URL: https://api.scb.se/OV0104/v2beta/api/v2
    (confirmed that the same data is also mirrored at statistikdatabasen.scb.se/api/v2)
Table discovery: GET /tables?lang=en&query=<keyword> supports keyword search (no need to know
    the table ID in advance). Searching "monetary financial institutions" returns the following
    table as the top result: TAB2824 "Monetary Financial Institutions (MFI), assets and
    liabilities by MFI, item and currency. Monthly 1998M01-", source: Swedish FSA (aggregated),
    monthly, 1998-01 to present.

TAB2824 dimensions (variables):
    Institut (institutions): S21 = "1. Monetary Financial Institutions (MFI)" (the aggregate)
    Kontopost (item, liability item): many detailed deposit items. The total deposits of
        residents (depositors located in Sweden) is not given as a single code but is the sum
        of the following two items (verified empirically, see below):
            K20500 "201011 Deposits, Swe, MFI"      (deposits placed by MFIs located in Sweden)
            K21400 "201012A Deposits, Swe, Non-MFI"  (deposits placed by non-MFIs located in Sweden)
        Verification: confirmed empirically that K20500(v0)+K21400(v0)+K22600(Sweden excl. EU
        Total, v0)+K23800(Rest of world Total, v0) exactly equals K20400 "201 Deposits, Total"
        (v0) at one point in time (2026M06) (11,246,916 SEK million). In other words, K20400 is
        total deposits of both residents and non-residents combined, so K20500+K21400 must be
        used when only residents are needed.
    Valuta (currency): v0=Total currency, v1=Foreign currency, v2=SEK
        (there is no breakdown by individual currency such as EUR/USD in this table, only the
        two-way split of SEK vs. foreign currency. Confirmed empirically that v1+v2 == v0
        exactly for every item.)
    ContentsCode: FM0401XX (the only value, "SEK million", end-of-month stock balance)
    Tid (month): 1998M01 to present, monthly.

TD (total deposits, residents) = K20500(v1+v2) + K21400(v1+v2)  [= K20500(v0)+K21400(v0)]
FCD (foreign-currency deposits, residents) = K20500(v1) + K21400(v1)
FCD_TD_RATIO = FCD/TD*100

Values are used in their original unit, SEK million (no conversion).

PxWebApi v2 can return values directly via a GET query (no POST body needed as with v1), so it
can be handled as a single request, but the parameter keys use bracket notation like
`valueCodes[Institut]=...`, so it's safer to construct the querystring directly rather than
risk a conflict with requests' default params encoding (lists/dicts). Also, the fmt=json-stat2
response comes back even with the default Accept header (unlike BEL/EST, no special Accept
header is required), but it is specified explicitly here for consistency with the other
parsers. Because this requires combining several parameters rather than a single GET, it is
handled via FILE_URL="__RENDER__" + render().
"""

from datetime import datetime, timezone

import pandas as pd
import requests

FILE_URL = "__RENDER__"

_BASE = "https://api.scb.se/OV0104/v2beta/api/v2/tables/TAB2824/data"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# Resident (Sweden-located) deposit items = MFI counterparty + Non-MFI counterparty
_RESIDENT_ITEMS = ["K20500", "K21400"]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SWE is handled via render() (needs PxWebApi v2 GET query parameter construction)")


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
    tid_index = dims["Tid"]["category"]["index"]  # "1998M01" -> 0, in ascending order
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
        # Dimension order [Institut(1), Kontopost, Valuta, ContentsCode(1), Tid]; Tid varies fastest.
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
