"""Canada: Bank of Canada foreign currency deposits of residents.

1) Prefer Bank of Canada Valet API full history once the series name is known.
2) Discover series name from the monetary-aggregates page (Playwright table),
   then pull observations from Valet.
3) Fallback: scrape the rendered table (usually only a short recent window).

TD: on the same "Selected Monetary Aggregates" table, no single "total deposits" row
exists, but the named (non-aggregate, non-adjustment) deposit line items sum to total
resident deposits across all instrument types:
    Personal: Chequable (V41552775_E1) + Non-chequable (V36818) + Fixed term (V36823)
    Non-personal demand/notice: Chequable (V41552777_E1) + Non-chequable (V36828_E1)
    Non-personal term deposits (V36830_E1)
    Foreign currency deposits of residents (V36876_E1, = FCD)
All 7 series share identical Valet history (1980-01~present), confirmed by direct query.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD, render_page
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_ROW_LABEL = "foreign currency deposits of residents"
_DEFAULT_PAGE = (
    "https://www.bankofcanada.ca/rates/banking-and-financial-statistics/"
    "selected-monetary-aggregates-and-their-components/"
)
# Common Valet series candidates (updated if page scrape finds a better id)
_VALET_CANDIDATES = [
    "V36876_E1",  # current live vector for FC deposits of residents (full 1980~ history)
    "V122647",  # historical vector sometimes used for FC deposits of residents
    "B2201",
]
# TD = sum of these named deposit line items (all instrument types, excludes M1/M2/M3
# aggregates and their "Adjustments to M*" reconciliation lines).
_TD_COMPONENT_SERIES = [
    "V41552775_E1",  # Personal, Chequable (Unadjusted)
    "V36818",         # Personal, Non-chequable (Unadjusted)
    "V36823",         # Personal, Fixed term (Unadjusted)
    "V41552777_E1",  # Non-personal demand/notice, Chequable (Unadjusted)
    "V36828_E1",      # Non-personal demand/notice, Non-chequable (Unadjusted)
    "V36830_E1",      # Non-personal term deposits (Unadjusted)
    "V36876_E1",      # Foreign currency deposits of residents (Unadjusted) = FCD
]
_VALET_OBS = "https://www.bankofcanada.ca/valet/observations/{name}/json"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,*/*",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("CAN is handled via render() (not a file download method)")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _rows_from_period_values(
    country_code: str,
    pairs: list[tuple[str, float]],
    now: str,
) -> pd.DataFrame:
    out = []
    for period, value in pairs:
        try:
            year = int(period[:4])
            mon = int(period[5:7])
            period_n = f"{year}-{mon:02d}"
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "country_code": country_code,
                "year": year,
                "period": period_n,
                "indicator": INDICATOR,  # FCD
                "value": float(value),
                "updated_at": now,
            }
        )
    if not out:
        return _empty()
    return (
        pd.DataFrame(out)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def _valet_observations(series_name: str) -> list[tuple[str, float]]:
    url = _VALET_OBS.format(name=series_name)
    params = {"start_date": "1980-01-01", "order_dir": "asc"}
    resp = requests.get(url, params=params, headers=_HEADERS, timeout=60)
    if resp.status_code != 200:
        return []
    data = resp.json()
    obs = data.get("observations") or []
    pairs: list[tuple[str, float]] = []
    for row in obs:
        d = row.get("d")
        if not d:
            continue
        # series key is usually the series name
        raw = row.get(series_name) or row.get("v")
        if isinstance(raw, dict):
            raw = raw.get("v")
        if raw is None:
            # single-series payloads put value under series name dynamically
            for k, v in row.items():
                if k == "d":
                    continue
                if isinstance(v, dict) and "v" in v:
                    raw = v["v"]
                    break
                if not isinstance(v, dict):
                    raw = v
                    break
        try:
            val = float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            continue
        # monthly label YYYY-MM-DD → YYYY-MM
        period = str(d)[:7]
        if re.match(r"^\d{4}-\d{2}$", period):
            pairs.append((period, val))
    return pairs


def _discover_series_and_table(url: str) -> tuple[list[str], list[tuple[str, float]]]:
    """Playwright: return (series_ids, recent table pairs)."""
    series_ids: list[str] = []
    pairs: list[tuple[str, float]] = []
    playwright, browser, page = render_page(url, wait_ms=3000)
    try:
        table = page.locator("table").first
        rows = table.locator("tr").all_inner_texts()
        if not rows:
            return series_ids, pairs

        header_cells = [c.strip() for c in rows[0].split("\t")]
        periods = [h.replace("‑", "-").replace("–", "-") for h in header_cells if h[:4].isdigit()]

        data_row = next((r for r in rows if _ROW_LABEL in r.lower()), None)
        if data_row is None:
            return series_ids, pairs

        cells = [c.strip() for c in data_row.split("\t")]
        # [label, series_id?, values...]
        for c in cells[1:4]:
            if re.fullmatch(r"[A-Za-z]?\d{4,}(_[A-Za-z]\d+)?", c) or re.fullmatch(r"V\d+(_[A-Za-z]\d+)?", c, re.I):
                series_ids.append(c)
            elif re.fullmatch(r"[A-Z]{1,3}\d+", c):
                series_ids.append(c)

        values = cells[2:] if len(cells) > 2 else []
        # if series id consumed one slot, align
        if series_ids and len(values) == len(periods) + 1:
            values = values[1:]
        for period_label, value in zip(periods, values):
            value = value.replace(",", "").replace("−", "-")
            if not value or value in ("-", "n.a.", "…"):
                continue
            try:
                pairs.append((period_label.replace("‑", "-")[:7], float(value)))
            except ValueError:
                continue
        return series_ids, pairs
    finally:
        browser.close()
        playwright.stop()


def _fetch_td(country_code: str, now: str) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor

    sums: dict[str, float] = {}
    counts: dict[str, int] = {}

    # Fetch the 7 component series in parallel to reduce wall-clock time (sequentially, each
    # request adds ~1s).
    with ThreadPoolExecutor(max_workers=len(_TD_COMPONENT_SERIES)) as executor:
        futures = {executor.submit(_valet_observations, name): name for name in _TD_COMPONENT_SERIES}
        for future in futures:
            name = futures[future]
            try:
                pairs = future.result()
            except Exception as e:
                logger.debug("[%s] Valet TD component %s: %s", country_code, name, e)
                continue
            for period, value in pairs:
                sums[period] = sums.get(period, 0.0) + value
                counts[period] = counts.get(period, 0) + 1

    rows = []
    for period, total in sums.items():
        if counts[period] < len(_TD_COMPONENT_SERIES):
            continue  # only use months where all 7 components are present
        year = int(period[:4])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR_TD,
            "value": round(total, 2),
            "updated_at": now,
        })
    if not rows:
        return _empty()
    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True)


def render(target: dict) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor

    country_code = target["country_code"]
    url = target.get("source_url") or _DEFAULT_PAGE
    now = datetime.now(timezone.utc).isoformat()

    # Fetching the 7 TD series is independent of the FCD Playwright page discovery, so it is
    # kicked off in the background while discovery is in progress (running the two steps
    # sequentially would simply add their durations together).
    td_executor = ThreadPoolExecutor(max_workers=1)
    td_future = td_executor.submit(_fetch_td, country_code, now)

    series_ids: list[str] = []
    table_pairs: list[tuple[str, float]] = []
    try:
        series_ids, table_pairs = _discover_series_and_table(url)
    except Exception as e:
        logger.warning("[%s] page scrape failed: %s", country_code, e)

    candidates = list(dict.fromkeys([*series_ids, *_VALET_CANDIDATES]))
    best = _empty()
    for name in candidates:
        try:
            pairs = _valet_observations(name)
            if len(pairs) < 3:
                continue
            df = _rows_from_period_values(country_code, pairs, now)
            if len(df) > len(best):
                best = df
                logger.info(
                    "[%s] Valet series %s → %d months (%s~%s)",
                    country_code,
                    name,
                    len(df),
                    df["period"].min(),
                    df["period"].max(),
                )
        except Exception as e:
            logger.debug("[%s] Valet %s: %s", country_code, name, e)

    fcd = best
    if fcd.empty and table_pairs:
        fcd = _rows_from_period_values(country_code, table_pairs, now)
        logger.info(
            "[%s] table fallback %d months (%s~%s)",
            country_code,
            len(fcd),
            fcd["period"].min() if len(fcd) else "-",
            fcd["period"].max() if len(fcd) else "-",
        )

    td = td_future.result()
    td_executor.shutdown(wait=False)

    if fcd.empty:
        logger.error("[%s] no FCD series found", country_code)
        return _empty()

    return pd.concat([fcd, td], ignore_index=True).sort_values(["period", "indicator"]).reset_index(drop=True)
