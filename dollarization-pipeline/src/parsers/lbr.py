"""Liberia: CBL Monthly Economic Review — commercial bank deposits by currency.

Listing page (paginated; document_type=194 is MER):
  https://www.cbl.org.lr/general/all-publications?keys=&field_document_type_target_id%5B%5D=194&items_per_page=25&page=N
  (the previously used /publications/document-type/monthly-economic-review page
  has no pagination and only surfaces the most recent few issues — switched to
  this listing page instead, iterating page=0..4 to reach all 118 issues back
  to 2015-01; fixed 2026-08-19)
Example PDF:
  /sites/default/files/documents/MONTHLY%20ECONOMIC%20REVIEW%20MAY%202026.pdf

Table "Deposits of commercial banks" / "Total Deposits (both USD & LRD) converted to LRD":
  Demand deposits – USD / LRD
  Time & savings deposits – USD / LRD
  Other deposits USD/LRD components
  Total Deposits (both USD & LRD) converted to LRD  → TD

FCD = TD − (Demand LRD + Time&savings LRD + Other LRD)
    = USD components converted into LRD (the official total is already in LRD)
Equivalently: back out the Total_LRD_deposits_share.

We read several recent MER issues and merge the monthly series (each issue
covers roughly the last 4 months).
Unit: LRD million (converted).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import pdfplumber
import requests
import urllib3
import pandas as pd

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_PAGE = "https://www.cbl.org.lr/publications/document-type/monthly-economic-review"
_LIST_PAGE_TMPL = (
    "https://www.cbl.org.lr/general/all-publications"
    "?keys=&field_document_type_target_id%5B%5D=194&items_per_page=25&page={page}"
)
_BASE = "https://www.cbl.org.lr"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("LBR fetches the MER PDF via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _list_mer_pdfs(max_files: int = 200, max_pages: int = 12) -> list[str]:
    """Paginated all-publications listing filtered to document type 194 (MER) —
    goes back to 2015-01 as of writing, unlike the un-paginated hub page."""
    seen = set()
    urls: list[str] = []
    for page in range(max_pages):
        list_url = _LIST_PAGE_TMPL.format(page=page)
        try:
            resp = requests.get(list_url, headers=_HEADERS, timeout=90, verify=False)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("[LBR] list page %d fail: %s", page, e)
            break
        hrefs = re.findall(r'href=["\']([^"\']+\.pdf)\s*["\']', resp.text, re.I)
        if not hrefs:
            break
        for h in hrefs:
            h = h.replace("&amp;", "&").strip()
            url = urljoin(_BASE, h)
            if url not in seen:
                seen.add(url)
                urls.append(url)
        if len(urls) >= max_files:
            break
    logger.info("[LBR] %d MER pdf links (paginated)", len(urls))
    return urls[:max_files]


def _nums(s: str) -> list[float]:
    parts = re.findall(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", s)
    out = []
    for p in parts:
        try:
            out.append(float(p.replace(",", "")))
        except ValueError:
            continue
    return out


def _header_periods(text: str) -> list[str] | None:
    """Try to find a header line with Month-YY or Month YYYY patterns near deposits table."""
    # e.g. Feb-25  Mar-25  Apr-25  May-25  or  Feb-26
    for line in text.splitlines():
        if not re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", line, re.I):
            continue
        hits = re.findall(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/\s]?(\d{2,4})",
            line,
            re.I,
        )
        if len(hits) >= 2:
            periods = []
            for mon_s, ys in hits:
                mon = _MONTHS[mon_s[:3].lower()]
                yy = int(ys)
                year = 2000 + yy if yy < 100 else yy
                periods.append(f"{year}-{mon:02d}")
            return periods
    return None


def _parse_mer_pdf(content: bytes) -> dict[str, tuple[float, float]]:
    """period -> (fcd, td) in LRD million."""
    with pdfplumber.open(BytesIO(content)) as pdf:
        full = "\n".join((p.extract_text() or "") for p in pdf.pages)

    # Locate Total Deposits converted to LRD line
    td_line = None
    for line in full.splitlines():
        if re.search(r"Total Deposits\s*\(both USD\s*&\s*LRD\)", line, re.I):
            td_line = line
            break
        if re.search(r"Total Deposits.*converted to LRD", line, re.I):
            td_line = line
            break

    # LRD components
    lrd_demand = None
    lrd_time = None
    lrd_other = None
    usd_demand = None
    usd_time = None
    usd_other = None

    lines = full.splitlines()
    for i, line in enumerate(lines):
        low = line.lower()
        if "demand deposits" in low and "usd" in low:
            usd_demand = _nums(line)
        elif "demand deposits" in low and "lrd" in low:
            lrd_demand = _nums(line)
        elif re.search(r"time\s*&\s*savings deposits\s*[–\-—]?\s*usd", low):
            usd_time = _nums(line)
        elif re.search(r"time\s*&\s*savings deposits\s*[–\-—]?\s*lrd", low):
            lrd_time = _nums(line)
        elif "actual us$ component of other" in low or "actual us$ component of other" in low:
            usd_other = _nums(line)
        elif "liberian $ component of other" in low or "liberian $ component of other" in low:
            lrd_other = _nums(line)
        # multi-line labels
        if "demand deposits" in low and i + 1 < len(lines):
            nxt = lines[i + 1].lower()
            if "usd" in nxt and usd_demand is None:
                usd_demand = _nums(lines[i + 1]) if _nums(lines[i + 1]) else _nums(line + " " + lines[i + 1])
            if "lrd" in nxt and lrd_demand is None:
                lrd_demand = _nums(lines[i + 1]) if _nums(lines[i + 1]) else _nums(line + " " + lines[i + 1])

    # Total deposits numbers: may be on same line or next
    td_vals = []
    if td_line:
        td_vals = _nums(td_line)
        if len(td_vals) < 2:
            # next few lines
            idx = full.splitlines().index(td_line) if td_line in full.splitlines() else -1
            if idx >= 0:
                for j in range(idx, min(idx + 4, len(lines))):
                    td_vals = _nums(lines[j])
                    if len(td_vals) >= 2:
                        break
    # sometimes label and values split:
    if len(td_vals) < 2:
        for i, line in enumerate(lines):
            if "converted to lrd" in line.lower() or (
                "total deposits" in line.lower() and "usd" in line.lower()
            ):
                chunk = " ".join(lines[i: i + 3])
                td_vals = _nums(chunk)
                if len(td_vals) >= 2:
                    break

    periods = _header_periods(full)
    # Infer n columns from td_vals
    n = len(td_vals)
    if n < 1:
        return {}
    if periods is None or len(periods) < n:
        # try extract from document title month
        title_m = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            full,
            re.I,
        )
        if title_m and n >= 1:
            end_mon = _MONTHS[title_m.group(1)[:3].lower()]
            end_year = int(title_m.group(2))
            # assume consecutive months ending at title month
            periods = []
            y, m = end_year, end_mon
            for _ in range(n):
                periods.append(f"{y}-{m:02d}")
                m -= 1
                if m == 0:
                    m = 12
                    y -= 1
            periods = list(reversed(periods))
        else:
            return {}
    periods = periods[-n:]

    # LRD local-currency deposit stock
    def col_sum(series_list, i):
        s = 0.0
        for ser in series_list:
            if ser is None or i >= len(ser):
                return None
            s += ser[i]
        return s

    out: dict[str, tuple[float, float]] = {}
    for i, period in enumerate(periods):
        if i >= len(td_vals):
            break
        td = td_vals[i]
        if td <= 0:
            continue
        lrd_parts = []
        for ser in (lrd_demand, lrd_time, lrd_other):
            if ser is not None and i < len(ser):
                lrd_parts.append(ser[i])
        if lrd_parts:
            lrd_total = sum(lrd_parts)
            fcd = td - lrd_total
        else:
            # fallback: if only total, skip FCD
            continue
        if fcd < 0:
            # numerical noise
            if fcd > -1:
                fcd = 0.0
            else:
                continue
        out[period] = (fcd, td)
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        urls = _list_mer_pdfs()
        if not urls:
            raise RuntimeError("no MER pdf links")

        # Sequential, oldest→newest so newer values overwrite on overlapping
        # periods. (A ThreadPoolExecutor version doing all downloads concurrently
        # was tried first for speed, but reproducibly hung after all 114/114
        # downloads had already completed and logged — some worker thread never
        # released cleanly on this network. The sequential version *also* hung
        # mid-run despite a requests-level (15, 60) timeout, which only bounds
        # socket I/O — the actual stall is presumably inside pdfplumber parsing a
        # specific malformed PDF, not the network call.
        #
        # A hard per-PDF deadline is needed to forcibly interrupt either case.
        # This used to be signal.alarm()-based, but that raises
        # "ValueError: signal only works in main thread of the main interpreter"
        # whenever this parser runs inside a worker thread — which is exactly
        # what happens under `main.py --workers N>1` (collectors run in a
        # ThreadPoolExecutor there). That ValueError was being swallowed by the
        # outer try/except below, silently turning every LBR run under
        # --workers>1 into an empty result with no visible error. A
        # single-use-per-PDF ThreadPoolExecutor with future.result(timeout=...)
        # gives the same hard deadline without touching signals, so it works from
        # any thread. A timed-out future's thread is abandoned (shutdown(wait=False))
        # rather than joined, since joining is exactly the kind of wait that hung
        # before.)
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

        def _fetch_and_parse(url: str) -> dict[str, tuple[float, float]]:
            resp = requests.get(url, headers=_HEADERS, timeout=(15, 60), verify=False)
            resp.raise_for_status()
            if not resp.content.startswith(b"%PDF"):
                return {}
            return _parse_mer_pdf(resp.content)

        merged: dict[str, tuple[float, float]] = {}
        for url in reversed(urls):
            ex = ThreadPoolExecutor(max_workers=1)
            try:
                future = ex.submit(_fetch_and_parse, url)
                part = future.result(timeout=90)
                logger.info("[LBR] %s -> %d periods", url.split("/")[-1][:40], len(part))
                merged.update(part)
            except FutureTimeoutError:
                logger.warning("[LBR] pdf hard-timeout (>90s) %s", url[-40:])
            except Exception as e:
                logger.warning("[LBR] pdf fail %s: %s", url[-40:], e)
            finally:
                ex.shutdown(wait=False)

        if not merged:
            logger.error("[%s] no periods parsed from MERs", country_code)
            return _empty()

        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for period in sorted(merged):
            fcd, td = merged[period]
            if td <= 0:
                continue
            year = int(period[:4])
            ratio = round((fcd / td) * 100, 4)
            if ratio < 50:
                # Liberia's genuine ratio has stayed in the ~60-100% band across
                # this whole series (it's one of the most heavily dollarized
                # economies — USD is de facto co-legal-tender). A handful of
                # periods (e.g. 2023-08 -> 4.8%) come out far below that because
                # some MER PDFs interleave two visually-separate tables into one
                # linear pdfplumber text stream, occasionally desyncing which
                # header column a value belongs to. Rather than trust a reading
                # that contradicts every neighboring month, drop it.
                logger.warning(
                    "[%s] %s ratio=%.2f%% abnormally low (<50%%) — treating as a "
                    "table-column misalignment and skipping",
                    country_code, period, ratio,
                )
                continue
            for indicator, value in (
                ("FCD", round(fcd, 4)),
                ("TD", round(td, 4)),
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
        out = (
            pd.DataFrame(rows)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] %d rows (%s~%s)",
            country_code, len(out), out["period"].min(), out["period"].max(),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
