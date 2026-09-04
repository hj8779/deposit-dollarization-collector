"""Switzerland: SNB (Swiss National Bank) data portal (data.snb.ch), cube 'babilpobm'
("Banks' balance sheet items by currency for selected bank categories - monthly").
data.snb.ch itself is an SPA (filter UI), so simply loading the page yields no table or
file, but behind it there is a clean REST API (/api/cube/{cubeId}/data/csv/{lang}) that can
be called directly with requests.

The approach initially proposed by the user was to select EUR and USD individually in the
UI and sum the two values, but the API's currency (WAEHRUNG) dimension only offers
individual CHF/EUR/USD entries plus 'T' (total across all currencies) — there are no
individual entries for other currencies like JPY or GBP (the user also flagged this
limitation). Instead, subtracting CHF from the overall total (T) yields a more complete FCD
that includes not just EUR+USD but all other foreign currencies as well, so that approach is
used: FCD = Total(WAEHRUNG=T) - CHF(WAEHRUNG=CHF).

Filters:
    D0(Balance sheet items) = VKE ('Amounts due in respect of customer deposits', liabilities/customer deposits)
    INLANDAUSLAND(Domestic and foreign) = I (Domestic, residents)
    BANKENGRUPPE(Bank category) = A40 (All banks)
    WAEHRUNG(Currency) = T, CHF

The time series goes back to 1987-12, but the CHF-specific values are empty until 1996-11
(a period when only the overall total existed and no currency breakdown was yet available),
so FCD cannot be computed for that range — data is collected only from 1996-12 onward, when
CHF values become available (before that, the source itself lacks a currency breakdown, so
it cannot be derived).
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
