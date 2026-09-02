"""Kazakhstan: NBRK Depository Organizations Deposits (by currency).

페이지:
  https://nationalbank.kz/en/depositoryorganizationsdeposits/depozity-v-depozitnyh-organizaciyah-
엑셀:
  https://nationalbank.kz/en/depositoryorganizationsdeposits/depozity-v-depozitnyh-organizaciyah-/excel

시트: 가로 시계열 (mln of tenge / end of period)
  row  'Deposits - total'  → TD
  row  'In FC:'            → FCD
헤더  'MM.YY' (예: 06.26 → 2026-06)

FCD_TD_RATIO = FCD/TD*100
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_PAGE = (
    "https://nationalbank.kz/en/depositoryorganizationsdeposits/"
    "depozity-v-depozitnyh-organizaciyah-"
)
_XLS_URL = _PAGE.rstrip("/") + "/excel"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("KAZ는 render()로 excel 엔드포인트를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().replace("\xa0", " ").replace(" ", "").replace(",", "")
        if t in {"", "-", "–", "—"}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _periods(df: pd.DataFrame) -> dict[int, str]:
    periods: dict[int, str] = {}
    for i in range(min(8, len(df))):
        hits: dict[int, str] = {}
        for j in range(1, df.shape[1]):
            v = df.iat[i, j]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            if hasattr(v, "year") and hasattr(v, "month"):
                hits[j] = f"{int(v.year)}-{int(v.month):02d}"
                continue
            if isinstance(v, str):
                m = re.search(r"(\d{1,2})\.(\d{2})", v.strip())
                if m:
                    mon, yy = int(m.group(1)), int(m.group(2))
                    if 1 <= mon <= 12:
                        year = 2000 + yy if yy < 70 else 1900 + yy
                        hits[j] = f"{year}-{mon:02d}"
        if len(hits) >= 3:
            return hits
    return periods


def _find_row(df: pd.DataFrame, *needles: str) -> int | None:
    for i in range(len(df)):
        lab = df.iat[i, 0]
        if not isinstance(lab, str):
            continue
        low = lab.strip().lower()
        if all(n.lower() in low for n in needles):
            return i
    return None


def _parse(content: bytes, country_code: str) -> pd.DataFrame:
    xl = pd.ExcelFile(BytesIO(content))
    df = xl.parse(xl.sheet_names[0], header=None)
    periods = _periods(df)
    if not periods:
        logger.error("[%s] no period header", country_code)
        return _empty()

    td_row = _find_row(df, "deposits", "total") or _find_row(df, "депозиты", "всего")
    fcd_row = _find_row(df, "in fc") or _find_row(df, "in foreign") or _find_row(df, "в ин")
    if td_row is None or fcd_row is None:
        logger.error("[%s] rows td=%s fcd=%s", country_code, td_row, fcd_row)
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for j, period in periods.items():
        fcd = _num(df.iat[fcd_row, j])
        td = _num(df.iat[td_row, j])
        if fcd is None or td is None or td <= 0:
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
        resp = requests.get(_XLS_URL, headers=_HEADERS, timeout=120, verify=False)
        resp.raise_for_status()
        if not resp.content.startswith(b"PK"):
            raise RuntimeError(f"not xlsx: {resp.content[:40]!r}")
        return _parse(resp.content, country_code)
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
