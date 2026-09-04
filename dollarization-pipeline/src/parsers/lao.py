"""Lao PDR: BOL Other Depository Corporations Survey.

Page:
  https://www.bol.gov.la/en/Money_and_Banking
File:
  https://www.bol.gov.la/statistics/Other Depository corporations Survey_Lao PDR.xlsx

Sheet ODC (billions of KIP, monthly eop):
  LAO_FOST_XDC     Deposits                     → TD
  LAO_FOST_FX_XDC  Deposits in foreign currency → FCD
  period header: 2009-12, 2010-01, ...
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import quote

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_PAGE = "https://www.bol.gov.la/en/Money_and_Banking"
_FALLBACK = (
    "https://www.bol.gov.la/statistics/"
    + quote("Other Depository corporations Survey_Lao PDR.xlsx")
)
_FCD_CODE = "LAO_FOST_FX_XDC"
_TD_CODE = "LAO_FOST_XDC"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("LAO fetches the xlsx via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _resolve_url() -> str:
    try:
        resp = requests.get(_PAGE, headers=_HEADERS, timeout=90, verify=False)
        resp.raise_for_status()
        m = re.search(
            r'href=["\']([^"\']*Other[^"\']*Depository[^"\']*\.xlsx)["\']',
            resp.text,
            re.I,
        )
        if m:
            href = m.group(1).replace(" ", "%20")
            if href.startswith("http"):
                return href
            if href.startswith("/"):
                return "https://www.bol.gov.la" + href
            return "https://www.bol.gov.la/" + href
    except Exception as e:
        logger.warning("[LAO] page scrape failed: %s", e)
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
    for i in range(min(15, len(df))):
        hits: dict[int, str] = {}
        for j in range(1, df.shape[1]):
            v = df.iat[i, j]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            if hasattr(v, "year") and hasattr(v, "month"):
                hits[j] = f"{int(v.year)}-{int(v.month):02d}"
                continue
            s = str(v).strip()
            m = re.match(r"^(\d{4})-(\d{1,2})$", s)
            if m:
                y, mon = int(m.group(1)), int(m.group(2))
                if 1 <= mon <= 12:
                    hits[j] = f"{y}-{mon:02d}"
        if len(hits) >= 3:
            return hits
    return {}


def _find_code_row(df: pd.DataFrame, code: str) -> int | None:
    code_u = code.upper()
    for i in range(len(df)):
        for j in range(min(4, df.shape[1])):
            v = df.iat[i, j]
            if isinstance(v, str) and v.strip().upper() == code_u:
                return i
    return None


def _parse(content: bytes, country_code: str) -> pd.DataFrame:
    xl = pd.ExcelFile(BytesIO(content))
    sheet = "ODC" if "ODC" in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)
    periods = _periods(df)
    if not periods:
        logger.error("[%s] no periods", country_code)
        return _empty()

    fcd_row = _find_code_row(df, _FCD_CODE)
    td_row = _find_code_row(df, _TD_CODE)
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
            # fallback fixed path
            resp = requests.get(_FALLBACK, headers=_HEADERS, timeout=120, verify=False)
            resp.raise_for_status()
        if not resp.content.startswith(b"PK"):
            raise RuntimeError(f"not xlsx: {resp.content[:40]!r}")
        return _parse(resp.content, country_code)
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
