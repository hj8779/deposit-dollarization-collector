"""Sierra Leone: Bank of Sierra Leone(BSL) Monetary Policy Report (quarterly) PDF, 'Monetary Survey' appendix table.

bsl.gov.sl must be accessed via https://bsl.gov.sl without the www. prefix
(the originally stored www.bsl.gov.sl gives a DNS error); the bare-domain
version returns 200 OK. Requests using the default requests User-Agent get
the connection reset (presumably a firewall/CDN setup that requires a
browser-like UA), but the browser UA header used by
src.collectors.base.download() gets a normal response.

BSL points users to the 'Statistics Data Warehouse' (app.datawarehousepro.com)
and the Open Data for Africa portal
(cb-sierraleone.opendataforafrica.org) as its statistics hub, but the latter
is blocked by a Cloudflare bot challenge ("Just a moment...") that neither
plain requests nor a Playwright headless browser could get past (checked
2026-08) — this path cannot be automated.

Instead, the appendix of BSL's own directly-hosted quarterly Monetary Policy
Report (MPR) PDF has an explicit resident foreign-currency deposits line item
in 'Table 4: Monetary Survey' (formerly named 'Table 3/4: Money Supply and
Components'):

    Demand deposit                          <- demand deposits
    Quasi money                             <- quasi-money deposits (subtotal)
      o.w. Foreign currency deposit         <- of which, foreign-currency deposits (FCD)
      Time and saving deposit               <- time/savings deposits (local currency)

    FCD = the "o.w. Foreign currency deposit" row
    TD  = the "Demand deposit" + "Quasi money" rows (= total deposit liabilities
          to banks, excluding government/interbank)

Units are labeled per-table as either 'Billions of Leones' (before the August
2022 redenomination, old SLL) or 'Millions of Leones' (after redenomination,
new SLE), but the two units are numerically equivalent (1 new SLE = 1,000 old
SLL, so a billion in old SLL equals a million in new SLE) — confirmed by
cross-checking that 2022Q1 Broad Money (M2)=15,163.12 appears identically in
reports both before and after redenomination. So we use the raw values as-is,
with no separate unit conversion.

Not every MPR includes this appendix table (roughly half only have a
narrative % change with no absolute-value table). render() finds every
'Monetary Policy Report' link on Publications.html, downloads each PDF, and
extracts data only from the PDFs that contain the table.

MPRs only go back to 2021 (16 quarters max as of the check date), so on a
2026-08-19 user report we extended the parser to also collect 'Annual Report
and Statement of Accounts' PDFs (2013-2024 are present on Publications.html as
plain static <a href> links — despite looking like a hover menu, they're
directly parseable with no JS needed). These annual reports also carry a
'Table N: Monetary Survey (Million/Billion Leones)' table in their appendix,
but the header uses month-year format ('Dec-12 Mar-13 Jun-13 ...') instead of
quarter numbers (2025Q1), and the row label is plain 'Foreign Currency
Deposits' rather than 'o.w. Foreign currency deposit'. The Dec/Mar/Jun/Sep
month-end snapshots correspond to Q4/Q1/Q2/Q3 respectively, so we convert them
to the same 'YYYY-QN' format and merge with the MPR data. Not every annual
report has this table as extractable text (e.g. the 2017 edition is a scanned
image with no extractable text — automatically skipped).
FCD = the 'Foreign Currency Deposits' row (no "o.w." prefix). TD = 'Demand
Deposits' + 'Quasi Money' (same definition as the MPR side).

The table header row (e.g. 'Millions of Leones 2025Q1 2025Q4 2026Q1 2025Q4
2026Q1 2025Q4 2026Q1') lists the quarter labels once for the actual level
columns, then reuses them (repeating the label) for the quarter-over-quarter
and year-over-year change columns further right. We determine the number of
level columns by finding where a label first starts repeating (e.g. 3 level
columns followed by 2 QoQ-change + 2 YoY-change columns = 7 tokens total).

Some recent reports (e.g. the December 2025 issue) have pdfplumber's text
extraction order reversed, so the line containing only the numeric level
values comes before the label line ('8,527.04 9,564.94 10,116.74' followed on
the next line by 'Reserve money (0.001) 5.77 19.87 18.64'). In that case, if
the label line itself has fewer numbers than the level-column count (i.e. only
the change-column numbers), we pull the level values from the line right
before it.
"""

