"""Lebanon: Banque du Liban — resident deposits in FC / total deposits.

The BDL website has strong Cloudflare bot protection, so plain requests get
a 403. We use Playwright (Chromium) to load the key figures / money supply
pages and resolve the Excel/CSV download links from there.

Primary target series:
  - Deposits of Residents in Foreign Currencies  (FCD)
  - Total Deposits in the Commercial Banks / Resident Customers Deposits (TD)

Candidate URLs:
  https://www.bdl.gov.lb/keyfiguressub.php?docId=97&code=3&filecode=321
  https://www.bdl.gov.lb/tabs/index/6/325/Money-Supply..html

Returns an empty frame if the site is unreachable (the cause is recorded in
adapter notes).
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

_HOME = "https://www.bdl.gov.lb/"
_KEY_FC = "https://www.bdl.gov.lb/keyfiguressub.php?docId=97&code=3&filecode=321"
_KEY_TOTAL = "https://www.bdl.gov.lb/keyfiguressub.php?docId=305&code=18&filecode=1864"
_MONEY = "https://www.bdl.gov.lb/tabs/index/6/325/Money-Supply..html"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _HOME,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("LBN performs the download via Playwright in render()")


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
        t = v.strip().replace(",", "").replace("\xa0", "")
        if t in {"", "-", "–", "—", "n.a.", "na"}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _period_from_cell(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "year") and hasattr(v, "month"):
        return f"{int(v.year)}-{int(v.month):02d}"
    s = str(v).strip()
    m = re.match(r"^(\d{4})[-/](\d{1,2})$", s)
    if m:
        return f"{int(m.group(1))}-{int(m.group(2)):02d}"
    m = re.match(
        r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/\s]?(\d{2,4})$",
        s,
        re.I,
    )
    if m:
        mon = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }[m.group(1)[:3].lower()]
        yy = int(m.group(2))
        year = 2000 + yy if yy < 100 else yy
        return f"{year}-{mon:02d}"
    m = re.match(r"^(\d{1,2})[-/](\d{4})$", s)
    if m:
        return f"{int(m.group(2))}-{int(m.group(1)):02d}"
    # Apr/2023
    m = re.match(
        r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*/(\d{4})$",
        s,
        re.I,
    )
    if m:
        mon = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }[m.group(1)[:3].lower()]
        return f"{int(m.group(2))}-{mon:02d}"
    return None


def _parse_series_table(content: bytes) -> dict[str, float]:
    """Parse excel/csv into period->value (first numeric series column)."""
    out: dict[str, float] = {}
    if content[:2] == b"PK" or content[:4] == b"\xd0\xcf\x11\xe0":
        xl = pd.ExcelFile(BytesIO(content))
        df = xl.parse(xl.sheet_names[0], header=None)
    else:
        # try csv
        try:
            df = pd.read_csv(BytesIO(content), header=None)
        except Exception:
            try:
                df = pd.read_csv(BytesIO(content), header=None, sep=";")
            except Exception:
                return out

    # find period col and value col
    for i in range(len(df)):
        p = _period_from_cell(df.iat[i, 0])
        if p is None and df.shape[1] > 1:
            p = _period_from_cell(df.iat[i, 1])
            val_cols = range(2, df.shape[1])
        else:
            val_cols = range(1, df.shape[1])
        if p is None:
            continue
        for j in val_cols:
            v = _num(df.iat[i, j])
            if v is not None:
                out[p] = v
                break
    return out


def _playwright_download(url: str) -> bytes | None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(
                user_agent=_HEADERS["User-Agent"],
                accept_downloads=True,
            )
            page = ctx.new_page()
            page.goto(url, timeout=90000, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            content = page.content()
            if "Just a moment" in content or "cf-browser-verification" in content:
                # wait longer for CF challenge
                page.wait_for_timeout(15000)
                content = page.content()
            if "Just a moment" in page.content():
                logger.warning("[LBN] Cloudflare challenge not cleared for %s", url)
                return None

            # try click Excel/CSV download
            for label in ("Excel", "CSV", "Download", "excel", "csv"):
                try:
                    loc = page.get_by_text(label, exact=False).first
                    if loc.count() == 0:
                        continue
                    with page.expect_download(timeout=15000) as dl_info:
                        loc.click()
                    download = dl_info.value
                    path = f"/tmp/lbn_{download.suggested_filename}"
                    download.save_as(path)
                    with open(path, "rb") as f:
                        return f.read()
                except Exception:
                    continue

            # href-based download
            hrefs = re.findall(
                r'href=["\']([^"\']+\.(?:xls|xlsx|csv)[^"\']*)["\']',
                page.content(),
                re.I,
            )
            for h in hrefs:
                full = urljoin(url, h)
                try:
                    # use storage state cookies
                    cookies = {c["name"]: c["value"] for c in ctx.cookies()}
                    r = requests.get(
                        full, headers=_HEADERS, cookies=cookies, timeout=60, verify=False
                    )
                    if r.status_code == 200 and len(r.content) > 100:
                        return r.content
                except Exception:
                    continue
            return None
        finally:
            browser.close()


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        fcd_bytes = None
        td_bytes = None
        for url in (_KEY_FC, _MONEY):
            try:
                data = _playwright_download(url)
                if data:
                    fcd_bytes = data
                    logger.info("[LBN] downloaded FC series from %s (%d bytes)", url, len(data))
                    break
            except Exception as e:
                logger.warning("[LBN] playwright %s: %s", url, e)

        for url in (_KEY_TOTAL, _MONEY):
            try:
                data = _playwright_download(url)
                if data:
                    td_bytes = data
                    logger.info("[LBN] downloaded TD series from %s (%d bytes)", url, len(data))
                    break
            except Exception as e:
                logger.warning("[LBN] playwright %s: %s", url, e)

        if not fcd_bytes and not td_bytes:
            # last resort: direct excel under CB Com (if path known)
            try:
                r = requests.get(
                    "https://www.bdl.gov.lb/CB%20Com/Statistics%20And%20Research/"
                    "Daily/BDL_DailyExchangeRates.xls",
                    headers=_HEADERS,
                    timeout=30,
                    verify=False,
                )
                logger.info(
                    "[LBN] Cloudflare/path block: only exchange-rate xls reachable (%s)",
                    r.status_code,
                )
            except Exception:
                pass
            logger.error("[%s] BDL deposit series unreachable (Cloudflare)", country_code)
            return _empty()

        fcd_map = _parse_series_table(fcd_bytes) if fcd_bytes else {}
        td_map = _parse_series_table(td_bytes) if td_bytes else {}

        # if single file has both columns, try multi-col parse
        if fcd_bytes and not td_map:
            # attempt richer parse
            try:
                xl = pd.ExcelFile(BytesIO(fcd_bytes))
                df = xl.parse(xl.sheet_names[0], header=None)
                # look for FC / Total columns by header labels
                header_row = None
                for i in range(min(10, len(df))):
                    rowtxt = " ".join(str(x) for x in df.iloc[i].tolist() if pd.notna(x)).lower()
                    if "foreign" in rowtxt or "deposit" in rowtxt:
                        header_row = i
                        break
                if header_row is not None:
                    headers = [str(x).lower() if pd.notna(x) else "" for x in df.iloc[header_row]]
                    fcd_col = next((j for j, h in enumerate(headers) if "foreign" in h), None)
                    td_col = next(
                        (j for j, h in enumerate(headers) if "total" in h or "resident" in h),
                        None,
                    )
                    for i in range(header_row + 1, len(df)):
                        p = _period_from_cell(df.iat[i, 0])
                        if not p:
                            continue
                        if fcd_col is not None:
                            v = _num(df.iat[i, fcd_col])
                            if v is not None:
                                fcd_map[p] = v
                        if td_col is not None:
                            v = _num(df.iat[i, td_col])
                            if v is not None:
                                td_map[p] = v
            except Exception as e:
                logger.warning("[LBN] multi-col parse: %s", e)

        if not fcd_map or not td_map:
            logger.error(
                "[%s] series incomplete fcd=%d td=%d",
                country_code, len(fcd_map), len(td_map),
            )
            return _empty()

        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for period in sorted(set(fcd_map) & set(td_map)):
            fcd, td = fcd_map[period], td_map[period]
            if td <= 0:
                continue
            year = int(period[:4])
            ratio = round((fcd / td) * 100, 4)
            for indicator, value in (
                ("FCD", round(fcd, 4)),
                ("TD", round(td, 4)),
                ("FCD_TD_RATIO", ratio),
            ):
                rows.append({
                    "country_code": country_code,
                    "year": year,
                    "period": period,
                    "indicator": indicator,
                    "value": value,
                    "updated_at": now,
                })
        if not rows:
            return _empty()
        out = (
            pd.DataFrame(rows)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] %d rows (%s~%s)",
            country_code, len(out), out["period"].min(), out["period"].max(),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
