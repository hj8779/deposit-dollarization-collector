"""Romania: BNR deposits by institutional sector & currency (cid=572).

Interactive query UI needs a date range; the result is a plain GET:

  https://www.bnr.ro/report?cid=572&type=2&dfrom=01-01-2007&dto=DD-MM-YYYY

Title: Structura depozitelor atrase … pe tipuri de sectoare instituționale
Units: mii lei (thousand RON) → we store **RON million** (÷1000).

Scope (resident non-government, matching BNR press “resident non-gov deposits”):
  Sectors: G=households, S=non-financial corporations, I=non-monetary financial inst.
  Exclude: AP=public administration, N=non-residents

  TD  = IFMDL_G + IFMDL_S + IFMDL_I
  FCD = sum of overnight/term euro + other FX for G,S,I:
        {G,S,I}{O,T}{E,X}  → GOE,GOX,GTE,GTX, SOE,SOX,STE,STX, IOE,IOX,ITE,ITX

Auto-update: each render() rebuilds dto=today and re-downloads the HTML table.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import requests
import urllib3
from bs4 import BeautifulSoup

from src.utils.fcd_series import empty_frame, long_rows
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_REPORT_TMPL = (
    "https://www.bnr.ro/report?cid=572&type=2"
    "&dfrom={dfrom}&dto={dto}"
)
_DEFAULT_DFROM = "01-01-2007"

# resident non-government sector totals
_TD_CODES = ("IFMDL_G", "IFMDL_S", "IFMDL_I")
# euro (E) + other FX (X) for overnight (O) and term (T) — not maturity sub-splits
_FCD_CODES = (
    "IFMDL_GOE",
    "IFMDL_GOX",
    "IFMDL_GTE",
    "IFMDL_GTX",
    "IFMDL_SOE",
    "IFMDL_SOX",
    "IFMDL_STE",
    "IFMDL_STX",
    "IFMDL_IOE",
    "IFMDL_IOX",
    "IFMDL_ITE",
    "IFMDL_ITX",
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ro;q=0.8",
}


def parse(content: bytes, country_code: str):
    """Parse saved BNR report HTML bytes."""
    return _parse_html(content.decode("utf-8", errors="replace"), country_code)


def _empty():
    return empty_frame()


def _num(s: str) -> float | None:
    if s is None:
        return None
    t = (
        str(s)
        .replace("\xa0", " ")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )
    if t in {"", "-", "–", "—", "n.a.", "na"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _parse_html(html: str, country_code: str):
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        logger.warning("[ROU] no table in report HTML")
        return _empty()

    # pick the table that has IFMDL_G header codes
    table = None
    for t in tables:
        text = t.get_text(" ", strip=True)
        if "IFMDL_G" in text or "IFMDL_S" in text:
            table = t
            break
    if table is None:
        table = max(tables, key=lambda t: len(t.find_all("tr")))

    rows = table.find_all("tr")
    if len(rows) < 6:
        logger.warning("[ROU] table too short (%d rows)", len(rows))
        return _empty()

    # find code header row
    code_row_i = None
    codes: list[str] = []
    for i, tr in enumerate(rows[:12]):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        joined = " ".join(cells)
        if "IFMDL_G" in joined:
            # drop leading empty / "Data" cell
            codes = [c for c in cells if c.startswith("IFMDL_")]
            if not codes and cells:
                codes = [c for c in cells[1:] if c]
            code_row_i = i
            break
    if not codes:
        logger.warning("[ROU] IFMDL code row not found")
        return _empty()

    obs: list[tuple[str, float, float]] = []
    for tr in rows[code_row_i + 1 :]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        date_lab = cells[0].strip()
        m = re.fullmatch(r"(\d{4})-(\d{2})", date_lab)
        if not m:
            continue
        period = f"{m.group(1)}-{m.group(2)}"
        vals = cells[1:]
        mp: dict[str, float] = {}
        for code, raw in zip(codes, vals):
            v = _num(raw)
            if v is not None:
                mp[code] = v

        td_k = sum(mp.get(c, 0.0) for c in _TD_CODES)
        fcd_k = sum(mp.get(c, 0.0) for c in _FCD_CODES)
        if td_k <= 0:
            continue
        # thousand lei → million RON
        td = td_k / 1000.0
        fcd = fcd_k / 1000.0
        if fcd < 0 or fcd > td * 1.05:
            continue
        if td < 1_000 or td > 50_000_000:
            continue
        ratio = fcd / td
        if ratio < 0.05 or ratio > 0.80:
            continue
        obs.append((period, fcd, td))

    if not obs:
        return _empty()
    # de-dupe by period (keep last)
    by_p = {p: (f, t) for p, f, t in obs}
    rows_out = [(p, by_p[p][0], by_p[p][1]) for p in sorted(by_p)]
    out = long_rows(country_code, rows_out)
    logger.info(
        "[ROU] BNR report cid=572 → %d rows (%s~%s)",
        len(out),
        out["period"].min(),
        out["period"].max(),
    )
    return out


def render(target: dict):
    country_code = target["country_code"]
    try:
        today = datetime.now(timezone.utc).date()
        dto = today.strftime("%d-%m-%Y")
        dfrom = _DEFAULT_DFROM
        # optional override from target notes / env-style fields
        url = _REPORT_TMPL.format(dfrom=dfrom, dto=dto)
        logger.info("[ROU] GET %s", url)
        r = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
        r.raise_for_status()
        if len(r.content) < 5_000:
            raise RuntimeError(f"report too small ({len(r.content)} bytes)")
        return _parse_html(r.text, country_code)
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
