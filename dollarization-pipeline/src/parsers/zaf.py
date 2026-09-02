"""South Africa: SARB Quarterly Bulletin KBP1 Money & Banking Excel (zip).

Primary source (full monthly history from ~1980s/90s):
  https://www.resbank.co.za/content/dam/sarb/publications/quarterly-bulletins/
    download-information-from-xlsx-data-files/{year}/{month}/
    01Kbp1 Money and Banking {Month} {Year}.zip

Inside: ``Kbp1-MBD-*.xlsx``, sheet ``M1`` (monthly), columns = KBP codes.

Series (EconData / SARB mnemonic list):
  **KBP1078M** — Liabilities of banking institutions:
                 Foreign currency deposits included in total
  **KBP1077M** — Liabilities of banking institutions: Total deposits

Unit: ZAR **million** (end of month). FCD_TD_RATIO = 1078/1077 × 100.

Update strategy:
  1) Resolve latest Kbp1 zip (index QB download pages + recent month path probes)
  2) Parse full history from that single file (already long from 1990s)
  3) Optional: merge with previous DB/seed if a month is missing (usually not needed)

Fallback: batchF verified point 2026-04 (private-sector scope may differ slightly).
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests
import urllib3

from src.utils.fcd_series import empty_frame, long_rows, merge_frames
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

# Banking-institution deposit stocks (ZAR million)
_CODE_FCD = "KBP1078M"  # foreign currency deposits included in total
_CODE_TD = "KBP1077M"  # total deposits

_BASE_XLSX = (
    "https://www.resbank.co.za/content/dam/sarb/publications/"
    "quarterly-bulletins/download-information-from-xlsx-data-files"
)

# Known good zip (user-provided / verified 2026-06)
_FALLBACK_ZIP = (
    f"{_BASE_XLSX}/2026/june/"
    "01Kbp1%20Money%20and%20Banking%20June%202026.zip"
)

_QB_HUBS = [
    "https://www.resbank.co.za/en/home/publications/quarterly-bulletin1/"
    "Quarterly-Bulletin-Publication",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/"
    "quarterly-bulletins/download-information-from-xlsx-data-files",
]

_MONTHS = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

# batchF (private-sector narrative point; may differ slightly from KBP1078/1077)
_SEED = [
    ("2026-04", 150010.0, 3692200.0),  # ZAR million (from bn × 1000)
]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Parse zip or xlsx bytes into long-form FCD/TD/RATIO."""
    if content[:2] == b"PK":
        # zip or xlsx both start with PK
        try:
            return _parse_zip(content, country_code)
        except zipfile.BadZipFile:
            return _parse_xlsx(content, country_code)
    return empty_frame()


def _parse_zip(content: bytes, country_code: str) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = [
            n
            for n in zf.namelist()
            if n.lower().endswith((".xlsx", ".xls")) and not n.startswith("__")
        ]
        if not names:
            raise RuntimeError("no xlsx inside zip")
        # prefer Kbp1 / MBD money-banking workbook
        names.sort(
            key=lambda n: (
                0 if re.search(r"kbp1|mbd|money", n, re.I) else 1,
                n,
            )
        )
        raw = zf.read(names[0])
        logger.info("[ZAF] zip member %s (%d bytes)", names[0], len(raw))
        return _parse_xlsx(raw, country_code)


