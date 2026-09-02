"""Moldova (MDA): BNM Monetary Survey (DPMC11) Excel export.

Authoritative series: National Bank of Moldova Reports Generator
  https://www.bnm.md/bdi/pages/reports/dpmc/DPMC11.xhtml?id=0&lang=en

The page is a PrimeFaces/JSF app (javax.faces.ViewState). Period config +
export requires a browser session — not reliably automatable. Workflow:

  1. Open DPMC11, set report period (e.g. Dec 2000 … latest month)
  2. Export statistical series → report.xlsx (Unit: MDL million)
  3. Either:
     - place file at $MDA_REPORT_XLSX / ./data/mda_report.xlsx, or
     - `python -c` parse+upsert, or dashboard half-manual entry

Sheet "BNM" layout (Monetary survey):
  FCD = "Deposits in foreign currency"  (banking system / M3 component)
  TD  = FCD + sight deposits domestic + term deposits domestic
      = M3 − Currency outside the banking system (M0)

Half-manual flag: web/src/lib/manualUpdateCountries.ts → MDA.
"""

from __future__ import annotations

import os
import re
from io import BytesIO
from pathlib import Path

import pandas as pd

from src.utils.fcd_series import empty_frame, long_rows
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_DEFAULT_PATHS = (
    os.environ.get("MDA_REPORT_XLSX", "").strip(),
    str(Path.home() / "Downloads" / "report.xlsx"),
    str(Path(__file__).resolve().parents[2] / "data" / "mda_report.xlsx"),
    str(Path(__file__).resolve().parents[2] / "runs" / "mda_report.xlsx"),
)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Parse a DPMC11 / Monetary survey Excel export (bytes)."""
    return _parse_workbook(content, country_code)


def _empty() -> pd.DataFrame:
    return empty_frame()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip().lower()


def _parse_month_header(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "year") and hasattr(v, "month"):
        return f"{int(v.year)}-{int(v.month):02d}"
    s = str(v).strip()
    m = re.match(r"([A-Za-z]+)\s+(\d{4})", s)
    if not m:
        return None
    mon = _MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    return f"{int(m.group(2))}-{mon:02d}"


def _label_at(df: pd.DataFrame, i: int) -> str:
    """Prefer the long indicator text (usually col 2), not N/(a)/codes."""
    candidates: list[str] = []
    for c in range(min(4, df.shape[1])):
        if pd.notna(df.iloc[i, c]):
            lab = _norm(str(df.iloc[i, c]))
            if lab and lab not in ("n", "a", "b", "indicator") and not re.fullmatch(
                r"[\d().ivx*]+", lab
            ):
                candidates.append(lab)
    if not candidates:
        return ""
    return max(candidates, key=len)


def _find_row(
    df: pd.DataFrame,
    *needles: str,
    exclude: tuple[str, ...] = (),
) -> int | None:
    """First row whose indicator label contains all needles and none of exclude."""
    phrase = " ".join(needles)
    for i in range(len(df)):
        lab = _label_at(df, i)
        if not lab:
            continue
        if any(x in lab for x in exclude):
            continue
        if all(n in lab for n in needles):
            # Prefer the shortest matching label (totals over sub-components)
            # → collect all and pick best
            pass
            return i
    # second pass: if first hit was too greedy, try endswith phrase
    for i in range(len(df)):
        lab = _label_at(df, i)
        if not lab or any(x in lab for x in exclude):
            continue
        if lab == phrase or lab.endswith(phrase):
            return i
    return None


def _parse_workbook(content: bytes | None, country_code: str, path: str | None = None) -> pd.DataFrame:
    try:
        if content is not None:
            df = pd.read_excel(BytesIO(content), header=None, engine="openpyxl")
        elif path:
            df = pd.read_excel(path, header=None, engine="openpyxl")
        else:
            return _empty()
    except Exception as e:
        logger.warning("[MDA] excel read failed: %s", e)
        return _empty()

    # Header row with month labels (e.g. "July 2026")
    header_row = None
    data_col0 = 3
    for i in range(min(10, len(df))):
        for c in range(2, min(8, df.shape[1])):
            if _parse_month_header(df.iloc[i, c]):
                header_row = i
                data_col0 = c
                break
        if header_row is not None:
            break
    if header_row is None:
        logger.warning("[MDA] no month header row found")
        return _empty()

    fcd_row = _find_row(
        df,
        "deposits in foreign currency",
        exclude=("sight", "term"),
    )
    sight_row = _find_row(df, "sight deposits in domestic currency")
    term_row = _find_row(df, "term deposits in domestic currency")
    m3_row = _find_row(df, "money supply (m3)")
    m0_row = _find_row(df, "currency outside the banking system")

    if fcd_row is None:
        logger.warning("[MDA] FCD row not found")
        return _empty()

    periods = [_parse_month_header(v) for v in df.iloc[header_row, data_col0:]]
    fcd = pd.to_numeric(df.iloc[fcd_row, data_col0:], errors="coerce")

    td = None
    if sight_row is not None and term_row is not None:
        sight = pd.to_numeric(df.iloc[sight_row, data_col0:], errors="coerce")
        term = pd.to_numeric(df.iloc[term_row, data_col0:], errors="coerce")
        td = fcd + sight + term
    elif m3_row is not None and m0_row is not None:
        m3 = pd.to_numeric(df.iloc[m3_row, data_col0:], errors="coerce")
        m0 = pd.to_numeric(df.iloc[m0_row, data_col0:], errors="coerce")
        td = m3 - m0
    else:
        logger.warning("[MDA] cannot build TD (need domestic deposit rows or M3/M0)")
        return _empty()

    obs: list[tuple[str, float, float]] = []
    for p, f, t in zip(periods, fcd, td):
        if not p or pd.isna(f) or pd.isna(t):
            continue
        f_f, t_f = float(f), float(t)
        if t_f <= 0 or f_f < 0 or f_f > t_f * 1.05:
            continue
        # MDL million — banking deposits roughly 1e3–5e5 in recent decades
        if t_f < 100 or t_f > 5_000_000:
            continue
        ratio = f_f / t_f
        if ratio < 0.05 or ratio > 0.90:
            continue
        obs.append((p, f_f, t_f))

    if not obs:
        return _empty()

    # de-dupe periods (prefer later column = usually newer export order is reverse chrono)
    by_p: dict[str, tuple[float, float]] = {}
    for p, f, t in obs:
        by_p[p] = (f, t)
    rows = [(p, by_p[p][0], by_p[p][1]) for p in sorted(by_p)]
    out = long_rows(country_code, rows)
    logger.info(
        "[MDA] monetary survey → %d rows (%s~%s) fcd_row=%s",
        len(out),
        out["period"].min(),
        out["period"].max(),
        fcd_row,
    )
    return out


def render(target: dict) -> pd.DataFrame:
    """Load local DPMC11 export if present; otherwise empty (half-manual)."""
    country_code = target["country_code"]
    try:
        for p in _DEFAULT_PATHS:
            if not p:
                continue
            path = Path(p).expanduser()
            if path.is_file() and path.stat().st_size > 1000:
                logger.info("[MDA] reading local export %s", path)
                df = _parse_workbook(None, country_code, path=str(path))
                if df is not None and not df.empty:
                    return df
        logger.warning(
            "[MDA] no local DPMC11 export found. "
            "Download report.xlsx from %s "
            "and set MDA_REPORT_XLSX or place at ~/Downloads/report.xlsx "
            "(dashboard: half-manual for MDA).",
            "https://www.bnm.md/bdi/pages/reports/dpmc/DPMC11.xhtml?id=0&lang=en",
        )
        return _empty()
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
