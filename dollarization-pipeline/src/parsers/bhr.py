"""Bahrain: the CBB (Central Bank of Bahrain) Publications page has a 'Statistical Bulletin'
section where a separate xlsx (2016-12~) / xls (2010-12~2015-12, year-end editions only) file
is posted each month. From 2020-01 onward a file is posted every month, but before that
(2010-12~2019-12) only the December (year-end) edition survives — i.e. monthly coverage is
available from 2020 onward, and only one annual snapshot per year before that. Before 2010-12
(2001~2009) there is no xls/xlsx, only PDFs; as described below, we also collect and merge in
those PDFs to extend coverage.

Sheet: the 'Deposit Liabilities to Non-Banks' table (the sheet is found dynamically in each
file by its title text — the tab number varies by period: '17'/'18' in 2010~2015, '18' in
2016~2023, '19' in 2026, etc., as tables are added/removed and everything shifts). Note that
tab '17' can be a completely different table depending on the period (e.g. 'Assets by
Currency'), so it must always be located by title, never by tab number.

Before 2010-12 (the period with no monthly xls/xlsx), data is extracted from PDFs posted in the
same 'Statistical Bulletin' section (filenames are extremely irregular — 'MSB-Dec2011.pdf' /
'QSB Dec 2007.pdf' / 'dec_2001.pdf', etc. — the month/year notation differs per file, so the
period cannot be trusted from the filename). Fortunately the table itself has the same
structure as the xlsx and can be extracted as text (pdfplumber's extract_tables() cleanly pulls
out a 4-row merged header + annual block + quarterly block + monthly block, 7 rows total), with
each cell containing values for multiple periods separated by newlines (e.g. one cell in the
monthly block holds 13 lines like 'Dec.\nJan.\nFeb....'). The table's last row is always the
monthly block, so only that row is used. Each PDF's monthly block covers the 13 months prior to
its publication month (so even a year-end-only edition captures the entire year), and iterating
over every PDF in the archive naturally produces overlapping periods that fill in the gaps —
periods already covered by xlsx/xls values take priority (the more reliable, newer format), and
PDFs only supplement periods not covered by xlsx/xls.

Column layout (stable and unchanged from 2001 to the present):
    General Government  BD, FC
    Private Sector Demand   BD, FC
    Private Sector Savings  BD, FC
    Private Sector Time 1/  BD, FC
    (followed by Total, Foreign Deposits, Total Deposits columns, which are not used)
For each item, the column bearing its label (Demand/Savings/Time) is that item's BD column, and
the following column is its FC column — columns are located dynamically per file by label text
(fixed indices must not be used; a separate table, sheet '3', confirms columns can shift
depending on whether a Government row is present, etc.).

TD (total deposits) = sum of BD+FC across Private Sector (Demand+Savings+Time). General
Government is excluded since it isn't part of the private sector (keeping scope consistent with
FCD). FCD = sum of FC across the same three items (the old parser used only Demand FC, but
since Savings/Time are also broken out by currency in this table, a much more accurate total FCD
can now be obtained).

Row structure: annual (col0=year, col1=blank) / quarterly (col1='Q1'..'Q4', year only on the Q1
row, then forward-filled) / monthly (col1='Jan.'..'Dec.', year likewise forward-filled) appear
in that order, one after another, on a single sheet. This parser extracts only the monthly rows
(annual/quarterly are skipped — for older years that only have a December edition and no
monthly data, only that single December 'monthly' row naturally gets captured).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

PUBLICATIONS_URL = "https://www.cbb.gov.bh/publications/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_TITLE = "deposit liabilities to non-banks"
_TITLE_SCAN_ROWS = 8
_HEADER_SCAN_ROWS = range(0, 16)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_LINK_RE = re.compile(r'href="([^"]+\.xlsx?)"')
_PDF_LINK_RE = re.compile(r'href="([^"]+\.pdf)"')


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BHR is handled via render() (iterates over every monthly/annual file posted)")


def _collect_bulletin_links() -> list[str]:
    response = requests.get(PUBLICATIONS_URL, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    html = response.text

    start = html.find('<h2 id="Statistical Bulletin"')
    if start == -1:
        return []
    end = html.find("<h2", start + 10)
    section = html[start:end] if end != -1 else html[start:]

    seen = set()
    links = []
    for url in _LINK_RE.findall(section):
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def _collect_pdf_links() -> list[str]:
    response = requests.get(PUBLICATIONS_URL, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    html = response.text

    start = html.find('<h2 id="Statistical Bulletin"')
    if start == -1:
        return []
    end = html.find("<h2", start + 10)
    section = html[start:end] if end != -1 else html[start:]

    seen = set()
    links = []
    for url in _PDF_LINK_RE.findall(section):
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def _clean_number(text: str) -> float | None:
    text = text.strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_pdf(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber

    now = datetime.now(timezone.utc).isoformat()
    empty = pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            table = None
            for page in pdf.pages:
                text = (page.extract_text() or "").lower()
                if _TITLE not in text:
                    continue
                tables = page.extract_tables()
                if tables and len(tables[0]) >= 5:
                    table = tables[0]
                    break
    except Exception:
        logger.warning("[%s] PDF parsing failed, skipping", country_code)
        return empty

    if table is None:
        return empty

    monthly_row = table[-1]
    if not monthly_row or monthly_row[0] is None:
        return empty

    # Columns: 0=period, 1/2=Government BD/FC, 3/4=Demand BD/FC, 5/6=Savings BD/FC, 7/8=Time BD/FC
    needed_idx = [3, 4, 5, 6, 7, 8]
    if max(needed_idx) >= len(monthly_row) or any(monthly_row[i] is None for i in needed_idx):
        return empty

    period_lines = str(monthly_row[0]).split("\n")
    value_cols = [str(monthly_row[i]).split("\n") for i in needed_idx]
    n = len(period_lines)
    if any(len(vc) != n for vc in value_cols):
        return empty

    rows = []
    current_year = None
    for i, line in enumerate(period_lines):
        m = re.match(r"^\s*(\d{4})\s+(.+?)\.?\s*$", line)
        if m:
            current_year = int(m.group(1))
            month_token = m.group(2)
        else:
            month_token = line
        if current_year is None:
            continue

        month_key = month_token.strip().rstrip(".").lower()[:3]
        month = _MONTHS.get(month_key)
        if month is None:
            continue

        values = [_clean_number(vc[i]) for vc in value_cols]
        if any(v is None for v in values):
            continue
        demand_bd_v, demand_fc_v, savings_bd_v, savings_fc_v, time_bd_v, time_fc_v = values

        fcd = demand_fc_v + savings_fc_v + time_fc_v
        td = demand_bd_v + demand_fc_v + savings_bd_v + savings_fc_v + time_bd_v + time_fc_v
        period = f"{current_year}-{month:02d}"

        rows.append({
            "country_code": country_code, "year": current_year, "period": period,
            "indicator": INDICATOR, "value": round(float(fcd), 4), "updated_at": now,
        })
        rows.append({
            "country_code": country_code, "year": current_year, "period": period,
            "indicator": INDICATOR_TD, "value": round(float(td), 4), "updated_at": now,
        })

    return pd.DataFrame(rows)


def _grid_from_xlsx(content: bytes) -> dict[str, list[list]]:
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    grids = {}
    for name in wb.sheetnames:
        ws = wb[name]
        grids[name] = [
            [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
            for r in range(1, ws.max_row + 1)
        ]
    return grids


def _grid_from_xls(content: bytes) -> dict[str, list[list]]:
    import xlrd

    wb = xlrd.open_workbook(file_contents=content)
    grids = {}
    for name in wb.sheet_names():
        ws = wb.sheet_by_name(name)
        grids[name] = [
            [ws.cell_value(r, c) if ws.cell_value(r, c) != "" else None for c in range(ws.ncols)]
            for r in range(ws.nrows)
        ]
    return grids


def _find_target_grid(grids: dict[str, list[list]]) -> list[list] | None:
    for grid in grids.values():
        for row in grid[:_TITLE_SCAN_ROWS]:
            if not row:
                continue
            cell = str(row[0] or "").strip().lower()
            if _TITLE in cell:
                return grid
    return None


def _find_columns(grid: list[list]) -> dict[str, int] | None:
    cols: dict[str, int] = {}
    for r in _HEADER_SCAN_ROWS:
        if r >= len(grid):
            break
        row = grid[r]
        for c, value in enumerate(row):
            label = str(value or "").strip().lower()
            if label == "demand" and "demand" not in cols:
                cols["demand"] = c
            elif label == "savings" and "savings" not in cols:
                cols["savings"] = c
            elif label.startswith("time") and "time" not in cols:
                cols["time"] = c
        if len(cols) == 3:
            break
    if len(cols) != 3:
        return None
    return cols


def _parse_workbook(content: bytes, country_code: str, is_xls: bool) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()

    try:
        grids = _grid_from_xls(content) if is_xls else _grid_from_xlsx(content)
    except Exception:
        logger.warning("[%s] Workbook parsing failed, skipping", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    grid = _find_target_grid(grids)
    if grid is None:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    cols = _find_columns(grid)
    if cols is None:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    demand_bd, savings_bd, time_bd = cols["demand"], cols["savings"], cols["time"]

    rows = []
    current_year = None
    for row in grid:
        if not row:
            continue
        year_cell = row[0] if len(row) > 0 else None
        month_cell = row[1] if len(row) > 1 else None

        if isinstance(year_cell, (int, float)):
            current_year = int(year_cell)

        if not isinstance(month_cell, str):
            continue
        month_key = month_cell.strip().rstrip(".").lower()[:3]
        month = _MONTHS.get(month_key)
        if month is None or current_year is None:
            continue

        needed = [demand_bd, demand_bd + 1, savings_bd, savings_bd + 1, time_bd, time_bd + 1]
        if max(needed) >= len(row):
            continue
        values = [row[i] for i in needed]
        if not all(isinstance(v, (int, float)) for v in values):
            continue
        demand_bd_v, demand_fc_v, savings_bd_v, savings_fc_v, time_bd_v, time_fc_v = values

        fcd = demand_fc_v + savings_fc_v + time_fc_v
        td = demand_bd_v + demand_fc_v + savings_bd_v + savings_fc_v + time_bd_v + time_fc_v
        period = f"{current_year}-{month:02d}"

        rows.append({
            "country_code": country_code, "year": current_year, "period": period,
            "indicator": INDICATOR, "value": round(float(fcd), 4), "updated_at": now,
        })
        rows.append({
            "country_code": country_code, "year": current_year, "period": period,
            "indicator": INDICATOR_TD, "value": round(float(td), 4), "updated_at": now,
        })

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    links = _collect_bulletin_links()
    logger.info("[%s] Found %d Statistical Bulletin files", country_code, len(links))

    frames = []
    for url in links:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=30)
            response.raise_for_status()
        except Exception:
            logger.warning("[%s] Download failed, skipping: %s", country_code, url)
            continue

        df = _parse_workbook(response.content, country_code, is_xls=url.lower().endswith(".xls"))
        if not df.empty:
            frames.append(df)

    if not frames:
        xlsx_df = pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])
    else:
        # links has the newest files first, so when the same period appears in multiple files
        # (to reflect revisions), the value from the more recently posted file takes priority.
        xlsx_df = pd.concat(frames, ignore_index=True)
        xlsx_df = xlsx_df.drop_duplicates(subset=["period", "indicator"], keep="first")

    covered_periods = set(xlsx_df["period"]) if not xlsx_df.empty else set()

    pdf_links = _collect_pdf_links()
    logger.info("[%s] Found %d Statistical Bulletin PDF files (to supplement periods before 2010-12)", country_code, len(pdf_links))

    pdf_frames = []
    for url in pdf_links:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=30)
            response.raise_for_status()
        except Exception:
            logger.warning("[%s] PDF download failed, skipping: %s", country_code, url)
            continue

        df = _parse_pdf(response.content, country_code)
        if not df.empty:
            pdf_frames.append(df)

    if pdf_frames:
        pdf_df = pd.concat(pdf_frames, ignore_index=True)
        pdf_df = pdf_df.drop_duplicates(subset=["period", "indicator"], keep="first")
        # Periods already covered by xlsx/xls are not overwritten, since that format is more reliable and up to date.
        pdf_df = pdf_df[~pdf_df["period"].isin(covered_periods)]
        merged = pd.concat([xlsx_df, pdf_df], ignore_index=True)
    else:
        merged = xlsx_df

    if merged.empty:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    return merged.sort_values(["period", "indicator"]).reset_index(drop=True)
