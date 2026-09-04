"""Singapore: Monetary Authority of Singapore(MAS) Monthly Statistical Bulletin(MSB)
Table 'I.4 Commercial Banks: Deposits and Balances (excluding S$NCDs) by Types of
Non-bank Customers'.

The top-level total rows in this table are exactly the indicators we need:
    TOTAL DEPOSITS - TOTAL            -> TD  (total deposits, residents + non-residents combined)
    TOTAL DEPOSITS - IN FOREIGN CURRENCIES -> FCD (total foreign-currency deposits)
    TOTAL DEPOSITS - IN S$            -> (unused, SGD deposits)

Note: this FCD is the entire commercial-bank foreign-currency deposit base,
combining not just residents but also non-residents (residents outside
Singapore, i.e. including Asian Currency Unit/ACU offshore deposits).
Singapore is an international financial center so the non-resident share is
large, but taking the banking-sector-wide figure that MAS itself publishes as
'Deposits and Balances' at face value is consistent with how this pipeline
handles other countries (adopting the central bank's own published 'foreign
currency deposits' figure as-is).

The data source requires stitching together two places to build the full
history:

1. MSB Historical Summary (discontinued/legacy data, ~1991-01 to 2021-06):
   https://www.mas.gov.sg/-/media/mas-media-library/statistics/monthly-statistical-bulletin/msb-historical/money-and-banking--i4--monthly.csv
   Column order matches the current live API (TOTAL/IN S$/IN FOREIGN CURRENCIES).

2. The JSON API that the current live MSB page calls internally (provides
   only a rolling ~5-year window, 2021-07 to present):
   https://www.mas.gov.sg/api/v1/MAS/chart/table_i_4_commercial_banks_deposits_and_balances_excluding_s_ncds_by_types_of_non_bank_customers
   Fields: dpst_bal_tot(=TD), dpst_bal_in_sgd, dpst_bal_in_forg_cur(=FCD).
   This endpoint was found because its URL is hardcoded in an
   `injectMasChartData(...)` script embedded in the human-facing page for
   this table
   (/statistics/monthly-statistical-bulletin/i-4-commercial-banks-deposits-and-balances-excluding-s$ncds).

Note: some interactive pages on mas.gov.sg (e.g. the old
/statistics/monthly-statistical-bulletin/money-and-banking URL) return a
"Maintenance" WAF page when accessed without a Referer header, but the actual
data endpoints (the CSV/API above) returned 200 normally even with just a
plain browser User-Agent (the WAF appears to apply only to certain paths). We
still send a Referer for safety.

Both sources connect with no missing months (legacy 1991-01~2021-06, live API
2021-07~). Validation: 2023-12 FCD=974,745.8 / TD=1,789,239.4 (ratio 54.5%),
2024-03 FCD=1,007,555.3 — this roughly matches the sample values noted during
preliminary research (FCD~936bn Dec 2023, ~1,008.2bn Mar 2024, ratio~55%),
confirming it's the same table/same definition (the preliminary-research
figures were approximate/back-calculated)."""

import csv
import json
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # not a single file — must stitch together the legacy CSV and the current API.

_HIST_CSV_URL = (
    "https://www.mas.gov.sg/-/media/mas-media-library/statistics/monthly-statistical-bulletin/"
    "msb-historical/money-and-banking--i4--monthly.csv"
)
_HIST_REFERER = "https://www.mas.gov.sg/statistics/monthly-statistical-bulletin/msb-historical-summary"

_LIVE_API_URL = (
    "https://www.mas.gov.sg/api/v1/MAS/chart/"
    "table_i_4_commercial_banks_deposits_and_balances_excluding_s_ncds_by_types_of_non_bank_customers"
)
_LIVE_REFERER = (
    "https://www.mas.gov.sg/statistics/monthly-statistical-bulletin/"
    "i-4-commercial-banks-deposits-and-balances-excluding-s$ncds"
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_COLUMNS = ["country_code", "year", "period", "indicator", "value", "updated_at"]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SGP is handled via render() (merges the legacy CSV and current API sources)")


def _emit(country_code: str, year: int, month: int, fcd: float, td: float, now: str) -> list[dict]:
    period = f"{year}-{month:02d}"
    rows = [
        {"country_code": country_code, "year": year, "period": period,
         "indicator": "FCD", "value": round(fcd, 2), "updated_at": now},
        {"country_code": country_code, "year": year, "period": period,
         "indicator": "TD", "value": round(td, 2), "updated_at": now},
    ]
    if td:
        rows.append({"country_code": country_code, "year": year, "period": period,
                      "indicator": "FCD_TD_RATIO", "value": round(fcd / td * 100, 2), "updated_at": now})
    return rows


def _parse_historical(content: bytes, country_code: str, now: str) -> list[dict]:
    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(StringIO(text))
    rows = []
    for cells in reader:
        if not cells:
            continue
        period_label = cells[0].strip()
        parts = period_label.split()
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        month = _MONTHS.get(parts[1].strip().lower()[:3])
        if month is None:
            continue
        year = int(parts[0])
        try:
            td = float(cells[1])
            fcd = float(cells[3])
        except (ValueError, IndexError):
            continue
        rows.extend(_emit(country_code, year, month, fcd, td, now))
    return rows


def _parse_live(content: bytes, country_code: str, now: str) -> list[dict]:
    payload = json.loads(content.decode("utf-8"))
    rows = []
    for el in payload.get("elements", []):
        year, month = el.get("year"), el.get("month")
        fcd, td = el.get("dpst_bal_in_forg_cur"), el.get("dpst_bal_tot")
        if year is None or month is None or fcd is None or td is None:
            continue
        rows.extend(_emit(country_code, int(year), int(month), float(fcd), float(td), now))
    return rows


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    rows: list[dict] = []
    try:
        hist_content = download(_HIST_CSV_URL, referer=_HIST_REFERER)
        rows.extend(_parse_historical(hist_content, country_code, now))
    except Exception:
        logger.warning("[%s] failed to fetch legacy CSV, proceeding with the live API only", country_code)

    try:
        live_content = download(_LIVE_API_URL, referer=_LIVE_REFERER)
        rows.extend(_parse_live(live_content, country_code, now))
    except Exception:
        logger.warning("[%s] failed to fetch live API", country_code)

    if not rows:
        return pd.DataFrame(columns=_COLUMNS)

    df = pd.DataFrame(rows)
    # Where the legacy CSV (~2021-06) and live API (2021-07~) overlap, prefer the live value.
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    return df.sort_values(["period", "indicator"]).reset_index(drop=True)
