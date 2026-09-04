"""Belize: combines two tables from the Central Bank of Belize 'Statistical Digest' (published
annually, with the full time series from 1977 through the latest year accumulated in a single
PDF).
    TABLE 7: DOMESTIC BANKS: SUMMARY OF LIABILITIES  -> 'Deposits Total' (sum across all currencies)
    TABLE 8: DOMESTIC BANKS: BREAKDOWN OF LOCAL CURRENCY DEPOSITS -> 'Total Local Currency Deposits'
FCD = Table 7's Deposits Total - Table 8's Total Local Currency Deposits

Two gotchas were found through hands-on testing and handled accordingly:
1) This PDF's pages are actually rendered rotated 180 degrees, so pdfplumber.extract_text()
   returns text with characters in reverse order (the same type of issue seen in ABW/BHR, etc.).
   On top of that, because the table is rotated, extract_text() splits each cell into its own
   line, which made coordinate-based reassembly difficult too — falling back to standard OCR
   (rendering the page to an image, rotating 180 degrees, then pytesseract) proved far more
   reliable.
2) The number of sub-columns under 'Deposits' in TABLE 7 varies by year (e.g. 1977 has 3:
   Demand/Savings/Time + Total, while 2025 has grown to 4: Demand/Savings·Chequing/Savings/Time
   + Total). So which value is 'Total' can't be pinned to a fixed column index — instead, the
   point where the running cumulative sum matches a value itself (i.e. the sum of the preceding
   values) is self-verified as 'Total'. TABLE 8's structure hasn't changed, so its last value is
   always Total Local Currency Deposits.

In this document TABLE 7 and TABLE 8 span 11 and 10 pages respectively (contiguous); the first
page's title carries 'TABLE 7'/'TABLE 8', and subsequent pages carry 'continued'. The page range
for each table is found dynamically by iterating over the actual pages and matching titles,
rather than relying on the document's table of contents (since the page count changes from
edition to edition).
"""

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "https://www.centralbank.org.bz/docs/default-source/4.2.5-statistical-digest/statistical-digest-2025c640da5a-dd75-4fc3-a3bc-3a431d52c202.pdf?sfvrsn=6342168f_1"

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_ROW_RE = re.compile(r"^(?P<label>[A-Za-z]+)\.?\s+(?P<rest>.*\d.*)$")
_NUM_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")
_STRAY_O_RE = re.compile(r"(?<=[\d,\s])O(?=[\d,\s]|$)")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _to_float(token: str) -> float | None:
    token = token.replace(",", "").strip()
    if not token or token == "-":
        return None
    try:
        return float(token)
    except ValueError:
        return None


_OCR_RESOLUTIONS = (240, 250, 260, 275, 300)


def _score_ocr_text(text: str) -> int:
    """Scores quality by how many data rows with a valid month label were correctly captured."""
    score = 0
    for line in text.splitlines():
        m = _ROW_RE.match(line.strip())
        if m and _MONTHS.get(m.group("label").strip().lower()[:3]) is not None:
            score += 1
    return score


def _ocr_page(page) -> str:
    """Depending on the resolution, tesseract sometimes misreads the table column-wise instead
    of row-wise (cause unknown, reproduces sporadically at 200/300/400dpi, etc.), so several
    resolutions are tried and the result with the most correctly captured 'label+numbers' rows
    is chosen (the same self-verification approach used for rotation selection in ABW, etc.)."""
    import pytesseract

    best_text, best_score = "", -1
    for resolution in _OCR_RESOLUTIONS:
        image = page.to_image(resolution=resolution).original.rotate(180, expand=True)
        text = pytesseract.image_to_string(image)
        score = _score_ocr_text(text)
        if score > best_score:
            best_text, best_score = text, score
    return best_text


def _find_table_pages(pdf, marker: str) -> list[int]:
    """Finds the contiguous page indices whose title contains marker (e.g.
    'SUMMARY OF LIABILITIES'). Continuation pages ('continued') repeat only the body title
    without 'TABLE 7:', so marker is given as the table's body title (which appears on every
    page in common)."""
    hits = []
    in_block = False
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        # The page is rotated 180 degrees, so both the line order and the character order within each line are reversed.
        head_lines = text.splitlines()[:8]
        first_lines = " ".join(line[::-1] for line in reversed(head_lines))
        if marker in first_lines:
            hits.append(i)
            in_block = True
        elif in_block:
            break
    return hits


def _extract_period_rows(pages, value_count_min: int) -> dict[str, list[float]]:
    """Extracts {period: [numbers...]} from the OCR text. period is 'YYYY-MM'."""
    result: dict[str, list[float]] = {}
    current_year = None
    for page in pages:
        text = _ocr_page(page)
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if _YEAR_RE.match(line):
                current_year = int(line)
                continue

            m = _ROW_RE.match(line)
            if not m or current_year is None:
                continue
            month = _MONTHS.get(m.group("label").strip().lower()[:3])
            if month is None:
                continue

            rest = _STRAY_O_RE.sub("0", m.group("rest"))
            values = [_to_float(t) for t in _NUM_RE.findall(rest)]
            values = [v for v in values if v is not None]
            if len(values) < value_count_min:
                continue

            result[f"{current_year}-{month:02d}"] = values
    return result


def _deposits_total(values: list[float]) -> float | None:
    """Treats the first point that matches the cumulative sum of preceding values as 'Total' (the column count varies by year, so the index cannot be fixed)."""
    cum = 0.0
    for i, v in enumerate(values):
        if i >= 2 and abs(v - cum) < 1.0:
            return v
        cum += v
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber
    from io import BytesIO

    now = datetime.now(timezone.utc).isoformat()

    with pdfplumber.open(BytesIO(content)) as pdf:
        t7_pages = [pdf.pages[i] for i in _find_table_pages(pdf, "DOMESTIC BANKS: SUMMARY OF LIABILITIES")]
        t8_pages = [pdf.pages[i] for i in _find_table_pages(pdf, "BREAKDOWN OF LOCAL CURRENCY DEPOSITS")]

        logger.info("[%s] OCR processing %d pages of TABLE 7, %d pages of TABLE 8", country_code, len(t7_pages), len(t8_pages))

        t7 = _extract_period_rows(t7_pages, value_count_min=4)
        t8 = _extract_period_rows(t8_pages, value_count_min=10)

    rows = []
    for period, values in t7.items():
        if period not in t8:
            continue
        deposits_total = _deposits_total(values)
        local_total = t8[period][-1]
        if deposits_total is None:
            continue

        fcd = deposits_total - local_total
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
            "value": round(deposits_total, 2),
            "updated_at": now,
        })

    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True) if rows else pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )
