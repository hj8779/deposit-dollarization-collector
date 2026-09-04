"""Denmark: Danmarks Nationalbank's Statbank (the legacy PC-Axis/StatBank5a ASP platform, no
PxWeb API) table 'DNPINDK: Domestic deposits in banks by instrument, data type, domestic
sector, currency and maturity'. The variable-selection screen sits inside an iframe, and the
submission result is also rendered inline inside an iframe (only the URL points to
saveselections.asp); the CSV export etc. is an <option> inside a <select>, so the download
event only fires when selected via select_option rather than a click - so this interaction
flow is reproduced with Playwright every time.

Selections: Instrument=Deposits in total, Data type=Outstanding amounts (DKK million),
Domestic sector=1000: All domestic sectors (sum across all resident sectors),
Currency=Foreign currency in total (sum of all foreign currencies excluding DKK),
Maturity=All maturities, Time=all months (2003-01-present). With this filtering, the result
table's time series collapses to a single 'Deposits in total' row, which is FCD itself.

TD (total deposits) = the same query with only the Currency filter switched to 'All
currencies' (sum across all currencies including DKK). The same select (index 7) has an 'All
currencies' option available, so the exact same query flow used for FCD can be reused.
"""

import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

TABLE_URL = "https://nationalbanken.statbank.dk/DNPINDK"
_CSV_EXPORT_OPTION_VALUE = "8"  # 'Comma sep. (*.csv)'

_MONTH_COL_RE = re.compile(r'"?(\d{4})M(\d{2})"?')


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("DNK is handled via render() (requires automating the Statbank ASP form)")


def _download_csv(currency_label: str, out_path: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(TABLE_URL, timeout=60000)
        page.wait_for_timeout(2000)

        frame = next(f for f in page.frames if "selectvarval" in f.url)
        selects = frame.query_selector_all("select")
        selects[1].select_option(label="Deposits in total")
        selects[3].select_option(label="Outstanding amounts (DKK million)")
        selects[5].select_option(label="1000: All domestic sectors")
        selects[7].select_option(label=currency_label)
        selects[9].select_option(label="All maturities")
        frame.eval_on_selector_all(
            "select",
            "(sels) => { const m = sels[11]; for (const o of m.options) o.selected = true; "
            "m.dispatchEvent(new Event('change')); }",
        )
        page.wait_for_timeout(500)
        frame.click("input[name=Forward]")
        page.wait_for_timeout(6000)

        result_frame = next(f for f in page.frames if "saveselections" in f.url)
        with page.expect_download(timeout=20000) as dl_info:
            result_frame.select_option(
                f'select:has(option[value="{_CSV_EXPORT_OPTION_VALUE}"])',
                value=_CSV_EXPORT_OPTION_VALUE,
            )
        download = dl_info.value
        download.save_as(out_path)
        browser.close()

    return open(out_path, "rb").read()


def _parse_csv(content: bytes, country_code: str, indicator: str, now: str) -> pd.DataFrame:
    text = content.decode("latin-1")
    lines = [ln for ln in text.splitlines() if ln.strip()]

    header_line = next((ln for ln in lines if "M01" in ln or "M02" in ln), None)
    data_line = next((ln for ln in lines if "Deposits in total" in ln), None)
    if header_line is None or data_line is None:
        logger.warning("[%s] Could not find header or 'Deposits in total' data row", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    periods = [f"{y}-{m}" for y, m in _MONTH_COL_RE.findall(header_line)]

    import csv as csvlib

    data_cells = next(csvlib.reader(StringIO(data_line)))
    # Only the numeric cells following the 'Deposits in total' label are treated as values.
    label_idx = next(i for i, c in enumerate(data_cells) if c.strip() == "Deposits in total")
    values = data_cells[label_idx + 1:]

    rows = []
    for period, value_str in zip(periods, values):
        value_str = value_str.strip().strip('"')
        if not value_str or value_str in ("..", "-"):
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue
        rows.append({
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": indicator,
            "value": round(value, 2),
            "updated_at": now,
        })

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor

    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    # The FCD and TD lookups are independent Playwright sessions, so they're run in parallel to
    # roughly halve the wall-clock time (each lookup is dominated by form-interaction waits
    # (wait_for_timeout), so sequential execution would double the total time).
    with ThreadPoolExecutor(max_workers=2) as executor:
        fcd_future = executor.submit(_download_csv, "Foreign currency in total", "/tmp/dnk_dnpindk_fcd.csv")
        td_future = executor.submit(_download_csv, "All currencies", "/tmp/dnk_dnpindk_td.csv")
        fcd_content = fcd_future.result()
        td_content = td_future.result()

    fcd_df = _parse_csv(fcd_content, country_code, INDICATOR, now)
    td_df = _parse_csv(td_content, country_code, INDICATOR_TD, now)

    return pd.concat([fcd_df, td_df], ignore_index=True).sort_values(["period", "indicator"]).reset_index(drop=True)
