"""Nepal: NRB Monthly Statistics (Banking) xlsx + Annual Report fallback.

Monthly files:
  https://www.nrb.org.np/category/monthly-statistics/
  e.g. contents/uploads/YYYY/MM/{NepaliMonth}_{year}_Publish.xlsx

Sheet C8: per-BFI balance sheet
  DEPOSITS row → TD (sum across BFIs)
  under Current/Savings/Fixed/Call/Others: "Foreign" rows → FCD

Unit: NPR million.
Annual report 2020/21 fallback: FCD=117674.8, TD=4662729.3 (mid-July 2021).
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
_LIST_PAGE = "https://www.nrb.org.np/category/monthly-statistics/"
_ANNUAL = (
    "https://www.nrb.org.np/contents/uploads/2022/05/Annual-Report-2020-21-English.pdf"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}

# Nepali month name → approximate Gregorian month-end of mid-month (NRB mid-month)
# Fiscal year Baisakh≈Apr/May ... Jestha≈May/Jun ... etc. Map publish filename
# to calendar month using file mtime year from path + conventional mapping.
_NEPALI_MONTH = {
    "baisakh": 5, "baishakh": 5,
    "jestha": 6, "jeth": 6,
    "asar": 7, "ashad": 7, "ashadh": 7,
    "shrawan": 8, "sawan": 8,
    "bhadau": 9, "bhadra": 9,
    "asoj": 10, "ashwin": 10, "aswin": 10,
    "kartik": 11,
    "mangshir": 12, "mangsir": 12,
    "poush": 1, "poush": 1, "pous": 1,
    "magh": 2,
    "falgun": 3, "phalgun": 3,
    "chaitra": 4,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("NPL fetches the xlsx via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _period_from_url(url: str) -> str | None:
    """Use Gregorian upload folder YYYY/MM as the observation period.

    NRB mid-month banking files are published with Nepali month names, but the
    contents/uploads/{year}/{month}/ path is the most reliable calendar anchor.
    """
    m = re.search(r"/contents/uploads/(20\d{2})/(\d{2})/", url)
    if m:
        return f"{int(m.group(1))}-{int(m.group(2)):02d}"
    return None


def _list_xlsx() -> list[str]:
    urls: list[str] = []
    for page_i in range(1, 8):
        page = _LIST_PAGE if page_i == 1 else f"{_LIST_PAGE}page/{page_i}/"
        try:
            resp = requests.get(page, headers=_HEADERS, timeout=45, verify=False)
            if resp.status_code != 200:
                continue
            for m in re.finditer(
                r'href=["\']([^"\']+\.xlsx)["\']', resp.text, re.I
            ):
                urls.append(urljoin(page, m.group(1)))
        except Exception as e:
            logger.warning("[NPL] list page %s: %s", page_i, e)
    # unique
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _parse_c8(content: bytes, period: str, country_code: str) -> pd.DataFrame:
    xl = pd.ExcelFile(BytesIO(content))
    sheet = "C8" if "C8" in xl.sheet_names else None
    if not sheet:
        for s in xl.sheet_names:
            if re.search(r"c8|balance|deposit", s, re.I):
                sheet = s
                break
    if not sheet:
        return _empty()
    df = xl.parse(sheet, header=None)

    # Find DEPOSITS row and Foreign rows under deposit section
    dep_row = None
    foreign_rows: list[int] = []
    bills_row = None
    for i in range(len(df)):
        lab = ""
        for j in range(min(4, df.shape[1])):
            if pd.notna(df.iat[i, j]) and isinstance(df.iat[i, j], str):
                lab = str(df.iat[i, j]).strip()
                break
        lab_u = lab.upper()
        if lab_u == "DEPOSITS" or re.match(r"^\d+\s*DEPOSITS$", lab_u):
            dep_row = i
        if dep_row is not None and bills_row is None:
            if re.search(r"bills payable", lab, re.I):
                bills_row = i
            elif lab_u == "FOREIGN" or lab.strip().lower() == "foreign":
                foreign_rows.append(i)

    if dep_row is None:
        return _empty()
    if bills_row is None:
        bills_row = dep_row + 20

    foreign_rows = [r for r in foreign_rows if dep_row < r < bills_row]
    # Bank columns start at col 3 typically
    start_col = 3
    td = 0.0
    fcd = 0.0
    for j in range(start_col, df.shape[1]):
        try:
            td += float(df.iat[dep_row, j])
        except (TypeError, ValueError):
            continue
        for ri in foreign_rows:
            try:
                fcd += float(df.iat[ri, j])
            except (TypeError, ValueError):
                continue

    if td <= 0 or fcd < 0:
        return _empty()

    year = int(period[:4])
    ratio = round((fcd / td) * 100, 4)
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for indicator, value in (
        ("FCD", round(fcd, 4)),
        ("TD", round(td, 4)),
        ("FCD_TD_RATIO", ratio),
    ):
        rows.append(
            {
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            }
        )
    return pd.DataFrame(rows)


def _annual_fallback(country_code: str) -> pd.DataFrame:
    # batch3 / annual report 2020/21 mid-July
    now = datetime.now(timezone.utc).isoformat()
    fcd, td = 117674.8, 4662729.3
    ratio = round((fcd / td) * 100, 4)
    period = "2021-07"
    rows = []
    for indicator, value in (
        ("FCD", fcd),
        ("TD", td),
        ("FCD_TD_RATIO", ratio),
    ):
        rows.append(
            {
                "country_code": country_code,
                "year": 2021,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            }
        )
    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        frames: list[pd.DataFrame] = []
        urls = _list_xlsx()
        logger.info("[NPL] found %d monthly xlsx links", len(urls))
        for url in urls[:24]:  # recent 2 years of monthly files
            try:
                period = _period_from_url(url)
                if not period:
                    continue
                resp = requests.get(url, headers=_HEADERS, timeout=90, verify=False)
                if resp.status_code != 200 or resp.content[:2] != b"PK":
                    continue
                df = _parse_c8(resp.content, period, country_code)
                if not df.empty:
                    frames.append(df)
                    logger.info(
                        "[NPL] %s -> ratio=%s",
                        period,
                        df.loc[df["indicator"] == "FCD_TD_RATIO", "value"].iloc[0],
                    )
            except Exception as e:
                logger.debug("[NPL] skip %s: %s", url[-40:], e)

        if not frames:
            logger.warning("[%s] monthly parse empty; annual fallback", country_code)
            return _annual_fallback(country_code)

        # merge annual for history if not overlapping
        frames.append(_annual_fallback(country_code))
        out = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["period", "indicator"], keep="first")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
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
        return _empty()
