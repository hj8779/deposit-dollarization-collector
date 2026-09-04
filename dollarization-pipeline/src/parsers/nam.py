"""Namibia: Bank of Namibia Monetary and Financial Statistics — Set of Table.

Page:
  https://www.bon.com.na/Economic-information/Statistical-information/Monetary-and-fincancial-statistics.aspx

Per-year XLSX (Set of Table YYYY):
  Table II.5 Deposits of Other Depository Corporations
  Unit: N$ Million (end period)

FCD = sum of all "In foreign currency" rows under Total Deposits
      (covers both rows included in and excluded from broad money — all under Total Deposits)
TD  = Total Deposits (code DODCtd)

Merges multiple yearly files to build the monthly time series.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_PAGE = (
    "https://www.bon.com.na/Economic-information/Statistical-information/"
    "Monetary-and-fincancial-statistics.aspx"
)
_BASE = "https://www.bon.com.na"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("NAM fetches the BoN xlsx via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().replace(",", "").replace(" ", "")
        if t in {"", "-", "–", "—"}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _list_set_of_table_urls() -> list[str]:
    """Return getattachment URLs for Set of Table 20xx, newest first."""
    resp = requests.get(_PAGE, headers=_HEADERS, timeout=90, verify=False)
    resp.raise_for_status()
    html = resp.text
    urls: list[tuple[int, str]] = []
    for year in range(2002, 2035):
        marker = f"Set of Table {year}"
        idx = html.find(marker)
        if idx < 0:
            continue
        # attachment immediately after the year label (within next 400 chars)
        chunk = html[idx : idx + 400]
        m = re.search(r'href="(/getattachment/[0-9a-f\-]+/[^"]*)"', chunk, re.I)
        if m:
            urls.append((year, urljoin(_BASE, m.group(1))))
    urls.sort(key=lambda x: x[0], reverse=True)
    return [u for _, u in urls]


def _find_ii5_sheet(xl: pd.ExcelFile) -> str | None:
    for name in xl.sheet_names:
        n = name.lower().replace(" ", "")
        if "ii.5" in n or "ii5" in n or re.search(r"ii\.?\s*5", name, re.I):
            return name
    # fallback: scan first rows for title
    for name in xl.sheet_names:
        try:
            df = xl.parse(name, header=None, nrows=3)
            blob = " ".join(str(x) for x in df.values.ravel() if pd.notna(x)).lower()
            if "deposits of other depository" in blob or "table ii.5" in blob:
                return name
        except Exception:
            continue
    return None


def _parse_ii5(content: bytes, country_code: str) -> pd.DataFrame:
    xl = pd.ExcelFile(BytesIO(content))
    sheet = _find_ii5_sheet(xl)
    if not sheet:
        logger.warning("[NAM] Table II.5 sheet not found in %s", xl.sheet_names)
        return _empty()
    df = xl.parse(sheet, header=None)

    # Period headers: row with Description + datetimes
    period_row = None
    periods: dict[int, str] = {}
    for i in range(min(8, len(df))):
        hits = {}
        for j in range(1, df.shape[1]):
            v = df.iat[i, j]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            if hasattr(v, "year") and hasattr(v, "month"):
                hits[j] = f"{int(v.year)}-{int(v.month):02d}"
            else:
                s = str(v)
                m = re.search(r"(20\d{2})[-/](\d{1,2})", s)
                if m:
                    hits[j] = f"{int(m.group(1))}-{int(m.group(2)):02d}"
        if len(hits) >= 3:
            period_row = i
            periods = hits
            break
    if not periods:
        return _empty()

    # Label column: prefer col 1 (Description), else col 0
    lab_col = 1 if df.shape[1] > 1 else 0
    td_row = None
    fcd_rows: list[int] = []
    for i in range(len(df)):
        lab = str(df.iat[i, lab_col]).strip() if pd.notna(df.iat[i, lab_col]) else ""
        # also check code col
        code = str(df.iat[i, 0]).strip() if pd.notna(df.iat[i, 0]) else ""
        lab_l = lab.lower()
        if lab_l == "total deposits" or code == "DODCtd":
            td_row = i
        if lab_l == "in foreign currency" or re.search(r"fc$", code, re.I):
            # rows whose code ends with fc (foreign currency) under deposits
            if "fc" in code.lower() or lab_l == "in foreign currency":
                fcd_rows.append(i)

    # Prefer explicit "In foreign currency" labels
    fcd_by_label = [
        i
        for i in range(len(df))
        if pd.notna(df.iat[i, lab_col])
        and str(df.iat[i, lab_col]).strip().lower() == "in foreign currency"
    ]
    if fcd_by_label:
        fcd_rows = fcd_by_label

    if td_row is None or not fcd_rows:
        logger.warning(
            "[NAM] td_row=%s fcd_rows=%s sheet=%s", td_row, fcd_rows, sheet
        )
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for j, period in periods.items():
        td = _num(df.iat[td_row, j])
        fcd = 0.0
        ok = False
        for ri in fcd_rows:
            v = _num(df.iat[ri, j])
            if v is not None:
                fcd += v
                ok = True
        if not ok or td is None or td <= 0:
            continue
        year = int(period[:4])
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
        return _empty()
    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        urls = _list_set_of_table_urls()
        if not urls:
            logger.error("[%s] no Set of Table links on BoN page", country_code)
            return _empty()

        frames: list[pd.DataFrame] = []
        # Limit to recent ~15 years for speed; still covers long history if needed
        for url in urls[:15]:
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=90, verify=False)
                if resp.status_code != 200 or resp.content[:2] != b"PK":
                    continue
                df = _parse_ii5(resp.content, country_code)
                if not df.empty:
                    frames.append(df)
                    logger.info(
                        "[NAM] %s -> %s~%s (%d)",
                        url.split("/")[-2] if "/" in url else url[-20:],
                        df["period"].min(),
                        df["period"].max(),
                        df["period"].nunique(),
                    )
            except Exception as e:
                logger.warning("[NAM] skip %s: %s", url[-40:], e)

        if not frames:
            logger.error("[%s] no Table II.5 data parsed", country_code)
            return _empty()

        out = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] %d rows (%s~%s)",
            country_code,
            len(out),
            out["period"].min(),
            out["period"].max(),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
