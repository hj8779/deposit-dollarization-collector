"""Cambodia: NBC Deposits with Deposit Money Banks (by currency).

Page:
  https://www.nbc.gov.kh/english/economic_research/monetary_and_financial_statistics_data.php
Filename pattern (updated monthly):
  .../download_files/data/english/17.depositwithdepositmoneybank*.xlsx

Sheet 'deposit' (In Billion KHR, horizontal time series):
  Deposits in Foreign Currency / Total  → FCD
  Grand Total                           → TD
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_PAGE = (
    "https://www.nbc.gov.kh/english/economic_research/"
    "monetary_and_financial_statistics_data.php"
)
_FALLBACK = (
    "https://www.nbc.gov.kh/download_files/data/english/"
    "17.depositwithdepositmoneybankmay-26_en_4193.xlsx"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("KHM locates the xlsx from the page via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _resolve_url() -> str:
    try:
        resp = requests.get(_PAGE, headers=_HEADERS, timeout=90, verify=False)
        resp.raise_for_status()
        # prefer newest depositwithdepositmoneybank xlsx
        hrefs = re.findall(
            r'href=["\']([^"\']*depositwithdepositmoneybank[^"\']*\.xlsx)["\']',
            resp.text,
            re.I,
        )
        if not hrefs:
            hrefs = re.findall(
                r'href=["\']([^"\']*17\.deposit[^"\']*\.xlsx)["\']',
                resp.text,
                re.I,
            )
        if hrefs:
            # last match often latest on page
            h = hrefs[-1]
            url = urljoin(_PAGE, h)
            logger.info("[KHM] resolved %s", url)
            return url
    except Exception as e:
        logger.warning("[KHM] page scrape failed: %s", e)
    return _FALLBACK


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().replace(",", "")
        if t in {"", "-", "–", "—"}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _periods(df: pd.DataFrame) -> dict[int, str]:
    for i in range(min(10, len(df))):
        hits: dict[int, str] = {}
        for j in range(1, df.shape[1]):
            v = df.iat[i, j]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            if hasattr(v, "year") and hasattr(v, "month"):
                hits[j] = f"{int(v.year)}-{int(v.month):02d}"
        if len(hits) >= 3:
            return hits
    return {}


def _find_section_total(df: pd.DataFrame, section_needle: str, total_label: str = "total") -> int | None:
    """Find Total row after a section header containing section_needle."""
    in_section = False
    for i in range(len(df)):
        lab = df.iat[i, 0]
        if not isinstance(lab, str):
            continue
        low = lab.strip().lower()
        if section_needle.lower() in low:
            in_section = True
            continue
        if in_section and low == total_label.lower():
            return i
        if in_section and low.startswith("deposits in") and section_needle.lower() not in low:
            # left section
            in_section = False
    return None


def _parse(content: bytes, country_code: str) -> pd.DataFrame:
    xl = pd.ExcelFile(BytesIO(content))
    sheet = "deposit" if "deposit" in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)
    periods = _periods(df)
    if not periods:
        logger.error("[%s] no periods", country_code)
        return _empty()

    fcd_row = _find_section_total(df, "foreign currency")
    # Grand Total is standalone
    td_row = None
    for i in range(len(df)):
        lab = df.iat[i, 0]
        if isinstance(lab, str) and lab.strip().lower() == "grand total":
            td_row = i
            break
    if fcd_row is None or td_row is None:
        logger.error("[%s] rows fcd=%s td=%s", country_code, fcd_row, td_row)
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for j, period in periods.items():
        fcd = _num(df.iat[fcd_row, j])
        td = _num(df.iat[td_row, j])
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
        return _empty()
    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] %d rows (%s~%s)",
        country_code, len(out), out["period"].min(), out["period"].max(),
    )
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        url = _resolve_url()
        resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
        resp.raise_for_status()
        if not resp.content.startswith(b"PK"):
            raise RuntimeError(f"not xlsx: {resp.content[:40]!r}")
        return _parse(resp.content, country_code)
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
