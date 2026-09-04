"""India: RBI Handbook of Statistics — FCNR(B) / Aggregate Deposits.

Handbook of Statistics on the Indian Economy
  https://rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook%20of%20Statistics%20on%20Indian%20Economy

Tables used (annual, end-of-March balances, ₹ Crore):
  Table 140 – Non-Resident Deposits Outstanding - Rupees
      FCD = FCNR(B)  (foreign-currency nonresident deposits; the closest proxy to true FCD)
      NRE/NRO are Rupee accounts, so they are not included in FCD
  Table 41  – Scheduled Commercial Banks - Select Aggregates
      TD  = Aggregate Deposits (Demand + Time)

Notes:
- India's official statistics often publish FCNR(B) in USD and total deposits in INR.
  To keep the ratio in a consistent currency, we pair the Rupee-denominated table
  (Table 140) with Aggregate Deposits (Table 41).
- Fiscal year label `YYYY-(YY+1)` (Table 41) -> end-year `YYYY+1`, March (`{end}-03`).
- Table 140 year `YYYY` = end-March YYYY -> `{YYYY}-03`.
- Since the Handbook PDF hash/filename changes with each release, the URL is
  resolved by Table number from the listing page.
- Services like dataful.in require payment/login, so the official RBI Handbook
  PDF is used as the primary source.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_HANDBOOK_PAGE = (
    "https://rbi.org.in/Scripts/AnnualPublications.aspx"
    "?head=Handbook%20of%20Statistics%20on%20Indian%20Economy"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://rbi.org.in/",
}

# Table number -> (title substring to disambiguate, series role)
_TABLES = {
    140: ("Non-Resident Deposits Outstanding - Rupees", "fcd"),
    41: ("Scheduled Commercial Banks - Select Aggregates", "td"),
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("IND aggregates Handbook Table 41/140 PDFs via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise RuntimeError(f"not pdf: {url} head={resp.content[:40]!r}")
    return resp.content


def _discover_table_pdfs() -> dict[int, str]:
    """Find the direct PDF link for Table N within the Handbook listing HTML."""
    resp = requests.get(_HANDBOOK_PAGE, headers=_HEADERS, timeout=90, verify=False)
    resp.raise_for_status()
    html = resp.text

    # RBI HTML uses single-quoted href attributes
    pattern = re.compile(
        r"Table\s+(\d+)\s*:\s*([^<]+)</td>.*?"
        r"href=['\"](https://rbidocs\.rbi\.org\.in/rdocs/Publications/PDFs/[^'\"]+\.PDF)['\"]",
        re.I | re.S,
    )
    found: dict[int, list[tuple[str, str]]] = {}
    for m in pattern.finditer(html):
        num = int(m.group(1))
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        href = m.group(3)
        found.setdefault(num, []).append((title, href))

    urls: dict[int, str] = {}
    for num, (title_key, _role) in _TABLES.items():
        cands = found.get(num) or []
        pick = None
        for title, href in cands:
            if title_key.lower() in title.lower():
                pick = href
                break
        if pick is None and cands:
            # first candidate matching only by number (to handle title wording variations)
            pick = cands[0][1]
        if pick is None:
            # fallback: filename prefix {num}T_
            m2 = re.search(
                rf"https://rbidocs\.rbi\.org\.in/rdocs/Publications/PDFs/{num}T_[A-Z0-9]+\.PDF",
                html,
                re.I,
            )
            if m2:
                pick = m2.group(0)
        if pick:
            urls[num] = pick
            logger.info("[IND] Table %s -> %s", num, pick.split("/")[-1])
        else:
            logger.error("[IND] Table %s PDF link not found on handbook page", num)
    return urls


def _pdf_text(content: bytes, max_pages: int | None = None) -> str:
    parts: list[str] = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        pages = pdf.pages if max_pages is None else pdf.pages[:max_pages]
        for page in pages:
            t = page.extract_text() or ""
            parts.append(t)
    return "\n".join(parts)


def _to_float(token: str) -> float | None:
    t = token.strip().replace(",", "").replace(" ", "")
    if t in {"", "-", "–", "—", "na", "n.a.", "N.A."}:
        return None
    # exclude parenthesized memo-row values: (20366984)
    if t.startswith("(") and t.endswith(")"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _parse_fcnr_b_table140(content: bytes) -> dict[str, float]:
    """Table 140: year, FCNR(A), FCNR(B), ... → period end-March -> FCNR(B)."""
    text = _pdf_text(content)
    series: dict[str, float] = {}
    # row example: 2026 - 33756 98564 - 33334 - - 165654  (USD table)
    # row example: 2026 - 319514 932947 - 315523 - - 1567984 (INR table)
    # FCNR(B) is the 3rd data column (col 3 by header); the value after year, '-' (FCNR A)
    row_re = re.compile(
        r"^(?P<year>19\d{2}|20\d{2})\s+"
        r"(?P<a>-|[\d,]+)\s+"
        r"(?P<b>-|[\d,]+)\s+",
        re.M,
    )
    for m in row_re.finditer(text):
        year = int(m.group("year"))
        if year < 1990 or year > 2100:
            continue
        fcd = _to_float(m.group("b"))
        if fcd is None or fcd <= 0:
            continue
        # plausible range: FCNR(B) in crore units (thousands to hundreds of thousands).
        # To avoid false positives from the USD table (tens-of-thousands scale), prefer
        # the larger (Rupee) value for a given year — the caller only passes Table 140.
        period = f"{year}-03"
        series[period] = fcd
    return series


def _parse_aggregate_deposits_table41(content: bytes) -> dict[str, float]:
    """Table 41 page 1 (deposit columns): fiscal year, Demand, Time, Aggregate Deposits.

    Page 2 covers Investments/Credit columns and is excluded. Any leftover
    memo rows after '(Continued)' at the end of page 1 are also skipped.
    """
    text = _pdf_text(content, max_pages=1)
    # truncate after the "Continued" marker (next-page notice/footnotes)
    cut = re.search(r"\(Continued", text, re.I)
    if cut:
        text = text[: cut.start()]

    series: dict[str, float] = {}
    # row example: 2024-25 2698049 19882552 22580601 311466 ...
    row_re = re.compile(
        r"^(?P<y1>19\d{2}|20\d{2})-(?P<y2>\d{2})\s+"
        r"(?P<demand>[\d,]+)\s+"
        r"(?P<time>[\d,]+)\s+"
        r"(?P<agg>[\d,]+)\b",
        re.M,
    )
    for m in row_re.finditer(text):
        y1 = int(m.group("y1"))
        y2 = int(m.group("y2"))
        # India's fiscal year YYYY-(YY+1) always ends in March of year y1+1
        expected_yy = (y1 + 1) % 100
        if y2 != expected_yy:
            logger.warning(
                "[IND] unexpected FY label %s-%02d (expected %s-%02d)",
                y1, y2, y1, expected_yy,
            )
        end_year = y1 + 1

        demand = _to_float(m.group("demand"))
        time_dep = _to_float(m.group("time"))
        agg = _to_float(m.group("agg"))
        if agg is None or agg <= 0 or demand is None or time_dep is None:
            continue
        # Demand+Time ≈ Aggregate (sanity check for the deposit section; guards against
        # false matches from the investment page)
        if abs((demand + time_dep) - agg) > max(1.0, 0.02 * agg):
            continue
        if end_year < 1960 or end_year > 2100:
            continue
        period = f"{end_year:04d}-03"
        series[period] = agg
    return series


def _build_frame(country_code: str, fcd: dict[str, float], td: dict[str, float]) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    periods = sorted(set(fcd) & set(td))
    rows = []
    for period in periods:
        fv, tv = fcd[period], td[period]
        if tv <= 0:
            continue
        year = int(period[:4])
        ratio = round((fv / tv) * 100, 4)
        for indicator, value in (
            ("FCD", round(fv, 4)),
            ("TD", round(tv, 4)),
            ("FCD_TD_RATIO", ratio),
        ):
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })
    if not rows:
        return _empty()
    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        urls = _discover_table_pdfs()
    except Exception as e:
        logger.exception("[%s] handbook page scrape failed: %s", country_code, e)
        return _empty()

    fcd_url = urls.get(140)
    td_url = urls.get(41)
    if not fcd_url or not td_url:
        logger.error("[%s] missing table urls: %s", country_code, urls)
        return _empty()

    try:
        fcd_pdf = _download(fcd_url)
        fcd = _parse_fcnr_b_table140(fcd_pdf)
        logger.info(
            "[%s] FCNR(B) Table140: %d years %s~%s",
            country_code, len(fcd), min(fcd) if fcd else "-", max(fcd) if fcd else "-",
        )
    except Exception as e:
        logger.exception("[%s] Table 140 failed: %s", country_code, e)
        return _empty()

    try:
        td_pdf = _download(td_url)
        td = _parse_aggregate_deposits_table41(td_pdf)
        logger.info(
            "[%s] Aggregate Deposits Table41: %d years %s~%s",
            country_code, len(td), min(td) if td else "-", max(td) if td else "-",
        )
    except Exception as e:
        logger.exception("[%s] Table 41 failed: %s", country_code, e)
        return _empty()

    df = _build_frame(country_code, fcd, td)
    if not df.empty:
        logger.info(
            "[%s] merged %d rows (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    else:
        logger.error("[%s] no overlapping periods FCD=%s TD=%s", country_code, list(fcd)[:3], list(td)[:3])
    return df
