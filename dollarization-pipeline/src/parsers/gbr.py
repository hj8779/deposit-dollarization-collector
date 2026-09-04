"""United Kingdom: Bank of England 'Interactive Database' (IADB, boeapps/database) statistics series.

Verified the EC code for the 'Foreign currency deposits at UK MFIs' column in
the 'A7.1 - Liquid assets outside M4' table at
https://www.bankofengland.co.uk/statistics/tables#m4: LPMVYAY (short code
VYAY). The codes VSUC/VSUF/VSUG/VWNI suggested by preliminary research all
turned out to be wrong upon verification (VWNI='Sterling deposits at Channel
Islands and IoM institutions', VSUC='Non-residents' sterling deposits at banks
in the BIS area', VSUF/VSUG='Gilts maturing within 1 year / 1-5 years', etc. —
all unrelated columns in the same table, unrelated to FCD). Series actually
confirmed:

    LPMVYAY = "Monthly amounts outstanding of monetary financial institutions' all foreign
               currency deposits from private sector (in sterling millions) NSA"   -> FCD
    LPMVRJX = "...sterling retail deposits (excluding notes and coin) from private sector..." NSA
    LPMVRJV = "...sterling wholesale M4 liabilities to private sector..." NSA

VRJX+VRJV = total sterling deposits held by the private sector, excluding
notes/coin, out of M4 (= the sum of retail+wholesale deposits in the A2.2.1
'Components of M4' table; empirically confirmed this differs from the M4 code
AUYM itself only by the notes&coin component). Since the scope matches FCD's
definition (M4 private sector = households + PNFC + OFC), TD is constructed as
TD = VRJX + VRJV + VYAY (total deposits across all currencies).

Download method: the IADB's old CSV export endpoint
(_iadb-fromshowcolumns.asp?csv.x=yes&...) now only returns an "Invalid series
code value supplied" error and no longer works (the direct CSV download
mentioned by preliminary research is now blocked). Instead, we use
fromshowcolumns.asp, which is what the statistics page's 'View chart' link
actually calls (EC codes need the LPM prefix): passing multiple SeriesCodes
comma-separated in a single GET request returns an HTML table
(<table id="stats-table">) with each series as a column. This table is parsed
with a regex (no separate JS rendering/Playwright needed, requests suffices).
"""

import re
from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SERIES = ["LPMVYAY", "LPMVRJX", "LPMVRJV"]  # FCD, sterling retail deposits, sterling wholesale deposits

FILE_URL = (
    "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"
    "?Travel=NIxAZxSUx&FromSeries=1&ToSeries=50&DAT=RNG"
    "&FD=1&FM=Jan&FY=1980&TD=31&TM=Dec&TY=2030&FNY=Y"
    "&CSVF=TT&html.x=66&html.y=26"
    f"&SeriesCodes={','.join(_SERIES)}&UsingCodes=Y&Filter=N&title=GBR_FCD&VPD=Y"
)

# British-style two-digit-year dates like "30 Jun 82" are followed by one cell per series
# (FCD, retail deposits, wholesale deposits). Early periods with no value are filled with "n/a".
_ROW_RE = re.compile(
    r"<tr><td[^>]*>(\d{1,2} [A-Za-z]{3} \d{2})</td>"
    r"<td[^>]*>([\d,]+|n/a)</td><td[^>]*>([\d,]+|n/a)</td><td[^>]*>([\d,]+|n/a)</td></tr>"
)


def _to_float(token: str) -> float | None:
    if token == "n/a":
        return None
    return float(token.replace(",", ""))


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    html = content.decode("utf-8", errors="ignore")
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for date_str, fcd_raw, retail_raw, wholesale_raw in _ROW_RE.findall(html):
        fcd = _to_float(fcd_raw)
        retail = _to_float(retail_raw)
        wholesale = _to_float(wholesale_raw)
        if fcd is None or retail is None or wholesale is None:
            continue  # skip the month if any of the three series is missing (e.g. early periods)

        dt = datetime.strptime(date_str, "%d %b %y")
        year, period = dt.year, f"{dt.year}-{dt.month:02d}"

        td = round(retail + wholesale + fcd, 2)
        ratio = round((fcd / td) * 100, 2) if td else None

        for indicator, value in (("FCD", round(fcd, 2)), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    if not rows:
        logger.warning("[%s] No rows parsed from BoE IADB response", country_code)

    return pd.DataFrame(rows, columns=["country_code", "year", "period", "indicator", "value", "updated_at"])
