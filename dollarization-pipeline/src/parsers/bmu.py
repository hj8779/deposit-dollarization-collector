"""Bermuda: BMA (Bermuda Monetary Authority) 'Annual Report' PDF series (2000~present, once a
year). The listing page (documents-centre/document-annual-reports/general-all-sectors) paginates
via client-side JS (swapping the HTML in place) rather than a server-side fetch, so requests
cannot retrieve the second page (a direct GET on fetchdata?page=2 returns 404) - Playwright must
actually click the '2' pagination link to load the second listing (covering 2000~2006).

In each annual report's 'Combined Balance Sheet of Bermuda Banks and Deposit Companies
(Consolidated)' table, the Liabilities section's 'Sub(-)Total (-) Deposits' row has three
columns Total/BD$/Other; Other (= currencies other than BD$, i.e. foreign currency) is FCD.

Each table covers 3 quarters at a time (e.g. Q4-2025/Q3-2025/Q2-2025), and this table appears
1-2 times within a report (recent reports split 6 quarters across 2 PDF pages, while early-2000s
reports fit the same 6 quarters into 2 blocks on a single PDF page). The quarter notation format
also varies by year:
    'Q4-2025' (recent), '2010-Q4' (2010s), '1998 - Q4' (2000 report, includes a space)
So a regex is used to find the quarter-header line in the page text and split it into blocks,
and within each block a row matching the 'Sub Total Deposits' family (case/spacing/dash notation
varies by year: 'Sub - Total Deposits' / 'sub total - Deposits' / 'Subtotal — Deposits', etc.)
is located, and its 9 numbers (3 quarters x Total/BD$/Other) are mapped in order to the block's
3 quarters.

When overlapping quarters appear across multiple reports (e.g. Q3-2024 shows up in both the 2025
report and the 2024 report), the figures from the more recently published report take priority
(annual reports sometimes slightly restate the previous quarter's figures on each new release,
so the latest edition is treated as more accurate).

Some files, such as the 2005 report, extract with every character doubled, but only on lines
rendered in bold like titles/headers ('CCoommbbiinneedd BBaallaannccee...') - this appears to be
pdfplumber picking up each stroke of the font's bold-simulation (slightly overlapping strokes) as
two separate characters. Regular-weight data rows, by contrast, extract fine, so blindly
de-duplicating the whole text would mangle a number like '16,200' down to '16,20'. Instead,
doubling is detected per line (_maybe_undouble) by checking whether, after removing whitespace
and splitting the string in half, the two halves are identical, and the character-deduplication
regex is applied only to lines where that's true.

Column layout also varies by year, mixing a 3-column Total/BD$/Other format with a 4-column
Total/BD$/US$/Other format (in the 4-column format, Other refers only to currencies other than
USD, so it has a different meaning than in the 3-column format). Rather than parsing column
names, computing FCD = Total - BD$ holds true in both formats, so the column count doesn't need
to be tracked.

Known gaps (a source-side issue that no other report can fill):
    2003-Q1, 2003-Q2 : The entire 2003 report (PDF) is a scanned image with no text layer, so
                        extraction is impossible. 2003-Q3/Q4 are reprinted in the 2004 report and
                        are filled in from there.
    2020-Q1, 2020-Q2 : The '50th Anniversary' special edition (published 2020) has no statistical
                        appendix at all. 2020-Q3/Q4 are reprinted in the 2021 report and are
                        filled in from there.
"""

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

LIST_URL = "https://www.bma.bm/documents-centre/document-annual-reports/general-all-sectors"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_TITLE_RE = re.compile(r"combined balance sheet of bermuda banks and deposit companies", re.I)
_SUBTOTAL_START_RE = re.compile(r"^sub\s*-?\s*total\b", re.I)
_SUBTOTAL_DEPOSITS_RE = re.compile(r"sub\s*-?\s*total\s*[-–—]?\s*deposits", re.I)
_NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")
_REPORT_YEAR_RE = re.compile(r"(19|20)\d{2}")

# Quarter header tokens: 'Q4-2025' / 'Q4 2018' (no dash) / 'Q4-21' (2-digit year) / '2010-Q4' /
# '1998 - Q4' / '2001 Year-end' (=Q4, in 2001~2003 reports)
_QTR_TOKEN_RE = re.compile(
    r"Q(?P<q1>[1-4])\s*-?\s*(?P<y1>\d{2,4})\b"
    r"|(?P<y2>\d{4})\s*-\s*Q(?P<q2>[1-4])"
    r"|(?P<y3>\d{4})\s+Year[- ]end",
    re.I,
)


_DOUBLED_CHAR_RE = re.compile(r"(.)\1")


def _maybe_undouble(line: str) -> str:
    """Restores the original characters for a line where every character got doubled due to bold rendering."""
    stripped = line.replace(" ", "")
    if stripped and len(stripped) % 2 == 0 and stripped[0::2] == stripped[1::2]:
        return _DOUBLED_CHAR_RE.sub(r"\1", line)
    return line


def _full_year(token: str) -> int:
    year = int(token)
    return 2000 + year if year < 100 else year


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BMU is handled via render() (the document listing uses JS pagination)")


