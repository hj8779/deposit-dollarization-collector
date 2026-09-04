"""Bahamas: Central Bank of The Bahamas 'Quarterly Statistical Digest' PDF series
(publications/qsd listing page, paginated ?page=2..6). Each issue includes Table 2.5
'Financial Survey' with annual (multi-year rolling), quarterly (most recent year), and monthly
(a rolling window of roughly the last ~15 months) data together. Reconstructing a continuous
monthly time series requires fetching all issues (about 93, from 2005 to the present).

Table 2.5 has no vector gridlines, so pdfplumber.extract_tables() only picks up the 3 header
lines and fails to find the data rows. It is parsed line-by-line with extract_text() instead.
Data rows follow the format 'period label + 14 numbers', and the order of the 14 values is:
    1 Net Foreign Assets
    2 Domestic Credit: To Government (Net)
    3 Domestic Credit: To Private Sector
    4 Domestic Credit: To Rest of Public Sector
    5 Domestic Credit TOTAL
    6 Currency In Active Circulation
    7 Demand Deposits: Domestic Banks (Adj.)
    8 Demand Deposits: Central Bank
    9 Money Supply(M1) TOTAL
    10 Quasi Money: Savings Deposits
    11 Quasi Money: Fixed Deposits
    12 Quasi Money: Foreign Currency Deposits   -> FCD
    13 Quasi Money TOTAL
    14 Other Items (NET), negative values shown in parentheses
There are three forms a period label line can take: a line with just a year (e.g. '2024') is
either an annual data row, or a header line that sets the year context for the QTR./month rows
that follow it. If the year is immediately followed by 14 numbers, it's an annual data row; if
there are no numbers, it's a context header.

TD (total deposits) = Demand Deposits (index6 Domestic Banks + index7 Central Bank) + Quasi
Money TOTAL (index12, = sum of Savings+Fixed+FCD). Verified against actual data that the
identities M1 TOTAL(index8)=Currency(index5)+Demand deposits and Quasi TOTAL=Savings+Fixed+FCD
hold (2016: M1 2460.6=280.5+2167.6+12.6; Quasi 4469.5=1295.6+2866.3+307.6).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

LIST_URL = "https://www.centralbankbahamas.com/publications/qsd"
_LIST_PAGES = range(1, 7)  # pages 1~6
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_NUM = r"\(?-?[\d,]+\.\d+\)?"
_ROW_RE = re.compile(rf"^(?P<label>\S+\.?(?:\s+[IVX]+)?)\s+(?P<values>(?:{_NUM}\s*){{14}})$")
_YEAR_ONLY_RE = re.compile(r"^(\d{4})$")
_FCD_VALUE_INDEX = 11  # 0-based, the 12th of 14 values
_DEMAND_DOMESTIC_INDEX = 6
_DEMAND_CENTRAL_BANK_INDEX = 7
_QUASI_TOTAL_INDEX = 12


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BHS is handled via render() (iterates over every issue)")


def _to_float(token: str) -> float:
    token = token.strip().replace(",", "")
    if token.startswith("(") and token.endswith(")"):
        return -float(token[1:-1])
    return float(token)


def _collect_pdf_links() -> list[str]:
    links: list[str] = []
    for page_no in _LIST_PAGES:
        url = LIST_URL if page_no == 1 else f"{LIST_URL}?page={page_no}"
        try:
            response = requests.get(url, headers=_HEADERS, timeout=30)
            response.raise_for_status()
        except Exception:
            continue
        links.extend(re.findall(r'href="([^"]+\.pdf)"', response.text))
    return sorted(set(links))


def _find_table_page(pdf):
    for page in pdf.pages:
        text = page.extract_text() or ""
        if text.startswith("Table 2.5"):
            return text
    return None


def _parse_pdf(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber

    now = datetime.now(timezone.utc).isoformat()
    with pdfplumber.open(BytesIO(content)) as pdf:
        text = _find_table_page(pdf)

    if not text:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    current_year = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        m_year = _YEAR_ONLY_RE.match(line)
        if m_year:
            current_year = int(m_year.group(1))
            continue

        m = _ROW_RE.match(line)
        if not m:
            continue

        label = m.group("label").rstrip(".")
        values = m.group("values").split()
        if len(values) != 14:
            continue
        try:
            fcd = _to_float(values[_FCD_VALUE_INDEX])
        except ValueError:
            continue

        if label.isdigit():
            year, period = int(label), f"{label}-Annual"
        elif label.upper().startswith("QTR"):
            if current_year is None:
                continue
            qtr_num = {"I": 1, "II": 2, "III": 3, "IV": 4}.get(m.group("label").split()[-1].upper())
            if qtr_num is None:
                continue
            year, period = current_year, f"{current_year}-Q{qtr_num}"
        else:
            month = _MONTHS.get(label.lower()[:3])
            if month is None or current_year is None:
                continue
            year, period = current_year, f"{current_year}-{month:02d}"

        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR,
            "value": round(fcd, 2),
            "updated_at": now,
        })

        try:
            demand = _to_float(values[_DEMAND_DOMESTIC_INDEX]) + _to_float(values[_DEMAND_CENTRAL_BANK_INDEX])
            quasi_total = _to_float(values[_QUASI_TOTAL_INDEX])
        except ValueError:
            continue
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR_TD,
            "value": round(demand + quasi_total, 2),
            "updated_at": now,
        })

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    links = _collect_pdf_links()
    logger.info("[%s] Found %d Quarterly Statistical Digest issues", country_code, len(links))

    frames = []
    for url in links:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=45)
            response.raise_for_status()
        except Exception:
            logger.warning("[%s] Download failed, skipping: %s", country_code, url)
            continue

        df = _parse_pdf(response.content, country_code)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="last")
    return merged.sort_values(["period", "indicator"]).reset_index(drop=True)
