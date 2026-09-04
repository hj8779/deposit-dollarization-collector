"""Bhutan: Royal Monetary Authority(RMA) 'Financial Sector Performance Review'
quarterly report PDF series (publication/41/ page, media/Publication/Financial%20Sector%20
Performance%20Review/{Month}%20{Year}.pdf, month=Mar/Jun/Sep/Dec, 2012~2022).

During an earlier investigation the RMA site itself was unreachable due to SSL/connection
errors (presumably because the site was being rebuilt); it is now accessible normally, and
the listing page enumerates quarterly reports under a predictable URL pattern. However, the
certificate chain still appears incomplete, since default verification (verify=True) fails
with an SSL error, so requests calls need verify=False (same pattern used in several other
country parsers).

Each report's 'ANNEXURE I a) Deposit by Customer' table (or, in older reports, 'Table 5.
Deposits by Customer') has a 'Foreign Currency' row (=FCD, the foreign-currency-denominated
portion of retail deposits) and a 'Total' row (=TD, total deposits). The same table reports
values for both the current quarter (e.g. Sep-22) and the same quarter of the prior year
(Sep-21), so each PDF yields two quarters of data.

Gotchas discovered through hands-on inspection:
  - Units differ across periods: recent tables (from roughly 2017 onward) are labeled
    'figures in million Nu.' (millions), while older tables (e.g. 2015) are labeled
    'Table 5. Deposits by Customer(Nu. in Billion)' (billions). The unit is determined by
    checking whether the table title/subtitle text contains 'billion'; if so, values are
    multiplied by 1000 to normalize to millions.
  - The left-right order of the two period values varies by report (e.g. the Sep-22 report
    lists [current quarter, same quarter prior year], while the Dec-18 report has them
    reversed as [same quarter prior year, current quarter]). Column indices cannot be
    hardcoded — the order must be inferred from the 'Mon-YY' tokens in the header line.
  - Above the 'Total' row there is sometimes a column-group header phrase like 'Total
    Deposits % Holding' that is not actual data (it also starts with the word 'Total').
    Only lines where 'Total' is immediately followed by a number are accepted as data rows
    (enforced via a regex anchor).
  - The 'Total' row itself is occasionally wrong in the source (observed: both the March
    2022 and June 2022 issues report the same Total of 188,845.48, while other rows such as
    Foreign Currency/Corporate deposits change normally between quarters. Cross-checking
    against the sum of Corporate deposits + Retail deposits confirms Mar-22 matches
    (188,845.49 ≈ 188,845.48), but Jun-22 comes out to 193,198.94, a completely different
    value — implying the Jun-22 'Total' label is a stale-copy error). Because of this, TD is
    not taken directly from the 'Total' label; instead it is computed as the sum of the
    'Corporate deposits' and 'Retail deposits' rows (confirmed to match the 'Total' label
    exactly in every normal case, and this approach is robust against stale-copy errors).

It appears that this quarterly report series was discontinued after the September 2022
issue (the successor publications, 'Core Financial Indicators' and 'Annual Supervision
Report', were checked and do not contain a deposit-by-currency breakdown table — they focus
on soundness indicators like CAR/NPL instead). As a result, data from 2022-Q3 onward cannot
be collected automatically by this parser and must be filled in via the dashboard's manual
entry table (MANUAL_UPDATE_COUNTRIES).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_BASE_URL = (
    "https://www.rma.org.bt/media/Publication/"
    "Financial%20Sector%20Performance%20Review/{month}%20{year}.pdf"
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

# Quarter-end month names as used in the URL -> quarter number
_QUARTER_MONTHS = {"March": 1, "June": 2, "September": 3, "December": 4}
_FIRST_YEAR = 2012
_LAST_YEAR = 2022  # the report series itself ends after 2022-09 (Q3)

# Only match an actual table title where the line starts with 'a)' or 'Table N.', so that
# narrative sentences like 'customer deposits...' elsewhere in the body text aren't
# mistaken for a table title (observed a false match on a sentence like 'Analysis on the
# deposit data reveals that customer deposits...').
_TITLE_RE = re.compile(r"^(?:[a-z]\)|table\s*\d+\.?)\s*deposits?\s+by\s+customer", re.I | re.M)
_FOREIGN_CURRENCY_ROW_RE = re.compile(r"^Foreign Currency\s+(?P<rest>[\d,.\s%()-]+)$", re.I)
_CORPORATE_ROW_RE = re.compile(r"^Corporate deposits\s+(?P<rest>[\d,.][\d,.\s%()-]*)$", re.I)
_RETAIL_ROW_RE = re.compile(r"^Retail deposits\s+(?P<rest>[\d,.][\d,.\s%()-]*)$", re.I)
_PERIOD_TOKEN_RE = re.compile(r"\b([A-Za-z]{3})-(\d{2})\b")
_NUM_RE = re.compile(r"-?[\d,]+\.\d+")

_MONTHS_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_TO_QUARTER = {3: 1, 6: 2, 9: 3, 12: 4}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BTN is handled via render() (needs to iterate over multiple quarterly PDFs)")


def _candidate_urls() -> list[str]:
    urls = []
    for year in range(_FIRST_YEAR, _LAST_YEAR + 1):
        for month in _QUARTER_MONTHS:
            if year == _LAST_YEAR and _QUARTER_MONTHS[month] > 3:
                continue  # 2022-Q3 (September) is the last published issue
            urls.append(_BASE_URL.format(month=month, year=year))
    return urls


def _parse_pdf(content: bytes, country_code: str) -> list[dict]:
    import pdfplumber

    now = datetime.now(timezone.utc).isoformat()

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not _TITLE_RE.search(text):
                continue

            lines = text.splitlines()
            title_idx = next((i for i, ln in enumerate(lines) if _TITLE_RE.search(ln)), None)
            if title_idx is None:
                continue

            # If 'billion' appears near the table title, the unit is billions (convert to
            # millions); otherwise assume millions by default.
            window = "\n".join(lines[max(0, title_idx - 2):title_idx + 20])
            scale = 1000.0 if re.search(r"\bbillion\b", window, re.I) else 1.0

            # Find the two period (Mon-YY) tokens in the table header, preserving their column order.
            periods: list[tuple[int, int]] | None = None
            for ln in lines[title_idx:title_idx + 10]:
                tokens = _PERIOD_TOKEN_RE.findall(ln)
                if len(tokens) >= 2:
                    parsed = []
                    for mon_str, yy_str in tokens[:2]:
                        month = _MONTHS_ABBR.get(mon_str.lower())
                        if month is None or month not in _MONTH_TO_QUARTER:
                            parsed = []
                            break
                        parsed.append((2000 + int(yy_str), month))
                    if len(parsed) == 2:
                        periods = parsed
                        break
            if periods is None:
                logger.warning("[%s] could not find period header (Mon-YY), skipping", country_code)
                continue

            fcd_values: list[float] | None = None
            corporate_values: list[float] | None = None
            retail_values: list[float] | None = None
            for ln in lines[title_idx:title_idx + 25]:
                stripped = ln.strip()
                if fcd_values is None:
                    m = _FOREIGN_CURRENCY_ROW_RE.match(stripped)
                    if m:
                        nums = [float(t.replace(",", "")) for t in _NUM_RE.findall(m.group("rest"))]
                        if len(nums) >= 2:
                            fcd_values = nums[:2]
                if corporate_values is None:
                    m = _CORPORATE_ROW_RE.match(stripped)
                    if m:
                        nums = [float(t.replace(",", "")) for t in _NUM_RE.findall(m.group("rest"))]
                        if len(nums) >= 2:
                            corporate_values = nums[:2]
                if retail_values is None:
                    m = _RETAIL_ROW_RE.match(stripped)
                    if m:
                        nums = [float(t.replace(",", "")) for t in _NUM_RE.findall(m.group("rest"))]
                        if len(nums) >= 2:
                            retail_values = nums[:2]
                if fcd_values is not None and corporate_values is not None and retail_values is not None:
                    break

            if fcd_values is None or corporate_values is None or retail_values is None:
                logger.warning(
                    "[%s] could not find Foreign Currency/Corporate deposits/Retail deposits rows, skipping",
                    country_code,
                )
                continue
            total_values = [corporate_values[i] + retail_values[i] for i in range(2)]

            rows = []
            for i, (year, month) in enumerate(periods):
                quarter = _MONTH_TO_QUARTER[month]
                period = f"{year}-Q{quarter}"
                rows.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": INDICATOR, "value": round(fcd_values[i] * scale, 2), "updated_at": now,
                })
                rows.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": INDICATOR_TD, "value": round(total_values[i] * scale, 2), "updated_at": now,
                })
            return rows

    return []


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    urls = _candidate_urls()
    logger.info("[%s] %d Financial Sector Performance Review candidate URLs (2012~2022-Q3)", country_code, len(urls))

    all_data: dict[tuple[str, str], float] = {}  # (period, indicator) -> value; latest issue wins
    found = 0
    for url in urls:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=60, verify=False)
        except Exception:
            continue
        if response.status_code != 200 or response.content[:4] != b"%PDF":
            continue  # year/quarter combination not published (404, etc.), skip silently

        rows = _parse_pdf(response.content, country_code)
        if not rows:
            continue
        found += 1
        for row in rows:
            all_data[(row["period"], row["indicator"])] = row["value"]

    logger.info("[%s] parsed %d actually published PDFs, obtained %d (period,indicator) pairs", country_code, found, len(all_data))

    if not all_data:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": indicator,
            "value": value,
            "updated_at": now,
        }
        for (period, indicator), value in sorted(all_data.items())
    ]
    return pd.DataFrame(rows)
