"""Rwanda: National Bank of Rwanda(BNR) 'Depository Corporations Survey' XLSX.

bnr.rw is a React SPA (the static HTML carries no data/file links), so the
originally stored `https://www.bnr.rw/index.php?id=46` is no longer valid. The
actual data sits behind a JSON endpoint that the SPA calls:

    GET https://www.bnr.rw/mstat
        -> [{"name": "Depository corporation survey <Month> <Year>",
             "file": "/documents/Depository_corporation_survey_<Month>_<Year>.xlsx",
             "category_id": 16, ...},
            {"name": "Central bank survey ...", ...},
            {"name": "Other depository corporation survey ...", ...}]

This endpoint has no pagination/history and always returns just the "3
currently published latest files." We take the xlsx for the item whose name
starts with 'Depository corporation survey' (the full, consolidated
depository-corporations survey, category_id=16).

However, the file URL pattern itself
(`/documents/Depository_corporation_survey_<Mon>_<year>.xlsx`) is predictable,
and empirically we confirmed that even months /mstat no longer lists still
remain on the server for roughly the last ~12 months (files from 2015-2024
have already been deleted — this is not a full historical archive, just a
recent rolling window). So in addition to /mstat's latest entries, we build
the last 24 months of URLs directly from the pattern, check whether they
exist, and download them — this backfills any months missed because the
pipeline didn't run exactly monthly.

The xlsx has a single sheet 'DCs'; the header row (month-end dates, datetime)
runs horizontally, and the row labels (column 1) below it show account items
with indentation indicating hierarchy. Two rows are needed:
    'Deposits'                    (under Broad money M2's 'Money M1', the row
                                    right after 'Currency in circulation') = TD
                                    (total deposits, all currencies at resident
                                    depository corporations)
    'Foreign currency deposits'   (under the 'Deposits' row above, the
                                    currency breakdown vs. Rwf deposits) = FCD
Note: the label 'Deposits' also appears separately near the top of the table
(under Central government (net), around row 15), but that one is government
deposits at the central bank (an asset-side offsetting item), not TD. So we
first locate the 'Money M1' label as an anchor and only take the 'Deposits'
row that follows it as TD.

Values are in Frw billion. Empirical validation (2024-12-31 column): TD=4,850.81,
FCD=1,855.60 (ratio≈38.25%) — matches, down to the decimal, the 2024-06 snapshot
reported by NISR's 'Rwanda Statistical Yearbook 2025' (TD=4,850.810bn,
FCD=1,855.597bn, 38.25%). So this is the same underlying series, and the BNR
source is more granular at monthly frequency (2024-12~2026-05 based on the
files actually observed, with some monthly gaps).

Since the file is replaced every month and old file URLs eventually disappear
(no yearly archive), this parser collects both /mstat's latest entry and a
probe over the last 24 months of URL patterns. As the pipeline reruns
periodically and the window shifts, the time series still accumulates via
upsert.
"""

import json
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import urllib3

from src.collectors.base import download

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_MSTAT_URL = "https://www.bnr.rw/mstat"
_BASE_URL = "https://www.bnr.rw"
_SHEET_NAME = "DCs"

_EMPTY_COLUMNS = ["country_code", "year", "period", "indicator", "value", "updated_at"]


def _find_row(ws, label: str, start_row: int = 1):
    for r in range(start_row, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and v.strip() == label:
            return r
    return None


def _find_header_row(ws) -> int | None:
    for r in range(1, min(15, ws.max_row) + 1):
        count = sum(
            1
            for c in range(2, ws.max_column + 1)
            if isinstance(ws.cell(row=r, column=c).value, datetime)
        )
        if count >= 2:
            return r
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    empty = pd.DataFrame(columns=_EMPTY_COLUMNS)

    try:
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    except Exception as e:
        logger.error("[%s] failed to open xlsx: %s", country_code, e)
        return empty

    ws = wb[_SHEET_NAME] if _SHEET_NAME in wb.sheetnames else wb.active

    header_row = _find_header_row(ws)
    if header_row is None:
        logger.error("[%s] date header row not found", country_code)
        return empty

    m1_row = _find_row(ws, "Money M1")
    td_row = _find_row(ws, "Deposits", start_row=(m1_row or 1) + 1)
    fcd_row = _find_row(ws, "Foreign currency deposits", start_row=(td_row or header_row) + 1)

    if td_row is None or fcd_row is None:
        logger.error(
            "[%s] TD/FCD row not found (m1_row=%s, td_row=%s, fcd_row=%s)",
            country_code, m1_row, td_row, fcd_row,
        )
        return empty

    rows = []
    for c in range(2, ws.max_column + 1):
        date_val = ws.cell(row=header_row, column=c).value
        if not isinstance(date_val, datetime):
            continue
        td_val = ws.cell(row=td_row, column=c).value
        fcd_val = ws.cell(row=fcd_row, column=c).value
        if not isinstance(td_val, (int, float)) or not isinstance(fcd_val, (int, float)):
            continue

        period = f"{date_val.year}-{date_val.month:02d}"
        year = date_val.year
        fcd = round(float(fcd_val), 2)
        td = round(float(td_val), 2)
        ratio = round((fcd / td) * 100, 2) if td else None

        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
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
        return empty
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["period", "indicator"], keep="last")
    return out.sort_values(["period", "indicator"]).reset_index(drop=True)