def _parse_xlsx(content: bytes, country_code: str) -> pd.DataFrame:
    xl = pd.ExcelFile(io.BytesIO(content))
    # Monthly sheet is "M1"
    sheet = "M1" if "M1" in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)
    if df.shape[0] < 2 or df.shape[1] < 3:
        raise RuntimeError(f"unexpected sheet shape {df.shape}")

    code_col: dict[str, int] = {}
    for j in range(1, df.shape[1]):
        code = str(df.iat[0, j]).strip().upper()
        if code.startswith("KBP"):
            code_col[code] = j

    # allow bare numeric mnemonic → KBP####M
    def _col(code: str) -> int | None:
        c = code.upper()
        if c in code_col:
            return code_col[c]
        # try without frequency suffix variants
        for k, j in code_col.items():
            if k.startswith(c[:7]):
                return j
        return None

    j_fcd = _col(_CODE_FCD)
    j_td = _col(_CODE_TD)
    if j_fcd is None or j_td is None:
        raise RuntimeError(
            f"missing {_CODE_FCD}/{_CODE_TD} in sheet {sheet}; "
            f"have {len(code_col)} codes"
        )

    obs: list[tuple[str, float, float]] = []
    for i in range(1, len(df)):
        d = df.iat[i, 0]
        try:
            di = int(float(d))
        except (TypeError, ValueError):
            continue
        # YYYYMMDD or YYYYMM00 style end-of-month labels
        year = di // 10000
        month = (di // 100) % 100
        if month == 0:
            month = 12
        if year < 1960 or year > 2100 or not (1 <= month <= 12):
            continue
        try:
            fcd = float(df.iat[i, j_fcd])
            td = float(df.iat[i, j_td])
        except (TypeError, ValueError):
            continue
        if np.isnan(fcd) or np.isnan(td) or td <= 0 or fcd < 0:
            continue
        # skip empty/placeholder early zeros if both tiny
        if fcd == 0 and td < 1:
            continue
        obs.append((f"{year}-{month:02d}", fcd, td))

    out = long_rows(country_code, obs)
    if len(out):
        logger.info(
            "[%s] KBP %s/%s → %d rows (%s~%s) unit=ZAR million",
            country_code,
            _CODE_FCD,
            _CODE_TD,
            len(out),
            out["period"].min(),
            out["period"].max(),
        )
    return out


def _probe_zip_url(year: int, month_name: str) -> str | None:
    """Try common Kbp1 Money and Banking zip path patterns for one month."""
    mon = month_name.lower()
    title = mon.capitalize()
    candidates = [
        f"{_BASE_XLSX}/{year}/{mon}/01Kbp1%20Money%20and%20Banking%20{title}%20{year}.zip",
        f"{_BASE_XLSX}/{year}/{mon}/01Kbp1 Money and Banking {title} {year}.zip".replace(
            " ", "%20"
        ),
        f"{_BASE_XLSX}/{year}/{mon}/01Kbp1%20Money%20and%20Banking%20{title.upper()}%20{year}.zip",
    ]
    for u in candidates:
        try:
            r = requests.get(u, headers=_HEADERS, timeout=45, stream=True)
            if r.status_code != 200:
                continue
            # read small prefix
            chunk = next(r.iter_content(64), b"")
            if chunk[:2] == b"PK":
                r.close()
                return u
            r.close()
        except Exception:
            continue
    return None


def _discover_latest_zip() -> str:
    """Find newest Kbp1 Money and Banking zip (path probe + hub HTML)."""
    now = datetime.now(timezone.utc)
    # Probe recent 24 months newest-first
    y, m_idx = now.year, now.month - 1  # 0-based
    for _ in range(24):
        mon = _MONTHS[m_idx]
        url = _probe_zip_url(y, mon)
        if url:
            logger.info("[ZAF] resolved zip via probe: %s", url)
            return url
        m_idx -= 1
        if m_idx < 0:
            m_idx = 11
            y -= 1

    # Hub pages (may be CF/404 — best effort)
    for hub in _QB_HUBS:
        try:
            r = requests.get(hub, headers=_HEADERS, timeout=40)
            if r.status_code != 200:
                continue
            for href in re.findall(
                r'href=["\']([^"\']*Kbp1[^"\']*Money[^"\']*\.zip)["\']',
                r.text,
                re.I,
            ):
                u = urljoin(hub, href.replace(" ", "%20"))
                logger.info("[ZAF] resolved zip via hub: %s", u)
                return u
            for href in re.findall(
                r'href=["\']([^"\']*01Kbp1[^"\']*\.zip)["\']', r.text, re.I
            ):
                u = urljoin(hub, href.replace(" ", "%20"))
                logger.info("[ZAF] resolved zip via hub: %s", u)
                return u
        except Exception as e:
            logger.debug("[ZAF] hub %s: %s", hub[-40:], e)

    logger.warning("[ZAF] using fallback zip %s", _FALLBACK_ZIP[-50:])
    return _FALLBACK_ZIP


def _download(url: str) -> bytes:
    r = requests.get(url, headers=_HEADERS, timeout=180)
    r.raise_for_status()
    if r.content[:2] != b"PK":
        raise RuntimeError(f"not zip/xlsx: {r.content[:40]!r} from {url}")
    return r.content


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        # Prefer explicit source_url if it points at a Kbp1 zip/xlsx
        src = (target.get("source_url") or "").strip()
        if re.search(r"kbp1|money%20and%20banking|\.zip|\.xlsx", src, re.I):
            url = src
        else:
            url = _discover_latest_zip()

        content = _download(url)
        live = parse(content, country_code)
        # KBP1078/1077 is the authoritative long history; do not mix batchF
        # private-sector seed (different scope) unless live is empty.
        if live is not None and len(live) > 0:
            out = live
        else:
            out = long_rows(country_code, _SEED)
            logger.warning("[%s] KBP empty — using seed fallback only", country_code)
        if len(out):
            logger.info(
                "[%s] %d rows (%s~%s) source=%s",
                country_code,
                len(out),
                out["period"].min(),
                out["period"].max(),
                url.rsplit("/", 1)[-1][:60],
            )
        return out if len(out) else empty_frame()
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        # last resort seed only
        return long_rows(country_code, _SEED)
