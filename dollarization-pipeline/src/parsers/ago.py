"""Angola: BNA(Banco Nacional de Angola) 'Nova Série' statistics page, 'Agregados Monetários' download.
The page doesn't use a plain <a href> — clicking it downloads the file via JS — so it has to be
driven with Playwright, clicking and then catching the download event. Legacy .xls, sheet
'IA2.AggrMon' (Quadro I.A.2 Agregados Monetários).

Layout: col B (index 1) = indicator name, col C (index 2) onward = monthly time series (row 4 =
Excel date serial, extending horizontally).
    row25 'Total dos depósitos em moeda externa'      -> FCD (memo item, official total)
    row12 'Depósitos transferíveis' (total, subtotal) -> TD component 1
    row17 'Outros depósitos' (total, subtotal)        -> TD component 2
    TD = row12 + row17
"""

from datetime import datetime, timezone

import pandas as pd
import xlrd

from src.collectors.base import INDICATOR
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

# bna.ao frequently responds very slowly or times out intermittently (a site-side issue), so
# use a more generous timeout and retry count than other countries' render().
_NAV_TIMEOUT_MS = 60000
_MAX_ATTEMPTS = 3

_SHEET_NAME = "IA2.AggrMon"
_DATE_ROW = 4
_FCD_ROW = 25
_TRANSFERABLE_TOTAL_ROW = 12
_OTHER_TOTAL_ROW = 17
_FIRST_DATA_COL = 2


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("AGO is handled via render() (Playwright click-to-download)")


def _download_workbook_path(url: str, country_code: str) -> str:
    from playwright.sync_api import sync_playwright

    last_error = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=_NAV_TIMEOUT_MS, wait_until="networkidle")
            with page.expect_download(timeout=20000) as dl_info:
                page.get_by_text("Agregados Monetários", exact=True).click()
            download = dl_info.value
            tmp_path = f"/tmp/{country_code.lower()}_agregados_{download.suggested_filename}"
            download.save_as(tmp_path)
            browser.close()
            playwright.stop()
            return tmp_path
        except Exception as e:
            last_error = e
            logger.warning(
                "[%s] Failed to access/download bna.ao (attempt %d/%d): %s",
                country_code, attempt, _MAX_ATTEMPTS, str(e)[:120],
            )
            playwright.stop()

    raise last_error


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    url = target["source_url"]
    now = datetime.now(timezone.utc).isoformat()

    try:
        tmp_path = _download_workbook_path(url, country_code)
    except Exception:
        logger.warning("[%s] Still failed to access after %d retries, skipping", country_code, _MAX_ATTEMPTS)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    wb = xlrd.open_workbook(tmp_path)
    ws = wb.sheet_by_name(_SHEET_NAME)

    rows = []
    for c in range(_FIRST_DATA_COL, ws.ncols):
        date_val = ws.cell_value(_DATE_ROW, c)
        fcd = ws.cell_value(_FCD_ROW, c)
        transferable = ws.cell_value(_TRANSFERABLE_TOTAL_ROW, c)
        other = ws.cell_value(_OTHER_TOTAL_ROW, c)
        if not isinstance(date_val, (int, float)):
            continue
        if not all(isinstance(v, (int, float)) for v in (fcd, transferable, other)):
            continue

        date = xlrd.xldate_as_datetime(date_val, wb.datemode)
        period = f"{date.year}-{date.month:02d}"
        td = transferable + other

        rows.append({
            "country_code": country_code, "year": date.year, "period": period,
            "indicator": INDICATOR, "value": round(fcd, 2), "updated_at": now,
        })
        rows.append({
            "country_code": country_code, "year": date.year, "period": period,
            "indicator": "TD", "value": round(td, 2), "updated_at": now,
        })

    return pd.DataFrame(rows)
