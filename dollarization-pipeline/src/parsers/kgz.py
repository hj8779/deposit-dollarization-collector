"""Kyrgyzstan: NBKR Deposits in commercial banks by the end of the period.

페이지: https://www.nbkr.kg/index1.jsp?item=124&lang=ENG
엑셀:   DOC/.../*.xls (페이지 링크에서 해석; 파일명 해시 월별 갱신)

시트 '1.total deposits' (ths of soms / end of period):
  Period | Total volume | ... | in national currency volume | ... | in foreign currency volume
  FCD = foreign currency volume (col 5)
  TD  = Total volume (col 1)

유의사항: 'Newly accepted deposits' 는 flow 이므로 사용하지 않음.
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
_PAGE = "https://www.nbkr.kg/index1.jsp?item=124&lang=ENG"
_BASE = "https://www.nbkr.kg/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("KGZ는 render()로 페이지에서 xls를 찾는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _resolve_xls_url() -> str:
    resp = requests.get(_PAGE, headers=_HEADERS, timeout=90, verify=False)
    resp.raise_for_status()
    # DOC/.../*.xls links
    m = re.search(
        r'href=["\']([^"\']*DOC/[^"\']+\.xls)["\']',
        resp.text,
        re.I,
    )
    if not m:
        m = re.search(r'(DOC/\d+/[0-9A-Fa-f]+\.xls)', resp.text, re.I)
    if not m:
        raise RuntimeError("KGZ deposits xls link not found on page")
    href = m.group(1)
    url = urljoin(_BASE, href)
    logger.info("[KGZ] resolved %s", url)
    return url


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().replace(",", "").replace(" ", "")
        if t in {"", "-", "–", "—"}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _parse_period_cell(text: str, last_year: int | None) -> tuple[int, int, int | None]:
    """'January 1996' / 'February' / 'January 1997' → (year, month, new_last_year)."""
    t = text.strip().replace("*", "")
    m = re.match(r"([A-Za-z]+)\s+(\d{4})", t)
    if m:
        mon = _MONTHS.get(m.group(1).lower())
        year = int(m.group(2))
        if mon:
            return year, mon, year
    mon = _MONTHS.get(t.lower())
    if mon and last_year:
        return last_year, mon, last_year
    return 0, 0, last_year


def _parse(content: bytes, country_code: str) -> pd.DataFrame:
    try:
        xl = pd.ExcelFile(BytesIO(content))
    except Exception:
        xl = pd.ExcelFile(BytesIO(content), engine="xlrd")

    sheet = next(
        (n for n in xl.sheet_names if "total deposit" in n.lower() or n.startswith("1.")),
        xl.sheet_names[0],
    )
    df = xl.parse(sheet, header=None)

    # find header: Period, Total volume, foreign currency volume
    # structure: col0 Period, col1 Total, col3 NC vol, col5 FC vol
    data_start = None
    for i in range(min(15, len(df))):
        lab = df.iat[i, 0]
        if isinstance(lab, str) and lab.strip().lower().startswith("period"):
            data_start = i + 1
            # skip sub-header rows until first month-like
            break
    if data_start is None:
        data_start = 8

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    last_year = None
    for i in range(data_start, len(df)):
        lab = df.iat[i, 0]
        if not isinstance(lab, str):
            continue
        year, mon, last_year = _parse_period_cell(lab, last_year)
        if not year or not mon:
            continue
        td = _num(df.iat[i, 1])
        fcd = _num(df.iat[i, 5])
        if td is None or fcd is None or td <= 0:
            continue
        period = f"{year}-{mon:02d}"
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
        "[%s] %d rows (%s~%s) sheet=%s",
        country_code, len(out), out["period"].min(), out["period"].max(), sheet,
    )
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        url = _resolve_xls_url()
        resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
        resp.raise_for_status()
        if not (resp.content.startswith(b"PK") or resp.content.startswith(b"\xd0\xcf\x11\xe0")):
            raise RuntimeError(f"not excel: {resp.content[:40]!r}")
        return _parse(resp.content, country_code)
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
