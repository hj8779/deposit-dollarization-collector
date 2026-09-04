"""Hungary: MNB monstatpubl — consolidated MFI liabilities (Table 3.2).

Source Excel:
  https://statisztika.mnb.hu/timeseries/0708-monstatpubl-enxls.xls
Detail page:
  https://statisztika.mnb.hu/timeseries/data-10957
  "Balance sheets of monetary financial institutions and monetary aggregates"

Of the several tables in the file, we use **Table 3.2** (Consolidated balance
sheet of MFIs S.121+S.122+S.123, Liabilities, end of period).
- Resident deposits with inter-MFI deposits netted out
- Better suited to customer-deposit dollarization than the standalone Other
  MFIs table (2.a.2)

Sheet header structure (HUF billions):
  Deposits of residents (col2 TOTAL)
    Central government: HUF (col4), Foreign currency (col5)
    Other residents:
      Overnight: HUF (col8), Foreign currency (col9)
      Agreed maturity: HUF (col11), Foreign currency (col12)

FCD = CG FC + Overnight FC + Agreed-maturity FC  (col5+col9+col12)
TD  = Deposits of residents total                 (col2)
FCD_TD_RATIO = FCD/TD*100

Time series: 1998-01 ~ latest month in the file (observed 2026-06), end-of-month balances.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_XLS_URL = "https://statisztika.mnb.hu/timeseries/0708-monstatpubl-enxls.xls"
_PAGE = "https://statisztika.mnb.hu/timeseries/data-10957"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}

_SHEET = "Table 3.2"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    empty = pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )
    try:
        xl = pd.ExcelFile(BytesIO(content), engine="xlrd")
    except Exception:
        try:
            xl = pd.ExcelFile(BytesIO(content))
        except Exception as e:
            logger.error("[%s] Failed to open xls: %s", country_code, e)
            return empty

    sheet = _SHEET if _SHEET in xl.sheet_names else None
    if sheet is None:
        # Variants: 'Table 3.2' / '3.2', etc.
        for name in xl.sheet_names:
            if "3.2" in name.replace(" ", "") or name.strip().endswith("3.2"):
                sheet = name
                break
    if sheet is None:
        logger.error("[%s] Table 3.2 sheet not found: %s", country_code, xl.sheet_names[:10])
        return empty

    df = xl.parse(sheet, header=None)
    cols = _locate_columns(df)
    if cols is None:
        logger.error("[%s] Failed to map HUF/Foreign currency columns", country_code)
        return empty
    td_col, fcd_cols = cols

    rows = []
    for i in range(len(df)):
        period = _to_period(df.iat[i, 0])
        if period is None:
            continue
        try:
            td = float(df.iat[i, td_col])
            fcd = 0.0
            for c in fcd_cols:
                v = df.iat[i, c]
                if v is None or (isinstance(v, float) and pd.isna(v)) or v == "-":
                    raise ValueError("missing FC")
                fcd += float(v)
        except (TypeError, ValueError):
            continue
        if pd.isna(td) or td <= 0:
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
        return empty
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["period", "indicator"], keep="last")
    return out.sort_values(["period", "indicator"]).reset_index(drop=True)


def _to_period(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "year") and hasattr(value, "month"):
        try:
            return f"{int(value.year)}-{int(value.month):02d}"
        except (TypeError, ValueError):
            return None
    return None


def _locate_columns(df: pd.DataFrame) -> tuple[int, list[int]] | None:
    """Deposits of residents total column + FC component columns (CG FC, overnight FC, maturity FC).

    Fixed-index fallback: td=2, fcd=[5,9,12] (current MNB layout).
    """
    # Find the column with the 'Deposits of residents' label (usually the header above col2)
    # Data column: col2 = total deposits of residents (rows with a date carry numbers)
    # FC columns: 'Foreign currency' in the header row, within the Deposits of residents block

    # Header rows
    fc_cols: list[int] = []
    for i in range(min(20, len(df))):
        for j in range(df.shape[1]):
            v = df.iat[i, j]
            if isinstance(v, str) and v.strip().lower() == "foreign currency":
                fc_cols.append(j)

    # Deduplicate while preserving order
    seen = set()
    fc_unique = []
    for c in fc_cols:
        if c not in seen:
            seen.add(c)
            fc_unique.append(c)

    # Only FC columns within the Deposits of residents block: usually the first 3 (CG, overnight, maturity)
    # FC columns on the debt securities side (e.g. c19) are not deposits — prefer the smaller col indices
    deposit_fc = [c for c in fc_unique if c <= 14]
    if len(deposit_fc) >= 3:
        deposit_fc = deposit_fc[:3]
    elif len(deposit_fc) < 1:
        deposit_fc = [5, 9, 12]  # fallback

    # TD column: first numeric column after date that matches deposits total
    # Standard layout col2
    td_col = 2
    # verify header
    for i in range(min(15, len(df))):
        v = df.iat[i, 2] if df.shape[1] > 2 else None
        if isinstance(v, str) and "deposit" in v.lower() and "resident" in v.lower():
            td_col = 2
            break
        v1 = df.iat[i, 1] if df.shape[1] > 1 else None
        if isinstance(v1, str) and "deposit" in v1.lower() and "resident" in v1.lower():
            # value still under col2 in data rows
            td_col = 2
            break

    return td_col, deposit_fc


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    logger.info("[%s] Downloading monstatpubl: %s", country_code, _XLS_URL)
    resp = requests.get(_XLS_URL, headers=_HEADERS, timeout=120)
    resp.raise_for_status()
    content = resp.content
    if not content.startswith(b"\xd0\xcf\x11\xe0") and not content.startswith(b"PK"):
        logger.error("[%s] Response is not an Excel file, len=%d", country_code, len(content))
        return pd.DataFrame(
            columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
        )
    df = parse(content, country_code)
    if not df.empty:
        logger.info(
            "[%s] %d rows (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    return df
