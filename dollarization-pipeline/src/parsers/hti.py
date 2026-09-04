"""Haiti: BRH Table 20R — Bilan consolidé des banques commerciales.

Source page: https://www.brh.ht/statistiques/monnaie/
Annual:  https://www.brh.ht/wp-content/uploads/2018/08/bilanbcmannuel.pdf
Monthly: https://www.brh.ht/wp-content/uploads/bilanconsolidemensuel.pdf

Table structure (millions de gourdes, consolidated commercial banks):
  Engagements envers le secteur privé
    Dépôts en gourdes   — domestic-currency deposits
    Dépôts en dollars   — foreign-currency (dollar) deposits  ← FCD (in gourde equivalent)

FCD = Dépôts en dollars
TD  = Dépôts en gourdes + Dépôts en dollars
     (= Engagements envers le secteur privé, confirmed as an identity empirically)

Notes:
- Dollar deposits are also reported in gourdes (converted at the end-of-period/
  end-of-month exchange rate). Recovering the original USD balance would require
  dividing back out by the exchange rate.
- Covers commercial banks only (excludes caisses populaires, etc.).
- The annual PDF's year header may have a gap after '1961' before resuming at
  2006~present (used as-is from the table).
- The PDF sometimes inserts spaces as thousands separators when extracting
  numbers (e.g. '3 1,730.79'), so spaces are stripped before parsing.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pdfplumber
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_ANNUAL_URL = "https://www.brh.ht/wp-content/uploads/2018/08/bilanbcmannuel.pdf"
_MONTHLY_URL = "https://www.brh.ht/wp-content/uploads/bilanconsolidemensuel.pdf"
_PAGE = "https://www.brh.ht/statistiques/monnaie/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse(content: bytes, country_code: str):
    raise NotImplementedError("HTI merges annual and monthly PDFs via render()")


def _empty():
    import pandas as pd
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=90, verify=False)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise RuntimeError(f"not pdf: {url} head={resp.content[:40]!r}")
    return resp.content


def _fix_num(token: str) -> float | None:
    t = token.strip().replace(" ", "").replace(",", "")
    if t in {"", "-", "–", "—"}:
        return None
    neg = t.startswith("(") and t.endswith(")")
    if neg:
        t = t[1:-1]
    try:
        v = float(t)
        return -v if neg else v
    except ValueError:
        return None


def _numbers_after_label(line: str) -> list[float | None]:
    """Parse numeric tokens after the label (tolerates PDF thousands-separator spaces)."""
    m = re.match(r"^([^\d\-\(]+)\s+(.*)$", line.strip())
    if not m:
        return []
    rest = m.group(2)
    tokens = re.findall(r"\(?\d[\d\s,]*\.?\d*\)?|\-", rest)
    out: list[float | None] = []
    for tok in tokens:
        if tok == "-":
            out.append(None)
        else:
            out.append(_fix_num(tok))
    return out


def _find_line(lines: list[str], *needles: str) -> str | None:
    for line in lines:
        low = line.lower()
        if all(n.lower() in low for n in needles):
            # avoid 'Dépôts à la Banque Centrale'
            if "banque centrale" in low:
                continue
            return line
    return None


def _parse_annual(content: bytes) -> dict[str, tuple[float, float]]:
    """period YYYY-12 -> (fcd, td)."""
    with pdfplumber.open(BytesIO(content)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    lines = text.splitlines()

    years: list[int] = []
    for line in lines:
        ys = [int(x) for x in re.findall(r"\b(19\d{2}|20\d{2})\b", line)]
        if len(ys) >= 5 and max(ys) >= 2000:
            years = ys
            break
    if not years:
        raise ValueError("annual year header not found")

    g_line = _find_line(lines, "dépôts en gourdes") or _find_line(lines, "depots en gourdes")
    d_line = _find_line(lines, "dépôts en dollars") or _find_line(lines, "depots en dollars")
    if not g_line or not d_line:
        raise ValueError("deposit lines not found in annual PDF")

    gourdes = _numbers_after_label(g_line)
    dollars = _numbers_after_label(d_line)
    if len(gourdes) != len(years) or len(dollars) != len(years):
        # trim to min length
        n = min(len(years), len(gourdes), len(dollars))
        years, gourdes, dollars = years[:n], gourdes[:n], dollars[:n]

    out: dict[str, tuple[float, float]] = {}
    for y, g, d in zip(years, gourdes, dollars):
        if g is None or d is None:
            continue
        fcd, td = d, g + d
        if td <= 0:
            continue
        out[f"{y}-12"] = (fcd, td)
    return out


def _parse_monthly(content: bytes) -> dict[str, tuple[float, float]]:
    """period YYYY-MM -> (fcd, td)."""
    with pdfplumber.open(BytesIO(content)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    lines = text.splitlines()

    months: list[str] = []
    for line in lines:
        found = re.findall(r"\b([A-Za-z]{3})-(\d{2})\b", line)
        if len(found) >= 4:
            for mon, yy in found:
                mnum = _MONTHS.get(mon.lower()[:3])
                if not mnum:
                    continue
                year = 2000 + int(yy) if int(yy) < 70 else 1900 + int(yy)
                months.append(f"{year}-{mnum:02d}")
            break
    if not months:
        raise ValueError("monthly header not found")

    g_line = _find_line(lines, "dépôts en gourdes") or _find_line(lines, "depots en gourdes")
    d_line = _find_line(lines, "dépôts en dollars") or _find_line(lines, "depots en dollars")
    if not g_line or not d_line:
        raise ValueError("deposit lines not found in monthly PDF")

    gourdes = _numbers_after_label(g_line)
    dollars = _numbers_after_label(d_line)
    n = min(len(months), len(gourdes), len(dollars))
    out: dict[str, tuple[float, float]] = {}
    for i in range(n):
        g, d = gourdes[i], dollars[i]
        if g is None or d is None:
            continue
        td = g + d
        if td <= 0:
            continue
        out[months[i]] = (d, td)
    return out


def _build_frame(country_code: str, series: dict[str, tuple[float, float]]):
    import pandas as pd

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period in sorted(series):
        fcd, td = series[period]
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
    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def render(target: dict):
    country_code = target["country_code"]
    merged: dict[str, tuple[float, float]] = {}

    try:
        annual = _download(_ANNUAL_URL)
        part = _parse_annual(annual)
        merged.update(part)
        logger.info(
            "[%s] annual Table 20R: %d years %s~%s",
            country_code, len(part),
            min(part) if part else "-", max(part) if part else "-",
        )
    except Exception as e:
        logger.exception("[%s] annual PDF failed: %s", country_code, e)

    try:
        monthly = _download(_MONTHLY_URL)
        part = _parse_monthly(monthly)
        # Monthly data overrides the year-end annual value (may reflect more recent provisional figures)
        merged.update(part)
        logger.info(
            "[%s] monthly Table 20R: %d months %s~%s",
            country_code, len(part),
            min(part) if part else "-", max(part) if part else "-",
        )
    except Exception as e:
        logger.exception("[%s] monthly PDF failed: %s", country_code, e)

    if not merged:
        return _empty()
    df = _build_frame(country_code, merged)
    logger.info(
        "[%s] merged %d rows (%s~%s)",
        country_code, len(df),
        df["period"].min() if not df.empty else "-",
        df["period"].max() if not df.empty else "-",
    )
    return df