import re
from datetime import datetime, timezone

import pandas as pd
import pdfplumber
from io import BytesIO

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

PUBLICATIONS_URL = "https://bsl.gov.sl/Publications.html"
BASE_URL = "https://bsl.gov.sl/"

_MPR_LINK_RE = re.compile(
    r'href="\.?/?([^"?#]*monetary\s*policy\s*report[^"?#]*\.pdf)"', re.I
)
_ANNUAL_LINK_RE = re.compile(
    r'href="\.?/?([^"?#]*annual\s*report[^"?#]*\.pdf)"', re.I
)

_PERIOD_TOKEN_RE = re.compile(r"\b(20\d{2})\s*Q\s*([1-4])\b", re.I)
_MONTH_YEAR_TOKEN_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{2})\b", re.I
)
_MONTH_TO_QUARTER = {
    "dec": 4, "mar": 1, "jun": 2, "sep": 3,
    # non-quarter-end months occasionally appear too; map to nearest quarter-end
    "jan": 4, "feb": 1, "apr": 1, "may": 2, "jul": 2, "aug": 3, "oct": 3, "nov": 4,
}
_NUM_RE = re.compile(r"\(?-?\d[\d,]*\.\d+\)?|\(?-?\d[\d,]*\)?")

_FCD_LABEL_RE = re.compile(r"^o\.?w\.?\s*foreign\s+currency\s+deposit", re.I)
_FCD_LABEL_PLAIN_RE = re.compile(r"^foreign\s+currency\s+deposit", re.I)
_DEMAND_LABEL_RE = re.compile(r"^demand\s+deposit", re.I)
_QUASI_LABEL_RE = re.compile(r"^quasi[\s-]*money", re.I)
_TABLE_MARKER_RE = re.compile(r"foreign currency deposit", re.I)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SLE is handled via render() (must iterate over multiple MPR PDFs)")


def _clean_number(tok: str) -> float:
    neg = tok.startswith("(") and tok.endswith(")")
    tok = tok.strip("()").replace(",", "")
    val = float(tok)
    return -val if neg else val


def _period_columns(header_line: str) -> list[str]:
    """Extracts quarter label tokens from the header line and returns only the
    'level column' span (up to just before the first repeat).

    Supports both the 'YYYYQN' format (MPR) and the 'Mon-YY' month-end
    snapshot format (Annual Report — mostly Dec/Mar/Jun/Sep quarter-ends);
    the latter is converted to the corresponding quarter and merged into the
    same 'YYYYQN' label namespace."""
    tokens = [f"{y}Q{q}" for y, q in _PERIOD_TOKEN_RE.findall(header_line)]
    if not tokens:
        for mon, yy in _MONTH_YEAR_TOKEN_RE.findall(header_line):
            q = _MONTH_TO_QUARTER.get(mon.lower())
            if q is None:
                continue
            year = 2000 + int(yy)
            tokens.append(f"{year}Q{q}")
    seen: list[str] = []
    for tok in tokens:
        if tok in seen:
            break
        seen.append(tok)
    return seen


_PURE_NUMERIC_LINE_RE = re.compile(r"^[\d,.\s()-]+$")


def _row_numbers(lines: list[str], idx: int, n: int) -> list[float] | None:
    """When lines[idx] is the line containing the target label, finds the n
    level values.

    Some reports have pdfplumber extract the level-value line and the label
    (+change-value) line in reversed order (a numbers-only line with just the
    level values comes before the label line). In that case, the numbers on
    the label line itself are change values (not levels), so we first check
    the line right before it if it consists purely of numbers.
    """
    if idx > 0:
        prev = lines[idx - 1].strip()
        if _PURE_NUMERIC_LINE_RE.match(prev):
            prev_nums = _NUM_RE.findall(prev)
            if len(prev_nums) == n:
                return [_clean_number(t) for t in prev_nums]

    this_nums = _NUM_RE.findall(lines[idx])
    if len(this_nums) >= n:
        return [_clean_number(t) for t in this_nums[:n]]

    return None


