"""Chile: Banco Central de Chile 'Statistics Database (BDE)' 조회 화면(si3.bcentral.cl/Siete).
공식적으로는 API(GetSeries/SearchSeries)가 있지만 이메일로 신청해 자격증명(user/pass)을
발급받아야 해서 외부에서 즉시 쓰기 어렵다. 대신 조회 화면 자체(si3.bcentral.cl/Siete/.../
Cuadro/.../E32)가 로그인/JS 없이 일반 GET만으로도 전체 시계열이 담긴 HTML 표를 그대로
서버에서 렌더링해 내려준다(Playwright로 확인해도 별도 XHR 없이 최초 페이지에 이미 표가
있음) - 그래서 API 대신 이 조회 화면을 직접 GET해서 표를 파싱한다.

표 제목 'Deposits in foreign currency, balances (millions of dollars)'의 'Serie' 열에
'Total deposits' / 'Transferable deposits and sight deposits' / 'Time deposits, savings
deposits and debt securities' 세 행이 있고, 나머지 열은 'Jan.2009'~현재까지 월별 값이다.
FCD = 'Total deposits' 행(이 표 자체가 이미 외화예금 표이므로 하위 두 항목의 합과 같다).

TD(총예금) 계산: 자국통화(페소) 예금 표(E31, 'Local currency deposits, balances (billions of
pesos)', 같은 사이트 CAP_DYB/MN_ESTAD_MON55/EM_DEP_MN/E31)의 'Total deposits' 행 + FCD.
E31은 'billions of pesos', E32(FCD)는 'millions of dollars'로 단위가 달라 그대로 더할 수 없으므로,
BCC 월별 명목환율표(TC_HIST, CAP_TIPO_CAMBIO/MN_TIPO_CAMBIO4/TC_HIST/TC_HIST, 'Exchange rate
(pesos/dollar)', Jan.1960~현재)로 페소 표시분을 달러로 환산한다:
    TD_usd = (E31_billions_pesos * 1000 / fx_rate) + E32_usd
(실측: Jan.2009 기준 E31=61,640억 페소, FX=623.01, E32=15,650.92 -> TD ≈ 114,590백만 달러)
"""

import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = "https://si3.bcentral.cl/Siete/en/Siete/Cuadro/CAP_DYB/MN_ESTAD_MON55/EM_DEP_ME/E32"

_LOCAL_DEPOSITS_URL = "https://si3.bcentral.cl/Siete/en/Siete/Cuadro/CAP_DYB/MN_ESTAD_MON55/EM_DEP_MN/E31"
_FX_RATE_URL = "https://si3.bcentral.cl/Siete/en/Siete/Cuadro/CAP_TIPO_CAMBIO/MN_TIPO_CAMBIO4/TC_HIST/TC_HIST"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

_COL_RE = re.compile(r"^([A-Za-z]{3})\.(\d{4})$")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _row_by_period(table: pd.DataFrame, serie_label: str) -> dict[str, float]:
    matched = table[table["Serie"].str.strip() == serie_label]
    if matched.empty:
        return {}
    row = matched.iloc[0]
    out: dict[str, float] = {}
    for col in table.columns:
        m = _COL_RE.match(str(col).strip())
        if not m:
            continue
        month = _MONTHS.get(m.group(1).lower())
        if month is None:
            continue
        year = int(m.group(2))
        value = row[col]
        if pd.isna(value):
            continue
        out[f"{year}-{month:02d}"] = float(value)
    return out


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    html = content.decode("utf-8")

    table = pd.read_html(StringIO(html))[0]
    fcd_by_period = _row_by_period(table, "Total deposits")
    if not fcd_by_period:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for period, value in fcd_by_period.items():
        year = int(period[:4])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR,
            "value": round(value, 2),
            "updated_at": now,
        })

    from concurrent.futures import ThreadPoolExecutor

    def _fetch(url: str) -> pd.DataFrame:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        return pd.read_html(StringIO(resp.content.decode("utf-8")))[0]

    # si3.bcentral.cl 응답이 각각 수 초씩 걸려(요청당 ~5-6s) 직렬로 하면 느리므로 병렬로 받는다.
    with ThreadPoolExecutor(max_workers=2) as executor:
        local_future = executor.submit(_fetch, _LOCAL_DEPOSITS_URL)
        fx_future = executor.submit(_fetch, _FX_RATE_URL)
        local_table = local_future.result()
        fx_table = fx_future.result()

    local_by_period = _row_by_period(local_table, "Total deposits")
    fx_by_period = _row_by_period(fx_table, "Exchange rate (pesos/dollar)")

    for period, fcd_value in fcd_by_period.items():
        local_pesos_billions = local_by_period.get(period)
        fx_rate = fx_by_period.get(period)
        if local_pesos_billions is None or not fx_rate:
            continue
        year = int(period[:4])
        td_value = local_pesos_billions * 1000 / fx_rate + fcd_value
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR_TD,
            "value": round(td_value, 2),
            "updated_at": now,
        })

    return pd.DataFrame(rows)
