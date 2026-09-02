"""Lithuania: Bank of Lithuania — deposits by currency (residents, non-MFIs).

UI: https://www.lb.lt/en/deposits-by-currency
  (Filters → period from 04/2004; HTML is often Cloudflare-blocked for bots)

Machine export (no key, works with browser UA + Referer):
  https://www.lb.lt/en/m_statistics/t-currency-breakdown-of-deposits/?export=csv
  Full history ~2004-04 … latest month (semicolon CSV).

  ?export=xlsx only returns a short rolling window (~13 months) — do not use alone.

Series (code suffix after …1.10.200.):
  000 + .E.SR  Total outstanding amounts (thousands of EUR; power=1000)
  100 + .R.SR  Litas share %  (domestic pre-euro)
  200 + .R.SR  Euro share %   (domestic from 2015-01 euro adoption)
  USD/CHF/GBP/JPY/3B1 + .R.SR  foreign currency shares %

  TD  = total / 1000  → EUR million
  FCD = TD × (100 − domestic_share) / 100
  domestic_share = LTL% if period < 2015-01 else EUR%
  (equivalently 100 − sum of non-domestic currency ratios)
"""

from __future__ import annotations

import re
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.utils.fcd_series import empty_frame, long_rows
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PAGE = "https://www.lb.lt/en/deposits-by-currency"
_CSV = (
    "https://www.lb.lt/en/m_statistics/t-currency-breakdown-of-deposits/?export=csv"
)
_XLSX = (
    "https://www.lb.lt/en/m_statistics/t-currency-breakdown-of-deposits/?export=xlsx"
)

# Total deposits of residents non-MFIs, outstanding amounts
_CODE_TD = "BPS.M.L20.A.1.10.200.000.LT.N.PAB__.E.SR"
_CODE_LTL_R = "BPS.M.L20.A.1.10.200.100.LT.N.PAB__.R.SR"
_CODE_EUR_R = "BPS.M.L20.A.1.10.200.200.LT.N.PAB__.R.SR"
# foreign ratios (fallback if domestic share missing)
_CODE_FX_R = (
    "BPS.M.L20.A.1.10.200.USD.LT.N.PAB__.R.SR",
    "BPS.M.L20.A.1.10.200.CHF.LT.N.PAB__.R.SR",
    "BPS.M.L20.A.1.10.200.GBP.LT.N.PAB__.R.SR",
    "BPS.M.L20.A.1.10.200.JPY.LT.N.PAB__.R.SR",
    "BPS.M.L20.A.1.10.200.3B1.LT.N.PAB__.R.SR",
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}

