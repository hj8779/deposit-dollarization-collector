"""Helpers for long-form FCD/TD series parsers (auto-updatable render())."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Iterable
from urllib.parse import urljoin

import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

EMPTY_COLS = ["country_code", "year", "period", "indicator", "value", "updated_at"]


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=EMPTY_COLS)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = False
    return s


def http_get(
    url: str,
    *,
    timeout: int = 90,
    sess: requests.Session | None = None,
    referer: str | None = None,
) -> requests.Response:
    s = sess or session()
    headers = {}
    if referer:
        headers["Referer"] = referer
    resp = s.get(url, timeout=timeout, headers=headers or None)
    resp.raise_for_status()
    return resp


def pdf_text(content: bytes, first: int | None = None, last: int | None = None) -> str:
    """Extract PDF text via pdftotext, then pdfplumber fallback."""
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        cmd = ["pdftotext", "-layout"]
        if first is not None:
            cmd += ["-f", str(first)]
        if last is not None:
            cmd += ["-l", str(last)]
        cmd += [path, "-"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.stdout and r.stdout.strip():
            return r.stdout
    except Exception:
        pass
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(content)) as pdf:
            pages = pdf.pages
            if first is not None or last is not None:
                lo = (first or 1) - 1
                hi = last or len(pages)
                pages = pages[lo:hi]
            return "\n".join((p.extract_text() or "") for p in pages)
    except Exception:
        return ""


def pdf_text_with_ocr(
    content: bytes,
    marker: str,
    scorer=None,
    max_pages: int = 12,
) -> str:
    """Text extract; OCR fallback via find_page_text_via_ocr when marker missing."""
    text = pdf_text(content)
    if marker.lower() in text.lower():
        return text
    try:
        import pdfplumber
        from src.collectors.base import find_page_text_via_ocr

        with pdfplumber.open(BytesIO(content)) as pdf:
            ocr = find_page_text_via_ocr(
                pdf, marker, max_pages=max_pages, scorer=scorer
            )
            if ocr:
                return ocr
    except Exception:
        pass
    return text


def list_pdf_links(page_url: str, *, pattern: str | None = None, sess=None) -> list[str]:
    """Collect absolute PDF links from an HTML page (optional regex on href)."""
    resp = http_get(page_url, sess=sess)
    hrefs = re.findall(r'href=["\']([^"\']+\.pdf)["\']', resp.text, flags=re.I)
    out = []
    for h in hrefs:
        full = urljoin(page_url, h)
        if pattern and not re.search(pattern, full, re.I):
            continue
        if full not in out:
            out.append(full)
    return out


def long_rows(
    country_code: str,
    observations: Iterable[tuple[str, float, float]],
    updated: str | None = None,
) -> pd.DataFrame:
    """observations: (period YYYY-MM, fcd, td)."""
    updated = updated or now_iso()
    rows = []
    for period, fcd, td in observations:
        if td is None or fcd is None:
            continue
        try:
            fcd_f = float(fcd)
            td_f = float(td)
        except (TypeError, ValueError):
            continue
        if td_f <= 0 or fcd_f < 0:
            continue
        year = int(period[:4])
        ratio = round((fcd_f / td_f) * 100, 4)
        for indicator, value in (
            ("FCD", round(fcd_f, 4)),
            ("TD", round(td_f, 4)),
            ("FCD_TD_RATIO", ratio),
        ):
            rows.append(
                {
                    "country_code": country_code,
                    "year": year,
                    "period": period,
                    "indicator": indicator,
                    "value": value,
                    "updated_at": updated,
                }
            )
    if not rows:
        return empty_frame()
    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def long_rows_ratio_only(
    country_code: str,
    observations: Iterable[tuple[str, float]],
    updated: str | None = None,
) -> pd.DataFrame:
    """When only percent ratios exist: synthetic FCD=ratio, TD=100.

    FCD_TD_RATIO is still (FCD/TD)*100 = ratio in **percent 0–100**, not 0–1.
    Absolute FCD/TD stocks are placeholders so the triple-indicator shape is kept.
    """
    updated = updated or now_iso()
    obs = []
    for period, ratio in observations:
        try:
            r = float(ratio)
        except (TypeError, ValueError):
            continue
        # Accept accidental 0–1 inputs (e.g. 0.27) as percent by scaling
        if 0 < r <= 1.0:
            r = r * 100.0
        obs.append((period, r, 100.0))
    return long_rows(country_code, obs, updated=updated)


def merge_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    parts = [f for f in frames if f is not None and len(f)]
    if not parts:
        return empty_frame()
    out = pd.concat(parts, ignore_index=True)
    return (
        out.drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def parse_nbu_year_month_sheet(
    df: pd.DataFrame,
    *,
    total_col: int = 1,
    fcd_col: int = 11,
    data_start_row: int = 12,
) -> list[tuple[str, float, float]]:
    """Parse NBU deposit excel sheets with Year / Month labels in col 0.

    Stops when year headers reverse (growth-rate section starts).
    """
    out: list[tuple[str, float, float]] = []
    year: int | None = None
    last_year_seen = 0
    for i in range(data_start_row, len(df)):
        lab = df.iat[i, 0]
        if pd.isna(lab):
            continue
        # year header
        if isinstance(lab, (int, float)) and 1990 <= float(lab) <= 2100:
            y = int(lab)
            if last_year_seen and y < last_year_seen - 1:
                # growth section (years restart)
                break
            last_year_seen = max(last_year_seen, y)
            year = y
            td, fcd = _cell_float(df, i, total_col), _cell_float(df, i, fcd_col)
            if td is not None and fcd is not None and td > 1000:
                out.append((f"{y}-12", fcd, td))
            continue
        if not isinstance(lab, str):
            continue
        name = lab.strip()
        mon = MONTHS.get(name.lower())
        if mon is None or year is None:
            continue
        td, fcd = _cell_float(df, i, total_col), _cell_float(df, i, fcd_col)
        if td is not None and fcd is not None and td > 1000:
            out.append((f"{year}-{mon:02d}", fcd, td))
    return out


def _cell_float(df: pd.DataFrame, row: int, col: int) -> float | None:
    try:
        v = df.iat[row, col]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, str):
            v = v.replace(",", "").replace("…", "").replace("...", "").strip()
            if v in ("", "–", "-", "…"):
                return None
        return float(v)
    except (TypeError, ValueError, IndexError):
        return None