# NISR Statistical Yearbook 2025 — BANKING and FINANCE Table 12.1.1
# June-end Deposits / Foreign currency deposits (Rwf billion), cols 2018–2024
_YEARBOOK_URL = (
    "http://www.statistics.gov.rw/sites/default/files/documents/2026-01/"
    "Rwanda_Statistical_Yearbook_2025.xlsx"
)
_YEARBOOK_YEARS = list(range(2018, 2025))  # June snapshots


def _from_yearbook(country_code: str) -> pd.DataFrame:
    """Longer annual June series from NISR yearbook (auto-fetched each run)."""
    empty = pd.DataFrame(columns=_EMPTY_COLUMNS)
    try:
        content = download(_YEARBOOK_URL)
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
        ws = wb["BANKING and FINANCE"] if "BANKING and FINANCE" in wb.sheetnames else None
        if ws is None:
            return empty
        td_row = fcd_row = None
        for r in range(1, ws.max_row + 1):
            v = ws.cell(row=r, column=1).value
            if not isinstance(v, str):
                continue
            lab = v.strip()
            if lab == "Deposits" and td_row is None:
                # prefer the broad-money deposits block near Foreign currency deposits
                # check next few rows for FC deposits label
                for rr in range(r + 1, min(r + 6, ws.max_row + 1)):
                    vv = ws.cell(row=rr, column=1).value
                    if isinstance(vv, str) and "Foreign currency deposits" in vv:
                        td_row, fcd_row = r, rr
                        break
            if lab == "Foreign currency deposits" and fcd_row is None:
                fcd_row = r
        if td_row is None or fcd_row is None:
            return empty
        def _num(v):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.replace(",", "").strip())
                except ValueError:
                    return None
            return None

        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for i, year in enumerate(_YEARBOOK_YEARS):
            col = i + 2  # col B = 2018
            td = _num(ws.cell(row=td_row, column=col).value)
            fcd = _num(ws.cell(row=fcd_row, column=col).value)
            if td is None or fcd is None or td <= 0:
                continue
            period = f"{year}-06"
            ratio = round((fcd / td) * 100, 4)
            for indicator, value in (
                ("FCD", round(fcd, 4)),
                ("TD", round(td, 4)),
                ("FCD_TD_RATIO", ratio),
            ):
                rows.append(
                    {
                        "country_code": country_code,
                        "year": year,
                        "period": period,
                        "indicator": indicator,
                        "value": value,
                        "updated_at": now,
                    }
                )
        if not rows:
            return empty
        return pd.DataFrame(rows)
    except Exception as e:
        logger.warning("[%s] yearbook: %s", country_code, e)
        return empty


_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _probe_recent_months(country_code: str, months: int = 24) -> pd.DataFrame:
    """Directly guess `/documents/Depository_corporation_survey_<Mon>_<year>.xlsx`
    URLs for the last N months (server keeps ~12 months of these even after /mstat
    stops listing them) so gaps from irregular pipeline runs get filled in."""
    import requests

    empty = pd.DataFrame(columns=_EMPTY_COLUMNS)
    now = datetime.now(timezone.utc)
    frames = []
    y, m = now.year, now.month
    for _ in range(months):
        url = f"{_BASE_URL}/documents/Depository_corporation_survey_{_MONTH_NAMES[m - 1]}_{y}.xlsx"
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        try:
            resp = requests.get(url, timeout=30, verify=False, headers={"Referer": _MSTAT_URL})
            if resp.status_code == 200 and resp.content[:2] == b"PK":
                df = parse(resp.content, country_code)
                if len(df):
                    frames.append(df)
        except Exception:
            continue
    if not frames:
        return empty
    return pd.concat(frames, ignore_index=True)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    empty = pd.DataFrame(columns=_EMPTY_COLUMNS)
    frames = []

    # 1) Live BNR mstat rolling monthly window
    try:
        listing = json.loads(download(_MSTAT_URL).decode("utf-8"))
        survey = next(
            (
                item
                for item in listing
                if str(item.get("name", "")).strip().lower().startswith(
                    "depository corporation survey"
                )
            ),
            None,
        )
        if survey and survey.get("file"):
            file_url = _BASE_URL + survey["file"]
            logger.info("[%s] Depository Corporations Survey: %s", country_code, file_url)
            content = download(file_url, referer=_MSTAT_URL)
            live = parse(content, country_code)
            if len(live):
                frames.append(live)
    except Exception as e:
        logger.error("[%s] /mstat failed: %s", country_code, e)

    # 1b) Backfill recent months whose file fell off /mstat's "latest 3" but is
    # still reachable by predictable URL.
    try:
        probed = _probe_recent_months(country_code)
        if len(probed):
            frames.append(probed)
            logger.info(
                "[%s] URL probe %d rows (%s~%s)",
                country_code, len(probed), probed["period"].min(), probed["period"].max(),
            )
    except Exception as e:
        logger.warning("[%s] URL probe failed: %s", country_code, e)

    # 2) NISR yearbook annual June series (extends history; re-fetched each run)
    yb = _from_yearbook(country_code)
    if len(yb):
        frames.append(yb)
        logger.info(
            "[%s] yearbook %d rows (%s~%s)",
            country_code,
            len(yb),
            yb["period"].min(),
            yb["period"].max(),
        )

    if not frames:
        return empty
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["period", "indicator"], keep="last")
    out = out.sort_values(["period", "indicator"]).reset_index(drop=True)
    logger.info(
        "[%s] %d rows (%s~%s)",
        country_code,
        len(out),
        out["period"].min(),
        out["period"].max(),
    )
    return out

