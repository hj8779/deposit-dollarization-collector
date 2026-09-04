"""Georgia: National Bank of Georgia (NBG) statistics portal M2.1.

The page https://nbg.gov.ge/en/statistics/statistics-data is a Next.js SPA, so
there's no Excel link in the static HTML; the actual data is served via the
following REST endpoints.

1. Category list: GET /gw/api/ct/statistics/data/categories
   (the `Accept-Language: en` header is required — without it, returns an empty array)
2. Table list per category: GET /gw/api/ct/statistics/categories/{id}/data
   - id=15 = "Monetary and Financial Statistics"
   - code="M2.1", title="Money Aggregates and Monetary Ratios"
3. Attached file: https://nbg.gov.ge/fm/{URL-encoded path}
   e.g. .../money-aggregates-and-monetary-ratioseng.xlsx

xlsx sheet 'Monetary Ratios-eng':
    col0  Period (end/start-of-month datetime)
    col9  Deposits in Foreign Currency  (= FCD, Million GEL)
    col10 Deposits, Total               (= TD)
    col13 Dollarization Ratio of Deposits, Included in Broad Money, %
          (empirically confirmed to match FCD/TD*100 within rounding error)

Definition of resident foreign currency deposits: this table's "Deposits in
Foreign Currency" is the balance of bank foreign-currency deposits included in
broad money, and is the numerator used to compute the dollarization ratio
(col13) in the same table.
"""

from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import quote

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_API_BASE = "https://nbg.gov.ge/gw/api/ct"
_FM_BASE = "https://nbg.gov.ge/fm/"
# Monetary and Financial Statistics (M2.x series)
_CATEGORY_ID = 15
_CODE = "M2.1"
_SHEET = "Monetary Ratios-eng"

_API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en",  # without this, categories/data returns an empty array
    "Referer": "https://nbg.gov.ge/en/statistics/statistics-data",
}

_DOWNLOAD_HEADERS = {
    "User-Agent": _API_HEADERS["User-Agent"],
    "Accept": "*/*",
    "Accept-Language": "en",
    "Referer": "https://nbg.gov.ge/en/statistics/statistics-data",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Builds a long-form FCD/TD/FCD_TD_RATIO DataFrame from the M2.1 xlsx bytes."""
    now = datetime.now(timezone.utc).isoformat()
    empty = pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )

    try:
        xl = pd.ExcelFile(BytesIO(content))
    except Exception as e:
        logger.error("[%s] Failed to open xlsx: %s", country_code, e)
        return empty

    sheet = _SHEET if _SHEET in xl.sheet_names else None
    if sheet is None:
        # fallback for variant English sheet names
        for name in xl.sheet_names:
            if "monetary" in name.lower() and "ratio" in name.lower():
                sheet = name
                break
    if sheet is None:
        logger.error("[%s] Could not find Monetary Ratios sheet: %s", country_code, xl.sheet_names)
        return empty

    df = xl.parse(sheet, header=None)
    header_row = _find_header_row(df)
    if header_row is None:
        logger.error("[%s] Could not find header row (Period / Deposits in Foreign Currency)", country_code)
        return empty

    fcd_col = _find_col(df, header_row, "Deposits in Foreign Currency")
    td_col = _find_col(df, header_row, "Deposits, Total")
    if fcd_col is None or td_col is None:
        logger.error(
            "[%s] FCD/TD columns not found (fcd_col=%s, td_col=%s)", country_code, fcd_col, td_col
        )
        return empty

    rows = []
    for i in range(header_row + 1, len(df)):
        period_val = df.iat[i, 0]
        period = _to_period(period_val)
        if period is None:
            continue
        try:
            fcd = float(df.iat[i, fcd_col])
            td = float(df.iat[i, td_col])
        except (TypeError, ValueError):
            continue
        if pd.isna(fcd) or pd.isna(td):
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4) if td else None
        for indicator, value in (
            ("FCD", round(fcd, 4)),
            ("TD", round(td, 4)),
            ("FCD_TD_RATIO", ratio),
        ):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    if not rows:
        return empty
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["period", "indicator"], keep="last")
    return out.sort_values(["period", "indicator"]).reset_index(drop=True)


def _find_header_row(df: pd.DataFrame) -> int | None:
    for i in range(min(10, len(df))):
        for j in range(min(15, df.shape[1])):
            v = df.iat[i, j]
            if isinstance(v, str) and "Deposits in Foreign Currency" in v:
                return i
    return None


def _find_col(df: pd.DataFrame, header_row: int, label: str) -> int | None:
    for j in range(df.shape[1]):
        v = df.iat[header_row, j]
        if isinstance(v, str) and label in v:
            return j
    return None


def _to_period(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return f"{value.year}-{value.month:02d}"
    if hasattr(value, "year") and hasattr(value, "month"):
        try:
            return f"{int(value.year)}-{int(value.month):02d}"
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        # "YYYY-MM" or "YYYY-MM-DD..."
        text = value.strip()
        if len(text) >= 7 and text[4] == "-":
            try:
                year = int(text[:4])
                month = int(text[5:7])
                if 1 <= month <= 12:
                    return f"{year}-{month:02d}"
            except ValueError:
                return None
    return None


def _resolve_m21_file() -> str:
    """Fetches the relative file path for the M2.1 item from the API. Falls back to a known default path on failure."""
    fallback = (
        "სტატისტიკა/monetary_statistics/eng/"
        "money-aggregates-and-monetary-ratioseng.xlsx"
    )
    try:
        resp = requests.get(
            f"{_API_BASE}/statistics/categories/{_CATEGORY_ID}/data",
            headers=_API_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        logger.warning("[GEO] Category API failed, using default file path: %s", e)
        return fallback

    for item in items or []:
        if str(item.get("code", "")).strip().upper() == _CODE:
            path = (item.get("file") or "").strip()
            if path:
                logger.info(
                    "[GEO] M2.1 file confirmed: %s (update=%s, next=%s)",
                    path, item.get("updateDate"), item.get("nextUpdateDate"),
                )
                return path

    logger.warning("[GEO] M2.1 item not found via API, using default path")
    return fallback


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    file_path = _resolve_m21_file()
    url = _FM_BASE + quote(file_path, safe="/")
    logger.info("[%s] Downloading M2.1: %s", country_code, url)
    resp = requests.get(url, headers=_DOWNLOAD_HEADERS, timeout=60)
    resp.raise_for_status()
    content = resp.content
    if not content.startswith(b"PK"):
        logger.error(
            "[%s] Response is not xlsx (len=%d, head=%r)",
            country_code, len(content), content[:80],
        )
        return pd.DataFrame(
            columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
        )
    return parse(content, country_code)
