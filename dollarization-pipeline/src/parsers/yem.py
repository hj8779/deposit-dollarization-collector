"""Yemen: Central Bank of Yemen (Aden, internationally-recognized) research page,
two families of PDF: "Annual Report" (published once a year) + "Monetary and Financial
Developments" monthly bulletin (plus some "CBY Quarterly Bulletin" issues) — both carry
the same 'Table 1: Monetary Survey of Yemen' table.

Both link types are scraped from https://english.cby-ye.com/researchandstatistics.

1) Annual Report (only 3 exist as of this writing: 2020/2024/2025; no separate annual
   report exists for 2021-2023 - CBY simply skipped that span). Table 1 in each report is a
   rolling 9-12 year window, and combining all three covers annual data from 2014 to 2025:
     - Annual Report 2020: ~2016-2020 (billion rials)
     - Annual Report 2024: ~2020-2024 (million rials)
     - Annual Report 2025: ~2021-2025 (million rials, with a footnote that market exchange
       rates are used starting 2022)
   Overlapping years are overwritten with the most recent report's value.
   → period="YYYY-Annual".

2) "Monetary and Financial Developments" monthly bulletin (published monthly from 2021-12;
   title wording is inconsistent - "Monetary and Financial Developments - December 2023"/
   "...development July 2022"/"...Developments Dec - 2025" - so month/year are extracted
   via free-form search) plus some "CBY Quarterly Bulletin" issues (from 2020-12). Table 1
   in these bulletins has the same 'Items' header plus rolling year columns, but only the
   last 1-2 columns are the actual month covered by that issue (e.g. Nov/Dec 2023); the
   rest are reprints of past year-end snapshots and overlap with other issues. So for these
   bulletins, **only the rightmost (last) column** is taken as the issue's own reporting
   month (month/year parsed from the title), and the remaining columns are discarded (the
   period namespace is kept separate as "YYYY-MM" so it doesn't matter if values overlap
   with the Annual Report track). → period="YYYY-MM". Empirically verified: the last column
   of Table 1 in the 2023-12 issue gives FCD=5,818.6 / TD(Quasi+Demand)=8,153.6 billion
   rials — the same figures appear in the "2023-Annual" row of Annual Report 2025 in
   million units (5,818,560 / 8,153,651.2), confirming a match.

The table header lists years on a row starting with 'Items'; since the document has
multiple tables using an 'Items' header (sector-level statistics tables, etc.), the
candidate headers are tried in order of most years listed first, and the first table where
all three rows - 'Foreign currency deposits'/'Quasi-money'/'Demand deposits' - match is
adopted.

TD = Quasi-money + Demand deposits (confirmed to closely match the value backed out from
the table's own 'Foreign currency deposits to total deposits' ratio). FCD = Foreign
currency deposits. Units vary by report (billion/million rials) and are stored as reported
(there is a scale discontinuity across years; FCD_TD_RATIO is unaffected)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.fcd_series import pdf_text
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_RESEARCH_PAGE = "https://english.cby-ye.com/researchandstatistics"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

_ANNUAL_REPORT_LINK_RE = re.compile(r'<a[^>]*href="(/files/[^"]+\.pdf)"[^>]*>\s*[^<]*[Aa]nnual\s+[Rr]eport[^<]*</a>')
_MONTHLY_LINK_RE = re.compile(
    r'<a[^>]*href="(/files/[^"]+\.pdf)"[^>]*>\s*([^<]*(?:[Mm]onetary\s+and\s+[Ff]inancial\s+[Dd]evelopment|[Qq]uarterly\s+[Bb]ulletin)[^<]*)</a>'
)
_ITEMS_HEADER_RE = re.compile(r"^Items\b")
_YEAR_TOKEN_RE = re.compile(r"\*?(\d{4})")

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_TITLE_MONTH_YEAR_RE = re.compile(
    r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")[a-z]*\W*(\d{4})",
    re.I,
)


def _parse_period_from_title(title: str) -> str | None:
    m = _TITLE_MONTH_YEAR_RE.search(title)
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    year = int(m.group(2))
    return f"{year}-{month:02d}"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("YEM crawls the annual-report listing via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _list_annual_report_urls() -> list[str]:
    resp = requests.get(_RESEARCH_PAGE, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return sorted({urljoin(_RESEARCH_PAGE, m) for m in _ANNUAL_REPORT_LINK_RE.findall(resp.text)})


def _list_monthly_bulletin_urls() -> list[tuple[str, str]]:
    """Return [(url, title)] for 'Monetary and Financial Developments' / 'CBY
    Quarterly Bulletin' issues (excludes Annual Report, matched separately)."""
    resp = requests.get(_RESEARCH_PAGE, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    out = []
    seen = set()
    for href, title in _MONTHLY_LINK_RE.findall(resp.text):
        url = urljoin(_RESEARCH_PAGE, href)
        if url not in seen:
            seen.add(url)
            out.append((url, title.strip()))
    return out


def _row_values(lines: list[str], header_idx: int, label: str, n: int) -> list[float] | None:
    for line in lines[header_idx: header_idx + 40]:
        low = line.lower()
        if label.lower() not in low:
            continue
        if "change" in low or "to broad" in low or "to total" in low:
            continue
        nums = re.findall(r"-?[\d,]+\.\d+", line)
        if len(nums) >= n:
            return [float(x.replace(",", "")) for x in nums[-n:]]
    return None


def _extract_monetary_survey(text: str) -> tuple[list[str], list[float], list[float], list[float]] | None:
    lines = text.splitlines()
    candidates = []
    for i, line in enumerate(lines):
        if not _ITEMS_HEADER_RE.match(line.strip()):
            continue
        years = _YEAR_TOKEN_RE.findall(line)
        if len(years) >= 2:
            candidates.append((i, years))

    for i, years in sorted(candidates, key=lambda c: -len(c[1])):
        n = len(years)
        fcd = _row_values(lines, i, "Foreign currency deposits", n)
        quasi = _row_values(lines, i, "Quasi-money", n)
        demand = _row_values(lines, i, "Demand deposits", n)
        if fcd and quasi and demand:
            return years, fcd, quasi, demand
    return None


def _extract_latest_column(text: str) -> tuple[float, float, float] | None:
    """Same Table 1 lookup as _extract_monetary_survey, but only the rightmost
    (this issue's own reporting month) column — used for monthly/quarterly
    bulletins where earlier columns just re-print prior year-end snapshots."""
    lines = text.splitlines()
    candidates = []
    for i, line in enumerate(lines):
        if not _ITEMS_HEADER_RE.match(line.strip()):
            continue
        years = _YEAR_TOKEN_RE.findall(line)
        if len(years) >= 2:
            candidates.append((i, len(years)))

    for i, n in sorted(candidates, key=lambda c: -c[1]):
        fcd = _row_values(lines, i, "Foreign currency deposits", n)
        quasi = _row_values(lines, i, "Quasi-money", n)
        demand = _row_values(lines, i, "Demand deposits", n)
        if fcd and quasi and demand:
            return fcd[-1], quasi[-1], demand[-1]
    return None


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()
    combined: dict[str, tuple[float, float]] = {}

    try:
        urls = _list_annual_report_urls()
    except Exception:
        urls = []
        logger.exception("[%s] failed to fetch annual report listing", country_code)

    logger.info("[%s] found %d annual report(s)", country_code, len(urls))

    for url in urls:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=120)
            resp.raise_for_status()
            text = pdf_text(resp.content)
            found = _extract_monetary_survey(text)
            if not found:
                logger.warning("[%s] Monetary Survey table not found: %s", country_code, url.rsplit("/", 1)[-1])
                continue
            years, fcd, quasi, demand = found
            for year, f, q, d in zip(years, fcd, quasi, demand):
                td = q + d
                if td > 0:
                    combined[f"{year}-Annual"] = (f, td)
            logger.info("[%s] %s -> %d year(s)", country_code, url.rsplit("/", 1)[-1], len(years))
        except Exception:
            logger.warning("[%s] failed to process %s", country_code, url, exc_info=True)

    try:
        monthly_urls = _list_monthly_bulletin_urls()
    except Exception:
        monthly_urls = []
        logger.exception("[%s] failed to fetch monthly bulletin listing", country_code)

    logger.info("[%s] found %d monthly/quarterly bulletin(s)", country_code, len(monthly_urls))

    def _one(item: tuple[str, str]) -> tuple[str, float, float] | None:
        url, title = item
        period = _parse_period_from_title(title)
        if period is None:
            logger.debug("[%s] failed to parse year/month from title: %s", country_code, title)
            return None
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=120)
            resp.raise_for_status()
            text = pdf_text(resp.content)
            found = _extract_latest_column(text)
            if not found:
                logger.warning("[%s] Monetary Survey table not found: %s", country_code, title)
                return None
            f, q, d = found
            td = q + d
            if td > 0:
                return period, f, td
        except Exception:
            logger.warning("[%s] failed to process %s", country_code, url, exc_info=True)
        return None

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_one, item): item for item in monthly_urls}
        for fut in as_completed(futs):
            result = fut.result()
            if result:
                period, f, td = result
                combined[period] = (f, td)

    if not combined:
        return _empty()

    rows = []
    for period, (fcd, td) in combined.items():
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