def _extract_table(text: str) -> dict[str, tuple[float, float]]:
    """Extracts a period -> (FCD, TD) mapping from the page text."""
    lines = text.splitlines()

    header_idx = None
    periods: list[str] = []
    for i, line in enumerate(lines):
        cols = _period_columns(line)
        if len(cols) >= 2:
            header_idx = i
            periods = cols
            break
    if header_idx is None:
        return {}

    n = len(periods)
    fcd_vals = demand_vals = quasi_vals = None

    for i in range(header_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if (_FCD_LABEL_RE.match(stripped) or _FCD_LABEL_PLAIN_RE.match(stripped)) and fcd_vals is None:
            fcd_vals = _row_numbers(lines, i, n)
        elif _DEMAND_LABEL_RE.match(stripped) and demand_vals is None:
            demand_vals = _row_numbers(lines, i, n)
        elif _QUASI_LABEL_RE.match(stripped) and quasi_vals is None:
            quasi_vals = _row_numbers(lines, i, n)
        if fcd_vals is not None and demand_vals is not None and quasi_vals is not None:
            break

    if fcd_vals is None or demand_vals is None or quasi_vals is None:
        return {}

    result = {}
    for period, fcd, demand, quasi in zip(periods, fcd_vals, demand_vals, quasi_vals):
        td = round(demand + quasi, 2)
        result[period] = (round(fcd, 2), td)
    return result


def _parse_mpr_pdf(content: bytes) -> dict[str, tuple[float, float]]:
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if _TABLE_MARKER_RE.search(text):
                    data = _extract_table(text)
                    if data:
                        return data
    except Exception as e:
        logger.warning("[SLE] failed to parse PDF: %s", e)
    return {}


def _collect_mpr_links() -> list[str]:
    try:
        html = download(PUBLICATIONS_URL).decode("utf-8", errors="ignore")
    except Exception as e:
        logger.warning("[SLE] failed to access Publications.html: %s", e)
        return []

    links = set()
    for path in _MPR_LINK_RE.findall(html):
        if "statement" in path.lower():
            continue
        links.add(BASE_URL + path)
    return sorted(links)


def _collect_annual_links() -> list[str]:
    """'Annual Report and Statement of Accounts' PDFs — Publications.html serves
    these as plain static <a href> links (no JS needed despite the hover-menu
    look), so a normal GET + regex is enough."""
    try:
        html = download(PUBLICATIONS_URL).decode("utf-8", errors="ignore")
    except Exception as e:
        logger.warning("[SLE] failed to access Publications.html: %s", e)
        return []

    from urllib.parse import quote

    links = set()
    for path in _ANNUAL_LINK_RE.findall(html):
        links.add(BASE_URL + quote(path))
    return sorted(links)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    links = _collect_mpr_links()
    logger.info("[%s] found %d Monetary Policy Report PDFs", country_code, len(links))

    annual_links = _collect_annual_links()
    logger.info("[%s] found %d Annual Report PDFs", country_code, len(annual_links))

    all_data: dict[str, tuple[float, float]] = {}
    # Annual reports first (older, spans further back) so MPR's more precise
    # recent-quarter figures win on any overlap.
    for url in annual_links:
        try:
            content = download(url, referer=PUBLICATIONS_URL)
        except Exception as e:
            logger.warning("[%s] Annual Report download failed, skipping: %s (%s)", country_code, url, e)
            continue
        data = _parse_mpr_pdf(content)
        if data:
            logger.info("[%s] %s -> %s", country_code, url.rsplit("/", 1)[-1][:50], sorted(data))
        for period, values in data.items():
            all_data[period] = values

    for url in links:
        try:
            content = download(url, referer=PUBLICATIONS_URL)
        except Exception as e:
            logger.warning("[%s] PDF download failed, skipping: %s (%s)", country_code, url, e)
            continue

        data = _parse_mpr_pdf(content)
        for period, values in data.items():
            all_data[period] = values

    if not all_data:
        logger.warning("[%s] Monetary Survey table not found", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for period in sorted(all_data.keys()):
        fcd, td = all_data[period]
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 2) if td else None
        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period.replace("Q", "-Q"),
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    return pd.DataFrame(rows)
