"""Seychelles: Central Bank of Seychelles(CBS) 'Monetary Survey.xlsx' (direct StaExcel link from
the Statistics > Statistics Data page), sheet 'Depository Corporation Survey'.

Earlier investigation notes recorded that the site failed to connect due to an SSL/connection
error, but a retry showed the site itself is up (curl passes with default verification), and the
SSLCertVerificationError only occurs on Python's default verify=True path due to a certificate
chain defect (see below; worked around with verify=False). The page itself simply lists numerous
direct xlsx links and requires no JS rendering, so requires_js=false is the correct setting.

'Deposit Distribution.xlsx' (the file the earlier investigation had focused on) actually only
provides a sectoral breakdown (Private/Public) with no currency breakdown (domestic vs. foreign
currency), so it can't be used to derive FCD -> rejected. Instead, the 'Depository Corporation
Survey' sheet in 'Monetary Survey.xlsx' contains exactly the 4 rows needed:
    row 'Transferable Deposits'      (domestic currency, part of M1)
    row 'Fixed Term Deposits'        (domestic currency, part of Quasi Money)
    row 'Savings Deposits'           (domestic currency, part of Quasi Money)
    row 'Foreign Currency Deposits'  (foreign-currency deposits, part of M3) -> FCD

TD (total deposits) = Transferable + Fixed Term + Savings + Foreign Currency
(matches values verified during the research phase, confirmed empirically: 2025-01
Transferable=8112.81, Fixed Term=1837.92, Savings=5239.72, FCD=10268.96 -> TD=25459.4~25460,
FCD/TD~40.33%).

This sheet also contains broader 'Broad Money(M3)'-related liability items, but they include
non-deposit items (Pipeline deposits, Other Items Net, etc.), so they are not used as the TD
denominator - only the 4 deposit-type rows above are summed.

Both row labels and columns (dates) are located dynamically via header text (no fixed indices
used, so it stays robust if the sheet layout changes).

cbs.sc has a certificate chain defect that causes an SSLCertVerificationError on Python's
default verify=True path (curl is lenient and passes; same workaround pattern as
kor.py/jpn.py/twn.py). Since `src.collectors.base.download()` has no verify option, this is
handled via `__RENDER__` + a dedicated requests session, even though it's a single file.
"""

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_XLSX_URL = "https://www.cbs.sc/Downloads/StaExcel/Monetary%20Survey.xlsx"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

_SHEET_NAME = "Depository Corporation Survey"
_HEADER_ROW = 2
_FIRST_DATA_COL = 2

_ROW_LABELS = {
    "transferable deposits": "transferable",
    "fixed term deposits": "fixed_term",
    "savings deposits": "savings",
    "foreign currency deposits": "fcd",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    ws = wb[_SHEET_NAME]

    # 1) Dynamically find the 4 required row numbers by label text.
    row_nums: dict[str, int] = {}
    for r in range(1, ws.max_row + 1):
        label = ws.cell(row=r, column=1).value
        if not isinstance(label, str):
            continue
        key = _ROW_LABELS.get(label.strip().lower())
        if key:
            row_nums[key] = r

    if set(row_nums) != set(_ROW_LABELS.values()):
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for c in range(_FIRST_DATA_COL, ws.max_column + 1):
        date_val = ws.cell(row=_HEADER_ROW, column=c).value
        if not isinstance(date_val, datetime):
            continue

        values = {
            key: ws.cell(row=row_nums[key], column=c).value
            for key in _ROW_LABELS.values()
        }
        if not all(isinstance(v, (int, float)) for v in values.values()):
            continue

        fcd = values["fcd"]
        td = values["transferable"] + values["fixed_term"] + values["savings"] + values["fcd"]
        ratio = round((fcd / td) * 100, 2) if td else None

        year, period = date_val.year, f"{date_val.year}-{date_val.month:02d}"
        for indicator, value in (("FCD", round(fcd, 2)), ("TD", round(td, 2)), ("FCD_TD_RATIO", ratio)):
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

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    response = requests.get(_XLSX_URL, headers=_HEADERS, timeout=30, verify=False)
    response.raise_for_status()
    return parse(response.content, country_code)
