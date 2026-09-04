"""Slovakia: Národná banka Slovenska(NBS) 'Deposits and loans received – sector break-down'
(v5-12a statistical form), monthly xls/xlsx time series.
https://nbs.sk/en/statistics/financial-institutions/banks/statistical-data-of-monetary-financial-institutions/deposits/

The page itself is server-rendered plain HTML (no JS rendering needed, can be parsed directly
with requests; the requires_js=true flag stored in targets.json turned out to be inaccurate), so
we fetch the page and parse, from the table in the "Deposits and loans received – sector
break-down" section, a grid of year(row) x month (roman numerals I~XII, each a separate file
link). The links come in two mixed forms: recent files use
`https://nbs.sk/dokument/{uuid}/stiahnut/?force=true` (UUID-based CMS download), while older
files (up to roughly 2022) use the direct path `https://nbs.sk/_img/Documents/STATIST/ZSU/
v5-12/v5-12a@YYYYMM.xls(x)`. Both forms are extracted directly from the page HTML, so there is
no need to guess the URL pattern.

The file format falls into three generations depending on the period (confirmed empirically):
    1) 2005-2008 annual archives (`v5-12a@YYYY.xls`, one file per year with monthly sheets):
       pre-euro layout entirely, using a three-currency SKK/EUR/OFC scheme with a completely
       different structure. This parser does not handle it (see "Known gaps" below).
    2) 2009-01 to 2011-12: row-based layout with "SECTORS"/"Currency" headers. Sectors are rows,
       and currency (EUR/CM) repeats as a pair of two rows per sector. The TOTAL(EUR)/(CM) row
       pair immediately following the "EURO area - Domestic" row group is the aggregate across
       all resident sectors. The DEPOSITS TOTAL value sits in column C (0-indexed 2), confirmed
       via header text containing both 'DEPOSITS' and 'TOTAL'. TD = EUR value + CM value,
       FCD = CM value (all foreign currencies combined into one figure).
    3) 2012-01 to present: label-based layout with a "row no." header (row labels such as
       'Total deposits'/'Deposits in EUR'/'Deposits in foreign currency' directly identify the
       indicator). Column order from left to right is TOTAL (worldwide aggregate) ->
       [an 'Euro area' column inserted from around 2016 onward] -> Domestic (aggregate across
       residents, with subsequent columns breaking this resident total down by sector). Because
       the presence of the 'Euro area' column shifts the position of the "Domestic" total column
       (around 2012-2015: the column right after TOTAL; from 2016 on: the column after TOTAL,
       Euro area), the position is located dynamically for every file by searching the header
       text for the strings 'all sectors'/'euro area'. TD = the Domestic column of the
       'Total deposits' row, FCD = the Domestic column of the 'Deposits in foreign currency' row.
       As a safeguard, every file is validated by checking that the 'Deposits in EUR' row value
       plus FCD matches TD (within rounding tolerance); on a mismatch (meaning the Domestic
       column was misidentified) that month is silently skipped (this project's principle that
       missing data is safer than wrong data).

Known gaps: 2005-2008 (pre-euro, SKK-denominated) is excluded from this implementation's scope
because the currency definitions themselves differ (SKK is the domestic currency, and EUR also
counts as "foreign currency") and the layout is an entirely different, third format. From
2009-01 onward the euro is already the domestic currency, so the FCD/TD definitions are
consistent with the current ones (no discontinuity).

Review of the ECB SDMX BSI API: for Slovakia (SK), the resident total-deposits-type series
(BS_COUNT_SECTOR=2000, Non-MFIs, COUNT_AREA=U6 Domestic) exists only with
CURRENCY_TRANS=Z01 (All currencies combined) and has no EUR/foreign-currency breakdown
(confirmed empirically: querying `M.SK.N.A.L20.A.1.U6.2000..` returns only Z01). Narrower
subsectors such as NFC (2240) do have a currency breakdown, but that is not the general
all-resident-sectors basis, so this implementation uses the original NBS files directly instead.

xlrd 2.x gives up parsing and raises an exception when it encounters a specific token (0x2d
AreaN) inside a NAME definition (macro/workbook named range) in some of this site's older .xls
files (a workbook-metadata parsing failure unrelated to the actual cell data). We work around
this by temporarily monkey-patching `xlrd.book.evaluate_name_formula` to a no-op within this
module only (restored immediately after the call).
"""

import re
import time
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # Not a single file download, since we need to iterate over multiple monthly files on the page.

DEPOSITS_PAGE_URL = (
    "https://nbs.sk/en/statistics/financial-institutions/banks/"
    "statistical-data-of-monetary-financial-institutions/deposits/"
)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_SECTION_START = "Deposits and loans received – sector break-down"
_SECTION_END = "Deposits and loans received – break-down by economic activity"

