"""Congo (DRC): Banque Centrale du Congo (BCC) new statistics site
(bcc.cd/statistiques/secteur-monetaire/depots), "Dépôts : Secteur monétaire" widget.

When this page is server-rendered via Next.js RSC, the entire time series is embedded
directly in the HTML as `self.__next_f.push([1,"..."])` streaming chunks (no separate API
call is needed — the full dataset is present even from the static HTML alone; the CSV/XLSX
export button also appears to just convert this already-loaded data into a file on the
client side). All chunks are concatenated, decoded with unicode-escape, and monthly
observations are extracted directly via the pattern
`"period":"YYYY-MM"...{"depots--mn":X,"depots--me":Y}`.

mn = monnaie nationale (domestic currency), me = monnaie étrangère (foreign currency) = FCD.
TD = mn + me (confirmed to match the depots--total-depots value exactly). Per the unit
stated on the page, values are in "million US dollars" (monthly from 2010-12) — since the
figures are denominated in dollars rather than Congolese francs, the series continues
without any currency-reform or exchange-rate discontinuities.

There is no data in this widget before 2010-12 (the annual report's Tableau 4.2 needs to be
looked up separately — registered as half_manual in
web/src/lib/manualUpdateCountries.ts, to be filled in manually on the dashboard).

www.bcc.cd has an incomplete TLS certificate chain (presumably a missing intermediate
certificate), which fails verification against Python's default certificate bundle
(certifi), even though curl succeeds because it uses a different system trust store —
hence verify=False is required.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PAGE_URL = "https://www.bcc.cd/statistiques/secteur-monetaire/depots"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

_NEXT_F_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.S)
_DEPOSIT_RE = re.compile(r'"period":"(\d{4}-\d{2})"[^}]*?"depots--mn":([\d.]+),"depots--me":([\d.]+)')


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("COD is handled via render(), which reads the streaming data embedded in the page")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    resp = requests.get(_PAGE_URL, headers=_HEADERS, timeout=60, verify=False)
    resp.raise_for_status()

    chunks = _NEXT_F_CHUNK_RE.findall(resp.text)
    if not chunks:
        logger.warning("[%s] could not find __next_f streaming chunks (page structure changed?)", country_code)
        return _empty()

    combined = "".join(chunks).encode().decode("unicode_escape")
    matches = _DEPOSIT_RE.findall(combined)
    if not matches:
        logger.warning("[%s] could not find depots--mn/me pattern", country_code)
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    seen_periods = set()
    for period, mn_s, me_s in matches:
        if period in seen_periods:
            continue
        seen_periods.add(period)
        mn, me = float(mn_s), float(me_s)
        td = mn + me
        if td <= 0:
            continue
        year = int(period[:4])
        ratio = round((me / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(me, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    if not rows:
        return _empty()

    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
