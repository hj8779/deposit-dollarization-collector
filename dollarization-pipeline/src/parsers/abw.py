"""Aruba: Centrale Bank van Aruba(CBA) Monthly Bulletin PDF, 'TABLE 2: COMPONENTS OF BROAD MONEY'.

The table has no vector gridlines, so pdfplumber's default extract_tables() can't detect the
cells. Instead, the page text is read line by line and annual (e.g. '2022 ...') and monthly
(e.g. '2025 January ...', 'February ...') rows are parsed with regex. The column layout follows
the column definitions in the PDF table's footnotes:

    (1) Currency issued            (2) Currency at banks
    (3=1-2) Currency outside banks (4) Demand deposits Afl.
    (5) Demand deposits Foreign currency        (6=4+5) Demand deposits Total
    (7=3+6) Money
    (8) Other deposits Savings Afl.             (9) Other deposits Savings Foreign currency
    (10) Other deposits Time Afl.               (11) Other deposits Time Foreign currency
    (12=8+9+10+11) Other deposits Total
    (13) Treasury bills and cash certificates
    (14=12+13) Quasi-money
    (15=7+14) Broad money

FCD (resident foreign currency deposits) = col(5) + col(9) + col(11)
TD (total deposits)                      = col(6) + col(12)

Collecting historical data (2010~): CBA exposes each month's PDF via a per-year archive page
(/document/monthly-tables-{YYYY}/), with URLs of the form `readBlob.do?id=NNNNN`. TABLE 2 in
each PDF itself contains a rolling window of roughly the last 18 months of monthly data plus
the prior 4 years of annual data, so fetching just one PDF per year (preferably December, or
otherwise the last month published that year) is enough to reconstruct most of that year's
monthly data. Some PDFs (2010, 2011, most of 2013/2014, plus a few months in 2018/2021) come
out as character-by-character reversed text when read with pdfplumber.extract_text(). It turns
out the rendered page itself is actually rotated 180 degrees (hard to tell by eye or with a
vision model, but the underlying pixels really are flipped), so rendering that page as an image,
rotating it 180 degrees, and running OCR reads it correctly. This is used as the project's
standard OCR fallback procedure: when plain text extraction fails, retry by locating the page
via `src.collectors.base.find_page_text_via_ocr()`
(see the README.md section 'Standard fallback when PDF text extraction fails' for details).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber

from src.collectors.base import download, find_page_text_via_ocr
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # Not a single file download — has to walk the per-year archive pages.

ARCHIVE_URL_TMPL = "https://www.cbaruba.org/document/monthly-tables-{year}/"
FIRST_ARCHIVE_YEAR = 2010

# Handles both label formats: "MonthlyTablesDec2010.pdf" (old) / "June 2026 Monthly Tables ..." (new)
_LABEL_OLD_RE = re.compile(r"MonthlyTables([A-Za-z]{3})(\d{4})\.pdf", re.I)
_LABEL_NEW_RE = re.compile(r"^([A-Za-z]+)\s+(\d{4})\s+Monthly Tables", re.I)
_ARCHIVE_LINK_RE = re.compile(
    r'<span class="text">([^<]*)</span>.*?readBlob\.do\?id=(\d+)', re.S
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_ABBR = {name[:3]: num for name, num in _MONTHS.items()}
_NUM_RE = r"-?[\d,]+\.\d+"
_ROW_RE = re.compile(
    rf"^(?:(?P<year>\d{{4}})\s+)?(?:(?P<month>[A-Za-z]+)\s+)?(?P<values>(?:{_NUM_RE}\s*){{15}})$"
)


_TABLE2_MARKER = "TABLE 2: COMPONENTS OF BROAD MONEY"
# OCR often drops the number/punctuation in "TABLE 2:" (e.g. "TABLE\n\n: COMPONENTS..."),
# so use a more lenient substring for OCR marker detection.
_TABLE2_OCR_MARKER = "COMPONENTS OF BROAD MONEY"


def _find_table2_page(pdf: pdfplumber.PDF):
    for page in pdf.pages:
        text = page.extract_text() or ""
        if text.startswith(_TABLE2_MARKER) or _TABLE2_MARKER in text.splitlines()[0:1]:
            return page
    for page in pdf.pages:
        text = page.extract_text() or ""
        if _TABLE2_MARKER in text:
            return page
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    with pdfplumber.open(BytesIO(content)) as pdf:
        page = _find_table2_page(pdf)
        text = page.extract_text() if page is not None else None

        if not text:
            # Standard OCR fallback: if plain text extraction can't find TABLE 2 (e.g. due to
            # broken character encoding), render the page as an image and try OCR at each
            # rotation. With the wrong rotation, the title may still be roughly recognizable
            # while the body numbers come out garbled, so pick the best rotation by the number
            # of rows that actually parse successfully.
            logger.info("[%s] Text extraction failed, trying OCR fallback", country_code)
            text = find_page_text_via_ocr(
                pdf, _TABLE2_OCR_MARKER,
                scorer=lambda t: len(_parse_table2_text(t, country_code)),
            )

    if not text:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    return _parse_table2_text(text, country_code)


def _parse_table2_text(text: str, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    current_year = None
    for raw_line in text.splitlines():
        # OCR output sometimes mixes in noise tokens like underscores/equals signs from the
        # table footnotes (e.g. '='), so strip those out.
        line = " ".join(tok for tok in raw_line.split() if tok not in ("=", "-", "|"))
        m = _ROW_RE.match(line)
        if not m:
            continue

        if m.group("year"):
            current_year = int(m.group("year"))
        if current_year is None:
            continue

        values = [float(v.replace(",", "")) for v in m.group("values").split()]
        if len(values) != 15:
            continue

        month_name = m.group("month")
        if month_name:
            month = _MONTHS.get(month_name.lower())
            if month is None:
                continue
            period = f"{current_year}-{month:02d}"
            year = current_year
        else:
            # Annual total row (e.g. '2022 336.6 ...')
            year = current_year
            period = f"{year}-Annual"

        demand_fcy, savings_fcy, time_fcy = values[4], values[8], values[10]
        demand_total, other_total = values[5], values[11]

        fcd = round(demand_fcy + savings_fcy + time_fcy, 2)
        td = round(demand_total + other_total, 2)
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


def _month_from_label(label: str) -> tuple[int, int] | None:
    """Extract (year, month) from an archive link's label text."""
    m = _LABEL_OLD_RE.search(label)
    if m:
        month = _MONTH_ABBR.get(m.group(1).lower()[:3])
        return (int(m.group(2)), month) if month else None

    m = _LABEL_NEW_RE.search(label)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        return (int(m.group(2)), month) if month else None

    return None


