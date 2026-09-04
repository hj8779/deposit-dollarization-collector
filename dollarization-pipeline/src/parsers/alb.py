"""Albania: Bank of Albania 'Sectoral balance sheet of Deposit money banks' interactive statistics page.

Pick items in the checkbox tree and click 'Show values' — this is a two-step process:
  1) First, the period (From/To) selection UI appears -> set From to the earliest available
     month (Dec 2006), then
  2) Clicking 'Show values' again opens the result in a **new tab** (?mode=alone), which
     contains the HTML table with the actual values (monthly columns tab-separated after the
     code/label).

Indicator selection: the 2 foreign-currency items under 'Deposits included in broad money' on
the LIABILITIES side, broken out by currency:
  - 2.1.1.2 Transferable deposits, In foreign currency  (checkbox id=85581)
  - 2.1.2.2 Other deposits, In foreign currency          (checkbox id=85601)
FCD = 2.1.1.2 + 2.1.2.2 (total bank foreign currency deposits included in broad money, in
millions of Lek)

TD (total deposits) = 2.1 Deposits included in broad money (checkbox id=85573), selecting the
parent total item directly. Verified empirically in the results table that 2.1 = 2.1.1
(Transferable deposits) + 2.1.2 (Other deposits), each being the sum of national currency +
foreign currency, so it is the parent total that FCD rolls up into (2.1 = 2.1.1 + 2.1.2,
2.1.1 = 2.1.1.1 + 2.1.1.2, etc.).

Checkbox ids start with a digit, so a CSS ID selector (#85581) can't be used — an attribute
selector ([id="85581"]) is used instead.
"""

import re
from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_FCD_CODES = {"2.1.1.2", "2.1.2.2"}
_TD_CODE = "2.1"
_CHECKBOX_IDS = ["85573", "85581", "85601"]

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_PERIOD_RE = re.compile(r"^([A-Za-z]{3})\s*(\d{4})$")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("ALB is handled via render() (Playwright form + new-tab flow)")


def render(target: dict) -> pd.DataFrame:
    from playwright.sync_api import sync_playwright

    country_code = target["country_code"]
    url = target["source_url"]
    now = datetime.now(timezone.utc).isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            page.locator("#id_select_clear_all").click(force=True)
            page.wait_for_timeout(300)
            for cb_id in _CHECKBOX_IDS:
                page.locator(f'[id="{cb_id}"]').click(force=True)
            page.wait_for_timeout(300)

            # 1st click: reveals the period selection UI
            page.get_by_text("Show values", exact=True).click(force=True)
            page.wait_for_timeout(2000)
            page.locator("select[name=periudha_nga]").select_option(index=0, force=True)  # earliest available month
            page.wait_for_timeout(500)

            # 2nd click: results open in a new tab
            with context.expect_page(timeout=15000) as new_page_info:
                page.get_by_text("Show values", exact=True).first.click(force=True)
            result_page = new_page_info.value
            result_page.wait_for_load_state("networkidle")
            result_page.wait_for_timeout(2000)

            table = result_page.locator("table").nth(1)
            lines = table.inner_text().splitlines()
        finally:
            browser.close()

    if not lines:
        logger.warning("[%s] Could not find results table", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    header = [c.strip() for c in lines[0].split("\t")]
    periods: dict[int, tuple[int, int]] = {}  # col_idx -> (year, month)
    for i, cell in enumerate(header):
        m = _PERIOD_RE.match(cell)
        if not m:
            continue
        month = _MONTHS.get(m.group(1).lower())
        if month:
            periods[i] = (int(m.group(2)), month)

    fcd_totals: dict[int, float] = {}
    td_totals: dict[int, float] = {}
    for line in lines[1:]:
        cells = [c.strip().replace("\xa0", " ").strip() for c in line.split("\t")]
        if not cells:
            continue
        code = cells[0].strip()
        if code in _FCD_CODES:
            target = fcd_totals
        elif code == _TD_CODE:
            target = td_totals
        else:
            continue
        for i, raw in enumerate(cells):
            if i not in periods:
                continue
            raw = raw.replace(",", "").replace("\xa0", "")
            if not raw or raw in ("-", "n.a.", ".."):
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            target[i] = target.get(i, 0.0) + value

    rows = []
    for i, (year, month) in periods.items():
        period = f"{year}-{month:02d}"
        if i in fcd_totals:
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": INDICATOR,
                "value": round(fcd_totals[i], 2),
                "updated_at": now,
            })
        if i in td_totals:
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": INDICATOR_TD,
                "value": round(td_totals[i], 2),
                "updated_at": now,
            })

    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True) if rows else pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )
