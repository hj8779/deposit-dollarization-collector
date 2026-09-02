"""Austria: OeNB report 1.7.10 — deposits with Austrian MFIs by residence.

Source (interactive report with CSV export):
  https://www.oenb.at/isawebstat/stabfrage/createReport?lang=EN&report=1.7.10

Default HTML view only shows a short recent window. Full history (from ~1998)
is available by POSTing expanded year/month range to the same form, then
downloading CSV via downloadResult.

Definitions (Domestic / home reference area ≈ resident Austria block):
  FCD = Currency 'Foreign currencies combined' for
        Economic sector MFIs + Non-MFIs  (sum; no Total FX row)
  TD  = Currency 'Total', Economic sector 'Total'
  FCD_TD_RATIO = FCD/TD*100

Prefer monthly stocks; yearly stocks fill gaps only when no monthly exists
for that year-end (period YYYY-12 from year rows if needed — by default we
use monthly only for density).
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_REPORT = "1.7.10"
_PAGE = (
    f"https://www.oenb.at/isawebstat/stabfrage/createReport"
    f"?lang=EN&report={_REPORT}"
)
_CREATE = (
    f"https://www.oenb.at/isawebstat/stabfrage/createReport"
    f"?lang=EN&original=false&report={_REPORT}"
)
_CSV = (
    f"https://www.oenb.at/isawebstat/stabfrage/downloadResult"
    f"?lang=EN&exportTyp=CSV&report={_REPORT}"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/csv,*/*",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("AUT는 render()로 CSV 전체 시계열을 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _form_full_range() -> dict[str, str]:
    """Yearly 1998–2025 + monthly 1998-01–2026-12."""
    return {
        "zeitElementeList[0].checked": "true",
        "_zeitElementeList[0].checked": "on",
        "zeitElementeList[0].periodizitaet": "J",
        "zeitElementeList[0].vonJahrSelected": "1998",
        "zeitElementeList[0].bisJahrSelected": "2025",
        "zeitElementeList[1].checked": "true",
        "_zeitElementeList[1].checked": "on",
        "zeitElementeList[1].periodizitaet": "M",
        "zeitElementeList[1].vonJahrSelected": "1998",
        "zeitElementeList[1].vonMonatSelected": "1",
        "zeitElementeList[1].bisJahrSelected": "2026",
        "zeitElementeList[1].bisMonatSelected": "12",
    }


def _download_csv() -> pd.DataFrame:
    sess = requests.Session()
    sess.headers.update(_HEADERS)
    # session cookie
    r0 = sess.get(_PAGE, timeout=60)
    r0.raise_for_status()
    form = _form_full_range()
    # refresh report with full range (optional but keeps UI state consistent)
    try:
        sess.post(_CREATE, data=form, timeout=90)
    except Exception as e:
        logger.debug("[AUT] createReport: %s", e)
    r = sess.post(_CSV, data=form, timeout=120)
    r.raise_for_status()
    ct = (r.headers.get("content-type") or "").lower()
    if "csv" not in ct and not r.content[:20].lstrip().startswith(b"period"):
        raise RuntimeError(
            f"unexpected CSV response ct={ct!r} head={r.content[:80]!r}"
        )
    text = r.content.decode("utf-8", errors="replace")
    return pd.read_csv(StringIO(text))


def _build_long(df: pd.DataFrame, country_code: str) -> pd.DataFrame:
    """Domestic region → FCD/TD/RATIO monthly series."""
    if df is None or df.empty:
        return _empty()

    # normalize column names (BOM / spacing)
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    region_col = "Region / business partner"
    if region_col not in df.columns:
        raise RuntimeError(f"missing {region_col}: {list(df.columns)}")

    dom = df[df[region_col].astype(str).str.contains("Domestic", case=False, na=False)]
    if dom.empty:
        raise RuntimeError("no Domestic rows in OeNB CSV")

    now = datetime.now(timezone.utc).isoformat()
    monthly = dom[dom["period"].astype(str).str.lower() == "month"].copy()

    def _get(g: pd.DataFrame, currency: str, sector: str) -> float | None:
        m = g[
            (g["Currency"].astype(str) == currency)
            & (g["Economic sector"].astype(str) == sector)
        ]
        if m.empty:
            return None
        try:
            return float(m["values"].iloc[0])
        except (TypeError, ValueError):
            return None

    rows: list[dict] = []
    for (year, month), g in monthly.groupby(["year", "month"]):
        try:
            y = int(year)
            mon = int(month)
        except (TypeError, ValueError):
            continue
        if mon < 1 or mon > 12:
            continue
        period = f"{y}-{mon:02d}"

        # FCD = FX MFI counterpart + FX Non-MFI counterpart
        fx_mfi = _get(
            g,
            "Foreign currencies combined",
            "Monetary financial institutions (MFIs)",
        )
        fx_nmfi = _get(
            g,
            "Foreign currencies combined",
            "Non-monetary financial institutions (Non-MFIs)",
        )
        fcd = None
        if fx_mfi is not None or fx_nmfi is not None:
            fcd = (fx_mfi or 0.0) + (fx_nmfi or 0.0)

        td = _get(g, "Total", "Total")
        if fcd is None or td is None or td <= 0:
            continue

        ratio = round((fcd / td) * 100, 4)
        for indicator, value in (
            ("FCD", round(fcd, 4)),
            ("TD", round(td, 4)),
            ("FCD_TD_RATIO", ratio),
        ):
            rows.append(
                {
                    "country_code": country_code,
                    "year": y,
                    "period": period,
                    "indicator": indicator,
                    "value": value,
                    "updated_at": now,
                }
            )

    if not rows:
        return _empty()
    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        raw = _download_csv()
        out = _build_long(raw, country_code)
        if out.empty:
            logger.error("[%s] CSV parsed but no FCD/TD rows", country_code)
            return _empty()
        logger.info(
            "[%s] %d rows (%s~%s) via OeNB CSV full range",
            country_code,
            len(out),
            out["period"].min(),
            out["period"].max(),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
