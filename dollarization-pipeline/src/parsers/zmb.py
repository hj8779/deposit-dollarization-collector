"""Zambia: Bank of Zambia "Fortnightly Time Series" xlsx
(boz.zm/statistics/monetary-and-financial-statistics → 'FORTNIGHTLYTIMESERIES...xlsx').

Sheet 'Comm. Banks Deposit Liabilities' (Table 12) mixes two currencies: 'Total Kwacha
Liabilities to the Public' (national currency, kwacha) and "Foreign currency Deposits
($'000)" (foreign currency, denominated in USD). The FX deposits are converted to kwacha
using the Mid-rate from sheet 'K-USD Exchange Rates' and then summed. For weeks whose date
doesn't line up exactly (holidays, etc.), the rate from the nearest prior business day is
used.

FCD_kwacha = FX deposits ($'000) × mid-rate. TD_kwacha = Total Kwacha Liabilities +
FCD_kwacha. Weekly (each Friday close), from 2014-01. Unit: K'000 (thousand kwacha)."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_LIST_PAGE = "https://www.boz.zm/statistics/monetary-and-financial-statistics"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("ZMB fetches the xlsx via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _find_xlsx_url() -> str | None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            page.goto(_LIST_PAGE, timeout=45000, wait_until="networkidle")
            page.wait_for_timeout(2000)
            hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            candidates = [h for h in hrefs if "FORTNIGHTLYTIMESERIES" in h.upper()]
            return candidates[0] if candidates else None
        finally:
            browser.close()


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    xlsx_url = _find_xlsx_url()
    if not xlsx_url:
        logger.warning("[%s] Fortnightly Time Series xlsx link not found", country_code)
        return _empty()

    resp = requests.get(xlsx_url, headers=_HEADERS, timeout=90)
    resp.raise_for_status()
    wb = openpyxl.load_workbook(BytesIO(resp.content), data_only=True)

    fx_sheet = wb["K-USD Exchange Rates"]
    fx_rates: dict[datetime, float] = {}
    for r in range(6, fx_sheet.max_row + 1):
        date = fx_sheet.cell(row=r, column=1).value
        rate = fx_sheet.cell(row=r, column=4).value
        if isinstance(date, datetime) and isinstance(rate, (int, float)):
            fx_rates[date.date()] = float(rate)
    if not fx_rates:
        logger.warning("[%s] exchange rate data not found", country_code)
        return _empty()
    sorted_fx_dates = sorted(fx_rates)

    def rate_for(d) -> float | None:
        if d in fx_rates:
            return fx_rates[d]
        import bisect
        idx = bisect.bisect_right(sorted_fx_dates, d) - 1
        return fx_rates[sorted_fx_dates[idx]] if idx >= 0 else None

    dep_sheet = wb["Comm. Banks Deposit Liabilities"]
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for r in range(6, dep_sheet.max_row + 1):
        date = dep_sheet.cell(row=r, column=1).value
        total_kwacha = dep_sheet.cell(row=r, column=4).value
        fcd_usd = dep_sheet.cell(row=r, column=5).value
        if not isinstance(date, datetime) or not isinstance(total_kwacha, (int, float)) or not isinstance(fcd_usd, (int, float)):
            continue
        rate = rate_for(date.date())
        if rate is None:
            continue

        fcd = fcd_usd * rate
        td = total_kwacha + fcd
        if td <= 0:
            continue
        period = f"{date.year}-{date.month:02d}"
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": date.year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    if not rows:
        return _empty()

    # Multiple weeks can fall into the same (period, indicator) (e.g. a 5-week month), so the last observation of that month is kept
    df = pd.DataFrame(rows)
    out = (
        df.sort_values(["period"])
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