def _candidates_per_year(archive_html: str) -> dict[int, list[tuple[int, str]]]:
    """Build a year -> [(month, doc_id), ...] map from a per-year archive page's HTML, sorted
    by month descending. Some PDFs are corrupted (text extracts character-reversed), which can
    make the best candidate (December/latest month) fail, so the full list is returned so
    render() can retry the next candidate in sequence on failure."""
    by_year: dict[int, list[tuple[int, str]]] = {}
    for label, doc_id in _ARCHIVE_LINK_RE.findall(archive_html):
        parsed = _month_from_label(label.strip())
        if parsed is None:
            continue
        year, month = parsed
        by_year.setdefault(year, []).append((month, doc_id))
    for year in by_year:
        by_year[year].sort(key=lambda pair: pair[0], reverse=True)
    return by_year


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now_year = datetime.now(timezone.utc).year

    frames = []
    for year in range(FIRST_ARCHIVE_YEAR, now_year + 1):
        archive_url = ARCHIVE_URL_TMPL.format(year=year)
        try:
            html = download(archive_url).decode("utf-8", errors="ignore")
        except Exception:
            logger.warning("[%s] Failed to access %s archive, skipping", country_code, year)
            continue

        candidates = _candidates_per_year(html).get(year, [])
        if not candidates:
            logger.info("[%s] No valid PDF links in the %s archive, skipping", country_code, year)
            continue

        df = pd.DataFrame()
        for _, doc_id in candidates:
            pdf_url = f"https://www.cbaruba.org/readBlob.do?id={doc_id}"
            try:
                content = download(pdf_url, referer=archive_url)
            except Exception:
                continue
            df = parse(content, country_code)
            if not df.empty:
                break
            logger.info(
                "[%s] No parse results from %s PDF (id=%s) (likely a text-corrupted PDF), retrying with a different month",
                country_code, year, doc_id,
            )

        if df.empty:
            logger.warning("[%s] Failed to parse all candidate PDFs for %s, skipping", country_code, year)
            continue
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    merged = pd.concat(frames, ignore_index=True)
    # Since the per-year archives can have overlapping periods (rolling window), deduplicate
    # on (period, indicator), preferring the value from the more recently published PDF
    # (later in the list, i.e. the later year).
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="last")
    merged = merged.sort_values(["period", "indicator"]).reset_index(drop=True)
    return merged
