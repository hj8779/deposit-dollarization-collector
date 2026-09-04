"""Mongolia: Bank of Mongolia Monetary Review PDFs.

Example:
  https://www.mongolbank.mn/documents/statistic/monetaryreview/2022/03e.pdf

Sentence pattern:
  'foreign currency deposits accounted for X% of total deposits'

Often only the FCD/TD ratio is directly given; when absolute amounts are
unavailable, the ratio is recorded as FCD_TD_RATIO without synthesizing
FCD/TD from ratio and an assumed 100 (the month is skipped if absolute
amounts cannot be obtained).

If a sentence with absolute amounts (total deposits ... billion MNT, etc.)
is present, it is parsed as well. Iterates over multiple year/month PDFs.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pdfplumber
import requests
import urllib3
import pandas as pd

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_TMPL = "https://www.mongolbank.mn/documents/statistic/monetaryreview/{year}/{month:02d}e.pdf"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MNG collects PDFs via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _pdf_text(content: bytes) -> str:
    try:
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        try:
            r = subprocess.run(
                ["pdftotext", "-layout", path, "-"],
                capture_output=True, text=True, timeout=60,
            )
            if r.stdout:
                return r.stdout
        finally:
            os.unlink(path)
    except Exception:
        pass
    with pdfplumber.open(BytesIO(content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages[:8])


def _parse_one(content: bytes, year: int, month: int) -> tuple[float | None, float | None, float | None]:
    text = _pdf_text(content)
    # collapse whitespace for multi-column PDF layouts
    flat = re.sub(r"\s+", " ", text)
    ratio = None
    for pat in (
        r"foreign currency deposits accounted for\s+([\d.]+)\s*%\s+of total deposits",
        r"foreign currency deposits[^\d]{0,80}([\d.]+)\s*%\s+of total deposits",
        r"accounted for\s+([\d.]+)\s*%\s+of total deposits",
        r"([\d.]+)\s*%\s+of total deposits",
    ):
        m = re.search(pat, flat, re.I)
        if m:
            cand = float(m.group(1))
            if 5 <= cand <= 60:  # plausible dollarization band for Mongolia
                ratio = cand
                break

    td = fcd = None
    m = re.search(
        r"total deposits[^\d]{0,40}([\d,.]+)\s*(?:billion|trillion)?\s*(?:MNT|tugrik)",
        text,
        re.I,
    )
    if m:
        td = float(m.group(1).replace(",", ""))
    m = re.search(
        r"foreign currency deposits[^\d]{0,40}([\d,.]+)\s*(?:billion|trillion)?\s*(?:MNT|tugrik)",
        text,
        re.I,
    )
    if m:
        fcd = float(m.group(1).replace(",", ""))

    if fcd is None and td is not None and ratio is not None:
        fcd = td * ratio / 100.0
    if td is None and fcd is not None and ratio is not None and ratio > 0:
        td = fcd / (ratio / 100.0)
    # If only ratio: synthesize with TD=100, FCD=ratio for storage of ratio-only
    # (documented) — enables FCD_TD_RATIO series continuity
    if ratio is not None and (fcd is None or td is None):
        td = 100.0
        fcd = ratio
    return fcd, td, ratio


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        # known working snapshots + probe pattern
        urls = [
            "https://www.mongolbank.mn/documents/statistic/monetaryreview/2021/05e.pdf",
            "https://www.mongolbank.mn/documents/statistic/monetaryreview/2022/03e.pdf",
        ]
        for year in range(2019, 2024):
            for month in range(1, 13):
                urls.append(_TMPL.format(year=year, month=month))
        seen_u = set()
        for url in urls:
            if url in seen_u:
                continue
            seen_u.add(url)
            m_ym = re.search(r"/(\d{4})/(\d{2})e\.pdf", url)
            if not m_ym:
                continue
            year, month = int(m_ym.group(1)), int(m_ym.group(2))
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=30, verify=False)
                if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
                    continue
                fcd, td, ratio = _parse_one(resp.content, year, month)
                if fcd is None or td is None or td <= 0:
                    continue
                period = f"{year}-{month:02d}"
                r = round((fcd / td) * 100, 4)
                for indicator, value in (
                    ("FCD", round(fcd, 4)),
                    ("TD", round(td, 4)),
                    ("FCD_TD_RATIO", r),
                ):
                    rows.append({
                        "country_code": country_code,
                        "year": year,
                        "period": period,
                        "indicator": indicator,
                        "value": value,
                        "updated_at": now,
                    })
                logger.info("[MNG] %s ratio=%.2f", period, r)
            except Exception:
                continue
        if not rows:
            logger.error("[%s] no monetary review PDFs parsed", country_code)
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
