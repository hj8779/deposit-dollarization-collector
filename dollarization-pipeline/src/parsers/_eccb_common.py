"""Shared by all 8 ECCU countries (AIA, ATG, DMA, GRD, MSR, KNA, LCA, VCT): ECCB
(Eastern Caribbean Central Bank) 'Summarized Monetary Survey > Interactive Database' query form.

The original brief assumed a public SDMX REST API at `sdmx.eccb-centralbank.org`, but that
domain doesn't even resolve (NXDOMAIN) — it's not a real endpoint. The actual data source is
the 'Interactive Database' at the URL below, which can only be queried through a Laravel-based
form (POST /search, with a CSRF token plus an encrypted hidden field). The form is built as a
select2 multi-select inside a Bootstrap modal (#modify), so rather than trying to replicate the
form directly with requests, it's far more reliable to drive the real UI flow with Playwright
(open modal -> pick country -> pick indicators -> submit).

Gotchas encountered while automating the form:
  - Clicking anywhere outside the select2 dropdown (page.mouse.click) closes the Bootstrap
    modal itself (a background click dismisses the modal). You need to click an inert area
    'inside' the modal (.modal-header) so only the dropdown closes and the modal stays open.
  - The country_code multi-select comes with 'ECCU' (region-wide aggregate) selected by
    default. Adding a specific country produces two side-by-side sets of columns in the
    results table, ordered '<country>, ECCU'.
  - Data rows in the results table (the second <table>) are ordered [indicator name, unit,
    year1-country, year1-ECCU, year2-country, year2-ECCU, ...]. The default query window is
    only the last 5 years (annual), so START_DATE is adjusted explicitly to pull data starting
    from 2000.
  - The start_date input is readonly (can't type into it directly) and is covered by a
    bootstrap-datepicker (minViewMode=2, year selection only, with an actual allowed range of
    1975-2029). Driving this calendar via UI clicks (navigating the year grid) frequently drops
    click events and the value doesn't update. (It's not actually that bootstrap-datepicker
    swallows clicks — setting `input.value` via JS doesn't change the underlying HTML `value`
    *attribute*, so checking with `get_attribute('value')` never reflected the change; you have
    to read `input_value()` to see the live value.) The most reliable approach is to skip the UI
    entirely and call the jQuery plugin's public API directly:
    `jQuery('#start_date').datepicker('setDate', new Date(2000,0,1))`.
"""

from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

QUERY_URL = (
    "https://www.eccb-centralbank.org/statistics-category/"
    "monetary-and-financial-statistics/summarized-monetary-survey/a"
)

# TD (total deposits, i.e. all deposits included in broad money M2) = the sum of the 3
# indicators below (transferable deposits in national currency + other deposits in national
# currency + foreign currency deposits). Verified empirically that these three rows are
# non-overlapping, distinct components (the ECCB results table has no separate 'Total
# Deposits' summary row).
_TD_COMPONENT_LABELS = [
    "Transferable Deposits, In National Currency",
    "Other Deposits, In National Currency",
    "Foreign Currency Deposits",
]


def fetch_fcd(country_code: str, country_label: str) -> pd.DataFrame:
    from playwright.sync_api import sync_playwright

    now = datetime.now(timezone.utc).isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
        try:
            page.goto(QUERY_URL, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(1500)
            page.get_by_text("Modify", exact=True).click()
            page.wait_for_timeout(1000)

            modal_safe_spot = page.locator(".modal-header, .modal-title").first

            # Adjust the start date to pull data from 2000 instead of the default window
            # (last 5 years). Since the calendar widget is readonly, call the jQuery plugin
            # API directly instead of clicking through the UI.
            page.evaluate("window.jQuery('#start_date').datepicker('setDate', new Date(2000, 0, 1))")
            page.wait_for_timeout(300)

            page.locator("#country_code + span.select2 .select2-selection").first.click()
            page.wait_for_timeout(300)
            page.locator(".select2-results__option").filter(has_text=country_label).first.click(force=True)
            page.wait_for_timeout(300)
            modal_safe_spot.click(force=True)
            page.wait_for_timeout(500)

            page.locator("#indicator-rows + span.select2 .select2-selection").first.click()
            page.wait_for_timeout(500)
            for label in _TD_COMPONENT_LABELS:
                page.locator(".select2-results__option").filter(has_text=label).first.click(force=True)
                page.wait_for_timeout(300)
            modal_safe_spot.click(force=True)
            page.wait_for_timeout(500)

            submit_btn = page.locator("form#frmModifyTable button[type=submit]")
            with page.expect_navigation(timeout=20000):
                submit_btn.first.click(force=True)
            page.wait_for_timeout(2000)

            years = [
                int(y) for y in page.locator("table").nth(0).locator("thead, tr").first.inner_text().split()
                if y.strip().isdigit() and len(y.strip()) == 4
            ]

            result_table = page.locator("table").nth(1)
            table_lines = result_table.inner_text().splitlines()
        finally:
            browser.close()

    row_texts: dict[str, str] = {}
    for line in table_lines:
        for label in _TD_COMPONENT_LABELS:
            if line.strip().startswith(label):
                row_texts[label] = line
                break

    if len(row_texts) != len(_TD_COMPONENT_LABELS) or not years:
        logger.warning("[%s] Could not find all deposit indicator rows in the ECCB query results (%d/%d)",
                        country_code, len(row_texts), len(_TD_COMPONENT_LABELS))
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    # label -> {year: value}; country values are at even indices (repeating in country, ECCU order)
    values_by_label: dict[str, dict[int, float]] = {}
    for label, row_text in row_texts.items():
        tokens = row_text.split("\t")
        values = [t.replace(",", "") for t in tokens[2:]]  # [indicator name, unit, v1_country, v1_eccu, v2_country, ...]
        per_year: dict[int, float] = {}
        for i, year in enumerate(years):
            idx = i * 2
            if idx >= len(values):
                break
            try:
                per_year[year] = float(values[idx])
            except ValueError:
                continue
        values_by_label[label] = per_year

    rows = []
    for year in years:
        component_values = [values_by_label[label].get(year) for label in _TD_COMPONENT_LABELS]
        fcd_value = values_by_label["Foreign Currency Deposits"].get(year)
        if fcd_value is not None:
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": f"{year}-Annual",
                "indicator": INDICATOR,
                "value": fcd_value,
                "updated_at": now,
            })
        if all(v is not None for v in component_values):
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": f"{year}-Annual",
                "indicator": INDICATOR_TD,
                "value": round(sum(component_values), 2),
                "updated_at": now,
            })

    return pd.DataFrame(rows)
