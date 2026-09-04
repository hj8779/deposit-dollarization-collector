"""Czechia: ČNB (Česká národní banka)'s ARAD time-series system (cnb.cz/arad, an Angular SPA).
Under the tree node 'Monetary and financial statistics > Monetary statistics > A. Statistics of
monetary developments in the CR > Deposits with MFIs' (treeId=8165396) there are indicators that
split deposits by instrument currency (CZK/All foreign currencies) and by counterpart sector
(residents).

Filtering by 'All foreign currencies'(D21856) x 'Levels'(D21657, stock/balance basis) leaves
exactly 4 indicators: Financial institutions except MFIs (S.124-129, includes
insurance/pension), Insurance corporations and pension funds (S.128+S.129), Households and
NPISH (S.14+S.15), Non-financial corporations (S.11). Since 'Financial institutions except
MFIs' is already a superset that includes 'Insurance and pension funds' (the code itself is
explicitly S.124+S.125+S.126+S.127+S.128+S.129), only the following three are summed to avoid
double-counting:
    FCD = SMV10M108013(Financial institutions except MFIs) + SMV10M107013(Households+NPISH)
          + SMV10M106013(Non-financial corporations)
The government sector (General/Central government) has no indicator at all in this currency
(FX) combination (count=0, presumably because government FX deposits are effectively
nonexistent or not separately disclosed) - so the three sectors above effectively cover all
resident FX deposits.

TD (total deposits) = in the same tree, switching the currency filter to 'All
currencies'(D21666) and the indicator attribute to 'Types total'(D21676, sum with no
maturity/type breakdown), then summing the '011'-suffix versions of the same 3 sector codes
(the FX version uses the '013' suffix; it was empirically confirmed that in this tree there
happens to be no maturity breakdown, so it was already a total even without 'Types total'. The
'All currencies' version, however, has separate maturity-split indicators, so the 'Types total'
filter is required):
    TD = SMV10M108011(Financial institutions except MFIs) + SMV10M107011(Households+NPISH)
         + SMV10M106011(Non-financial corporations)
(Empirically confirmed that only 8 sector indicators remain under the all-currencies, Types
total, Levels combination, and only the same 3 sectors used for FCD are used here.)

ARAD does have a real REST API (/aradb/api/v13/...), but the indicator-data endpoint
(indicators-data-by-codes) returns a 'Přístup byl zablokován' (access blocked) page every time
it's called directly with indicator codes in the URL query (presumably the WAF flags this
pattern as a direct call outside a normal session and blocks it). Reproducing the actual UI
flow with Playwright (tree navigation -> filter selection -> checking the 3 indicators ->
clicking the 'view as table' icon), however, gets a normal response - so this process is
automated every time and the response JSON is intercepted.
"""

from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

ARAD_URL = "https://www.cnb.cz/arad/#/en/indicators"
_FCD_CODES = ["SMV10M108013", "SMV10M107013", "SMV10M106013"]
_TD_CODES = ["SMV10M108011", "SMV10M107011", "SMV10M106011"]

_MONTHS = {
    "01": 1, "02": 2, "03": 3, "04": 4, "05": 5, "06": 6,
    "07": 7, "08": 8, "09": 9, "10": 10, "11": 11, "12": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("CZE is handled via render() (requires reproducing the ARAD SPA UI flow)")


def _fetch_indicator_data(
    currency_label: str, codes: list[str], extra_filter_labels: list[str] | None = None
) -> dict:
    import json as jsonlib

    from playwright.sync_api import sync_playwright

    captured = {}

    def on_response(response):
        if "indicators-data-by-codes" in response.url:
            captured["body"] = response.text()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("response", on_response)
        page.goto(ARAD_URL, timeout=60000)
        page.wait_for_timeout(2000)
        try:
            page.click("text=I AGREE!", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(500)
        page.click("text=Statistical data")
        page.wait_for_timeout(1200)
        page.click("text=Monetary and financial statistics")
        page.wait_for_timeout(1200)
        page.click("text=Monetary statistics")
        page.wait_for_timeout(1200)
        page.click("text=A. Statistics of monetary developments in the CR")
        page.wait_for_timeout(1200)
        page.click("text=Deposits with MFIs")
        page.wait_for_timeout(2000)
        page.click(f"text={currency_label}", timeout=5000)
        page.wait_for_timeout(1200)
        page.click("text=Levels", timeout=5000)
        page.wait_for_timeout(1200)
        for label in extra_filter_labels or []:
            page.click(f"text={label}", timeout=5000)
            page.wait_for_timeout(1200)
        for code in codes:
            page.click(f"label[for={code}]", force=True)
            page.wait_for_timeout(300)
        page.click("text=Selected indicators")
        page.wait_for_timeout(1500)
        page.click(".icon.h-primary", force=True)
        page.wait_for_timeout(3000)
        browser.close()

    if "body" not in captured:
        raise RuntimeError("Failed to intercept the ARAD indicators-data-by-codes response")
    return jsonlib.loads(captured["body"])


def _totals_from_indicators(indicators: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for ind in indicators:
        for snap in ind["snapshots_data"]:
            for period_str, value in snap["chart_data"]:
                mm, yyyy = period_str.split(".")
                month = _MONTHS.get(mm)
                if month is None or not isinstance(value, (int, float)):
                    continue
                period = f"{yyyy}-{mm}"
                totals[period] = totals.get(period, 0.0) + float(value)
    return totals


def render(target: dict) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor

    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    # The FCD and TD lookups are independent ARAD SPA tree navigations, so they're run in
    # parallel to roughly halve the wall-clock time (each lookup is dominated by multi-step
    # tree clicks + wait_for_timeout, so sequential execution takes 40+ seconds and is prone
    # to dying under a short hard timeout, e.g. --timeout-sec 10).
    with ThreadPoolExecutor(max_workers=2) as executor:
        fcd_future = executor.submit(_fetch_indicator_data, "All foreign currencies", _FCD_CODES)
        td_future = executor.submit(
            _fetch_indicator_data, "All currencies", _TD_CODES, extra_filter_labels=["Types total"]
        )
        fcd_payload = fcd_future.result()
        try:
            td_payload = td_future.result()
        except Exception as e:
            logger.warning("[%s] TD lookup failed: %s", country_code, e)
            td_payload = None

    fcd_indicators = fcd_payload["data"][0]["indicators"]
    found_codes = {ind["code"] for ind in fcd_indicators}
    if found_codes != set(_FCD_CODES):
        logger.warning("[%s] Indicator codes differ from expected: %s", country_code, found_codes)

    fcd_totals = _totals_from_indicators(fcd_indicators)
    rows = [
        {
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": INDICATOR,
            "value": round(value, 2),
            "updated_at": now,
        }
        for period, value in fcd_totals.items()
    ]

    if td_payload is not None:
        td_indicators = td_payload["data"][0]["indicators"]
        found_td_codes = {ind["code"] for ind in td_indicators}
        if found_td_codes != set(_TD_CODES):
            logger.warning("[%s] TD indicator codes differ from expected: %s", country_code, found_td_codes)
        td_totals = _totals_from_indicators(td_indicators)
        rows.extend(
            {
                "country_code": country_code,
                "year": int(period[:4]),
                "period": period,
                "indicator": INDICATOR_TD,
                "value": round(value, 2),
                "updated_at": now,
            }
            for period, value in td_totals.items()
        )

    return pd.DataFrame(rows).sort_values(["period", "indicator"]).reset_index(drop=True)
