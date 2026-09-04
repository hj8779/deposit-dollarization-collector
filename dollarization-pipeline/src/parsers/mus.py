"""Mauritius: Bank of Mauritius — Monetary Developments PDFs.

Listing (paginated via page=0..N):
  https://www.bom.mu/publications-and-statistics/statistics/monetary-and-financial-statistics/depository-corporation-survey?page=N
Only links whose text matches "Monetary Developments: <Month> <Year>" are used
(titles appear in two styles — all caps like "MAY 2008" or normal case like
"December 2008" — the regex matches case-insensitively).

The "COMPONENTS AND SOURCES OF BROAD MONEY LIABILITIES" table has three
distinct states depending on the period (confirmed by opening documents one
by one to check whether text extraction works and which labels are used):
  - 2008-2011: text is extractable, uses the old-style labels (OLD below).
  - 2012-2020: the table is a scanned image, so text extraction fails (page 2
    is blank) → OCR is required. Labels are a mix of old-style (OLD) up to
    around 2018 and new-style (NEW) afterward.
  - 2021-present: text is extractable, uses the new-style labels (NEW).

OLD labels: '2. Transferable Deposits' / '1. Savings Deposits' / '2. Time
            Deposits' / '3. Foreign Currency Deposits' (the 'II. Quasi-Money
            Liabilities (1+2+3)' total row under Narrow Money is frequently
            garbled by OCR and not used; instead the four items are summed
            directly: TD = Transferable + Savings + Time + FCD)
NEW labels: 'II. Deposit Liabilities' (total) / 'II.2. Foreign Currency
            Deposits' (TD = the total as-is, FCD is its sub-item)

For OCR, pytesseract with psm 6 (assumes a uniform block of text) best
preserves label/number alignment for tables (the default psm 3 sometimes
splits the table into multiple blocks, separating label and number columns).
Files where the labels themselves are too garbled by OCR to recognize (e.g.
2018-01, 2018-09) are skipped rather than producing an unreliable value
(inferring position from the order of number lines is not used, since a
single misaligned line risks silently inserting an incorrect value).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import pandas as pd
import pdfplumber
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_LIST_PAGE = (
    "https://www.bom.mu/publications-and-statistics/statistics/"
    "monetary-and-financial-statistics/depository-corporation-survey"
)
_MAX_LIST_PAGES = 40  # last page was 33 as of last check; iterate with margin

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_LINK_RE = re.compile(
    r'href="([^"]+\.pdf)">\s*Monetary Developments:\s*([A-Za-z]+)\s+(\d{4})\s*</a>', re.I
)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MUS fetches Monetary Developments PDFs via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _list_issues() -> list[tuple[str, str]]:
    """[(period, pdf_url), ...] — walks the listing pagination to the end, collecting only actually published links."""
    out: list[tuple[str, str]] = []
    for page_no in range(_MAX_LIST_PAGES):
        url = _LIST_PAGE if page_no == 0 else f"{_LIST_PAGE}?page={page_no}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=20, verify=False)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        matches = _LINK_RE.findall(resp.text)
        if not matches:
            continue
        for href, mon_s, year_s in matches:
            month = _MONTH_MAP.get(mon_s.lower())
            if not month:
                continue
            period = f"{int(year_s)}-{month:02d}"
            out.append((period, urljoin(url, href)))
    dedup = {period: url for period, url in out}  # later pages are unlikely to be updated versions, order doesn't matter
    logger.info("[MUS] found %d Monetary Developments issues in listing (%s~%s)",
                len(dedup), min(dedup) if dedup else "-", max(dedup) if dedup else "-")
    return sorted(dedup.items())


def _pdf_text(content: bytes) -> str:
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        try:
            r = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=60)
            if r.stdout:
                return r.stdout
        finally:
            import os
            os.unlink(path)
    except Exception:
        pass
    with pdfplumber.open(BytesIO(content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _ocr_table_page(content: bytes) -> str | None:
    import pytesseract

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            page = pdf.pages[1] if len(pdf.pages) > 1 else pdf.pages[0]
            img = page.to_image(resolution=350).original
            return pytesseract.image_to_string(img, config="--psm 6")
    except Exception:
        logger.warning("[MUS] OCR failed", exc_info=True)
        return None


def _num_after(text: str, label: str) -> float | None:
    """Finds the line containing `label` and extracts the first number that follows it
    (comma-separated, or space-separated in 3-digit groups). OCR output may render
    thousands as '62 551' (split by a space) or '62,551' (comma preserved), so both
    forms are handled."""
    for line in text.splitlines():
        idx = line.lower().find(label.lower())
        if idx == -1:
            continue
        rest = line[idx + len(label):].strip()
        toks = rest.split()
        if not toks:
            continue
        first = toks[0].replace(",", "")
        if not re.fullmatch(r"-?\d+\.?\d*", first):
            continue
        if re.fullmatch(r"-?\d{1,3}", first) and len(toks) > 1 and re.fullmatch(r"\d{3}", toks[1]):
            first += toks[1]
        try:
            return float(first)
        except ValueError:
            continue
    return None


def _extract_new_format(text: str) -> tuple[float, float] | None:
    """(fcd, td) — 'II. Deposit Liabilities' total + 'Foreign Currency Deposits' sub-item."""
    fcd = _num_after(text, "Foreign Currency Deposits")
    td = _num_after(text, "Deposit Liabilities")
    if fcd is None or td is None or td <= 0:
        return None
    return fcd, td


def _extract_old_format(text: str) -> tuple[float, float] | None:
    """(fcd, td) — direct sum of Transferable + Savings + Time + FCD (the total row's
    label is frequently garbled by OCR and not trusted)."""
    fcd = _num_after(text, "Foreign Currency Deposits")
    transferable = _num_after(text, "Transferable Deposits")
    savings = _num_after(text, "Savings Deposits")
    time_dep = _num_after(text, "Time Deposits")
    if None in (fcd, transferable, savings, time_dep):
        return None
    td = transferable + savings + time_dep + fcd
    if td <= 0:
        return None
    return fcd, td


def _extract_fcd_td(text: str) -> tuple[float, float] | None:
    return _extract_new_format(text) or _extract_old_format(text)


def _parse_pdf(content: bytes, period: str, country_code: str) -> pd.DataFrame:
    text = _pdf_text(content)
    result = _extract_fcd_td(text)
    if result is None:
        ocr_text = _ocr_table_page(content)
        if ocr_text:
            result = _extract_fcd_td(ocr_text)
    if result is None:
        logger.warning("[%s] could not find FCD/TD labels: %s", country_code, period)
        return _empty()

    fcd, td = result
    year = int(period[:4])
    ratio = round((fcd / td) * 100, 4)
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {"country_code": country_code, "year": year, "period": period, "indicator": ind, "value": val, "updated_at": now}
        for ind, val in (("FCD", round(fcd, 4)), ("TD", round(td, 4)), ("FCD_TD_RATIO", ratio))
    ]
    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        issues = _list_issues()
        if not issues:
            logger.error("[%s] no issues found in listing", country_code)
            return _empty()

        def _one(period: str, url: str) -> pd.DataFrame | None:
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=60, verify=False)
                if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
                    return None
                return _parse_pdf(resp.content, period, country_code)
            except Exception:
                logger.warning("[%s] failed to process %s", country_code, period, exc_info=True)
                return None

        frames: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(_one, period, url): period for period, url in issues}
            for fut in as_completed(futs):
                df = fut.result()
                if df is not None and not df.empty:
                    frames.append(df)

        if not frames:
            return _empty()

        out = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] %d rows (%s~%s) from %d/%d issues",
            country_code, len(out), out["period"].min(), out["period"].max(),
            len(frames), len(issues),
        )
        return out
    except Exception:
        logger.exception("[%s] failed", country_code)
        return _empty()
