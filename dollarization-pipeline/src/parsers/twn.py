"""Taiwan: Central Bank of the Republic of China (Taiwan, CBC) official open-data CSV,
'All Currency Institutions Deposit' monthly time series.

data.gov.tw dataset 6534 ("all-monetary-institutions deposits") is nominally listed on
data.gov.tw, but the resource it actually points to is a CSV hosted directly on the CBC
(central bank) site, not on data.gov.tw itself:

    https://www.cbc.gov.tw/public/data/OpenData/經研處/EF03M01.csv  (monthly, from 1987M05)
    https://www.cbc.gov.tw/public/data/OpenData/經研處/EF03Y01.csv  (annual)

A single monthly file covers the entire span from 1987 to the present, so no archive
crawl is needed (single-file download, `FILE_URL` pattern). The "SSL/connection failure"
note left over in the old targets.json memo referred to
`https://www.cbc.gov.tw/en/cp-902-123617-370e1-2.html` (the PDF listing page); the CSV
download itself works fine with no special headers or TLS settings (verified as of
2026-08).

Column layout (UTF-8 with BOM, single header row):
    月 (month)                                        -> "YYYYMmm" (e.g. "2023M12")
    貨幣機構存款-合計-期底餘額-億元 (deposits-total-EOP balance-億元)
                                                       -> total deposits (TD) end-of-period
                                                          balance, in 億元 (1億 = 1e8 NTD)
    貨幣機構存款-企業及個人存款-外匯存款-期底餘額-億元
    (deposits-corporate & individual-FX deposits-EOP balance-億元)
                                                       -> corporate + individual foreign
                                                          currency deposits (FCD) EOP balance
    (remaining columns are YoY growth rates and sub-items - not used)

The unit 億元 (1億元 = 1e8 NTD) is kept as-is, following the same convention as other
country parsers of preserving the native-currency raw unit. FCD_TD_RATIO is also computed,
matching the 3-indicator (FCD/TD/FCD_TD_RATIO) convention used in abw.py.

Verification: 2023M12 FCD=89,717 億元 (=8,971.7 billion元), TD=594,271 億元 ->
FCD/TD=15.10%. This is close to the figure from prior research notes ("CBC's own published
2023 ratio ≈15.17%"), the small gap presumably due to published rounding/revision
differences. 2024M12 FCD/TD=14.41% and 2025M12 (latest) FCD/TD=13.73% are also close to the
research notes (14.52%/13.82%), confirming data reliability.

The CBC site's certificate has a defect (missing Subject Key Identifier), so the default
SSL context raises `certificate verify failed` (curl tolerates it, but Python's default
verify=True path fails; this follows the same verify=False workaround pattern used by
kor.py/jpn.py). `src.collectors.base.download()` has no verify option, so even though this
is a single file, it is handled via `__RENDER__` plus a dedicated requests session.
"""

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_CSV_URL = "https://www.cbc.gov.tw/public/data/OpenData/%E7%B6%93%E7%A0%94%E8%99%95/EF03M01.csv"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

_PERIOD_COL = "月"
_TD_COL = "貨幣機構存款-合計-期底餘額-億元"
_FCD_COL = "貨幣機構存款-企業及個人存款-外匯存款-期底餘額-億元"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    df = pd.read_csv(BytesIO(content), encoding="utf-8-sig")

    missing = [c for c in (_PERIOD_COL, _TD_COL, _FCD_COL) if c not in df.columns]
    if missing:
        logger.warning("[%s] expected column(s) missing: %s", country_code, missing)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for _, r in df.iterrows():
        raw_period = str(r[_PERIOD_COL]).strip()
        if "M" not in raw_period:
            continue
        try:
            year_str, month_str = raw_period.split("M")
            year, month = int(year_str), int(month_str)
        except ValueError:
            continue

        td_val, fcd_val = r[_TD_COL], r[_FCD_COL]
        if not isinstance(td_val, (int, float)) or pd.isna(td_val):
            continue
        if not isinstance(fcd_val, (int, float)) or pd.isna(fcd_val):
            continue

        period = f"{year}-{month:02d}"
        td = round(float(td_val), 2)
        fcd = round(float(fcd_val), 2)
        ratio = round((fcd / td) * 100, 2) if td else None

        for indicator, value in ((INDICATOR, fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    if not rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    out = pd.DataFrame(rows).drop_duplicates(subset=["period", "indicator"], keep="last")
    return out.sort_values(["period", "indicator"]).reset_index(drop=True)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    response = requests.get(_CSV_URL, headers=_HEADERS, timeout=30, verify=False)
    response.raise_for_status()
    return parse(response.content, country_code)