def _collect_report_links() -> list[str]:
    from playwright.sync_api import sync_playwright

    links: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(LIST_URL, timeout=60000)
        page.wait_for_timeout(2000)
        links.extend(page.eval_on_selector_all("a[href$='.pdf']", "els => els.map(e => e.href)"))

        try:
            page.click("a.page-link[title='2']", timeout=5000)
            page.wait_for_timeout(2000)
            links.extend(page.eval_on_selector_all("a[href$='.pdf']", "els => els.map(e => e.href)"))
        except Exception:
            logger.warning("BMU listing page 2 click failed (using only page 1 results)")

        browser.close()

    urls = {url for url in links if "cdn.bma.bm" in url}

    def _report_year(url: str) -> int:
        # The upload timestamp prefix on the filename (YYYY-MM-DD-HH-MM-SS-) is unrelated to the
        # actual report year (all of 2000~2017 were bulk-uploaded on 2018-12-28), so it's
        # stripped first, then the year is looked for in the remaining description part. If none
        # is found (e.g. filenames like the 'BMA 50th Anniversary' report with no year in the
        # name), the upload timestamp's year is used as a fallback.
        basename = url.rsplit("/", 1)[-1]
        stripped = re.sub(r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-", "", basename)
        years = [int(m.group()) for m in _REPORT_YEAR_RE.finditer(stripped)]
        if years:
            return max(years)
        prefix_years = [int(m.group()) for m in _REPORT_YEAR_RE.finditer(basename)]
        return max(prefix_years) if prefix_years else 0

    return sorted(urls, key=_report_year)


def _quarter_tokens(line: str) -> list[str]:
    """Extracts 'YYYY-QN' format quarter labels from a line, preserving left->right order."""
    tokens = []
    for m in _QTR_TOKEN_RE.finditer(line):
        if m.group("y1"):
            tokens.append(f"{_full_year(m.group('y1'))}-Q{m.group('q1')}")
        elif m.group("y2"):
            tokens.append(f"{m.group('y2')}-Q{m.group('q2')}")
        else:
            tokens.append(f"{m.group('y3')}-Q4")
    return tokens


def _normalize_text(text: str) -> str:
    return "\n".join(_maybe_undouble(line) for line in text.splitlines())


def _parse_page(text: str, country_code: str, now: str) -> list[dict]:
    lines = _normalize_text(text).splitlines()

    # 1) Lines carrying a quarter header (a group of 3) are used as block start points.
    blocks: list[tuple[list[str], int]] = []  # (quarters, start_line_idx)
    for i, line in enumerate(lines):
        tokens = _quarter_tokens(line)
        if len(tokens) >= 3:
            blocks.append((tokens[:3], i))

    if not blocks:
        return []

    rows = []
    for b, (quarters, start) in enumerate(blocks):
        end = blocks[b + 1][1] if b + 1 < len(blocks) else len(lines)
        for i in range(start, end):
            line = lines[i].strip()
            if not _SUBTOTAL_START_RE.match(line):
                continue

            # The column label normally ends in 'Deposits', but in some narrower-layout editions
            # (2016~2017, etc.) the numbers come right after 'Sub Total -' and only the
            # 'Deposits' label wraps to the next line. Numbers are never taken from the next line
            # (it could be the next item's data row, and mixing them in would throw off the
            # count) - the next line is used only to confirm the label.
            if _SUBTOTAL_DEPOSITS_RE.search(line):
                row_text = line
            else:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if next_line.lower().rstrip(".") != "deposits":
                    continue
                row_text = line

            values = _NUM_RE.findall(row_text)
            # Two formats are mixed: 3 quarters x 3 columns (Total/BD$/Other) or 4 columns
            # (Total/BD$/US$/Other). Regardless of column names, FCD = Total - BD$ holds in both formats.
            per_quarter = len(values) // 3
            if per_quarter < 2 or len(values) % 3 != 0:
                continue
            values = [float(v.replace(",", "")) for v in values]

            for q_idx, period in enumerate(quarters):
                block = values[q_idx * per_quarter: (q_idx + 1) * per_quarter]
                total, bd = block[0], block[1]
                fcd = total - bd
                year = int(period[:4])
                rows.append({
                    "country_code": country_code,
                    "year": year,
                    "period": period,
                    "indicator": INDICATOR,
                    "value": round(fcd, 2),
                    "updated_at": now,
                })
                rows.append({
                    "country_code": country_code,
                    "year": year,
                    "period": period,
                    "indicator": INDICATOR_TD,
                    "value": round(total, 2),
                    "updated_at": now,
                })
            break  # only one subtotal row is used per block

    return rows


def _parse_report(content: bytes, country_code: str, now: str) -> list[dict]:
    import pdfplumber
    from io import BytesIO

    rows = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not _TITLE_RE.search(_normalize_text(text)):
                continue
            rows.extend(_parse_page(text, country_code, now))
    return rows


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    links = _collect_report_links()
    logger.info("[%s] Found %d BMA Annual Reports", country_code, len(links))

    all_rows: list[dict] = []
    for url in links:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=60)
            response.raise_for_status()
        except Exception:
            logger.warning("[%s] Download failed, skipping: %s", country_code, url)
            continue

        rows = _parse_report(response.content, country_code, now)
        logger.info("[%s] %s -> %d quarters", country_code, url.rsplit("/", 1)[-1], len(rows))
        all_rows.extend(rows)

    if not all_rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    df = pd.DataFrame(all_rows)
    # Processed in report publication order (sorted by filename), so keep='last' keeps values from the report processed later (i.e. more recent)
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    return df.sort_values("period").reset_index(drop=True)
