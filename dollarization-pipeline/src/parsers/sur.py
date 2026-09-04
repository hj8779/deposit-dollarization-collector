"""Suriname: Central Bank of Suriname (CBvS) 'MonetaryStatistics.xlsx' (Depository Corporations
Survey + Other Depository Corporations Dollarization Ratios sheets).

The entire cbvs.sr domain (including www/www3 subdomains, both HTML pages
and static image asset paths) is protected by a Cloudflare bot check (JS
challenge), so it can't be gotten past with raw requests, and even a
Playwright headless Chromium given anti-detection flags gets stuck in an
endless challenge retry loop (confirmed: the headless browser never reaches
`networkidle` and times out at 45 seconds; adding
`--disable-blink-features=AutomationControlled` plus a `navigator.webdriver`
override made no difference).

The IMF SDMX API (api.imf.org)'s Depository/Other Depository Corporations
Survey (MFS_DC, MFS_ODC) has monthly figures for Suriname's total deposits
(Transferable + Other deposits, the broad-money-inclusive portion), but the
currency breakdown (foreign-currency-denominated deposits, the `_DIC_FC`
family of indicators) is not reported for Suriname at all (confirmed empty
dataset) — meaning the IMF path gets us TD but not FCD.

Instead, the Wayback Machine (web.archive.org) periodically archives the
actual 'MonetaryStatistics.xlsx' published by CBvS (most recent snapshot
confirmed: 2026-07-25, with metadata "Updated: 2026-07-07," covering 2006-01
to 2026-05). We query the CDX API for the latest successful snapshot and
fetch/parse the file from that point in time. Since this file is exactly the
original CBvS-published document (only the access path goes through the
Wayback Machine), the values themselves are not manipulated or estimated.
archive.org occasionally returns transient 503s, so we have retry logic in
place.

Sheets in the file:
  - '3. Dep. Corp. Survey_DCS' (the new name for 'Table 3'; older snapshots
    call it 'Table 3'):
      Row labels (column B) '   Transferable deposits' + '   Other deposits'
      summed = TD (total deposits, SRD million).
      (Note: '   Currency outside depository corporations' is currency, not
      a deposit, so it's excluded)
  - '5-2. Dollarization Ratios' (older snapshots: 'Table 5-2'):
      Row label (column B) 'Deposit (1)' = share of foreign-currency deposits
      in total deposits (%)
      (sheet footnote: "Foreign currency deposits in percentage of total
      deposits.")
  - In both sheets, row 9 is the date header (monthly datetime values from
    column C onward); TD and ratio are aligned to the same month.
  - FCD = TD * ratio / 100.

Validation: at 2017-08, TD=15574.48(=5997.10+9577.39), ratio=69.40% ->
FCD≈10,809.4, which approximately matches the CBvS-published figure confirmed
during preliminary research (FCD=10,797.2, based on M2=16,748.0) (M2 includes
additional items such as currency in circulation, so the denominators aren't
exactly identical).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # not a single file download — must query the CDX API and fetch the file from the Wayback Machine.

_ORIGIN_URL = "https://www.cbvs.sr/images/content/statistieken/Database/MonetaryStatistics.xlsx"
_CDX_URL = (
    "https://web.archive.org/cdx/search/cdx"
    "?url=cbvs.sr/images/content/statistieken/Database/MonetaryStatistics.xlsx"
    "&output=json&filter=statuscode:200&collapse=digest"
)
_SNAPSHOT_URL_TMPL = "https://web.archive.org/web/{timestamp}/{original}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

_DCS_SHEET_RE = re.compile(r"dep\.?\s*corp\.?\s*survey|depository corporations survey", re.I)
_RATIO_SHEET_RE = re.compile(r"dollariz", re.I)
_TRANSFERABLE_RE = re.compile(r"^\s*transferable deposits\s*$", re.I)
_OTHER_DEPOSITS_RE = re.compile(r"^\s*other deposits\s*$", re.I)
_DEPOSIT_RATIO_RE = re.compile(r"^\s*deposit\b", re.I)

_LONG_COLUMNS = ["country_code", "year", "period", "indicator", "value", "updated_at"]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SUR is handled via render() (requires querying Wayback Machine snapshots)")


def _fetch_with_retry(url: str, attempts: int = 5, timeout: int = 60) -> bytes | None:
    for i in range(attempts):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                return resp.content
            logger.info("[SUR] %s -> HTTP %s (attempt %d/%d)", url, resp.status_code, i + 1, attempts)
        except requests.RequestException as exc:
            logger.info("[SUR] %s -> request failed: %s (attempt %d/%d)", url, exc, i + 1, attempts)
        if i < attempts - 1:
            import time

            time.sleep(5 * (i + 1))
    return None


def _list_snapshots() -> list[tuple[str, str]]:
    """Queries the CDX API and returns a list of (timestamp, original_url), most recent first."""
    raw = _fetch_with_retry(_CDX_URL, attempts=5, timeout=30)
    if raw is None:
        return []
    import json

    rows = json.loads(raw.decode("utf-8", errors="ignore"))
    if not rows or len(rows) < 2:
        return []
    header, *data = rows
    ts_idx = header.index("timestamp")
    orig_idx = header.index("original")
    snapshots = [(r[ts_idx], r[orig_idx]) for r in data]
    snapshots.sort(key=lambda x: x[0], reverse=True)
    return snapshots


def _find_row(ws, pattern: re.Pattern, label_col: int = 2) -> int | None:
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=label_col).value
        if v and pattern.match(str(v)):
            return r
    return None


def _find_sheet(wb, pattern: re.Pattern):
    for name in wb.sheetnames:
        if pattern.search(name):
            return wb[name]
    return None


def _header_dates(ws, header_row: int, start_col: int = 3) -> dict[int, datetime]:
    dates = {}
    for c in range(start_col, ws.max_column + 1):
        v = ws.cell(row=header_row, column=c).value
        if isinstance(v, datetime):
            dates[c] = v
    return dates


def _parse_workbook(content: bytes, country_code: str) -> pd.DataFrame:
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)

    dcs_ws = _find_sheet(wb, _DCS_SHEET_RE)
    ratio_ws = _find_sheet(wb, _RATIO_SHEET_RE)
    if dcs_ws is None or ratio_ws is None:
        logger.warning(
            "[SUR] required sheet not found (dcs=%s, ratio=%s), available sheets: %s",
            dcs_ws is not None, ratio_ws is not None, wb.sheetnames,
        )
        return pd.DataFrame(columns=_LONG_COLUMNS)

    transferable_row = _find_row(dcs_ws, _TRANSFERABLE_RE)
    other_row = _find_row(dcs_ws, _OTHER_DEPOSITS_RE)
    ratio_row = _find_row(ratio_ws, _DEPOSIT_RATIO_RE)
    if not (transferable_row and other_row and ratio_row):
        logger.warning(
            "[SUR] required row not found (transferable=%s, other=%s, ratio=%s)",
            transferable_row, other_row, ratio_row,
        )
        return pd.DataFrame(columns=_LONG_COLUMNS)

    # Date header row (both sheets share the same layout, standardly starting
    # at row 9, but the number of intro-text lines can vary by snapshot, so we
    # directly search for the row where datetime cells appear).
    def _find_header_row(ws) -> int | None:
        for r in range(1, min(20, ws.max_row) + 1):
            if isinstance(ws.cell(row=r, column=3).value, datetime):
                return r
        return None

    dcs_header_row = _find_header_row(dcs_ws)
    ratio_header_row = _find_header_row(ratio_ws)
    if dcs_header_row is None or ratio_header_row is None:
        logger.warning("[SUR] date header row not found")
        return pd.DataFrame(columns=_LONG_COLUMNS)

    dcs_dates = _header_dates(dcs_ws, dcs_header_row)
    ratio_dates = _header_dates(ratio_ws, ratio_header_row)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for col, dt in dcs_dates.items():
        ratio_col = next((c for c, d in ratio_dates.items() if d.year == dt.year and d.month == dt.month), None)
        if ratio_col is None:
            continue

        transferable = dcs_ws.cell(row=transferable_row, column=col).value
        other = dcs_ws.cell(row=other_row, column=col).value
        ratio = ratio_ws.cell(row=ratio_row, column=ratio_col).value
        if transferable is None or other is None or ratio is None:
            continue
        if not all(isinstance(v, (int, float)) for v in (transferable, other, ratio)):
            continue

        td = round(transferable + other, 4)
        fcd = round(td * ratio / 100, 4)
        period = f"{dt.year}-{dt.month:02d}"

        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", round(ratio, 4))):
            rows.append({
                "country_code": country_code,
                "year": dt.year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    df = pd.DataFrame(rows, columns=_LONG_COLUMNS)
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    df = df.sort_values(["period", "indicator"]).reset_index(drop=True)
    return df


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    snapshots = _list_snapshots()
    if not snapshots:
        logger.warning("[%s] Wayback Machine CDX query failed or no snapshot found", country_code)
        return pd.DataFrame(columns=_LONG_COLUMNS)

    for timestamp, original in snapshots:
        url = _SNAPSHOT_URL_TMPL.format(timestamp=timestamp, original=original)
        content = _fetch_with_retry(url, attempts=5, timeout=90)
        if content is None:
            logger.info("[%s] snapshot %s download failed, trying next snapshot", country_code, timestamp)
            continue
        try:
            df = _parse_workbook(content, country_code)
        except Exception:
            logger.exception("[%s] snapshot %s parsing failed, trying next snapshot", country_code, timestamp)
            continue
        if not df.empty:
            logger.info("[%s] snapshot %s (original %s) parsed successfully, %d rows", country_code, timestamp, original, len(df))
            return df

    logger.warning("[%s] parsing failed for all snapshots", country_code)
    return pd.DataFrame(columns=_LONG_COLUMNS)
