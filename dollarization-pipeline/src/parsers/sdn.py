"""Sudan: Central Bank of Sudan (CBOS) annual reports, "Deposits in Local/Foreign
Currency" tables.

Listing: collected from https://cbos.gov.sd/en/publication-type/annual-reports,
gathering /en/content/annual-report-YYYY links (only 2002-2018 exist; nothing
published after 2019 — the last annual report posted on the CBOS site itself
is for 2018). Each annual report page has an English PDF link (plus an
unrelated Arabic org-chart PDF link that appears on every year's page in
common); we exclude the Arabic (percent-encoded, starting with %D8) link and
take the first PDF.

Each report contains tables for two years, the report year and the prior year
(e.g. "Deposits in Local Currency by the end of 2017 and 2018"; the exact table
title wording varies slightly by year — sometimes a prefix or "the years" is
inserted, as in "Total deposits in Local Currency by the end of the years 2013
and 2014" — so instead of matching an exact phrase, we search loosely for the
combination of two 4-digit numbers + "Local/Foreign Currency" + "Deposit").
Scanning every 2002-2018 report and letting overlapping years be overwritten
by the more recent report's values produces a complete 2002-2018 annual time
series.

The table breaks deposits down by depositor type (government/public
enterprises/private) and then has a 'Grand Total' row with the sum for both
years; we use that total directly: FCD = Grand Total from the Foreign Currency
table, TD = Local Grand Total + Foreign Grand Total. Units are SDG million
(note: before 2007, Sudan reports in the old dinar, pre-currency-reform, so the
absolute scale differs — we store the value exactly as printed in the report).

pdftotext -layout reads the font encoding of these PDFs far more reliably than
pdfplumber (the embedded fonts in older reports come out of pdfplumber entirely
as garbled (cid:NN) characters), so we use pdftotext as the primary extractor.

--- Quarterly bulletins (additional) ---
Listing: https://cbos.gov.sd/en/periodicals-publications?field_publication_type_tid_i18n=44
(quarters 2003-2025, extending more recently than the annual reports). Post
slugs come in several different forms — 'Nth-quarter-YYYY',
'quarter-N-YYYY', 'first-quarter-YYYY', 'NYYYY' (looks like a typo, e.g.
'32020-0' = 2020-Q3) — so we try several regexes. Bulletin titles/link text
are also inconsistently formatted, and the PDF links are mostly Arabic
filenames; but inside the PDF, the 'Table No.(20) Money Supply' table (the
number can change issue to issue, so we locate it by finding the table where
'Money Supply' and 'Foreign Currency Deposits' appear together) uses English
labels + roman numerals even within the Arabic report, so it parses fine as-is.

This table shows the most recent 9 periods side by side each issue (past
year-ends + recent quarters) as a rolling window, so rather than parsing
header alignment, we just take the 'last number' on each row (= that issue's
own quarter, the rightmost column of the table); we already know that quarter
from the post slug, so no header matching is needed. TD = Demand Deposits +
Local Currency Deposits + Foreign Currency Deposits (= Money Supply M2 -
Currency with the Public; we verified both approaches match exactly).
FCD = Foreign Currency Deposits."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.fcd_series import pdf_text
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_ARCHIVE_URL = "https://cbos.gov.sd/en/publication-type/annual-reports"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

_REPORT_LINK_RE = re.compile(r'href="(/en/content/annual-report-[^"]*)"')
_PDF_LINK_RE = re.compile(r'href="(https://cbos\.gov\.sd/sites/default/files/[^"]+\.pdf)"', re.I)
_TITLE_RE = re.compile(
    r"[Dd]eposits?[^\n]{0,40}(Local|Foreign) Currency[^\n]{0,40}?(\d{4})\s+and\s*(?:the\s+year[s]?\s+)?(\d{4})",
)
_GRAND_TOTAL_RE = re.compile(r"Grand [Tt]otal\s*\n*\s*([\d,]+\.?\d*)\s+([\d,]+\.?\d*)")
_GRAND_TOTAL_FALLBACK_RE = re.compile(r"Grand [Tt]otal[^\n]*\n?[^\n]*?([\d,]+\.?\d*)[^\n]*?([\d,]+\.?\d*)")

_QUARTERLY_LIST_URL = "https://cbos.gov.sd/en/periodicals-publications?field_publication_type_tid_i18n=44"
_QUARTER_LINK_RE = re.compile(r'href="(/en/content/[^"]*)"')
_QUARTER_SLUG_PATTERNS = [
    re.compile(r"(\d)(?:st|nd|rd|th)-quarter-(\d{4})"),
    re.compile(r"quarter-(\d)-(\d{4})"),
    re.compile(r"(first|second|third|fourth)-quarter-(\d{4})"),
    re.compile(r"^(\d)(\d{4})(?:-\d+)?$"),
]
_QUARTER_WORD_MAP = {"first": "1", "second": "2", "third": "3", "fourth": "4"}


def _period_from_slug(slug: str) -> str | None:
    for pat in _QUARTER_SLUG_PATTERNS:
        m = pat.search(slug)
        if not m:
            continue
        q, year = m.group(1), m.group(2)
        q = _QUARTER_WORD_MAP.get(q, q)
        if q in ("1", "2", "3", "4"):
            return f"{year}-Q{q}"
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SDN iterates the annual report list via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _list_report_pages() -> list[str]:
    resp = requests.get(_ARCHIVE_URL, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    return sorted({urljoin(_ARCHIVE_URL, m) for m in _REPORT_LINK_RE.findall(resp.text)})


def _find_pdf_url(report_page_url: str) -> str | None:
    """Finds the bulletin PDF link. Quarterly bulletins often have only an
    Arabic filename (but the table labels inside are in English, so it still
    parses fine); we exclude only the unrelated org-chart PDF that appears on
    every year's page ('...82%5D.pdf') and take the first PDF otherwise."""
    resp = requests.get(report_page_url, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    for url in _PDF_LINK_RE.findall(resp.text):
        if "82%5D.pdf" in url:
            continue
        return url
    return None


def _extract_deposits(text: str) -> dict[tuple[str, int], float]:
    results: dict[tuple[str, int], float] = {}
    for m in _TITLE_RE.finditer(text):
        kind = m.group(1).lower()
        y1, y2 = int(m.group(2)), int(m.group(3))
        window = text[m.end(): m.end() + 3000]
        gt = _GRAND_TOTAL_RE.search(window) or _GRAND_TOTAL_FALLBACK_RE.search(window)
        if not gt:
            continue
        try:
            v1 = float(gt.group(1).replace(",", ""))
            v2 = float(gt.group(2).replace(",", ""))
        except ValueError:
            continue
        results[(kind, y1)] = v1
        results[(kind, y2)] = v2
    return results


def _render_annual(country_code: str) -> pd.DataFrame:
    try:
        report_pages = _list_report_pages()
    except Exception:
        logger.exception("[%s] failed to fetch annual report list", country_code)
        return _empty()

    logger.info("[%s] found %d annual reports", country_code, len(report_pages))

    combined: dict[tuple[str, int], float] = {}
    for page_url in report_pages:
        try:
            pdf_url = _find_pdf_url(page_url)
            if not pdf_url:
                logger.warning("[%s] no PDF link: %s", country_code, page_url)
                continue
            resp = requests.get(pdf_url, headers=_HEADERS, timeout=120, verify=False)
            resp.raise_for_status()
            text = pdf_text(resp.content)
            found = _extract_deposits(text)
            if found:
                combined.update(found)  # overwritten by the most recent report (years walked in ascending order)
                logger.info("[%s] %s -> %d entries", country_code, pdf_url.rsplit("/", 1)[-1][:50], len(found))
            else:
                logger.warning("[%s] table not found: %s", country_code, pdf_url.rsplit("/", 1)[-1][:50])
        except Exception:
            logger.warning("[%s] failed to process %s", country_code, page_url, exc_info=True)

    years = sorted({y for _, y in combined})
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for year in years:
        local = combined.get(("local", year))
        fx = combined.get(("foreign", year))
        if local is None or fx is None:
            continue
        td = local + fx
        if td <= 0:
            continue
        period = f"{year}-Annual"
        ratio = round((fx / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fx, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })
    return pd.DataFrame(rows) if rows else _empty()


def _last_number(line: str) -> float | None:
    nums = re.findall(r"[\d,]+\.?\d*", line)
    nums = [n for n in nums if re.search(r"\d", n)]
    if not nums:
        return None
    try:
        return float(nums[-1].replace(",", ""))
    except ValueError:
        return None


def _extract_money_supply_last_col(text: str) -> tuple[float, float, float] | None:
    """(fcd, local, demand) — the rightmost values in the 'Money Supply' table
    (= the quarter that this bulletin itself covers)."""
    if "Money Supply" not in text or "Foreign Currency Deposits" not in text:
        return None
    fcd = local = demand = None
    for line in text.splitlines():
        if "Foreign Currency Deposits" in line and fcd is None:
            fcd = _last_number(line)
        elif "Local Currency Deposits" in line and local is None:
            local = _last_number(line)
        elif "Demand Deposits" in line and demand is None:
            demand = _last_number(line)
    if fcd is None or local is None or demand is None:
        return None
    return fcd, local, demand


def _list_quarterly_pages() -> list[tuple[str, str]]:
    """[(period, page_url), ...]"""
    resp = requests.get(_QUARTERLY_LIST_URL, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    out = []
    for href in set(_QUARTER_LINK_RE.findall(resp.text)):
        slug = href.rsplit("/", 2)[-1] if href.endswith("/") else href.rsplit("/", 1)[-1]
        period = _period_from_slug(slug)
        if period:
            out.append((period, urljoin(_QUARTERLY_LIST_URL, href)))
    return sorted(set(out))


def _render_quarterly(country_code: str) -> pd.DataFrame:
    try:
        pages = _list_quarterly_pages()
    except Exception:
        logger.exception("[%s] failed to fetch quarterly bulletin list", country_code)
        return _empty()

    logger.info("[%s] found %d quarterly bulletins", country_code, len(pages))

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period, page_url in pages:
        try:
            pdf_url = _find_pdf_url(page_url)
            if not pdf_url:
                logger.warning("[%s] no PDF link: %s", country_code, page_url)
                continue
            resp = requests.get(pdf_url, headers=_HEADERS, timeout=120, verify=False)
            resp.raise_for_status()
            text = pdf_text(resp.content)
            found = _extract_money_supply_last_col(text)
            if not found:
                logger.warning("[%s] Money Supply table not found: %s (%s)", country_code, period, pdf_url.rsplit("/", 1)[-1][:50])
                continue
            fcd, local, demand = found
            td = local + demand + fcd
            if td <= 0:
                continue
            year = int(period[:4])
            ratio = round((fcd / td) * 100, 4)
            for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
                rows.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": indicator, "value": value, "updated_at": now,
                })
            logger.info("[%s] %s -> FCD=%.1f TD=%.1f", country_code, period, fcd, td)
        except Exception:
            logger.warning("[%s] failed to process %s", country_code, page_url, exc_info=True)

    return pd.DataFrame(rows) if rows else _empty()


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    annual = _render_annual(country_code)
    quarterly = _render_quarterly(country_code)

    frames = [df for df in (annual, quarterly) if not df.empty]
    if not frames:
        return _empty()

    out = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] %d rows total (annual=%d, quarterly=%d)",
        country_code, len(out), len(annual), len(quarterly),
    )
    return out
