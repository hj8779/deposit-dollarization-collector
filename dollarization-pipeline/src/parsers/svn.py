"""Slovenia: Banka Slovenije(BSI) PxWeb statistical database (px.bsi.si), PxWeb API v1 (POST/JSON-stat2).

The Monthly Bulletin PDF path stored in targets.json was noted in an earlier investigation as
hard to parse with plain text/table extraction, because the "Selected Liabilities of Other MFIs
by Sector" table on page 169 has a three-level nested header of residency x product type x
currency. However, the same data is published by the BSI's own PxWeb statistical portal
(bsi.si/en/statistics/data-series -> "Money and Monetary Financial Institutions") as a much
easier-to-handle flat PxWeb table, so there is no need to use the PDF path.

Table: I1_6AAE "Selected obligations of other Monetary Financial Institutions - by sector (Total)"
    Path: /pxweb/en/serije_ang/serije_ang__10_denar_mfi__70_OBVEZ_MFI/i1_6aae.px
    (Like its sibling country SWE, this is on the PxWeb family, but BSI uses the older v1 rather
    than the newer PxWebApi v2, so it needs a POST + JSON query body rather than a GET
    querystring -> FILE_URL="__RENDER__")

Table variables (dimensions):
    Date: 2004M12 to present, monthly
    Currency: 0=SIT (tolar, values exist only before 2007-01), 1=EUR (values exist only from
        2007-01 onward)
        -> Confirmed empirically that the two series do not overlap in time (only SIT is
           populated through 2006M12, only EUR from 2007M01 onward), so they can be concatenated
           cleanly. This is because the BSI redefined "domestic currency" at the point of euro
           adoption (before 2007: domestic currency=SIT, foreign currency=everything except SIT
           / after 2007: domestic currency=EUR, foreign currency=everything except EUR) -
           which matches exactly the definition required for this project.
    Frequency: 0=Monthly, 1=Annual (only Monthly is used)
    Items: the 8 deposit types for "All domestic sectors" (the aggregate resident sector),
        split into domestic-currency/foreign-currency pairs:
        0 overnight (domestic currency)       4 overnight (foreign currency)
        1 short-term (domestic currency)      5 short-term (foreign currency)
        2 long-term (domestic currency)       6 long-term (foreign currency)
        3 redeemable at notice (domestic currency)  7 redeemable at notice (foreign currency)
        (Items 8 and 9 are issued debt securities, not deposits, so they are excluded. Item 10,
        the "Liabilities to all domestic sectors" total, also includes debt securities, so it is
        not used as TD; instead items 0-7 are summed directly.)

    TD (total deposits, residents) = sum of items[0..7]
    FCD (foreign-currency deposits, residents) = sum of items[4..7]
    FCD_TD_RATIO = FCD/TD*100

Values are used in their original units (Mio SIT before 2006-12, Mio EUR from 2007-01 onward).
Because the unit changes at the point of euro adoption, the absolute level itself is
discontinuous at that point (unavoidable, since it's a genuine currency redenomination), but
FCD_TD_RATIO is computed within the same currency unit at each point in time, so it is
unaffected.
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
    raise NotImplementedError("SVN is handled via render() (needs a PxWeb v1 POST query body)")


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    response = requests.post(_URL, headers=_HEADERS, json=_QUERY, timeout=30)
    response.raise_for_status()
    payload = response.json()

    dims = payload["dimension"]
    date_index = dims["Date"]["category"]["index"]  # "2004M12" -> 0, ascending order
    dates = sorted(date_index.keys(), key=lambda k: date_index[k])
    n_dates = len(dates)

    currency_ids = list(dims["Currency"]["category"]["index"].keys())
    item_ids = list(dims["Items"]["category"]["index"].keys())
    n_currency = len(currency_ids)
    n_items = len(item_ids)

    values = payload["value"]

    # Dimension order [Date, Currency, Frequency(=1), Items]; Items varies fastest.
    def cell(date_idx: int, currency_idx: int, item_idx: int) -> float | None:
        offset = (date_idx * n_currency + currency_idx) * n_items + item_idx
        return values[offset]

    item_pos = {item_id: idx for idx, item_id in enumerate(item_ids)}

    rows = []
    for date_idx, date in enumerate(dates):
        year_str, month_str = date.split("M")
        year = int(year_str)
        period = f"{year_str}-{month_str}"

        # Of the two currency-denominated series SIT(0)/EUR(1), use whichever one actually has
        # values populated at that point in time (never both populated at once; if both are
        # empty, this date is skipped).
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
