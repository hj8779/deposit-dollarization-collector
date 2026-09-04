"""Malaysia: data.gov.my Monetary Aggregates (BNM M1/M2/M3 components), 2013-01~present.

CSV:
  https://storage.data.gov.my/finsector/money_aggregates.csv

FCD = m2_deposit_fx          (Foreign currency deposits, RM million)
TD  = m1_deposit_demand
    + m2_deposit_saving
    + m2_deposit_fixed
    + m2_deposit_fx
    + m2_deposit_other
      (sum of banking-system deposit components; currency/NID/repo excluded)

api.bnm.gov.my/public/msb/1.3 (Open API) does not support historical queries — it
always returns only the latest month's snapshot (year/month specified via path or
query params is either ignored or returns 404), so it can't be used to extend the
historical range.

For the period before 2013-01 (1998-01~2012-12), data is supplemented from the
'1.3 Monetary Aggregates: M1, M2 and M3' table attached to individual BNM 'Monthly
Statistical Bulletin' issues, in the old XLS format (BIFF, read via xlrd). This
table contains the full cumulative time series up to the issue's publication date
(annual from 1969, monthly from 1998-01), so a single file — the issue immediately
before 2013-01 (the December 2012 issue) — covers the entire 1998-01~2012-12 monthly
range (no need to scrape every issue separately — checked across several issues and
confirmed the table layout is stable). Column layout (0-indexed): 0=year (only on the
first row of each year), 1=month (1-12, monthly section only; mixed string/numeric),
3=M3, 4=M2, 5=M1, 6=currency in circulation, 7=demand deposits, 8=narrow quasi-money
total, 9=savings deposits, 10=fixed deposits, 11=NID, 12=repo, 13=foreign currency
deposits (FCD), 14=other deposits, 15=deposits placed with other financial
institutions. As with the data.gov.my CSV, TD = 7+9+10+13+14 (NID/repo/interbank
placements excluded), FCD = column 13. FCD values are populated for the full period
from 1998-01 onward (earlier annual-only sections show 0 for the undisaggregated
figure and are excluded). The CMS document ID of the attachment in the issue URL can
change, so the current 1.3.xls link is found by scraping the issue's page each time.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO, StringIO

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_CSV = "https://storage.data.gov.my/finsector/money_aggregates.csv"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
}

_TD_PARTS = (
    "m1_deposit_demand",
    "m2_deposit_saving",
    "m2_deposit_fixed",
    "m2_deposit_fx",
    "m2_deposit_other",
)
_FCD = "m2_deposit_fx"

# Issue immediately before 2013-01 (December 2012 issue) — covers the entire
# 1998-01~2012-12 monthly range.
_HISTORICAL_ISSUE_URL = "https://www.bnm.gov.my/-/monthly-statistical-bulletin-dec-2012"
_XLS_LINK_RE = re.compile(r'href="(/documents/20124/\d+/1\.3\.xls)"')
_HIST_TABLE_TITLE = "1.3"
# Do not insert duplicate rows past the last month this historical issue covers
# (the data.gov.my CSV takes over from the following month).
_HISTORICAL_LAST_PERIOD = "2012-12"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MYS fetches the CSV via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _emit(country_code: str, period: str, fcd: float, td: float, now: str) -> list[dict]:
    if td <= 0:
        return []
    ratio = round((fcd / td) * 100, 4)
    year = int(period[:4])
    return [
        {"country_code": country_code, "year": year, "period": period, "indicator": ind, "value": val, "updated_at": now}
        for ind, val in (("FCD", round(fcd, 4)), ("TD", round(td, 4)), ("FCD_TD_RATIO", ratio))
    ]


def _render_historical(country_code: str) -> pd.DataFrame:
    """1998-01~2012-12 (old-format XLS 'Monetary Aggregates' from the December 2012 issue).

    bnm.gov.my appears to have a bot-blocking rule that returns 403 when the
    requests library's default header combination (Accept-Encoding/Connection, etc.)
    is present (curl -A "Mozilla/5.0" always passes, while the requests default
    header set always gets 403), so this uses a session with only the User-Agent
    header set to work around it."""
    import xlrd

    session = requests.Session()
    session.headers.clear()
    session.headers["User-Agent"] = "Mozilla/5.0"

    page = session.get(_HISTORICAL_ISSUE_URL, timeout=30)
    page.raise_for_status()
    match = _XLS_LINK_RE.search(page.text)
    if not match:
        logger.warning("[%s] could not find 1.3.xls link on the historical issue page", country_code)
        return _empty()
    xls_url = "https://www.bnm.gov.my" + match.group(1)

    resp = session.get(xls_url, timeout=60)
    resp.raise_for_status()
    wb = xlrd.open_workbook(file_contents=resp.content)
    sh = wb.sheet_by_index(0)

    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    current_year: int | None = None
    for r in range(9, sh.nrows):
        year_cell = sh.cell_value(r, 0)
        month_cell = sh.cell_value(r, 1)
        if isinstance(year_cell, (int, float)) and year_cell:
            current_year = int(year_cell)
        elif isinstance(year_cell, str) and year_cell.strip().isdigit():
            current_year = int(year_cell.strip())

        month_str = str(month_cell).strip()
        if not month_str or not month_str.replace(".0", "").isdigit() or current_year is None:
            continue  # skip rows outside the monthly section (annual totals, blank separator rows, etc.)
        month = int(float(month_str))
        if not (1 <= month <= 12):
            continue
        period = f"{current_year}-{month:02d}"
        if period > _HISTORICAL_LAST_PERIOD:
            continue

        try:
            demand = float(sh.cell_value(r, 7))
            saving = float(sh.cell_value(r, 9))
            fixed = float(sh.cell_value(r, 10))
            fcd = float(sh.cell_value(r, 13))
            other = float(sh.cell_value(r, 14))
        except (ValueError, TypeError):
            continue
        if fcd <= 0:
            continue  # section where FX deposits weren't broken out separately (pre-1998 annual data, etc.)

        td = demand + saving + fixed + fcd + other
        rows.extend(_emit(country_code, period, fcd, td, now))

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    frames = []
    try:
        historical = _render_historical(country_code)
        if not historical.empty:
            frames.append(historical)
            logger.info(
                "[%s] historical (bulletin issue) %d rows (%s~%s)", country_code, len(historical),
                historical["period"].min(), historical["period"].max(),
            )
    except Exception:
        logger.warning("[%s] failed to collect historical (bulletin issue) data, using 2013- onward only", country_code, exc_info=True)

    try:
        resp = requests.get(_CSV, headers=_HEADERS, timeout=90, verify=False)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        if not {"date", "measure", "value"}.issubset(df.columns):
            logger.error("[%s] unexpected columns %s", country_code, df.columns.tolist())
        else:
            wide = (
                df.pivot_table(index="date", columns="measure", values="value", aggfunc="last")
                .sort_index()
            )
            missing = [c for c in (_FCD, *_TD_PARTS) if c not in wide.columns]
            if missing:
                logger.error("[%s] missing columns %s", country_code, missing)
            else:
                now = datetime.now(timezone.utc).isoformat()
                rows = []
                for date, row in wide.iterrows():
                    fcd = row[_FCD]
                    if pd.isna(fcd):
                        continue
                    td = sum(float(row[c]) for c in _TD_PARTS)
                    ts = pd.Timestamp(date)
                    period = f"{ts.year}-{ts.month:02d}"
                    rows.extend(_emit(country_code, period, float(fcd), td, now))
                if rows:
                    frames.append(pd.DataFrame(rows))
    except Exception:
        logger.exception("[%s] failed to collect 2013- CSV", country_code)

    if not frames:
        return _empty()

    out = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] %d rows total (%s~%s)",
        country_code, len(out), out["period"].min(), out["period"].max(),
    )
    return out
