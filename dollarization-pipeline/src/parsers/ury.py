"""Uruguay: BCU SSF Depositos.xlsx — full Total Sistema Bancario series.

Primary (auto-updating workbook):
  https://www.bcu.gub.uy/Servicios-Financieros-SSF/Series%20IF/Depositos.xlsx
  Sheet: Total Sist. Banc.
  FCD = ME (col 8), TD = Total (col 9), millones de pesos
  Monthly from ~1998 to latest published month.

Re-running render() re-downloads the workbook.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from src.utils.fcd_series import empty_frame, http_get, long_rows, now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_URL = "https://www.bcu.gub.uy/Servicios-Financieros-SSF/Series%20IF/Depositos.xlsx"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    return _from_xlsx(content, country_code)


def _from_xlsx(content: bytes, country_code: str) -> pd.DataFrame:
    df = pd.read_excel(BytesIO(content), sheet_name="Total Sist. Banc.", header=None)
    obs = []
    for i in range(9, len(df)):
        d = df.iat[i, 0]
        if not (hasattr(d, "year") and hasattr(d, "month")):
            continue
        try:
            fcd = float(df.iat[i, 8])
            td = float(df.iat[i, 9])
        except (TypeError, ValueError):
            continue
        if td <= 0 or fcd < 0:
            continue
        obs.append((f"{int(d.year)}-{int(d.month):02d}", fcd, td))
    return long_rows(country_code, obs)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        resp = http_get(_URL, timeout=90)
        if resp.content[:2] != b"PK":
            logger.error("[%s] not xlsx", country_code)
            return empty_frame()
        out = _from_xlsx(resp.content, country_code)
        if len(out):
            logger.info(
                "[%s] %d rows (%s~%s)",
                country_code,
                len(out),
                out["period"].min(),
                out["period"].max(),
            )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return empty_frame()
