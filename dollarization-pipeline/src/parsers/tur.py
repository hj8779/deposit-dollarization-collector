"""Turkey: Central Bank of the Republic of Turkey (TCMB/CBRT) "Weekly Money and Banking
Statistics" bulletin (Money_Bank.pdf).

TCMB's EVDS (evds2.tcmb.gov.tr) REST API is free but requires an API key that must be obtained
after registering (there is no self-service issuance path without human verification), so it
can't be used in this environment. Instead we use the 'Weekly Money and Banking Statistics' PDF
(Money_Bank.pdf) that TCMB publishes every week. This PDF shows "Residents" deposits split into
TRY/FX in Table 2 (new format) / Table 7 (old format), so FCD (resident foreign-currency
deposits) and TD (resident total deposits) can be obtained directly.

    FCD = the FX (foreign-currency) portion of resident deposits
    TD  = total resident deposits (TRY + FX)

Empirically confirmed (2026-07-24, new format Table 2): FX (residents)=10,499,925,050 thousand
TRY, resident total deposits=28,416,399,833 thousand TRY -> ratio=36.95%. This matches exactly
the figures from the earlier investigation (FX 10.500 trillion, total deposits 28.416 trillion,
ratio~36.95%).

The format falls into two types depending on the period (since the same asset URL is
overwritten weekly, older versions can only be obtained via web.archive.org's CDX snapshots):

1. New format (roughly 2025-02 to present, 9 pages): "Table 2. Banking Sector Selected Balance
   Sheet Items" shows "A. DEPOSITS -> 1. Residents -> a. TRY / b. FX" across 5 weekly columns.
   Values are extracted from the region of the page between "1. Residents" and "2. Resident
   Banks" (the same "a. TRY"/"b. FX" labels also repeat elsewhere, e.g. under "2. Resident
   Banks", "3. Non-Residents", so this scoping is required).

2. Old format (up to ~2024-09, 11 pages): "Table 7. Deposits With Banks" splits TRY/FX into two
   fully separate sections (I.TRY DEPOSITS, II.FX DEPOSITS), each with an "A.Residents" row
   repeated under "I.I.DEPOSIT MONEY BANKS"/"I.II.PARTICIPATION BANKS" (appearing 4 times total:
   TRY-deposit banks, TRY-participation banks, FX-deposit banks, FX-participation banks). There
   are 4 reference-point columns (current week/prior week/prior year-end/same week prior year).
   TD = sum of the first two A.Residents occurrences, FCD = sum of the latter two.

The number format (thousands separator) is also mixed across snapshots, sometimes
English-style (1,234,567) and sometimes Turkish-style (1.234.567) (apparently the locale
changes each time the same document asset is republished in the CMS). Since this table's amount
columns are always integers (thousand TRY units) with no decimal point, stripping all '.' and
',' from the token and parsing as an integer is safe regardless of locale (the percentage growth
rate columns are not an issue since the column count is counted precisely and anything past
that is never read).

Obtaining historical data: since this PDF is overwritten weekly at the same URL
(wps/wcm/connect/122c325c-.../Money_Bank.pdf), the site itself has no archive. Instead, the
Wayback Machine has repeatedly snapshotted this fixed URL since 2018 (queried via the CDX API),
and since each PDF holds 4-5 weekly columns (4 reference points for the old format, the most
recent 5 weeks for the new format), collecting all the snapshots lets us reconstruct the
2018-present period fairly densely (though not completely). Periods with large gaps between
snapshots (e.g. 2019-07 to 2020-08, 2023-04 to 2024-02) are naturally left empty.
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_HEADERS = {"User-Agent": "Mozilla/5.0"}

# The "current" issue, overwritten weekly at the same asset ID (live latest data).
_CURRENT_URL = (
    "https://www.tcmb.gov.tr/wps/wcm/connect/"
    "122c325c-6afd-4718-8573-49f75964ff34/Money_Bank.pdf?MOD=AJPERES"
)

# Full list of Wayback Machine snapshots for the fixed URL above (deduplicated by content digest).
_CDX_URL = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=tcmb.gov.tr/wps/wcm/connect/122c325c-6afd-4718-8573-49f75964ff34/Money_Bank.pdf"
    "&matchType=prefix&collapse=digest&filter=statuscode:200&output=json&limit=1000"
)

_DATE_RE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}")
_NUM = r"-?[\d.,]+"


def _num(token: str) -> int:
    """Safely parses '1,234,567' / '1.234.567' / '1234567' as an integer (this column only ever
    uses thousands separators with no decimal point, so it's fine to just strip all '.' and ',')."""
    return int(token.replace(",", "").replace(".", ""))


def _row_values(text: str, label: str, ncols: int) -> list[int] | None:
    pattern = re.compile(
        rf"^{re.escape(label)}\s+((?:{_NUM}\s+){{{ncols - 1}}}{_NUM})", re.MULTILINE
    )
    m = pattern.search(text)
    if not m:
        return None
    tokens = m.group(1).split()
    if len(tokens) != ncols:
        return None
    return [_num(t) for t in tokens]


def _header_dates(text: str, ncols: int) -> list[str] | None:
    lines = text.splitlines()
    for line in lines[:3]:
        dates = _DATE_RE.findall(line)
        if len(dates) >= ncols:
            out = []
            for d in dates[:ncols]:
                day, month, year = d.split(".")
                out.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
            return out
    return None


def _parse_new_format(pdf: pdfplumber.PDF) -> dict[str, tuple[int, int]]:
    """New format (Table 2, 'A. DEPOSITS' -> '1. Residents' -> a.TRY/b.FX). Returns: {period: (fcd, td)}."""
    for page in pdf.pages:
        text = page.extract_text() or ""
        lines = text.splitlines()
        if not lines or "Table 2." not in lines[0]:
            continue
        if "1. Residents" not in text or "A. DEPOSITS" not in text:
            continue

        # Scoped to everything before "2. Resident Banks" to avoid duplicate 'a. TRY'/'b. FX'
        # labels (the same labels also appear in the Resident Banks and Non-Residents sections).
        scoped = text.split("\n2. Resident Banks")[0]

        ncols = len(_DATE_RE.findall(text.splitlines()[1])) if len(text.splitlines()) > 1 else 0
        if ncols == 0:
            continue

        td_vals = _row_values(scoped, "1. Residents", ncols)
        fcd_vals = _row_values(scoped, "b. FX", ncols)
        dates = _header_dates(text, ncols)
        if not (td_vals and fcd_vals and dates):
            continue

        return {date: (fcd, td) for date, fcd, td in zip(dates, fcd_vals, td_vals)}

    return {}


def _parse_old_format(pdf: pdfplumber.PDF) -> dict[str, tuple[int, int]]:
    """Old format (Table 7. Deposits With Banks). 'A.Residents' appears 4 times in order:
    TRY-deposit banks, TRY-participation banks, FX-deposit banks, FX-participation banks."""
    for page in pdf.pages:
        text = page.extract_text() or ""
        first_line = text.splitlines()[0] if text.splitlines() else ""
        if "Table 7." not in first_line or "Deposits With Banks" not in first_line:
            continue

        scoped = text.split("III.TOTAL DEPOSITS")[0]
        ncols = len(_DATE_RE.findall(text.splitlines()[1])) if len(text.splitlines()) > 1 else 0
        if ncols == 0:
            continue

        matches = list(
            re.finditer(
                rf"^A\.Residents\s+((?:{_NUM}\s+){{{ncols - 1}}}{_NUM})", scoped, re.MULTILINE
            )
        )
        if len(matches) < 4:
            continue

        def vals(m):
            tokens = m.group(1).split()
            return [_num(t) for t in tokens] if len(tokens) == ncols else None

        try_deposit_banks = vals(matches[0])
        try_participation = vals(matches[1])
        fx_deposit_banks = vals(matches[2])
        fx_participation = vals(matches[3])
        dates = _header_dates(text, ncols)
        if not (try_deposit_banks and try_participation and fx_deposit_banks and fx_participation and dates):
            continue

        result = {}
        for i, date in enumerate(dates):
            fcd = fx_deposit_banks[i] + fx_participation[i]
            td_try = try_deposit_banks[i] + try_participation[i]
            result[date] = (fcd, td_try + fcd)
        return result

    return {}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    columns = ["country_code", "year", "period", "indicator", "value", "updated_at"]

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            by_period = _parse_new_format(pdf)
            if not by_period:
                by_period = _parse_old_format(pdf)
    except Exception as exc:
        logger.info("[%s] PDF parsing failed (assumed corrupted archived copy), skipping: %s", country_code, exc)
        return pd.DataFrame(columns=columns)

    if not by_period:
        return pd.DataFrame(columns=columns)

    rows = []
    for period, (fcd, td) in by_period.items():
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 2) if td else None
        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
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
    return pd.DataFrame(rows)


def _wayback_urls() -> list[str]:
    try:
        response = requests.get(_CDX_URL, headers=_HEADERS, timeout=30)
        response.raise_for_status()
        rows = response.json()
    except Exception as exc:
        logger.warning("TUR: Wayback CDX lookup failed, using only the current issue: %s", exc)
        return []

    if not rows or len(rows) < 2:
        return []

    urls = []
    for ts, original in ((r[1], r[2]) for r in rows[1:]):
        urls.append(f"https://web.archive.org/web/{ts}if_/{original}")
    return urls


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    frames = []

    urls = [_CURRENT_URL] + _wayback_urls()
    logger.info("[%s] iterating over %d Weekly Money and Banking Statistics PDFs (current+archived)", country_code, len(urls))

    for url in urls:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=60)
            response.raise_for_status()
            content = response.content
        except Exception as exc:
            logger.info("[%s] download failed, skipping: %s (%s)", country_code, url, exc)
            continue

        df = parse(content, country_code)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="first")
    merged = merged.sort_values(["period", "indicator"]).reset_index(drop=True)
    return merged
