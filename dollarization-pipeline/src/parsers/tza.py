"""Tanzania: Bank of Tanzania (BoT) 'Monthly Economic Review' (MER) PDF series.

The listing page https://www.bot.go.tz/Publications/Filter/1 (filter category 1 = Monthly
Economic Review; confirmed that /Publications/Filter/16 is for payment-systems/trade
statistics and unrelated to monetary statistics) exposes every issue (2002-present, roughly
280 of them) in a single unpaginated table. Each row looks like
`<a href=".../Monthly Economic Review/en/{token}.pdf">{Mon YY} - Monthly Economic
Review</a>`. The numeric token in the filename is just an upload timestamp unrelated to the
actual reporting period, so it is not used; the "Mon YY" label in the link text is also
only a rough reference — the actual period is read directly from the column headers
("Mon-YY") inside the table.

Each issue carries a "Money Supply and Its Main Components"-style table (the title varies
slightly across issues: "Table 2.1: Money Supply and Components" / "...and its Main
Components" / "Sources and Uses of Money Supply" / numbering also varies, e.g. "Table
2.2.1"/"Table 2.3.1") with a rolling 3-month window (same month last year, prior month,
current month -- e.g. 'Nov-24 Oct-25 Nov-25') of Outstanding stock (unit: Billion TZS). The
table contains these rows:

    Extended broad money (M3)        -> M3
    Foreign currency deposits        -> FCD (resident foreign currency deposits)
    Other deposits
    Currency in circulation
    Transferable deposits

TD (total deposits, monetary-survey definition) = Transferable deposits + Other deposits +
                                                   FCD (= M3 - Currency in circulation,
                                                   verified)
FCD_TD_RATIO = FCD / TD * 100

Directly verified against the Dec-25 column (the latest at the time) of the "Jan 26" issue
published 2026-02-18 (file 2026021821282158.pdf):
FCD=13,381.1, Other=17,944.2, Currency=8,492.3, M3=61,524.3
-> TD = 61,524.3 - 8,492.3 = 53,032.0 (Transferable 21,706.7 + Other 17,944.2 + FCD 13,381.1
   = 53,032.0, matches) -> FCD_TD_RATIO = 25.23%. This matches the figure from prior
   research.

These tables have no vector grid lines, so pdfplumber.extract_tables() cannot read them;
extract_text() is used instead with line-by-line parsing. Older issues (roughly
2014-2017) have a font-tracking quirk where a spurious space is inserted after certain
characters (following a capital letter) — e.g. "M 3", "O ther deposits", "Extended broad
m oney supply". Using x_tolerance=4 with extract_text() instead of the default (3) removes
these spurious spaces and yields the same format as recent issues (confirmed empirically).
A handful of extremely old issues still fail to parse even so (some from around 2013, where
the table itself appears to be missing or embedded as an image); these are silently
skipped -- the standard OCR fallback does not apply to this case (the text itself is
present and not corrupted; rather, the table is simply absent, or its vector layout has the
columns completely scrambled, so OCR would not fix it either).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # Must crawl the full set of issues (~280), so not a single-file download.

BASE_URL = "https://www.bot.go.tz"
LIST_URL = f"{BASE_URL}/Publications/Filter/1"  # Category 1 = Monthly Economic Review

# Each issue row on the listing page: <td>Sn.</td><td>upload date</td><td>category</td>
# <td class="text-left"><a href="{pdf path}">{Mon YY} - Monthly Economic Review</a></td>
_ROW_RE = re.compile(
    r'<tr>\s*<td>\d+\.</td>\s*<td>\s*([^<]+?)\s*</td>\s*<td>\s*([^<]+?)\s*</td>\s*'
    r'<td class="text-left">\s*<a href="([^"]+\.pdf)"[^>]*>\s*([^<]+?)\s*</a>',
    re.S,
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_HEADER_TOKEN_RE = re.compile(r"\b([A-Za-z]{3})-(\d{2})\b")
# All values in the table have exactly one decimal digit (e.g. '13,543.4'). In some issues
# (e.g. the June 2026 one) there is no space at all between two adjacent columns
# ("14,553.513,308.6"); greedily matching with '\d+' would merge the two numbers into one.
# Pinning the fractional part to exactly one digit ('\d') and letting the separator between
# numbers be '\s*' (allowing zero spaces) naturally breaks at the decimal point into the
# next number, even when there's no whitespace. The leading character must be a digit
# ('\d[\d,]*'): some issues around 2010 have the opposite problem, a spurious space before
# a thousands comma (e.g. "2 ,060.0"). If a leading comma were also allowed (e.g. the old
# '[\d,]+'), such a line would mis-match ",060.0" as the bogus number "60.0", throwing the
# value way off (an actual case found: in the April 2010 issue, FCD was mis-parsed as 60.0
# instead of 2,060.0). Rows where a number is split by a leading space simply fail to match
# under this constraint and are silently skipped — leaving that month missing is safer than
# producing a wrong value.
_NUM = r"-?\d[\d,]*\.\d"
_ROW_VALUES_RE = re.compile(
    rf"^(?P<label>[A-Za-z][A-Za-z0-9 /().%-]*?)\s+(?P<v1>{_NUM})\s*(?P<v2>{_NUM})\s*(?P<v3>{_NUM})"
    rf"(?:\s*{_NUM}){{0,6}}\s*$"
)

_TARGETS = {
    "M3": "extended broad money",
    "FCD": "foreign currency deposits",
    "OTHER": "other deposits",
    "CURRENCY": "currency in circulation",
    "TRANSFERABLE": "transferable deposits",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("TZA is handled via render() (crawls the full list of issues)")


def _collect_pdf_links() -> list[tuple[str, str]]:
    """Return a list of (label, absolute PDF URL). The listing page itself has no
    pagination (everything is shown at once)."""
    html = download(LIST_URL).decode("utf-8", errors="ignore")
    links = []
    for _upload_date, _category, href, label in _ROW_RE.findall(html):
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        url = url.replace(" ", "%20")
        label = " ".join(label.split())
        links.append((label, url))
    return links


def _period_from_header_token(month_abbr: str, year_2digit: str) -> tuple[int, int] | None:
    month = _MONTHS.get(month_abbr.lower())
    if month is None:
        return None
    year = 2000 + int(year_2digit)
    return year, month


def _extract_table_periods_and_row(text: str) -> tuple[list[tuple[int, int]], dict[str, dict[tuple[int, int], float]]] | None:
    """Extract column periods (up to 3) and a per-target-row {period: value} mapping
    from the page text."""
    lines = text.splitlines()

    periods: list[tuple[int, int]] | None = None
    for line in lines:
        tokens = _HEADER_TOKEN_RE.findall(line)
        if len(tokens) >= 3:
            candidate = [_period_from_header_token(m, y) for m, y in tokens[:3]]
            if all(candidate):
                periods = candidate  # type: ignore[assignment]
                break
    if periods is None:
        return None

    values: dict[str, dict[tuple[int, int], float]] = {key: {} for key in _TARGETS}
    for line in lines:
        m = _ROW_VALUES_RE.match(line.strip())
        if not m:
            continue
        label_lc = " ".join(m.group("label").lower().split())
        if "million" in label_lc or "usd" in label_lc:
            continue  # exclude the auxiliary "...(Millions of USD)" row

        matched_key = None
        if label_lc.startswith(_TARGETS["OTHER"]):
            matched_key = "OTHER"
        elif "outside" not in label_lc and label_lc.startswith(_TARGETS["CURRENCY"]):
            matched_key = "CURRENCY"
        elif label_lc.startswith(_TARGETS["TRANSFERABLE"]):
            matched_key = "TRANSFERABLE"
        elif _TARGETS["FCD"] in label_lc:
            matched_key = "FCD"
        elif label_lc.startswith(_TARGETS["M3"]):
            matched_key = "M3"
        if matched_key is None:
            continue

        try:
            v1, v2, v3 = (float(m.group(g).replace(",", "")) for g in ("v1", "v2", "v3"))
        except ValueError:
            continue
        for period, value in zip(periods, (v1, v2, v3)):
            values[matched_key].setdefault(period, value)

    return periods, values


def _parse_pdf(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages[:12]:  # monetary statistics table is always near the front (pages 2-7)
            text = page.extract_text(x_tolerance=4) or ""
            if "foreign currency deposits" not in text.lower():
                continue
            result = _extract_table_periods_and_row(text)
            if result is None:
                continue
            periods, values = result
            if not values["FCD"]:
                continue

            for period in periods:
                fcd = values["FCD"].get(period)
                if fcd is None:
                    continue

                td = None
                transferable = values["TRANSFERABLE"].get(period)
                other = values["OTHER"].get(period)
                if transferable is not None and other is not None:
                    td = round(transferable + other + fcd, 2)
                else:
                    m3 = values["M3"].get(period)
                    currency = values["CURRENCY"].get(period)
                    if m3 is not None and currency is not None:
                        td = round(m3 - currency, 2)

                year, month = period
                period_str = f"{year}-{month:02d}"
                indicator_values = [("FCD", round(fcd, 2))]
                if td:
                    indicator_values.append(("TD", td))
                    indicator_values.append(("FCD_TD_RATIO", round(fcd / td * 100, 2)))

                for indicator, value in indicator_values:
                    rows.append({
                        "country_code": country_code,
                        "year": year,
                        "period": period_str,
                        "indicator": indicator,
                        "value": value,
                        "updated_at": now,
                    })
            break  # once the table has been found and parsed, no need to look at the rest of this PDF's pages

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    links = _collect_pdf_links()
    logger.info("[%s] found %d Monthly Economic Review issues", country_code, len(links))

    frames = []
    for label, url in links:
        try:
            content = download(url, referer=LIST_URL)
        except Exception:
            logger.warning("[%s] download failed, skipping: %s (%s)", country_code, label, url)
            continue

        try:
            df = _parse_pdf(content, country_code)
        except Exception:
            logger.warning("[%s] parse failed, skipping: %s (%s)", country_code, label, url)
            continue

        if not df.empty:
            frames.append(df)
        else:
            logger.info("[%s] monetary statistics table not found, skipping: %s", country_code, label)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    merged = pd.concat(frames, ignore_index=True)
    # Each issue re-reports the last 3 months via a rolling window, so dedupe on
    # (period, indicator). links are in most-recent-first order (as shown on the listing
    # page), so keep="first" prefers the value from the most recent issue (more likely to
    # be a finalized figure).
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="first")
    merged = merged.sort_values(["period", "indicator"]).reset_index(drop=True)
    return merged
