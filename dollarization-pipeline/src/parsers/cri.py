"""Costa Rica: BCCR(Banco Central de Costa Rica) 'Indicadores Económicos' 데이터 포털
(gee.bccr.fi.cr)의 개별 통계표(CodCuadro) 두 개를 합친다.
    CodCuadro=167: Depósitos de ahorro en moneda extranjera mantenidos en el sistema financiero
                   (외화 저축예금, 1997~현재)
    CodCuadro=147: Depósitos en cuenta corriente en moneda extranjera mantenidos en el sistema
                   bancario (외화 당좌예금, 1987~현재)
FCD = 167 + 147. BCCR 검색(frmBusquedas.aspx)으로 '외화 정기예금(depósito a plazo en moneda
extranjera)'에 해당하는 별도 통계표를 찾아봤으나 존재하지 않았다 - 위 두 카테고리가 BCCR가
공개하는 전부다.

각 통계표 페이지 자체는 UI 위젯(날짜 범위 입력 등)이라 JS 없이는 표를 못 보지만, 페이지에
내장된 'Exportar datos a Excel' 버튼(js_doExport())이 실제로 여는 URL은 그냥
'...frmVerCatCuadro.aspx?CodCuadro={코드}&Idioma=1&Exportar=True'라 requests로 직접 GET
가능하다. 응답은 확장자만 .xls이고 실제로는 HTML 테이블이라 pandas.read_html로 바로 읽힌다.

내보내진 표는 연도(행) x 월(열) 매트릭스이고, 값이 정수로 스케일링되어 있다(예: 1998년 1월
저축예금 원자료 22104846115 -> 실제 값은 221.048...백만 달러). 페이지에 표시되는 값
(스페인어 천단위 '.'/소수점 ',' 표기, 예: '5.176,9')과 대조해 스케일 계수가 정확히 1e8임을
확인했다(517690172446 / 1e8 = 5176.90 = 표시값 '5.176,9'와 일치).

TD(총예금) 계산: 국내통화(콜론) 대응 통계표
    CodCuadro=172: Depósitos de ahorro en moneda nacional mantenidos en el sistema financiero
                   (FCD의 167과 동일 scope: sistema financiero)
    CodCuadro=138: Depósitos en cuenta corriente en moneda nacional mantenidos en el sistema
                   bancario (FCD의 147과 동일 scope: sistema bancario)
+ FCD(167+147). 콜론 표는 'millones de colones', 달러 표(FCD)는 'millones de dólares'로 단위가
달라, CodCuadro=748 'Tipo de cambio promedio MONEX'(일별, 콜론/달러, 2006~현재)를 월평균으로
집계해 환산한다: TD_usd = (172+138)_colones / fx_avg + FCD_usd. MONEX 환율표가 2006년부터만
있어 TD는 2006-01부터 산출되고, 그 이전(1987~2005) 구간은 FCD만 존재한다.
"""

from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = "__RENDER__"

_EXPORT_URL = "https://gee.bccr.fi.cr/indicadoreseconomicos/Cuadros/frmVerCatCuadro.aspx?CodCuadro={code}&Idioma=1&Exportar=True"
_SAVINGS_CODE = 167
_CURRENT_ACCOUNT_CODE = 147
_SAVINGS_MN_CODE = 172
_CURRENT_ACCOUNT_MN_CODE = 138
_FX_CODE = 748
_SCALE = 1e8

_MONTH_COL_TO_NUM = {i: i for i in range(1, 13)}  # col1=Enero..col12=Diciembre
_MONTHS_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("CRI는 render()를 통해 처리한다 (두 통계표를 합산해야 함)")


def _fetch_series(code: int) -> dict[str, float]:
    response = requests.get(
        _EXPORT_URL.format(code=code),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
        timeout=60,
    )
    response.raise_for_status()

    table = pd.read_html(StringIO(response.text))[0]

    series: dict[str, float] = {}
    for _, row in table.iterrows():
        year_str = str(row[0]).strip()
        if not year_str.isdigit():
            continue
        year = int(year_str)
        for col, month in _MONTH_COL_TO_NUM.items():
            value_str = str(row[col]).strip()
            if value_str and value_str.lower() != "nan" and value_str.lstrip("-").isdigit():
                series[f"{year}-{month:02d}"] = float(value_str) / _SCALE
    return series


def _fetch_monthly_fx_avg(code: int) -> dict[str, float]:
    """일별(day-row x year-col) MONEX 환율표를 월평균으로 집계한다."""
    response = requests.get(
        _EXPORT_URL.format(code=code),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
        timeout=60,
    )
    response.raise_for_status()
    table = pd.read_html(StringIO(response.text))[0]

    year_row = table.iloc[4]
    years: dict[int, int] = {}
    for c in range(1, table.shape[1]):
        v = year_row[c]
        if pd.notna(v):
            try:
                years[c] = int(float(v))
            except ValueError:
                continue

    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for r in range(5, table.shape[0]):
        label = str(table.iloc[r, 0]).strip()
        parts = label.split()
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        month = _MONTHS_ES.get(parts[1].lower()[:3])
        if month is None:
            continue
        for c, year in years.items():
            raw = table.iloc[r, c]
            if pd.isna(raw):
                continue
            raw_s = str(raw).strip()
            if not raw_s:
                continue
            try:
                value = float(raw_s) / _SCALE
            except ValueError:
                continue
            if value == 0:
                continue
            period = f"{year}-{month:02d}"
            sums[period] = sums.get(period, 0.0) + value
            counts[period] = counts.get(period, 0) + 1

    return {period: sums[period] / counts[period] for period in sums}


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    savings = _fetch_series(_SAVINGS_CODE)
    current_account = _fetch_series(_CURRENT_ACCOUNT_CODE)

    rows = []
    fcd_by_period: dict[str, float] = {}
    for period in set(savings) | set(current_account):
        value = savings.get(period, 0.0) + current_account.get(period, 0.0)
        if period not in savings and period not in current_account:
            continue
        fcd_by_period[period] = value
        rows.append({
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": INDICATOR,
            "value": round(value, 4),
            "updated_at": now,
        })

    savings_mn = _fetch_series(_SAVINGS_MN_CODE)
    current_account_mn = _fetch_series(_CURRENT_ACCOUNT_MN_CODE)
    fx_avg = _fetch_monthly_fx_avg(_FX_CODE)

    for period, fcd_value in fcd_by_period.items():
        rate = fx_avg.get(period)
        mn_savings = savings_mn.get(period)
        mn_current = current_account_mn.get(period)
        if rate is None or mn_savings is None or mn_current is None:
            continue
        td_value = (mn_savings + mn_current) / rate + fcd_value
        rows.append({
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": INDICATOR_TD,
            "value": round(td_value, 4),
            "updated_at": now,
        })

    return pd.DataFrame(rows).sort_values(["period", "indicator"]).reset_index(drop=True)
