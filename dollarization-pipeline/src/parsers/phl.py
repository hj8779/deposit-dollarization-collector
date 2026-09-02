"""Philippines: BSP deposit liabilities — FCD / TD absolute stocks.

Sources (direct Excel downloads, auto-updated by BSP):

1) Philippine Banking System Balance Sheet (latest / long monthly):
   https://www.bsp.gov.ph/Statistics/Financial%20Statements/Balance%20Sheet/historical_frp%203.xlsx
   Sheet "PBS BS", amounts in thousand pesos.
   Excel row 54 (0-index 53): DEPOSIT LIABILITIES          → TD
   Excel row 60 (0-index 59): Foreign Currency (deposits) → FCD
   Span ~2008-03 … present (monthly).

2) Depository Corporations Survey (pre-SRF) for history before FRP:
   https://www.bsp.gov.ph/Statistics/Financial%20System%20Accounts/dcs.xls
   Sheet "DCS Pre SRF template", levels in million pesos.
   FCD = Transferable and Other Deposits in Foreign Currency (FCD-Residents)
   TD  = (M1 − currency outside DC) + Quasi-Money + FCD-Residents
         i.e. peso deposit liabilities in broad money + resident FCD
   Span ~2001-12 … ~2014-06.

Merge: DCS fills pre-FRP months; FRP wins on overlap (banking-system deposit
liabilities, continuous to present). Stored unit: **million PHP**.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import numpy as np
import pandas as pd
import requests
import urllib3

from src.utils.fcd_series import empty_frame, long_rows, merge_frames
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_DCS_URL = (
    "https://www.bsp.gov.ph/Statistics/Financial%20System%20Accounts/dcs.xls"
)
_FRP_URL = (
    "https://www.bsp.gov.ph/Statistics/Financial%20Statements/"
    "Balance%20Sheet/historical_frp%203.xlsx"
)
_FRP_URL_ALT = (
    "https://www.bsp.gov.ph/Statistics/Financial Statements/"
    "Balance Sheet/historical_frp 3.xlsx"
)

# FRP: 0-based row indices (Excel rows 54 / 60)
_FRP_ROW_TD = 53  # deposit_liab — DEPOSIT LIABILITIES
_FRP_ROW_FCD = 59  # deposit_liab_foreign — Foreign Currency
_FRP_DATE_ROW = 9
_FRP_DATA_COL0 = 2

# DCS: 0-based rows in levels block
_DCS_DATE_ROW = 4
_DCS_DATA_COL0 = 6
_DCS_ROW_FCD = 30  # FCD-Residents
_DCS_ROW_M1 = 27
_DCS_ROW_QUASI = 28
_DCS_ROW_CURRENCY = 37  # Currency outside depository corporations

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Parse whichever file is passed (by magic / content). Prefer render()."""
    if content[:2] == b"PK":
        return _parse_frp(content, country_code)
    return _parse_dcs(content, country_code)


def _empty() -> pd.DataFrame:
    return empty_frame()


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
        if r.status_code != 200 or len(r.content) < 5_000:
            return None
        return r.content
    except Exception as e:
        logger.debug("[PHL] download %s: %s", url[-40:], e)
        return None


def _period_ym(ts: pd.Timestamp) -> str:
    return f"{ts.year}-{ts.month:02d}"


def _parse_frp(content: bytes, country_code: str) -> pd.DataFrame:
    """PBS Balance Sheet → FCD/TD in million PHP."""
    try:
        df = pd.read_excel(BytesIO(content), header=None, engine="openpyxl")
    except Exception:
        df = pd.read_excel(BytesIO(content), header=None)

    # Locate rows by stable codes / labels if layout shifts
    fcd_row, td_row = _FRP_ROW_FCD, _FRP_ROW_TD
    for i in range(min(90, len(df))):
        key = str(df.iloc[i, 0] or "").strip().lower()
        lab = str(df.iloc[i, 1] or "").strip().lower()
        if key == "deposit_liab" or lab == "deposit liabilities":
            td_row = i
        if key == "deposit_liab_foreign":
            fcd_row = i
        elif lab == "foreign currency" and td_row is not None and abs(i - td_row) <= 10:
            fcd_row = i

    date_row = _FRP_DATE_ROW
    for i in range(min(15, len(df))):
        if any(isinstance(v, (datetime, pd.Timestamp)) for v in df.iloc[i, 2:8].values):
            date_row = i
            break

    dates = pd.to_datetime(df.iloc[date_row, _FRP_DATA_COL0:], errors="coerce")
    fcd = pd.to_numeric(df.iloc[fcd_row, _FRP_DATA_COL0:], errors="coerce")
    td = pd.to_numeric(df.iloc[td_row, _FRP_DATA_COL0:], errors="coerce")
    # thousand pesos → million PHP
    fcd = fcd / 1000.0
    td = td / 1000.0

    obs: list[tuple[str, float, float]] = []
    for d, f, t in zip(dates, fcd, td):
        if pd.isna(d) or pd.isna(f) or pd.isna(t):
            continue
        ts = pd.Timestamp(d)
        if t <= 0 or f < 0 or f > t * 1.05:
            continue
        # sanity: banking deposits millions PHP — order 1e5–1e8
        if t < 100_000 or t > 5e8:
            continue
        ratio = f / t
        if ratio < 0.02 or ratio > 0.50:
            continue
        obs.append((_period_ym(ts), float(f), float(t)))

    if not obs:
        logger.warning("[PHL] FRP: no observations (fcd_row=%s td_row=%s)", fcd_row, td_row)
        return _empty()

    out = long_rows(country_code, obs)
    logger.info(
        "[PHL] FRP → %d rows (%s~%s) fcd_row=%d td_row=%d",
        len(out),
        out["period"].min(),
        out["period"].max(),
        fcd_row,
        td_row,
    )
    return out


