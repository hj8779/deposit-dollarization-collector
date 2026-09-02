"""Sri Lanka: CBSL Banking Sector Liabilities — LKR vs FCY deposits.

페이지:
  https://www.cbsl.gov.lk/en/statistics/statistical-tables/financial-sector
파일 (월/분기 갱신):
  .../statistics/sheets/Table2.0_YYYYMMDD_e.xlsx

시트 'Liabilities & Capital' — Banking Sector:
  row 'FCY Deposits' → FCD (Rs. Mn)
  row 'Deposits'     → TD  (Rs. Mn)
  열: 분기말 (2022 Q1 …)

period: Q1→03, Q2→06, Q3→09, Q4→12
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
_PAGE = "https://www.cbsl.gov.lk/en/statistics/statistical-tables/financial-sector"
_FALLBACK = (
    "https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/"
    "statistics/sheets/Table2.0_20260622_e.xlsx"
)
_BASE = "https://www.cbsl.gov.lk"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}

_Q_TO_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("LKA는 render()로 xlsx를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _list_xlsx_urls(limit: int = 24) -> list[str]:
    """List Table2.0 (and legacy table2.00) xlsx archives; newest first."""
    urls: list[str] = []
    try:
        resp = requests.get(_PAGE, headers=_HEADERS, timeout=90, verify=False)
        resp.raise_for_status()
        hrefs = re.findall(
            r'href=["\']([^"\']*Table2\.0[^"\']*\.xlsx)["\']',
            resp.text,
            re.I,
        )
        if not hrefs:
            hrefs = re.findall(
                r'href=["\']([^"\']*table2\.0[^"\']*\.xlsx)["\']',
                resp.text,
                re.I,
            )

        def _score(h: str) -> tuple:
            h_l = h.lower()
            legacy = 0 if "table2.00" in h_l else 1
            m = re.search(r"(20\d{6})", h)
            date = int(m.group(1)) if m else 0
            return (legacy, date)

        ranked = sorted(set(hrefs), key=_score, reverse=True)
        for h in ranked[:limit]:
            urls.append(urljoin(_BASE, h))
        logger.info("[LKA] listed %d Table2.0 xlsx candidates", len(urls))
    except Exception as e:
        logger.warning("[LKA] page scrape failed: %s", e)
    if _FALLBACK not in urls:
        urls.append(_FALLBACK)
    return urls


def _resolve_url() -> str:
    urls = _list_xlsx_urls(limit=1)
    return urls[0] if urls else _FALLBACK


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


def _parse(content: bytes, country_code: str) -> pd.DataFrame:
    xl = pd.ExcelFile(BytesIO(content))
    sheet = None
    for s in xl.sheet_names:
        if re.search(r"liabilit", s, re.I):
            sheet = s
            break
    if sheet is None:
        sheet = xl.sheet_names[0]
    df = xl.parse(sheet, header=None)

    # find Banking Sector block start (first 'Deposits' under Banking Sector)
    sector_row = None
    for i in range(len(df)):
        v = df.iat[i, 0]
        if isinstance(v, str) and re.search(r"banking\s+sector", v, re.I):
            sector_row = i
            break
    start = sector_row if sector_row is not None else 0

    # period headers: year row + quarter row
    periods: dict[int, str] = {}
    year_row = None
    for i in range(start, min(start + 10, len(df))):
        years = []
        for j in range(1, df.shape[1]):
            v = df.iat[i, j]
            if isinstance(v, (int, float)) and not pd.isna(v) and 2000 <= int(v) <= 2100:
                years.append((j, int(v)))
            elif isinstance(v, str) and re.fullmatch(r"20\d{2}", v.strip()):
                years.append((j, int(v.strip())))
        if len(years) >= 2:
            year_row = i
            # quarter row is next
            qrow = i + 1
            year_by_col: dict[int, int] = {}
            # years may span multiple quarter cols
            # read year values and forward-fill across columns
            cur_y = None
            for j in range(1, df.shape[1]):
                v = df.iat[year_row, j]
                if isinstance(v, (int, float)) and not pd.isna(v) and 2000 <= int(v) <= 2100:
                    cur_y = int(v)
                elif isinstance(v, str) and re.fullmatch(r"20\d{2}", v.strip()):
                    cur_y = int(v.strip())
                if cur_y is not None:
                    year_by_col[j] = cur_y
            for j in range(1, df.shape[1]):
                qv = df.iat[qrow, j] if qrow < len(df) else None
                q = None
                if isinstance(qv, str):
                    m = re.search(r"Q\s*([1-4])", qv, re.I)
                    if m:
                        q = int(m.group(1))
                elif isinstance(qv, (int, float)) and not pd.isna(qv):
                    # sometimes just 1..4
                    if 1 <= int(qv) <= 4:
                        q = int(qv)
                if q and j in year_by_col:
                    periods[j] = f"{year_by_col[j]}-{_Q_TO_MONTH[q]:02d}"
            break

    if not periods:
        logger.error("[%s] no quarter periods", country_code)
        return _empty()

    # find FCY Deposits and Deposits rows in Banking Sector only (before LCB section)
    fcd_row = td_row = None
    end = len(df)
    for i in range(start, len(df)):
        v = df.iat[i, 0]
        if isinstance(v, str) and re.search(r"licensed commercial banks", v, re.I):
            end = i
            break
    for i in range(start, end):
        v = df.iat[i, 0]
        if not isinstance(v, str):
            continue
        lab = v.strip().lower()
        if lab == "fcy deposits":
            fcd_row = i
        elif lab == "deposits":
            td_row = i
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
        frames: list[pd.DataFrame] = []
        for url in _list_xlsx_urls(limit=24):
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
                if resp.status_code != 200 or not resp.content.startswith(b"PK"):
                    continue
                df = _parse(resp.content, country_code)
                if not df.empty:
                    frames.append(df)
                    logger.info(
                        "[LKA] %s → %d rows (%s~%s)",
                        url.rsplit("/", 1)[-1][:40],
                        len(df),
                        df["period"].min(),
                        df["period"].max(),
                    )
            except Exception as e:
                logger.debug("[LKA] skip %s: %s", url[-50:], e)
        if not frames:
            logger.error("[%s] no Table2.0 xlsx parsed", country_code)
            return _empty()
        out = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] merged %d rows (%s~%s) from %d files",
            country_code,
            len(out),
            out["period"].min(),
            out["period"].max(),
            len(frames),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
