"""Kuwait: CBK Monthly Monetary Statistical Bulletin PDF.

페이지:
  https://www.cbk.gov.kw/en/statistics-and-publication/bulletins-and-periodicals/monthly-monetary-statistical-bulletin
다운로드:
  /en/redirects/download?compId=...&esIndex=reports  (페이지 최신 링크)

Table 15 / 15-1 Local Banks : Residents Deposits By Type (Million KD):
  Private Sector Deposits:
    Sight | Savings | Time | CDs | Total(KD) | In Foreign Currency | Total
  FCD = In Foreign Currency (private sector, residents)
  TD  = Total private sector deposits (KD + FC)

각 월보 PDF 표에 연말 + 최근 ~13개월 롤링이 있으므로,
목록 페이지의 **모든 download?compId= 링크**를 순회·병합하면 과거가 확장된다.
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
_PAGE = (
    "https://www.cbk.gov.kw/en/statistics-and-publication/"
    "bulletins-and-periodicals/monthly-monetary-statistical-bulletin"
)
_BASE = "https://www.cbk.gov.kw"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("KWT는 render()로 PDF를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


_SHOW_ALL_PAGE = _PAGE + "/get-list?page=1&selYear=&showAll=yes"


def _list_pdf_urls(limit: int = 200) -> list[str]:
    """All Monthly Monetary Statistical Bulletin download links, including history.

    The hub page only default-renders page 1 (~last 12 issues), but it's backed by
    a `get-list?...&showAll=yes` endpoint that returns the *entire* archive (back to
    Jan 2019 as of writing, ~90 issues) in one response — use that instead of the
    paginated default view so old bulletins aren't silently dropped.
    """
    out: list[str] = []
    seen: set[str] = set()
    for page_url in (_SHOW_ALL_PAGE, _PAGE):
        try:
            resp = requests.get(page_url, headers=_HEADERS, timeout=90, verify=False)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("[KWT] list fetch failed for %s: %s", page_url, e)
            continue
        hrefs = re.findall(
            r'href=["\']([^"\']*redirects/download\?compId=\d+[^"\']*)["\']',
            resp.text,
            re.I,
        )
        for h in hrefs:
            href = h.replace("&amp;", "&")
            url = urljoin(_BASE, href)
            if url not in seen:
                seen.add(url)
                out.append(url)
    if not out:
        raise RuntimeError("KWT bulletin download link not found")
    logger.info("[KWT] listed %d bulletin download links", len(out))
    return out[:limit]


def _resolve_pdf_url() -> str:
    return _list_pdf_urls(limit=1)[0]


def _nums(line: str) -> list[float]:
    # full integer/decimal tokens (avoid splitting 10558.4 into 105 + 58.4)
    parts = re.findall(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", line)
    out = []
    for p in parts:
        try:
            out.append(float(p.replace(",", "")))
        except ValueError:
            continue
    return out


def _parse_period_token(token: str, year_hint: int | None) -> tuple[int | None, int | None]:
    t = token.strip().lower().rstrip(".")
    if t in _MONTHS:
        return year_hint, _MONTHS[t]
    m = re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/]?(\d{2,4})?$", t)
    if m:
        mon = _MONTHS[m.group(1)[:3]]
        y = year_hint
        if m.group(2):
            yy = int(m.group(2))
            y = 2000 + yy if yy < 100 else yy
        return y, mon
    return None, None


def _parse_residents_table(text: str) -> list[tuple[str, float, float]]:
    """Return list of (period, fcd, td) from Residents Deposits By Type text."""
    lines = text.splitlines()
    # Prefer pure "Residents Deposits By Type" (skip Non-Residents / combined titles)
    start = None
    for i, line in enumerate(lines):
        low = line.lower()
        if "residents deposits by type" not in low:
            continue
        if "non residents" in low or "non-residents" in low:
            continue
        if "residents & non" in low or "residents and non" in low:
            continue
        start = i
        break
    if start is None:
        return []

    year = None
    results: list[tuple[str, float, float]] = []
    for line in lines[start: start + 100]:
        low = line.lower()
        if ("non residents deposits by type" in low or "non-residents deposits by type" in low) and results:
            break
        if re.search(r"table\s*\)?\s*1[6-9]", low) and results:
            break

        bare = line.strip()
        if re.fullmatch(r"20\d{2}", bare):
            year = int(bare)
            continue

        mon = None
        for tok in line.split()[:5]:
            t = tok.strip().lower().rstrip(".")
            if t[:3] in _MONTHS:
                mon = _MONTHS[t[:3]]
                break
            m2 = re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", t)
            if m2:
                mon = _MONTHS[m2.group(1)[:3]]
                break

        nums = _nums(line)
        if not nums:
            continue

        if mon is None:
            # annual eop: "2021 10558.4 ..."
            if 1990 <= nums[0] <= 2100 and nums[0] == float(int(nums[0])):
                year = int(nums[0])
                mon = 12
                nums = nums[1:]
            else:
                continue
        else:
            if nums and 1990 <= nums[0] <= 2100 and nums[0] == float(int(nums[0])):
                year = int(nums[0])
                nums = nums[1:]
            if year is None:
                continue

        if len(nums) < 6:
            continue

        # Private: Sight Sav Time [CDs skipped] TotalKD FC TotalPriv ...
        fcd, td = None, None
        for i in range(min(4, len(nums) - 2)):
            total_kd, fc, total_priv = nums[i], nums[i + 1], nums[i + 2]
            if total_priv <= 1000 or total_kd <= 1000 or fc < 0:
                continue
            if abs((total_kd + fc) - total_priv) <= max(2.0, 0.03 * total_priv):
                fcd, td = fc, total_priv
                break
        if fcd is None or td is None:
            continue
        results.append((f"{year}-{mon:02d}", fcd, td))

    by_p: dict[str, tuple[float, float]] = {}
    for p, f, t in results:
        by_p[p] = (f, t)
    return [(p, by_p[p][0], by_p[p][1]) for p in sorted(by_p)]


def _parse_pdf(content: bytes, country_code: str) -> pd.DataFrame:
    records: list[tuple[str, float, float]] = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "Residents Deposits By Type" in text and "Non Residents" not in text.split("Residents Deposits By Type")[0][-40:]:
                recs = _parse_residents_table(text)
                if recs:
                    records.extend(recs)
            elif re.search(r"Residents Deposits By Type", text, re.I):
                recs = _parse_residents_table(text)
                if recs:
                    records.extend(recs)

    if not records:
        # full document text fallback
        with pdfplumber.open(BytesIO(content)) as pdf:
            full = "\n".join((p.extract_text() or "") for p in pdf.pages)
        records = _parse_residents_table(full)

    if not records:
        logger.error("[%s] no residents deposits rows parsed", country_code)
        return _empty()

    by_p: dict[str, tuple[float, float]] = {}
    for p, f, t in records:
        by_p[p] = (f, t)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period in sorted(by_p):
        fcd, td = by_p[period]
        if td <= 0:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
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


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        urls = _list_pdf_urls()
        frames: list[pd.DataFrame] = []

        def _one(url: str) -> pd.DataFrame:
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
                if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
                    return _empty()
                return _parse_pdf(resp.content, country_code)
            except Exception as e:
                logger.debug("[KWT] skip %s: %s", url[-40:], e)
                return _empty()

        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(_one, u): u for u in urls}
            for fut in as_completed(futs):
                df = fut.result()
                if df is not None and not df.empty:
                    frames.append(df)

        if not frames:
            logger.error("[%s] no bulletin PDFs parsed", country_code)
            return _empty()

        out = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] merged %d rows (%s~%s) from %d PDFs",
            country_code,
            len(out),
            out["period"].min(),
            out["period"].max(),
            len(frames),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
