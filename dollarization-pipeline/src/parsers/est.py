"""Estonia: Eesti Pank (Bank of Estonia) statistics portal (statistika.eestipank.ee).

The URL originally saved in targets.json (#/en/p/1009/r/1015, andmestikId=873,
'Analytical accounts of monetary financial institutions') actually points to an
old report under 'Archives' (nodeID=891), whose source data itself ends at
2004-01~2010-12 (not a widget-interaction issue — that report genuinely stops in
2010). The same portal's 'Credit institutions statistics > Deposits'
(nodeID=900) section contains 'Stock of deposits by customer group, residence,
currency and maturity' (nodeID=936, andmestikId=806), which is the successor
report that continues to the present (1997-01~) and has both a
Residence x Currency (EUR/EEK/USD/Other) breakdown, so we use that instead.

Rather than driving the widget with Playwright, we GET the REST endpoints the
widget actually calls under the hood — `/spring/getReadSumma` (values) and
`/spring/getVeerud` (period headers) — directly with a wide date range, seen in
the browser's network tab (a single request, no JS needed). However, if the
request uses default browser-style headers (Accept: text/html...) the server
returns XML instead of JSON, so Accept: application/json must be set explicitly
(the same gotcha as the BEL parser) -> handled via FILE_URL="__RENDER__" +
render().

Query parameters:
    VALIK1=RESIDENT (residents only), VALIK2=KOKKU (all customer groups summed),
    VALIK4=KOKKU (all maturities summed)
    Omitting VALIK3 (display all) returns separate rows per currency:
    TOTAL/EUR/EEK/USD/Other.

TD = the "Residents/TOTAL" row (sum across all currencies).
FCD = TD - the 'domestic currency' column at that point in time. Estonia
    switched from the kroon (EEK) to the euro (EUR) in 2011-01, so before
    2011-01 the domestic currency = EEK (excluded from the sum), and from
    2011-01 onward the domestic currency = EUR (excluded from the sum).
    (Empirically confirmed that EUR+EEK+USD+Other sums to TOTAL within
    rounding error.)
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
_START_DATE = "31.01.1997"  # Source data start date (per the portal's 'Data available' indicator)
_EURO_ADOPTION_PERIOD = "2011-01"  # Before = EEK is the domestic currency, after = EUR is the domestic currency

_TAG_RE = re.compile(r"<[^>]+>")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("EST is handled via render() (requires the Accept: application/json header + 2 endpoints)")


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