_ROMAN = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_YEAR_CELL_RE = re.compile(r"^\s*<t[hd][^>]*>\s*(\d{4})\s*</t[hd]>")
_LINK_CELL_RE = re.compile(r'<a href="([^"]+)"[^>]*>\s*([IVX]+)\s*<')

_REL_TOL = 0.02  # Tolerance for the Domestic-column consistency check (absorbs rounding/thousands-place differences)

_OLE_SIG = b"\xd0\xcf\x11\xe0"  # Legacy .xls (OLE) signature
_ZIP_SIG = b"PK"  # Modern .xlsx (ZIP) signature


def _download_file(url: str, retries: int = 4, backoff: float = 1.5) -> bytes | None:
    """Confirmed empirically: nbs.sk's WAF intermittently blocks even legitimate requests with a
    403 (HTML error page) (retrying the same URL repeatedly mostly succeeds -> assumed to be a
    transient rate limit). Retries whenever the response doesn't actually start with an
    xls/xlsx signature (i.e. a WAF block page or similar)."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            if resp.status_code == 200 and resp.content[:2] == _ZIP_SIG:
                return resp.content
            if resp.status_code == 200 and resp.content[:4] == _OLE_SIG:
                return resp.content
        except requests.RequestException:
            pass
        time.sleep(backoff * (attempt + 1))
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SVK is handled via render() (must iterate over multiple monthly files)")


def _extract_month_links(html: str) -> dict[tuple[int, int], str]:
    """Extracts the (year, month) -> file URL mapping from the 'sector break-down' section.
    The 2005-2008 annual archives (a separate table with a completely different layout) are
    deliberately excluded."""
    import html as htmlmod

    i0 = html.find(_SECTION_START)
    i1 = html.find(_SECTION_END)
    if i0 == -1 or i1 == -1 or i1 <= i0:
        return {}
    section = htmlmod.unescape(html[i0:i1])

    tables = re.findall(r"<table.*?</table>", section, re.S)
    if not tables:
        return {}

    result: dict[tuple[int, int], str] = {}
    for row_html in _ROW_RE.findall(tables[0]):
        year_m = _YEAR_CELL_RE.match(row_html)
        if not year_m:
            continue
        year = int(year_m.group(1))
        for href, roman in _LINK_CELL_RE.findall(row_html):
            month = _ROMAN.get(roman)
            if month:
                result[(year, month)] = href
    return result


def _matrix_from_bytes(content: bytes) -> list[list]:
    """Converts xlsx/xls bytes into a 2D list of cell values."""
    if content[:2] == b"PK":
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
        ws = wb.worksheets[0]
        return [[cell for cell in row] for row in ws.iter_rows(values_only=True)]

    import xlrd
    import xlrd.book as xlrd_book

    original = xlrd_book.evaluate_name_formula
    xlrd_book.evaluate_name_formula = lambda *a, **k: None
    try:
        wb = xlrd.open_workbook(file_contents=content, ignore_workbook_corruption=True)
    finally:
        xlrd_book.evaluate_name_formula = original
    ws = wb.sheet_by_index(0)
    return [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]


def _norm(v) -> str:
    return " ".join(str(v).split()).strip().lower() if isinstance(v, str) else ""


def _find_header_end(matrix: list[list]) -> int | None:
    """Finds the index of the column-number row shaped like 'a', 'b', 1, 2, 3 ... (a marker of the new format)."""
    for r, row in enumerate(matrix):
        if len(row) >= 2 and _norm(row[0]) == "a" and _norm(row[1]) == "b":
            return r
    return None


def _find_domestic_column(matrix: list[list], header_end: int) -> tuple[int | None, int | None]:
    """Locates the 'all sectors' (TOTAL column) and, if present, the 'euro area' column in the
    header text, and dynamically computes the position of the resident (Domestic) total column.
    Returns (domestic_col, total_col)."""
    ncols = max((len(r) for r in matrix[:header_end]), default=0)
    col_text = []
    for c in range(ncols):
        parts = [_norm(matrix[r][c]) for r in range(header_end) if c < len(matrix[r])]
        col_text.append(" ".join(p for p in parts if p))

    col_total = next((c for c in range(2, ncols) if "all sectors" in col_text[c]), None)
    if col_total is None:
        return None, None

    col_ea = next((c for c in range(col_total + 1, ncols) if "euro area" in col_text[c]), None)
    domestic_col = (col_ea + 1) if col_ea is not None else (col_total + 1)
    if domestic_col >= ncols:
        return None, col_total
    return domestic_col, col_total


def _parse_new_format(matrix: list[list], year: int, month: int, country_code: str, now: str) -> list[dict]:
    header_end = _find_header_end(matrix)
    if header_end is None:
        return []

    domestic_col, _ = _find_domestic_column(matrix, header_end)
    if domestic_col is None:
        logger.warning("[%s] %04d-%02d: could not find Domestic column, skipping", country_code, year, month)
        return []

    td_val = fcd_val = eur_val = None
    for row in matrix[header_end + 1:]:
        if not row or domestic_col >= len(row):
            continue
        label = _norm(row[0])
        if label == "total deposits" and td_val is None:
            td_val = row[domestic_col]
        elif label == "deposits in eur" and eur_val is None:
            eur_val = row[domestic_col]
        elif label == "deposits in foreign currency" and fcd_val is None:
            fcd_val = row[domestic_col]

    if not all(isinstance(v, (int, float)) for v in (td_val, fcd_val, eur_val)):
        logger.warning("[%s] %04d-%02d: could not find required rows (Total/EUR/foreign currency), skipping",
                        country_code, year, month)
        return []

    # Consistency check: EUR + foreign currency == total (mismatch means the Domestic column was misidentified)
    if abs((eur_val + fcd_val) - td_val) > max(1.0, abs(td_val) * _REL_TOL):
        logger.warning("[%s] %04d-%02d: EUR+FCD != TD (likely Domestic column misidentification), skipping",
                        country_code, year, month)
        return []

    return _rows(country_code, year, month, td_val, fcd_val, now)


def _parse_old_format(matrix: list[list], year: int, month: int, country_code: str, now: str) -> list[dict]:
    # First check whether the "SECTORS" / "Currency" / "DEPOSITS" headers are present (avoids false-positive format detection)
    has_marker = any(
        any(_norm(v) == "deposits" for v in row) and any(_norm(v) == "sectors" for v in row)
        for row in matrix[:15]
    )
    if not has_marker:
        return []

    section_row = next(
        (r for r, row in enumerate(matrix) if row and _norm(row[0]) == "euro area - domestic"),
        None,
    )
    if section_row is None or section_row + 2 >= len(matrix):
        logger.warning("[%s] %04d-%02d: could not find the 'EURO area - Domestic' section, skipping",
                        country_code, year, month)
        return []

    eur_row = matrix[section_row + 1]
    cm_row = matrix[section_row + 2]
    if _norm(eur_row[1]) != "eur" or _norm(cm_row[1]) != "cm":
        logger.warning("[%s] %04d-%02d: could not find the Domestic TOTAL row pair (EUR/CM), skipping",
                        country_code, year, month)
        return []

    eur_val, cm_val = eur_row[2], cm_row[2]
    if not all(isinstance(v, (int, float)) for v in (eur_val, cm_val)):
        return []

    td_val = eur_val + cm_val
    fcd_val = cm_val
    return _rows(country_code, year, month, td_val, fcd_val, now)


def _rows(country_code: str, year: int, month: int, td: float, fcd: float, now: str) -> list[dict]:
    period = f"{year}-{month:02d}"
    td = round(float(td), 2)
    fcd = round(float(fcd), 2)
    ratio = round((fcd / td) * 100, 2) if td else None
    out = []
    for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
        if value is None:
            continue
        out.append({
            "country_code": country_code, "year": year, "period": period,
            "indicator": indicator, "value": value, "updated_at": now,
        })
    return out


def _parse_month(content: bytes, year: int, month: int, country_code: str, now: str) -> list[dict]:
    try:
        matrix = _matrix_from_bytes(content)
    except Exception:
        logger.exception("[%s] %04d-%02d file parsing failed (workbook open error), skipping", country_code, year, month)
        return []

    rows = _parse_new_format(matrix, year, month, country_code, now)
    if rows:
        return rows
    return _parse_old_format(matrix, year, month, country_code, now)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    page_html = None
    for attempt in range(5):
        try:
            resp = requests.get(DEPOSITS_PAGE_URL, headers=_HEADERS, timeout=30)
            if resp.status_code == 200:
                page_html = resp.text
                break
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    if page_html is None:
        logger.warning("[%s] deposits page request failed (assumed temporary WAF block, retries exhausted)", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    links = _extract_month_links(page_html)
    if not links:
        logger.warning("[%s] found no monthly file links on the deposits page", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    all_rows: list[dict] = []
    for (year, month), url in sorted(links.items()):
        content = _download_file(url)
        if content is None:
            logger.warning("[%s] %04d-%02d file download failed (retries exhausted), skipping", country_code, year, month)
            continue
        all_rows.extend(_parse_month(content, year, month, country_code, now))

    if not all_rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    df = df.sort_values(["period", "indicator"]).reset_index(drop=True)
    return df
