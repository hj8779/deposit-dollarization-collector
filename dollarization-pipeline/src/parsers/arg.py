"""Argentina: BCRA(Banco Central de la República Argentina) 공식 통계 REST API.

사용자가 제시한 idVariable=14는 실제로는 'Tasa de interés de préstamos personales'
(개인대출 금리, 연율 %)였다 — 예금과 무관. 전체 변수 목록(/estadisticas/v4.0/Monetarias)을
받아 설명(descripcion)에서 직접 검색해 맞는 ID를 찾았다:

    idVariable 1414: 'Depósitos totales del total de sectores' (전 부문 총예금, 외화(USD) 표시분),
                      categoria='Depósitos por cuenta', unidadExpresion='En millones de USD'

BCRA에서 USD 단위로 집계되는 예금은 정의상 외화(달러)예금이므로 이것이 FCD에 해당한다.
또한 API 버전이 v3.0에서 v4.0으로 이미 바뀌어 있었다(v3/v2 호출 시 HTTP 410 Gone,
"Método correspondiente a la v3 ha sido deprecado" 응답).

TD(총예금, 통화 구분 없는 전체) 계산: 같은 'idVariable 1369'가 페소(ARS) 표시분 총예금
('Depósitos totales del total de sectores', unidadExpresion='En millones de ARS', moneda='ML')
이다. 1369(ARS)와 1414(USD)는 서로 다른 통화 단위이므로 그대로 더할 수 없어, 'idVariable 5'
(Tipo de cambio mayorista de referencia, Pesos por USD)로 페소분을 달러로 환산한 뒤 더한다:
    TD_usd = (1369_ars / fx_rate) + 1414_usd
FCD가 이미 USD 단위로 저장되므로 TD도 동일하게 USD 단위로 맞춰 비율 계산이 가능하게 한다.

일별(Saldos, periodicidad=D) 시계열이라 매월 마지막 관측치를 월말 값으로 사용해 월별로
집계한다. 서버가 한 번에 최대 3000건 정도만 주므로(limit=7000처럼 과도하게 요청하면
빈 응답) offset을 증가시키며 페이지네이션한다. SSL 인증서는 정상 검증되어(verify=False
불필요) 기본 설정으로 요청한다.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

API_BASE = "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias"
_ID_FCD_USD = 1414
_ID_TD_ARS = 1369
_ID_FX_RATE = 5
_PAGE_LIMIT = 3000
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("ARG는 render()를 통해 처리한다 (페이지네이션 필요한 REST API)")


def _fetch_monthly_series(id_variable: int) -> dict[str, float]:
    """일별 Saldos 시계열을 받아 월별(월 마지막 관측치)로 집계해 {period: value} 반환."""
    all_records = []
    offset = 0
    while True:
        response = requests.get(
            f"{API_BASE}/{id_variable}", headers=_HEADERS,
            params={"limit": _PAGE_LIMIT, "offset": offset}, timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        if not results:
            break

        detalle = results[0].get("detalle", [])
        all_records.extend(detalle)

        total = payload.get("metadata", {}).get("resultset", {}).get("count", 0)
        offset += _PAGE_LIMIT
        if offset >= total:
            break

    by_month: dict[str, tuple[str, float]] = {}
    for rec in all_records:
        fecha = rec["fecha"]  # 'YYYY-MM-DD'
        period = fecha[:7]
        if period not in by_month or fecha > by_month[period][0]:
            by_month[period] = (fecha, rec["valor"])

    return {period: value for period, (_, value) in by_month.items()}


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    fcd_usd = _fetch_monthly_series(_ID_FCD_USD)
    if not fcd_usd:
        logger.warning("[%s] BCRA API에서 데이터를 받지 못함", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    td_ars = _fetch_monthly_series(_ID_TD_ARS)
    fx_rate = _fetch_monthly_series(_ID_FX_RATE)

    rows = []
    for period, value in fcd_usd.items():
        year = int(period[:4])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR,
            "value": round(float(value), 2),
            "updated_at": now,
        })

    for period, ars_value in td_ars.items():
        rate = fx_rate.get(period)
        usd_value = fcd_usd.get(period)
        if rate is None or usd_value is None:
            continue
        year = int(period[:4])
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": INDICATOR_TD,
            "value": round(ars_value / rate + usd_value, 2),
            "updated_at": now,
        })

    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True)
