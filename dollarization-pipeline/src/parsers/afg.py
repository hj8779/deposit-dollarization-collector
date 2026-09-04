"""Afghanistan: Da Afghanistan Bank(DAB) Annual/Quarterly Economic Bulletin PDFs, the
'In Foreign currency' row (the foreign-currency component of Other Deposits/Quasi Money) in
'Table 2.1'-style tables ('Monetary Aggregates' / "...Analytical Balance Sheet and Monetary
Aggregate...").

Collection procedure:
1. Visit the landing page (list of Annual/Quarterly Bulletins) and collect every a[href$=".pdf"]
   on the page (the DAB site links PDFs directly on the listing page, with no separate post
   detail page).
2. Download each PDF and extract the 'In Foreign currency' row via pdfplumber with regex.
   The table always consists of 7 numeric tokens: [period1 amount, period2 amount, YoY%,
   YoY change, period3 (latest) amount, YoY%, YoY change], and the 3rd-from-last token
   (period3 amount) is the latest value as of that bulletin's publication.

TD (total deposits) = 'Demand Deposits' row + 'Other Deposits (Quasi Money)' row (same table,
same 7-token structure). 'In Foreign currency' is a sub-component of 'Other Deposits (Quasi
Money)' (In Afghani + In Foreign currency = Other Deposits), so Demand Deposits + Other
Deposits together equal the total deposits included in broad money (M2). Verified empirically:
2020-12 Demand 252,219 + Other 40,373.93 = 292,592.93; Other 40,373.93 = In Afghani 9,191.67 +
In Foreign currency 31,182.26, which matches.
3. Period labels are extracted from the far more reliable **link text (filename)** rather than
   the PDF's internal text (documents mix Afghan solar and Gregorian calendars, and the table
   header itself comes out character-scrambled from pdfplumber). If the year in the filename is
   below 1500, it's treated as Afghan solar hijri (SH) and normalized to the Gregorian calendar
   by adding 621 (e.g. FY1399 -> 2020).
"""

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import unquote, urljoin

import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

from src.collectors.base import INDICATOR, INDICATOR_TD, download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

LANDING_URLS = [
    "https://dab.gov.af/Annual-Economic-and-Statistical-Bulletins",
    "https://dab.gov.af/quarterly-economic-and-statistical-bulletins",
]

_NUM_TOKENS = r"([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+(-?[\d.]+%)\s+(-?[\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+(-?[\d.]+%)\s+(-?[\d,]+\.?\d*)"
_ROW_RE = re.compile(r"In Foreign currency\s+" + _NUM_TOKENS)
_DEMAND_ROW_RE = re.compile(r"Demand Deposits\s+" + _NUM_TOKENS)
_OTHER_DEPOSITS_ROW_RE = re.compile(r"Other Deposits \(Quasi Money\)\s+" + _NUM_TOKENS)

_QUARTER_PATTERNS = [
    re.compile(r"(\d)(?:st|nd|rd|th)\s*Quarter\s*of\s*FY\s*(\d{4})", re.I),
    re.compile(r"Q(\d)\s*[-–,_]\s*(\d{4})", re.I),
]
_ANNUAL_PATTERN = re.compile(r"Annual.*?(\d{4})", re.I)


def _normalize_year(year: int) -> int:
    """Convert the year in the filename to the Gregorian calendar if it's Afghan solar hijri (SH)."""
    return year + 621 if year < 1500 else year


def _period_from_label(label: str) -> str | None:
    for pattern in _QUARTER_PATTERNS:
        m = pattern.search(label)
        if m:
            quarter, year = int(m.group(1)), _normalize_year(int(m.group(2)))
            return f"{year}-Q{quarter}"
    m = _ANNUAL_PATTERN.search(label)
    if m:
        return f"{_normalize_year(int(m.group(1)))}-Annual"
    return None


def _collect_pdf_links() -> list[tuple[str, str]]:
    """List of (period, absolute_pdf_url). Skipped if a period label can't be derived."""
    links: dict[str, str] = {}
    for landing_url in LANDING_URLS:
        try:
            html = download(landing_url).decode("utf-8", errors="ignore")
        except Exception:
            logger.warning("[AFG] Failed to access landing page: %s", landing_url)
            continue

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.lower().endswith(".pdf"):
                continue
            filename = unquote(href.split("/")[-1])
            period = _period_from_label(filename)
            if period is None:
                continue
            # If multiple files exist for the same period (e.g. reposts), overwrite with the
            # later one found, preferring whatever appears lower on the landing page
            # (usually the more recent repost).
            links[period] = urljoin(landing_url, href)

    return list(links.items())


def _extract_fcd_td(content: bytes) -> tuple[str | None, str | None]:
    """Return the latest (rightmost) amounts from the 'In Foreign currency' (FCD) and
    'Demand Deposits'+'Other Deposits (Quasi Money)' (TD) rows in the PDF, as strings."""
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            fcd_m = _ROW_RE.search(text)
            if not fcd_m:
                continue
            fcd = fcd_m.group(5)  # [amt1, amt2, pct, diff, amt3 (latest), pct, diff]

            demand_m = _DEMAND_ROW_RE.search(text)
            other_m = _OTHER_DEPOSITS_ROW_RE.search(text)
            td = None
            if demand_m and other_m:
                try:
                    td = str(
                        float(demand_m.group(5).replace(",", ""))
                        + float(other_m.group(5).replace(",", ""))
                    )
                except ValueError:
                    td = None
            return fcd, td
    return None, None


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    pdf_links = _collect_pdf_links()
    logger.info("[%s] Found %d labelable PDFs", country_code, len(pdf_links))

    rows = []
    for period, pdf_url in pdf_links:
        try:
            content = download(pdf_url)
        except Exception:
            logger.warning("[%s] Failed to download %s (%s), skipping", country_code, period, pdf_url)
            continue

        try:
            amount, td_amount = _extract_fcd_td(content)
        except Exception:
            logger.warning("[%s] Failed to parse %s PDF, skipping", country_code, period)
            continue

        if amount is None:
            logger.info("[%s] No 'In Foreign currency' row in %s PDF, skipping", country_code, period)
            continue

        year = int(period.split("-")[0])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR,
            "value": float(amount.replace(",", "")),
            "updated_at": now,
        })
        if td_amount is not None:
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": INDICATOR_TD,
                "value": round(float(td_amount), 2),
                "updated_at": now,
            })

    if not rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last").sort_values(["period", "indicator"]).reset_index(drop=True)
    return df