def _parse_dcs_date(v) -> pd.Timestamp | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (datetime, pd.Timestamp, np.datetime64)):
        ts = pd.Timestamp(v)
        # early columns are month-start → month-end
        if ts.day == 1:
            ts = ts + pd.offsets.MonthEnd(0)
        return ts
    s = str(v).strip()
    # "Jun 14 p", "Dec 13 r", "Apr 14 "
    m = re.match(r"([A-Za-z]{3})\s+(\d{2})\s*[prPR]?", s)
    if m:
        try:
            ts = pd.Timestamp(f"20{m.group(2)}-{m.group(1)}-01") + pd.offsets.MonthEnd(0)
            return ts
        except Exception:
            return None
    try:
        ts = pd.Timestamp(v)
        if ts.day == 1:
            ts = ts + pd.offsets.MonthEnd(0)
        return ts
    except Exception:
        return None


def _parse_dcs(content: bytes, country_code: str) -> pd.DataFrame:
    """DCS pre-SRF → FCD/TD in million PHP (pre-FRP history)."""
    try:
        df = pd.read_excel(BytesIO(content), header=None)
    except Exception as e:
        logger.warning("[PHL] DCS read failed: %s", e)
        return _empty()

    # Locate key rows by label text
    fcd_row = _DCS_ROW_FCD
    m1_row = _DCS_ROW_M1
    quasi_row = _DCS_ROW_QUASI
    curr_row = _DCS_ROW_CURRENCY
    for i in range(min(50, len(df))):
        blob = " ".join(
            str(df.iloc[i, c]) for c in range(1, 6) if pd.notna(df.iloc[i, c])
        ).lower()
        if "fcd-residents" in blob or (
            "foreign currency" in blob and "transferable and other deposits" in blob
        ):
            fcd_row = i
        if "narrow money, m1" in blob or blob.strip().endswith("narrow money, m1)"):
            m1_row = i
        if "quasi-money" in blob and "other deposits" in blob and "growth" not in blob:
            if i < 50:
                quasi_row = i
        if "currency outside depository" in blob or "currency in circulation" in blob:
            if i < 50 and "gdp" not in blob:
                curr_row = i

    dates_raw = df.iloc[_DCS_DATE_ROW, _DCS_DATA_COL0:]
    fcd = pd.to_numeric(df.iloc[fcd_row, _DCS_DATA_COL0:], errors="coerce")
    m1 = pd.to_numeric(df.iloc[m1_row, _DCS_DATA_COL0:], errors="coerce")
    quasi = pd.to_numeric(df.iloc[quasi_row, _DCS_DATA_COL0:], errors="coerce")
    curr = pd.to_numeric(df.iloc[curr_row, _DCS_DATA_COL0:], errors="coerce")

    obs: list[tuple[str, float, float]] = []
    for d_raw, f, m1v, q, c in zip(dates_raw, fcd, m1, quasi, curr):
        ts = _parse_dcs_date(d_raw)
        if ts is None or pd.isna(f):
            continue
        # TD = peso deposits (M1 − currency + quasi) + FCD
        if pd.isna(m1v) or pd.isna(q) or pd.isna(c):
            continue
        peso_dep = float(m1v) - float(c) + float(q)
        td = peso_dep + float(f)
        if td <= 0 or f < 0 or f > td * 1.05:
            continue
        if td < 50_000 or td > 5e8:  # million PHP
            continue
        ratio = float(f) / td
        if ratio < 0.02 or ratio > 0.50:
            continue
        obs.append((_period_ym(ts), float(f), float(td)))

    if not obs:
        logger.warning("[PHL] DCS: no observations")
        return _empty()

    out = long_rows(country_code, obs)
    logger.info(
        "[PHL] DCS → %d rows (%s~%s)",
        len(out),
        out["period"].min(),
        out["period"].max(),
    )
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        frames: list[pd.DataFrame] = []

        # 1) DCS historical (fills pre-2008; FRP overrides overlap)
        dcs_bytes = _download(_DCS_URL)
        if dcs_bytes:
            dcs_df = _parse_dcs(dcs_bytes, country_code)
            if dcs_df is not None and not dcs_df.empty:
                frames.append(dcs_df)
        else:
            logger.warning("[PHL] DCS download failed")

        # 2) FRP banking-system deposits (primary, latest)
        frp_bytes = _download(_FRP_URL) or _download(_FRP_URL_ALT)
        if frp_bytes:
            frp_df = _parse_frp(frp_bytes, country_code)
            if frp_df is not None and not frp_df.empty:
                frames.append(frp_df)
        else:
            logger.warning("[PHL] FRP download failed")

        if not frames:
            logger.error("[%s] no BSP excel sources parsed", country_code)
            return _empty()

        # later frame wins on period overlap → FRP last
        out = merge_frames(*frames)
        logger.info(
            "[%s] merged %d rows (%s~%s)",
            country_code,
            len(out),
            out["period"].min() if len(out) else "-",
            out["period"].max() if len(out) else "-",
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
