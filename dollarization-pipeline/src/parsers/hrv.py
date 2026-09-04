"""Croatia: HNB OMFI deposit tables (archive pre-euro + current post-euro).

Background
----------
Croatia adopted the euro on 2023-01-01. To track "foreign-currency deposits"
before that date, we need to use the legacy D8 statistics. The historical data
in the current D6 series (2010~) reclassifies euro and euro-pegged kuna deposits
as domestic currency, which understates pre-adoption FCD.

Sources
-------
1) Archive ESA 2010 until 31/12/2022
   https://www.hnb.hr/en/statistics/statistical-data/archive/esa-2010-until-31-12-2022
   - D8 Foreign currency deposits with OMFIs  (FCD)
   - D7 Kuna deposits with OMFIs              (domestic-currency savings and time deposits)
   - D6 Demand deposits with OMFIs            (demand deposits)
   File UUIDs (HNB documents/20182/...):
     D8: a8cc09f5-ef59-4f6f-90a3-be6e26b2b05d  (e-d8.xlsx)
     D7: 10346d21-39f2-4b11-9867-68d607984dc9  (e-d7.xlsx)
     D6: 997bb6f9-4585-4888-a68e-02deb0d0e72f  (e-d6.xlsx)

2) Current Aggregated balance sheet of OMFIs
   https://www.hnb.hr/en/statistics/statistical-data/financial-sector/other-monetary-financial-institutions/aggregated-balance-sheet-of-omfis
   - D6 Total deposits by sectors and currency (e-d6.xlsx)
     UUID: 3ab0d8ca-377d-b0e5-a185-78e424fedb2e

Definitions (EUR sheet, million EUR, end-of-period)
----------------------------------------------------
Archive period (~2022-12):
  FCD = D8 'Total (1+2)'   # foreign-currency savings + time deposits (all resident sectors)
  TD  = D6 Total + D7 Total + D8 Total
        # demand deposits + kuna savings/time deposits + foreign-currency savings/time deposits

Current period (2023-01~, post-euro-adoption):
  FCD = D6 'B Total'   # IN FOREIGN CURRENCY (foreign currency excluding euro)
  TD  = D6 'TOTAL (A+B)'

Merging: periods <= 2022-12 use the archive; periods after that use current D6.
The fixed exchange rate 1 EUR = 7.53450 HRK is already applied in the HNB EUR
sheet, so no separate conversion is needed.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://www.hnb.hr/",
}

_DOC = "https://www.hnb.hr/documents/20182"
# archive (until 2022-12)
_ARCH_D8 = f"{_DOC}/a8cc09f5-ef59-4f6f-90a3-be6e26b2b05d"
_ARCH_D7 = f"{_DOC}/10346d21-39f2-4b11-9867-68d607984dc9"
_ARCH_D6 = f"{_DOC}/997bb6f9-4585-4888-a68e-02deb0d0e72f"
# current
_CUR_D6 = f"{_DOC}/3ab0d8ca-377d-b0e5-a185-78e424fedb2e"

_EURO_CUTOFF = "2022-12"  # inclusive archive


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("HRV merges several HNB tables via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=90)
    resp.raise_for_status()
    content = resp.content
    if not content.startswith(b"PK") and not content.startswith(b"\xd0\xcf\x11\xe0"):
        raise RuntimeError(f"not excel: {url} head={content[:40]!r}")
    return content


def _to_period(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "year") and hasattr(value, "month"):
        try:
            return f"{int(value.year)}-{int(value.month):02d}"
        except (TypeError, ValueError):
            return None
    return None


def _num(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        text = value.strip()
        if text in {"-", "....", "…", "", "n.a.", "na"}:
            return None
        text = text.replace(",", "")
        try:
            return float(text)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_date_row(df: pd.DataFrame) -> int | None:
    for i in range(min(12, len(df))):
        hits = 0
        for j in range(2, min(df.shape[1], 20)):
            if _to_period(df.iat[i, j]):
                hits += 1
        if hits >= 3:
            return i
    return None


def _find_total_row(df: pd.DataFrame, *needles: str) -> int | None:
    """Find a row in the label column (col1) containing all needles, or a Total row."""
    wanted = [n.lower() for n in needles]
    # prefer explicit total markers
    for i in range(len(df)):
        v = df.iat[i, 1] if df.shape[1] > 1 else df.iat[i, 0]
        if not isinstance(v, str):
            continue
        s = re.sub(r"\s+", " ", v).strip().lower()
        if wanted:
            if all(w in s for w in wanted):
                return i
        elif s.startswith("total") or s.startswith("a\ttotal") or "total (1" in s:
            return i
    if not needles:
        for i in range(len(df)):
            v = df.iat[i, 1] if df.shape[1] > 1 else None
            if isinstance(v, str) and "total" in v.lower():
                return i
    return None


def _series_from_total_row(content: bytes, sheet_prefer: str = "EUR") -> dict[str, float]:
    """Extract the Total row time series from the Excel file as period->value (EUR sheet preferred)."""
    xl = pd.ExcelFile(BytesIO(content))
    sheet = sheet_prefer if sheet_prefer in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)
    date_row = _find_date_row(df)
    if date_row is None:
        raise ValueError("date row not found")

    # Total row: 'Total (1+2)' or 'Total (1+2+...)' or 'B Total', etc.
    total_row = None
    for i in range(len(df)):
        v = df.iat[i, 1] if df.shape[1] > 1 else None
        if not isinstance(v, str):
            continue
        s = re.sub(r"[\t\s]+", " ", v).strip().lower()
        # archive style
        if s.startswith("total (") or s == "total":
            total_row = i
            break
    if total_row is None:
        # current D6: 'B Total' / 'TOTAL (A+B)' handled by caller via needles
        raise ValueError(f"total row not found in {sheet}")

    out: dict[str, float] = {}
    for j in range(2, df.shape[1]):
        period = _to_period(df.iat[date_row, j])
        if period is None:
            continue
        val = _num(df.iat[total_row, j])
        if val is None:
            continue
        out[period] = val
    return out


def _series_by_label(content: bytes, label_pred, sheet_prefer: str = "EUR") -> dict[str, float]:
    """Time series of the first row for which label_pred(str)->bool is True."""
    xl = pd.ExcelFile(BytesIO(content))
    sheet = sheet_prefer if sheet_prefer in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)
    date_row = _find_date_row(df)
    if date_row is None:
        raise ValueError("date row not found")
    row = None
    for i in range(len(df)):
        v = df.iat[i, 1] if df.shape[1] > 1 else None
        if isinstance(v, str) and label_pred(re.sub(r"[\t\s]+", " ", v).strip()):
            row = i
            break
    if row is None:
        raise ValueError("label row not found")
    out: dict[str, float] = {}
    for j in range(2, df.shape[1]):
        period = _to_period(df.iat[date_row, j])
        if period is None:
            continue
        val = _num(df.iat[row, j])
        if val is None:
            continue
        out[period] = val
    return out


def _build_frame(country_code: str, series: dict[str, tuple[float, float]]) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period in sorted(series):
        fcd, td = series[period]
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
    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    merged: dict[str, tuple[float, float]] = {}

    # --- archive ---
    try:
        d8 = _download(_ARCH_D8)
        d7 = _download(_ARCH_D7)
        d6 = _download(_ARCH_D6)
        fcd_arch = _series_from_total_row(d8)
        kuna = _series_from_total_row(d7)
        demand = _series_from_total_row(d6)
        periods = sorted(set(fcd_arch) | set(kuna) | set(demand))
        n = 0
        for p in periods:
            if p > _EURO_CUTOFF:
                continue
            fcd = fcd_arch.get(p)
            td_parts = [demand.get(p), kuna.get(p), fcd_arch.get(p)]
            if fcd is None or any(x is None for x in td_parts):
                continue
            td = sum(td_parts)  # type: ignore[arg-type]
            merged[p] = (fcd, td)
            n += 1
        logger.info(
            "[%s] archive D6+D7+D8: %d months (%s~%s)",
            country_code, n,
            min(merged) if merged else "-",
            max((p for p in merged if p <= _EURO_CUTOFF), default="-"),
        )
    except Exception as e:
        logger.exception("[%s] archive tables failed: %s", country_code, e)

    # --- current D6 (post-euro months) ---
    try:
        cur = _download(_CUR_D6)
        fcd_cur = _series_by_label(
            cur,
            lambda s: s.upper().startswith("B") and "TOTAL" in s.upper(),
        )
        td_cur = _series_by_label(
            cur,
            lambda s: s.upper().startswith("TOTAL") and "A+B" in s.upper().replace(" ", ""),
        )
        # fallback looser match for TOTAL
        if not td_cur:
            td_cur = _series_by_label(
                cur,
                lambda s: "TOTAL" in s.upper() and "A" in s.upper() and "B" in s.upper(),
            )
        n = 0
        for p, fcd in fcd_cur.items():
            if p <= _EURO_CUTOFF:
                continue  # keep archive FCD (true pre-euro FX)
            td = td_cur.get(p)
            if td is None or td <= 0:
                continue
            merged[p] = (fcd, td)
            n += 1
        logger.info(
            "[%s] current D6 (post-%s): %d months",
            country_code, _EURO_CUTOFF, n,
        )
    except Exception as e:
        logger.exception("[%s] current D6 failed: %s", country_code, e)

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
