"""Algeria: Banque d'Algérie (Bank of Algeria) Bulletin Statistique Trimestriel.

Collects the annual quarterly-statistics Bulletin PDFs from
bank-of-algeria.dz/bulletins-statistiques/. Extracts the "DEPÔTS EN DEVISES" (foreign-currency
deposits) column from each PDF's "G 3.4 Structure des dépôts" table.

TD (total deposits) = col0 (DEPÔTS A VUE total) + col4 (DEPÔTS A TERME total). The table itself
splits the entire 'Structure des dépôts' (deposit structure) along two axes, demand (A VUE) and
term (A TERME), so the sum of these two is the total deposits (DEVISES/DINARS is only a
currency sub-breakdown of A TERME - A VUE has no currency split; empirically confirmed: col4 =
col5(DINARS)+col6(DEVISES), col0 = col1+col2+col3 (breakdown by depository institution)).

File structure:
- URL pattern: https://www.bank-of-algeria.dz/bulletins-statistiques-{YYYY}/
- PDF pattern: stoodroa/YYYY/MM/Bulletin_NN_Month_YYYY.pdf
- Table G 3.4: monthly deposit structure (DINARS vs DEVISES column split)
- Units: billion dinars (milliards de DZD)

Uses verify=False due to a TLS certificate chain issue on the site.
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FILE_URL = "__RENDER__"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# List of yearly bulletin pages (confirmed for 2007-2021)
_YEAR_RANGE = range(2007, 2026)

_MONTHS_FR = {
    "janv": 1, "jan": 1, "févr": 2, "fév": 2, "feb": 2, "mars": 3, "mar": 3,
    "avr": 4, "apr": 4, "mai": 5, "may": 5, "juin": 6, "jun": 6,
    "juil": 7, "jul": 7, "août": 8, "aou": 8, "aug": 8,
    "sept": 9, "sep": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12,
}

# G 3.4 table header pattern
_TABLE_TITLE_RE = re.compile(r"G\s*3\.4|Structure\s+des\s+d[ée]p[ôo]ts", re.I)
_DEVISES_RE = re.compile(r"D[ÉE]P[ÔO]TS\s+EN\s+DEVISES", re.I)
# The last two column headers of the table ('DEPOTS EN DINARS'/'DEPOTS EN DEVISES') are narrow
# enough that pdfplumber sometimes extracts them character-scrambled (e.g.
# 'DEP D Ô E T V S IS E E N S'), so pages are not filtered by whether the intact 'DEVISES'
# string is present - the table title alone is specific enough.
_VARIATION_SECTION_RE = re.compile(r"variation\s+en\s*%", re.I)
# Loosely matches French number notation (thousands-separator space): handles '167,4' (no
# space), '2 949,1' (one space), and '1531,5' (space dropped entirely, reconstructed backward
# as '1'+'531'+',5').
_NUMBER_RE = re.compile(r"\d{1,3}(?:\s?\d{3})*,\d+")
# In some documents (e.g. Bulletin_48_Dec_2019) a spurious space is rendered in the middle of a
# 3-digit number (e.g. '8 60,2' is actually 860,2). Since a proper French thousands separator
# always has exactly 3 digits in the group before the comma, only spaces with 1-2 digits before
# the comma are removed to restore the original number (e.g. '8 60,2'->'860,2' is stripped,
# while '3 537,5' is preserved since it has 3 digits before the comma, a normal thousands
# separator).
_SPURIOUS_SPACE_RE = re.compile(r"(?<=\d)\s(?=\d{1,2},)")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("DZA is handled via render() (needs to iterate over multiple PDFs)")


def _collect_pdf_links() -> list[str]:
    """Collects PDF links by iterating over the yearly pages."""
    links: set[str] = set()

    for year in _YEAR_RANGE:
        url = f"https://www.bank-of-algeria.dz/bulletins-statistiques-{year}/"
        try:
            r = requests.get(url, headers=_HEADERS, timeout=30, verify=False)
            if r.status_code != 200:
                continue
            pdfs = re.findall(r'href=["\']([^"\']+\.pdf)', r.text, re.I)
            for pdf in pdfs:
                if "bulletin" in pdf.lower():
                    links.add(pdf)
        except Exception as e:
            logger.warning("[DZA] Failed to collect year page %d: %s", year, e)

    return sorted(links)


def _parse_period(text: str) -> tuple[int, int] | None:
    """Extracts year/month from formats like '2021janv.' or '2014 déc.'."""
    # year + month pattern
    m = re.match(r"(\d{4})\s*([a-zéûô]+)", text.strip(), re.I)
    if m:
        year = int(m.group(1))
        month_key = m.group(2).lower()[:4].rstrip(".")
        month = _MONTHS_FR.get(month_key)
        if month:
            return year, month
    return None


def _extract_devises_from_page(text: str) -> list[tuple[str, float, float | None]]:
    """Extracts per-period (period, FCD, TD) values from the page text.

    In the table, the year appears only in the first month of that year (e.g.
    '2008 sept. ...'), and the remaining months of the same year appear with only the month,
    no year (e.g. 'oct. ...', 'nov. ...') - so the year is forward-filled.
    The table always has 7 columns in this order (DEPOTS A VUE total / DANS LES BANQUES /
    AU TRESOR / AU CCP / DEPOTS A TERME total / EN DINARS / EN DEVISES), so the last number is
    the DEVISES column (FCD), and col0+col4 is TD (total deposits).
    After the data block, a 'Variation en %' (month-over-month/year-over-year change) section
    follows in the same year/month format, but these aren't absolute values, so reading stops
    once that section's heading appears.
    """
    results = []
    current_year: int | None = None
    prev_month: int | None = None

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if _VARIATION_SECTION_RE.search(line):
            break

        # Year (4 digits) + month name, or just a month name with no year (carrying over from
        # the previous year). A '*' (provisional-value marker, e.g. 'Juin*') sometimes follows
        # the month name, so both '.' and '*' are allowed.
        m = re.match(r"(?:(\d{4})\s*)?([a-zéûô]+)[.*]?\s+(.*)", line, re.I)
        if not m:
            continue

        year_str, month_str, rest = m.groups()
        month = _MONTHS_FR.get(month_str.lower()[:4].rstrip(".")) or _MONTHS_FR.get(month_str.lower()[:3])
        if month is None:
            continue
        if year_str:
            current_year = int(year_str)
        elif current_year is not None and prev_month is not None and month <= prev_month:
            # If there's no year notation and the month becomes equal to or earlier than the
            # previous month (e.g. déc.->sept.), the year has rolled over.
            # Sometimes some months (e.g. Jan-Aug 2010) are omitted entirely from the table and
            # only the following December's value reappears with its year - at that point
            # year_str gets filled in again and self-corrects.
            current_year += 1
        if current_year is None:
            continue
        prev_month = month

        rest = _SPURIOUS_SPACE_RE.sub("", rest)
        numbers = _NUMBER_RE.findall(rest)
        if len(numbers) < 2:  # need at least 2 columns (avoid false positives)
            continue

        values = [float(n.replace(" ", "").replace(",", ".")) for n in numbers]
        fcd = values[-1]
        td = values[0] + values[4] if len(values) >= 5 else None
        results.append((f"{current_year}-{month:02d}", fcd, td))

    return results


def _parse_bulletin(content: bytes, country_code: str) -> pd.DataFrame:
    """Extracts foreign-currency deposit data from a single PDF."""
    now = datetime.now(timezone.utc).isoformat()

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            # Find the page with the G 3.4 table. The table-of-contents (TOC) page also
            # matches _TABLE_TITLE_RE since it contains the table title text, but it has no
            # actual data rows, so _extract_devises_from_page returns an empty result and the
            # loop naturally moves to the next page at the 'if data:' check below.
            for page in pdf.pages:
                text = page.extract_text() or ""
                if _TABLE_TITLE_RE.search(text):
                    data = _extract_devises_from_page(text)
                    if data:
                        rows = []
                        for period, fcd, td in data:
                            year = int(period[:4])
                            rows.append({
                                "country_code": country_code,
                                "year": year,
                                "period": period,
                                "indicator": INDICATOR,
                                "value": round(fcd, 2),
                                "updated_at": now,
                            })
                            if td is not None:
                                rows.append({
                                    "country_code": country_code,
                                    "year": year,
                                    "period": period,
                                    "indicator": INDICATOR_TD,
                                    "value": round(td, 2),
                                    "updated_at": now,
                                })
                        if rows:
                            return pd.DataFrame(rows)
    except Exception as e:
        logger.warning("[%s] PDF parsing failed: %s", country_code, e)

    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    links = _collect_pdf_links()
    logger.info("[%s] Found %d Bulletin PDFs", country_code, len(links))

    if not links:
        logger.warning("[%s] Could not find any PDF links", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    all_data: dict[tuple[str, str], float] = {}  # (period, indicator) -> value (latest value wins)

    for url in links:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=60, verify=False)
            r.raise_for_status()
        except Exception as e:
            logger.warning("[%s] PDF download failed, skipping: %s (%s)", country_code, url, e)
            continue

        df = _parse_bulletin(r.content, country_code)
        if df.empty:
            continue

        for _, row in df.iterrows():
            key = (row["period"], row["indicator"])
            # Do not overwrite a period that's already present (sorted later, so the latest
            # PDF takes priority)
            if key not in all_data:
                all_data[key] = row["value"]

    if not all_data:
        logger.warning("[%s] Could not find any foreign-currency deposit data", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for (period, indicator), value in sorted(all_data.items()):
        year = int(period[:4])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": indicator,
            "value": value,
            "updated_at": now,
        })

    result = pd.DataFrame(rows)
    logger.info("[%s] Extracted %d rows of foreign-currency deposit data (%s to %s)",
                country_code, len(result), result["period"].min(), result["period"].max())
    return result
