"""Tajikistan: National Bank of Tajikistan(NBT) "Banking Statistics Bulletin" PDFs.

An earlier investigation only found the Monetary Survey / Financial Corporations Survey files,
where deposits appear only as a single "DEPOSITS" aggregate line with no currency breakdown
(a dead end). This time, an additional source was found at
nbt.tj/en/statistics/statistical_bulletin.php ("Banking statistics bulletin"), published
roughly monthly (usually the December issue cumulates that year's January-December), and the
PDF inside it contains a "Structure of outstanding savings (deposits) in credit financial
institutions" table (Russian title "Структура остатков сбережений (депозитов) в
кредитных...организациях") with the following rows:

    1.   Всего депозитов / Total deposits              -> TD
    1.1. в национальной валюте / In domestic currency
    1.2. в иностранной валюте / In foreign currency     -> FCD

The 2025-12-31 values (TD=33,895,226.6 thousand somoni, FCD=12,730,085.1 thousand somoni,
FCD/TD=37.6%) essentially match the press release (nbt.tj/en/news/618354/, TD~33.9bn TJS, FX
share 37.5%), confirming that this table is in fact a reliable time series.

Collection procedure:
1. From the statistical_bulletin.php listing page, collect all *.pdf links along with their
   adjacent text ("Last issue of 2024", "Issue of 2026, May No.5 (370)", etc.) and extract the
   year (items without a year are skipped). Since the link list is updated to the latest issue
   every time a new one is published, the URLs are never hardcoded and are always read
   dynamically.
2. Each PDF is converted to text with pdftotext -layout (pdfplumber.extract_text() sometimes
   produces reversed characters with certain fonts used in these PDFs, so pdftotext is more
   reliable here — this is not a case requiring a full OCR fallback, just a simple layout
   reconstruction issue, so pdftotext -layout is sufficient).
3. All occurrences of the "остатков сбережений (депозитов) в кредитн" table heading are located
   (it also appears in the table of contents, hence duplicates), and beneath each occurrence the
   three rows "1. Всего депозитов" (total), "1.1. в национальной валюте" (domestic currency),
   and "1.2. в иностранной валюте" (foreign currency) are parsed; only the table that passes the
   domestic+foreign~total check is accepted.
4. The table's header row (columns) is sometimes just years (e.g. '2019', 12 monthly cells), and
   sometimes a mix of historical years plus the current year (e.g. '2012' '2013' ... '2017' 'I'
   'II' ... 'XII') — older bulletins tend to have more columns, following a pattern of "N
   cumulative historical years + 12 monthly columns for the current year". Roman-numeral (I-XII)
   columns are treated as that bulletin's monthly values for its reporting year, and 4-digit
   year columns are treated as that year's December (year-end balance) value.
5. Some bulletins (the December 2020 issue, and a few from 2011-2015) have broken font encoding
   that produces no usable text even via pdftotext — these failures are silently skipped (since
   there is at most one bulletin per issue, a handful of years can end up missing entirely.
   Still, thanks to the historical columns accumulated in more recent bulletins, most year-end
   snapshots from 2012 onward can be recovered).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

BULLETIN_LIST_URL = "https://nbt.tj/en/statistics/statistical_bulletin.php"

_ROMAN = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}

_HEADING_RE = re.compile(
    r"остатков сбережений\s*\(депозитов\)\s*в кредитн", re.IGNORECASE
)
_YEAR_IN_TEXT_RE = re.compile(r"(?:Last issue of|Issue of)\s*(\d{4})", re.IGNORECASE)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("TJK is handled via render() by iterating over multiple bulletin PDFs")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _discover_bulletin_urls() -> list[tuple[int, str]]:
    """Finds all (year, absolute PDF URL) pairs on the listing page."""
    html = download(BULLETIN_LIST_URL).decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        text = a.get_text(" ", strip=True)
        m = _YEAR_IN_TEXT_RE.search(text)
        if not m:
            continue
        year = int(m.group(1))
        url = urljoin(BULLETIN_LIST_URL, href)
        if url in seen:
            continue
        seen.add(url)
        out.append((year, url))
    return out


def _pdf_text(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        path = tmp.name
    try:
        r = subprocess.run(
            ["pdftotext", "-layout", path, "-"],
            capture_output=True, text=True, timeout=120,
        )
        return r.stdout or ""
    finally:
        os.unlink(path)


def _split_cols(line: str) -> list[str]:
    return [t for t in re.split(r"\s{2,}", line.strip()) if t]


def _to_float(tok: str) -> float:
    return float(tok.replace(" ", "").replace(",", "."))


# Plausible values top out in the tens-of-millions to hundreds-of-millions range (thousand
# somoni units; total deposits were ~35.2 million thousand somoni as of May 2026). In some older
# bulletins (before 2016), the gap between columns is less than 2 spaces, causing the regex to
# glue several numbers into a single token, which produces an implausibly large digit count
# (e.g. 1.68e+41), so this is filtered out by capping the digit count.
_MAX_DIGITS = 9  # Allows up to 999,999,999 thousand somoni (=TJS ~1 trillion), set generously above the actual maximum


def _plausible_token(tok: str) -> bool:
    int_part = re.split(r"[.,]", tok)[0]
    digits = re.sub(r"[^\d]", "", int_part)
    return 0 < len(digits) <= _MAX_DIGITS


def _find_header_cols(window: str) -> list[str] | None:
    for line in window.split("\n"):
        if "Description" not in line:
            continue
        cols = []
        for tok in _split_cols(line):
            t = tok.strip("/").strip()
            if t in _ROMAN or re.match(r"^(19|20)\d{2}$", t):
                cols.append(t)
        return cols or None
    return None


def _find_value_row(window: str, prefix: str, keyword: str) -> list[str] | None:
    for line in window.split("\n"):
        stripped = line.strip()
        if stripped.startswith(prefix) and keyword in line:
            toks = _split_cols(stripped)
            nums = [t for t in toks if re.match(r"^-?[\d ]*\d(?:[.,]\d+)?$", t) and any(c.isdigit() for c in t)]
            if nums:
                return nums
    return None


def _extract_table(text: str) -> tuple[list[str], list[str], list[str], list[str]] | None:
    """Returns (header_cols, total, domestic, foreign). Returns None on failure."""
    matches = list(_HEADING_RE.finditer(text))
    for m in reversed(matches):  # Prefer the actual table (usually later in the document) over the table of contents
        window = text[m.end(): m.end() + 4000]
        header = _find_header_cols(window)
        total = _find_value_row(window, "1.", "Всего депозитов")
        domestic = _find_value_row(window, "1.1.", "национальной валюте")
        foreign = _find_value_row(window, "1.2.", "иностранной валюте")
        if not (header and total and domestic and foreign):
            continue
        if not (len(total) == len(domestic) == len(foreign)):
            continue
        if len(header) < len(total):
            continue
        header = header[: len(total)]
        if not all(_plausible_token(tok) for tok in (*total, *domestic, *foreign)):
            # Case where the gap between columns is less than 2 spaces, causing several numbers
            # to be glued into one token (an implausibly large digit count) -- this table can't
            # be trusted, so try the next candidate.
            continue
        try:
            ok = all(
                abs(_to_float(d) + _to_float(f) - _to_float(t)) < max(1.0, 0.01 * abs(_to_float(t)))
                for d, f, t in zip(domestic, foreign, total)
            )
        except ValueError:
            ok = False
        if ok:
            return header, total, domestic, foreign
    return None


def _rows_from_bulletin(bulletin_year: int, text: str, country_code: str, now: str) -> list[dict]:
    extracted = _extract_table(text)
    if extracted is None:
        return []
    header, total, domestic, foreign = extracted
    rows = []
    for col, t_tok, f_tok in zip(header, total, foreign):
        if not (_plausible_token(t_tok) and _plausible_token(f_tok)):
            continue
        try:
            td = _to_float(t_tok)
            fcd = _to_float(f_tok)
        except ValueError:
            continue
        if td <= 0 or fcd < 0 or fcd > td * 1.05:
            continue
        if col in _ROMAN:
            year, period = bulletin_year, f"{bulletin_year}-{_ROMAN[col]:02d}"
        elif re.match(r"^(19|20)\d{2}$", col):
            year, period = int(col), f"{col}-12"
        else:
            continue
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in (("FCD", round(fcd, 2)), ("TD", round(td, 2)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })
    return rows


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()
    try:
        bulletins = _discover_bulletin_urls()
    except Exception as e:
        logger.exception("[%s] failed to list statistical bulletins: %s", country_code, e)
        return _empty()

    if not bulletins:
        logger.error("[%s] no bulletin links discovered", country_code)
        return _empty()

    all_rows: list[dict] = []
    for bulletin_year, url in bulletins:
        try:
            content = download(url)
            if not content.startswith(b"%PDF"):
                continue
            text = _pdf_text(content)
            if not text.strip():
                logger.warning("[%s] empty text extraction for %s (year=%s), skipping", country_code, url, bulletin_year)
                continue
            rows = _rows_from_bulletin(bulletin_year, text, country_code, now)
            if not rows:
                logger.warning("[%s] could not locate/parse deposits-by-currency table in %s (year=%s)", country_code, url, bulletin_year)
                continue
            all_rows.extend(rows)
            logger.info("[%s] parsed %d rows from bulletin year=%s (%s)", country_code, len(rows), bulletin_year, url)
        except Exception as e:
            logger.warning("[%s] failed on bulletin year=%s (%s): %s", country_code, bulletin_year, url, e)
            continue

    if not all_rows:
        logger.error("[%s] no bulletins parsed successfully", country_code)
        return _empty()

    out = (
        pd.DataFrame(all_rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows total (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
