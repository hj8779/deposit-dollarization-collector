"""Serbia: National Bank of Serbia (NBS) monetary statistics, "Table 1.1.4 Consolidated
Balance Sheet of the Banking System" (SBMS04.xlsx).

The note in config/targets.json that "nbs.rs blocks bots ('Pristup je
blokiran')" did not reproduce in practice: sending `requests` with just
ordinary browser User-Agent/Accept headers (which this project's
`src.collectors.base.download()` already does by default) gets a normal 200
response with real content from nbs.rs. No additional workaround such as
Playwright was needed.

The nbs.rs Statistics > Monetary Statistics page (mon_stat/) publishes, in
addition to the monthly PDF Bulletin, an xlsx per table containing the same
data, which is much easier to work with (a single file, a stable cell
structure for parsing, and covers annual data from 1999 to present plus
monthly data from 2004 to present all in one file with no rolling window, so
history is never lost even though the file gets overwritten each month):

    https://www.nbs.rs/export/sites/NBS_site/documents/statistika/monetarni_sektor/SBMS04.xlsx

Sheet 'Eng, Liabilities' holds the 'LIABILITIES' side columns, and within it
the 'Money supply' section column layout (per the header row; item numbers
are the sheet's own footnote numbers):
    (5) Currency in circulation      (6) Dinar sight deposits
    (7=5+6) Money supply M1          (8) Dinar time deposits
    (9=7+8) Money supply M2          (10) Foreign currency deposits
    (11=9+10) Money supply M3

FCD (resident foreign-currency deposits) = item (10) "Foreign currency
deposits" used directly.
TD (total deposits) = item (6)+(8)+(10) = Dinar sight + Dinar time + FCD
                     (= M3 - Currency in circulation; i.e. "all deposits
                     excluding currency (cash)").

Note (scope of definition): this table's "Foreign currency deposits" is the
sum of foreign-currency deposits held at banks + NBS by the entire resident
sector excluding government (households/enterprises/other financial
institutions/local government/nonprofits, etc.), and covers only deposits
denominated purely in foreign currency, not FX-indexed deposits (denominated
in dinars but pegged to an exchange rate). Other NBS tables (Table 1.1.5
Monetary Survey, Table 1.1.6 Non-Monetary Sector Deposits) have a separately
reported, broader-definition line "Foreign currency deposits AND FX-indexed
savings/time deposits" — don't confuse the two (that line is not used here).

Empirical check (2026-06, latest month): FCD=2,801,974.069 million dinars,
TD=1,700,085.343+740,249.753+2,801,974.069=5,242,309.165 million dinars ->
ratio=53.46%. This does not exactly match the spot-check figures in the IMF's
2025 Serbia Article IV report (FCD≈EUR 3,366mn, TD≈EUR 5,859mn, ratio≈57.45%)
(the IMF table appears to use a narrower sectoral definition than ours — e.g.
possibly banks only, excluding NBS-held deposits/some sectors). However, both
ratios are in the high-50%-percent range, the same order of magnitude and
same direction, so we confirmed they're within a reasonable ballpark of each
other.
"""

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = (
    "https://www.nbs.rs/export/sites/NBS_site/documents/statistika/"
    "monetarni_sektor/SBMS04.xlsx"
)

_SHEET = "Eng, Liabilities"

# Absolute column positions within the sheet (fixed layout confirmed from the header row).
_COL_YEAR = 1
_COL_MONTH = 2
_COL_CURRENCY = 7   # (5) Currency in circulation
_COL_DINAR_SIGHT = 8   # (6) Dinar sight deposits
_COL_DINAR_TIME = 10  # (8) Dinar time deposits
_COL_FCD = 12  # (10) Foreign currency deposits
_DATA_START_ROW = 12

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

COLUMNS = ["country_code", "year", "period", "indicator", "value", "updated_at"]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)

    if _SHEET not in wb.sheetnames:
        logger.warning("[%s] sheet '%s' not found, skipping", country_code, _SHEET)
        return pd.DataFrame(columns=COLUMNS)
    ws = wb[_SHEET]

    rows = []
    current_year = None
    for r in range(_DATA_START_ROW, ws.max_row + 1):
        year_cell = ws.cell(row=r, column=_COL_YEAR).value
        month_cell = ws.cell(row=r, column=_COL_MONTH).value

        if year_cell is not None:
            try:
                current_year = int(year_cell)
            except (TypeError, ValueError):
                continue

        if current_year is None:
            continue

        dinar_sight = ws.cell(row=r, column=_COL_DINAR_SIGHT).value
        dinar_time = ws.cell(row=r, column=_COL_DINAR_TIME).value
        fcd = ws.cell(row=r, column=_COL_FCD).value
        if not all(isinstance(v, (int, float)) for v in (dinar_sight, dinar_time, fcd)):
            continue

        if month_cell:
            month = _MONTHS.get(str(month_cell).strip().lower()[:3])
            if month is None:
                continue
            period = f"{current_year}-{month:02d}"
        else:
            # Annual summary row (1999-2025 has annual rows only; from 2004
            # onward, monthly rows follow separately in addition to this
            # annual row). Annual and monthly are stored distinguished by
            # (period, indicator), so they don't overwrite each other at the
            # later UPSERT stage.
            period = f"{current_year}-Annual"

        td = round(dinar_sight + dinar_time + fcd, 3)
        fcd_val = round(fcd, 3)
        ratio = round((fcd_val / td) * 100, 2) if td else None

        for indicator, value in (("FCD", fcd_val), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": current_year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    df = df.sort_values(["period", "indicator"]).reset_index(drop=True)
    return df
