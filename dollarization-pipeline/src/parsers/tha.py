"""Thailand: Bank of Thailand statistics portal, table EC_MB_004_S2 "Monetary
Aggregates and Components" (app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=7).

This is an ASP.NET WebForms postback page, so it can't be fetched with plain requests and
requires browser automation via Playwright: the default view only shows the last 6 months, so
we set the 'From' year/month dropdowns (#drpFromYear, #drpFromMonth) to January 2003 (this
table's start month) and click #btnSubmit to load the full period, then click the CSV export
button (#imbExportText, an ASP.NET image button that starts the download immediately on click)
to receive the file.

TD = Broad Money (row 1) minus Currency outside DCs & Central Gov. (row 3) (= Transferable
Deposits + Quasi-money, i.e. all deposit-type liabilities excluding cash. Confirmed this
matches the Broad Money formula exactly). FCD = sum of the two 'Foreign Currency Deposits' rows
(the commercial-bank share + the specialized-banks share - this table repeats rows with the
same label for each type of depository institution, so we simply sum the first two occurrences).
Monthly, from 2003-01. Unit: million baht."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_REPORT_URL = "https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=7&language=ENG"
_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
_PERIOD_HEADER_RE = re.compile(r"([A-Z]{3})\s+(\d{4})")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("THA is handled via render() using Playwright to fetch the CSV")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _download_csv() -> str | None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(_REPORT_URL, timeout=45000, wait_until="networkidle")
            page.wait_for_timeout(1500)
            page.select_option("#drpFromYear", "2003xxxx")
            page.select_option("#drpFromMonth", "xxxx01xx")
            page.click("#btnSubmit")
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_selector("#imbExportText", timeout=10000)
            page.wait_for_timeout(1000)
            with page.expect_download(timeout=20000) as dl_info:
                page.click("#imbExportText")
            download = dl_info.value
            path = download.path()
            if not path:
                return None
            with open(path, "rb") as f:
                return f.read().decode("utf-8-sig")
        except Exception:
            logger.warning("[THA] BOT portal download failed", exc_info=True)
            return None
        finally:
            browser.close()


def _parse_csv(text: str, country_code: str) -> pd.DataFrame:
    rows = list(csv.reader(StringIO(text)))
    header_row = None
    for r in rows:
        if len(r) > 2 and _PERIOD_HEADER_RE.search(r[2] or ""):
            header_row = r
            break
    if header_row is None:
        return _empty()

    periods = []
    for cell in header_row[2:]:
        m = _PERIOD_HEADER_RE.search(cell)
        if not m:
            periods.append(None)
            continue
        month = _MONTHS.get(m.group(1))
        year = int(m.group(2))
        periods.append(f"{year}-{month:02d}" if month else None)

    def find_row(label: str) -> list[str] | None:
        for r in rows:
            if len(r) > 1 and r[1].strip() == label:
                return r[2:]
        return None

    def find_all_rows(label: str) -> list[list[str]]:
        return [r[2:] for r in rows if len(r) > 1 and r[1].strip() == label]

    broad_money = find_row("Broad Money (1+2)")
    currency = find_row("1.1 Currency outside DCs & Central Gov.")
    fcd_rows = find_all_rows("Foreign Currency Deposits")
    if not broad_money or not currency or not fcd_rows:
        logger.warning("[%s] could not find required rows (broad_money=%s currency=%s fcd_rows=%d)",
                        country_code, bool(broad_money), bool(currency), len(fcd_rows))
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    out_rows = []
    for i, period in enumerate(periods):
        if not period:
            continue
        try:
            bm = float(broad_money[i])
            cur = float(currency[i])
            fcd = sum(float(fr[i]) for fr in fcd_rows if i < len(fr) and fr[i] not in ("", None))
        except (ValueError, IndexError):
            continue
        td = bm - cur
        if td <= 0:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            out_rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    if not out_rows:
        return _empty()

    out = (
        pd.DataFrame(out_rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    text = _download_csv()
    if not text:
        return _empty()
    return _parse_csv(text, country_code)
