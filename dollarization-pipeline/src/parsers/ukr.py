"""Ukraine: NBU deposit Excel — full resident / household FCD/TD series.

Primary (auto-updating single workbook, re-published by NBU):
  https://bank.gov.ua/files/3.2-Deposits_e.xlsx
  Sheet 3.2.4.1 — Deposits by households, by currency
    TD  = Total (col 1)
    FCD = in foreign currency total (col 11)
  Units: UAH million, end-of-period; annual + monthly from ~2002.

Fallback: StatService deposit API (Deposits_Households, odr030=02/total)
plus documented pre-2002 research points.

Re-running render() always re-downloads the workbook → quarterly jobs stay current.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.utils.fcd_series import (
    empty_frame,
    http_get,
    long_rows,
    long_rows_ratio_only,
    merge_frames,
    now_iso,
    parse_nbu_year_month_sheet,
    session,
)
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_XLSX = "https://bank.gov.ua/files/3.2-Deposits_e.xlsx"
_API = "https://bank.gov.ua/NBUStatService/v1/statdirectory/deposit"
_SHEET = "3.2.4.1"  # households by currency
_SEED_RATIOS = [
    ("1995-12", 44.0),
    ("1996-12", 38.5),
    ("2000-12", 25.5),
]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    return _from_xlsx(content, country_code)


def _from_xlsx(content: bytes, country_code: str) -> pd.DataFrame:
    df = pd.read_excel(BytesIO(content), sheet_name=_SHEET, header=None)
    obs = parse_nbu_year_month_sheet(df, total_col=1, fcd_col=11, data_start_row=12)
    # also try all-resident sheet if households thin
    if len(obs) < 12:
        try:
            df2 = pd.read_excel(BytesIO(content), sheet_name="3.2.1.2.", header=None)
            obs = parse_nbu_year_month_sheet(df2, total_col=1, fcd_col=11, data_start_row=12)
        except Exception:
            pass
    return long_rows(country_code, obs)


def _api_month(sess: requests.Session, date_str: str) -> tuple[str, float, float] | None:
    try:
        resp = sess.get(
            _API,
            params={
                "date": date_str,
                "json": "",
                "id_api": "Deposits_Households",
                "odkodter": "total",
            },
            timeout=60,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
        vals: dict[str, float] = {}
        for row in data if isinstance(data, list) else []:
            if row.get("id_api") != "Deposits_Households":
                continue
            if row.get("odkodter") != "total" or row.get("ods183dd") != "total":
                continue
            if row.get("odk111") != "total" or row.get("odk051") != "total":
                continue
            if row.get("odf074") != "total":
                continue
            vals[str(row.get("odr030") or "")] = float(row["value"])
        td, fcd = vals.get("total"), vals.get("02")
        if td and fcd and td > 0:
            y, m = int(date_str[:4]), int(date_str[4:6])
            return f"{y}-{m:02d}", fcd, td
    except Exception as e:
        logger.debug("[UKR] api %s: %s", date_str, e)
    return None


def _api_recent(country_code: str, months: int = 24) -> pd.DataFrame:
    """Fill any gap at the tail with API months (workbook lag)."""
    from calendar import monthrange
    from datetime import datetime

    now = datetime.utcnow()
    dates = []
    y, m = now.year, now.month
    for _ in range(months):
        dates.append(f"{y}{m:02d}01")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    sess = session()
    obs = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(_api_month, sess, d) for d in dates]
        for fut in as_completed(futs):
            r = fut.result()
            if r:
                obs.append(r)
    return long_rows(country_code, obs)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        updated = now_iso()
        frames = []
        try:
            content = http_get(_XLSX, timeout=120).content
            if content[:2] == b"PK":
                live = _from_xlsx(content, country_code)
                if len(live):
                    frames.append(live)
                    logger.info(
                        "[%s] xlsx %d rows (%s~%s)",
                        country_code,
                        len(live),
                        live["period"].min(),
                        live["period"].max(),
                    )
        except Exception as e:
            logger.warning("[%s] xlsx failed: %s", country_code, e)

        try:
            api_df = _api_recent(country_code, months=18)
            if len(api_df):
                frames.append(api_df)
        except Exception as e:
            logger.debug("[%s] api tail: %s", country_code, e)

        seed = long_rows_ratio_only(country_code, _SEED_RATIOS, updated=updated)
        # seed only fills gaps before live starts
        if frames:
            live_min = min(f["period"].min() for f in frames if len(f))
            seed = seed[seed["period"] < live_min] if len(seed) else seed
        frames.append(seed)

        out = merge_frames(*frames)
        if not len(out):
            return empty_frame()
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
        return empty_frame()