# Lithuania adopted the euro 2015-01-01
_EURO_START = "2015-01"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Parse BoL CSV or xlsx export bytes."""
    if content[:2] == b"PK":
        return _parse_xlsx(content, country_code)
    return _parse_csv(content, country_code)


def _empty() -> pd.DataFrame:
    return empty_frame()


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=180, verify=False)
        if r.status_code != 200 or len(r.content) < 500:
            return None
        return r.content
    except Exception as e:
        logger.debug("[LTU] download %s: %s", url[-40:], e)
        return None


def _parse_csv(content: bytes, country_code: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(BytesIO(content), sep=";", quotechar='"')
    except Exception as e:
        logger.warning("[LTU] CSV parse failed: %s", e)
        return _empty()

    need = {"code", "date", "value"}
    if not need.issubset(set(df.columns)):
        logger.warning("[LTU] unexpected CSV columns: %s", list(df.columns))
        return _empty()

    df = df.copy()
    df["date"] = df["date"].astype(str).str.strip()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    if "power" in df.columns:
        df["power"] = pd.to_numeric(df["power"], errors="coerce").fillna(1)
    else:
        df["power"] = 1.0

    def series(code: str) -> pd.Series:
        s = df.loc[df["code"] == code, ["date", "value", "power"]].dropna(subset=["value"])
        if s.empty:
            return pd.Series(dtype=float)
        # thousands of EUR → EUR million when power==1000
        amt = s["value"] / 1000.0
        # if power is not 1000, still treat value as thousands for this export
        out = pd.Series(amt.values, index=s["date"].values)
        return out.groupby(level=0).last()

    def ratio_series(code: str) -> pd.Series:
        s = df.loc[df["code"] == code, ["date", "value"]].dropna(subset=["value"])
        if s.empty:
            return pd.Series(dtype=float)
        out = pd.Series(s["value"].values, index=s["date"].values)
        return out.groupby(level=0).last()

    td = series(_CODE_TD)
    if td.empty:
        # fallback: any …1.10.200.000…E.SR
        m = df["code"].astype(str).str.contains(
            r"\.1\.10\.200\.000\..*\.E\.SR$", regex=True
        )
        if m.any():
            code = df.loc[m, "code"].iloc[0]
            td = series(code)
            logger.info("[LTU] TD code fallback %s", code)
    if td.empty:
        logger.error("[LTU] total deposits series not found in CSV")
        return _empty()

    ltl = ratio_series(_CODE_LTL_R)
    eur = ratio_series(_CODE_EUR_R)
    fx_parts = [ratio_series(c) for c in _CODE_FX_R]
    fx_sum = None
    for p in fx_parts:
        if p.empty:
            continue
        fx_sum = p if fx_sum is None else fx_sum.add(p, fill_value=0.0)

    obs: list[tuple[str, float, float]] = []
    for period, td_v in td.items():
        p = str(period)[:7]  # YYYY-MM
        if not re.fullmatch(r"\d{4}-\d{2}", p):
            continue
        try:
            td_f = float(td_v)
        except (TypeError, ValueError):
            continue
        if td_f <= 0:
            continue

        # domestic share: LTL before euro, EUR thereafter
        dom = None
        if p < _EURO_START and p in ltl.index and pd.notna(ltl.loc[p]):
            dom = float(ltl.loc[p])
        elif p >= _EURO_START and p in eur.index and pd.notna(eur.loc[p]):
            dom = float(eur.loc[p])
        elif p in eur.index and pd.notna(eur.loc[p]) and float(eur.loc[p]) > 50:
            # post-euro-style EUR dominance even if date parse odd
            dom = float(eur.loc[p])
        elif p in ltl.index and pd.notna(ltl.loc[p]) and float(ltl.loc[p]) > 50:
            dom = float(ltl.loc[p])

        if dom is not None and 0 <= dom <= 100:
            fcd_f = td_f * (100.0 - dom) / 100.0
        elif fx_sum is not None and p in fx_sum.index and pd.notna(fx_sum.loc[p]):
            fcd_f = td_f * float(fx_sum.loc[p]) / 100.0
        else:
            continue

        if fcd_f < 0 or fcd_f > td_f * 1.02:
            continue
        # Lithuania total deposits EUR mn: thousands → tens of thousands
        if td_f < 100 or td_f > 5_000_000:
            continue
        ratio = fcd_f / td_f
        if ratio > 0.95:  # sanity
            continue
        obs.append((p, fcd_f, td_f))

    if not obs:
        return _empty()
    out = long_rows(country_code, obs)
    logger.info(
        "[LTU] CSV → %d rows (%s~%s)",
        len(out),
        out["period"].min(),
        out["period"].max(),
    )
    return out


def _parse_xlsx(content: bytes, country_code: str) -> pd.DataFrame:
    """Short rolling-window xlsx (fallback only)."""
    xl = pd.ExcelFile(BytesIO(content))
    df = xl.parse(xl.sheet_names[0], header=None)
    obs: list[tuple[str, float, float]] = []
    for i in range(len(df)):
        lab = df.iat[i, 0]
        if lab is None or (isinstance(lab, float) and pd.isna(lab)):
            continue
        s = str(lab).strip()
        m = re.match(r"^(\d{1,2})/(\d{4})$", s)
        if not m:
            continue
        mon, year = int(m.group(1)), int(m.group(2))
        if not (1 <= mon <= 12):
            continue
        period = f"{year}-{mon:02d}"
        try:
            td = float(df.iat[i, 1])
        except (TypeError, ValueError):
            continue
        eur_share = None
        try:
            eur_share = float(df.iat[i, 3])
        except (TypeError, ValueError):
            pass
        if td <= 0:
            continue
        if eur_share is not None and 0 <= eur_share <= 100:
            # xlsx window is post-euro only in practice
            if period < _EURO_START:
                # col2 may be LTL share historically — try col2
                try:
                    ltl_share = float(df.iat[i, 2])
                    if 0 <= ltl_share <= 100:
                        fcd = td * (100.0 - ltl_share) / 100.0
                    else:
                        fcd = td * (100.0 - eur_share) / 100.0
                except (TypeError, ValueError):
                    fcd = td * (100.0 - eur_share) / 100.0
            else:
                fcd = td * (100.0 - eur_share) / 100.0
        else:
            continue
        if fcd < 0:
            continue
        obs.append((period, fcd, td))
    if not obs:
        return _empty()
    out = long_rows(country_code, obs)
    logger.info(
        "[LTU] XLSX → %d rows (%s~%s)",
        len(out),
        out["period"].min(),
        out["period"].max(),
    )
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        raw = _download(_CSV)
        if raw and (b"code" in raw[:200] or b"BPS." in raw[:500]):
            df = _parse_csv(raw, country_code)
            if df is not None and not df.empty:
                return df
        logger.warning("[LTU] CSV export failed/empty — trying short xlsx window")
        raw_x = _download(_XLSX)
        if raw_x and raw_x[:2] == b"PK":
            return _parse_xlsx(raw_x, country_code)
        logger.error("[%s] no BoL export available", country_code)
        return _empty()
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
