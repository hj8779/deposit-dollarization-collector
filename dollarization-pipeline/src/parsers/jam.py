"""Jamaica: Bank of Jamaica FS.CB.17 — Commercial Banks' Deposit Balances by Currency.

Page:
  https://boj.org.jm/statistics/financial-sector/commercial-banks/
File:
  https://boj.org.jm/wp-content/uploads/2020/09/FS.CB.17.xls

Sheet FS.CB.17 (unit J$ Millions, end of month):
  Date | Local Currency | Foreign Currency | Total | Deposit Dollarisation

FCD = Foreign Currency
TD  = Total  (= Local + Foreign)
FCD_TD_RATIO = FCD/TD*100  (same definition as the file's Deposit Dollarisation column)

Time coverage: per the Data Range metadata, Jan 2000 through the latest month
in the file (observed 2026-06).
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_XLS_URL = "https://boj.org.jm/wp-content/uploads/2020/09/FS.CB.17.xls"
_PAGE = "https://boj.org.jm/statistics/financial-sector/commercial-banks/"
_SHEET = "FS.CB.17"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _to_period(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "year") and hasattr(value, "month"):
        try:
            y, m = int(value.year), int(value.month)
            if 1980 <= y <= 2100 and 1 <= m <= 12:
                return f"{y}-{m:02d}"
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        # 2000-01-31 / 2000-01
        if len(text) >= 7 and text[4] == "-":
            try:
                y, m = int(text[:4]), int(text[5:7])
                if 1980 <= y <= 2100 and 1 <= m <= 12:
                    return f"{y}-{m:02d}"
            except ValueError:
                return None
    return None


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        t = value.strip().replace(",", "")
        if t in {"", "-", "–", "—"}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _find_header_row(df: pd.DataFrame) -> int | None:
    for i in range(min(30, len(df))):
        cells = [
            str(df.iat[i, j]).strip().lower()
            for j in range(min(6, df.shape[1]))
            if df.iat[i, j] is not None and not (isinstance(df.iat[i, j], float) and pd.isna(df.iat[i, j]))
        ]
        joined = " | ".join(cells)
        if "date" in joined and "foreign" in joined and "total" in joined:
            return i
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    try:
        xl = pd.ExcelFile(BytesIO(content), engine="xlrd")
    except Exception:
        try:
            xl = pd.ExcelFile(BytesIO(content))
        except Exception as e:
            logger.error("[%s] xls open failed: %s", country_code, e)
            return _empty()

    sheet = _SHEET if _SHEET in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)
    hdr = _find_header_row(df)
    if hdr is None:
        logger.error("[%s] header row not found", country_code)
        return _empty()

    # map columns by header labels
    col_date = col_fcd = col_td = None
    for j in range(min(8, df.shape[1])):
        lab = df.iat[hdr, j]
        if not isinstance(lab, str):
            continue
        low = lab.strip().lower()
        if low == "date" or low.startswith("date"):
            col_date = j
        elif "foreign" in low:
            col_fcd = j
        elif low == "total" or low.startswith("total"):
            col_td = j
    if col_date is None or col_fcd is None or col_td is None:
        # positional fallback: Date, Local, Foreign, Total
        col_date, col_fcd, col_td = 0, 2, 3

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for i in range(hdr + 1, len(df)):
        period = _to_period(df.iat[i, col_date])
        if not period:
            continue
        fcd = _to_float(df.iat[i, col_fcd])
        td = _to_float(df.iat[i, col_td])
        if fcd is None or td is None or td <= 0:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in (
            ("FCD", round(fcd, 4)),
            ("TD", round(td, 4)),
            ("FCD_TD_RATIO", ratio),
        ):
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    if not rows:
        logger.error("[%s] no data rows parsed", country_code)
        return _empty()

    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] FS.CB.17: %d rows (%s~%s)",
        country_code, len(out), out["period"].min(), out["period"].max(),
    )
    return out


def render(target: dict) -> pd.DataFrame:
    """Find the FS.CB.17 link on the page, falling back to the fixed URL."""
    country_code = target["country_code"]
    url = _XLS_URL
    try:
        page = requests.get(_PAGE, headers=_HEADERS, timeout=60, verify=False)
        if page.ok:
            import re
            m = re.search(r'https?://[^"\']+FS\.CB\.17\.xls', page.text, re.I)
            if m:
                url = m.group(0)
            else:
                m = re.search(r'href=["\']([^"\']*FS\.CB\.17\.xls)["\']', page.text, re.I)
                if m:
                    href = m.group(1)
                    if href.startswith("/"):
                        url = "https://boj.org.jm" + href
                    elif href.startswith("http"):
                        url = href
    except Exception as e:
        logger.warning("[%s] page scrape failed, using fixed xls url: %s", country_code, e)

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
        resp.raise_for_status()
        if not (
            resp.content.startswith(b"\xd0\xcf\x11\xe0") or resp.content.startswith(b"PK")
        ):
            raise RuntimeError(f"not excel: head={resp.content[:40]!r}")
        return parse(resp.content, country_code)
    except Exception as e:
        logger.exception("[%s] download/parse failed: %s", country_code, e)
        return _empty()
