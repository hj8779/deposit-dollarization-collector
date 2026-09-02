"""Bolivia: BCB(Banco Central de Bolivia) 'sector-monetario' 페이지의 개별 통계 엑셀 목록 중
'Créditos y Depósitos > OSD > 17. Depósitos totales por monedas serie.xlsx'
(전체 금융시스템(은행+Pyme+저축은행+협동조합 등) 예금의 통화별 시계열, 월별, 2017-12~현재).

처음엔 사용자가 짚어준 '2. Base Monetaria...' 파일 31행 'Moneda Extranjera'를 검토했으나,
그건 중앙은행 지급준비금(Encaje Legal 등) 중 외화로 예치된 부분일 뿐 시중은행 고객의
외화예금이 아니어서(금액도 훨씬 작음) 채택하지 않았다. 같은 목록의 '17. Depósitos totales
por monedas serie.xlsx'가 전체 금융시스템 예금을 통화별(MN/ME/UFV/MVDOL)로 집계한
진짜 시계열이라 이걸 사용한다(사용자 확인 완료).

워크북은 시트가 'Total'/'MN'/'ME'/'UFV'/'MVDOL'로 나뉘어 있고, 각 시트는 금융기관별
(은행/Pyme/저축은행/협동조합 등 여러 그룹)로 행이 나열되다 각 그룹 끝에 'TOTAL' 소계 행,
맨 마지막에 전체를 합산한 'TOTAL SISTEMA' 행이 온다. TD = 'Total' 시트의 'TOTAL SISTEMA' 행
(날짜는 5행에 월말 기준으로 나열).

2026-08-19 버그 수정 (중요): 'ME' 시트의 'TOTAL SISTEMA' 행은 볼리비아노 환산액이 아니라
**원화(달러) 그대로** 찍혀있다 — 시트 제목이 "POR ENTIDADES FINANCIERAS DE MONEDA DÓLARES"인데,
'MN'/'UFV'/'MVDOL' 시트는 전부 볼리비아노 기준이라 그동안 FCD(=ME 원장) / TD(=Total, 볼리비아노)를
그대로 나눠 ratio를 계산해온 게 사실상 "USD 예금액 ÷ Bs 총예금"이라는 단위 불일치였다(사용자
제보로 '3. Sistema Monetario.xlsx' Pasivo 탭과 교차검증하다 발견). 검증: 2026-06 Total(Bs)=
255,956,216.02, MN(Bs)=227,326,162.06, UFV=1,460,453.86, MVDOL=226,029.27 인데 ME(2,557,741.23)를
그대로 더하면 24.4M Bs가 안 맞고, 그 시점 BCB 공식 환율(9.76, 2026-06-26 변동환율제 전환 직후
TCO 기준)을 곱하면(2,557,741.23×9.76≈24,963,571) 합계가 255.98M Bs로 0.8%까지 맞아떨어짐 —
즉 실제 달러화 비율은 기존 계산(~1.0%)이 아니라 그 몇 배(2026-06 기준 9.4~9.8%대)였다.

환율: 볼리비아는 2011년 11월부터 2026-06-26 변동환율제 전환 전까지 고정환율(매수 6.96 Bs/USD)을
유지했다(이 기간 전체가 이 파일이 다루는 2017-12~2026-06 이력의 대부분). 변동환율제 전환 이후는
BCB가 'TCO(Tipo de Cambio Oficial)' 일별 은행별 상세를 CSV로 공개하며(tco_tcreferencial_
descargar_csv.php?desde=&hasta=), 각 cut-off 날짜별 'TOTAL BANCOS' 열의 가중평균 TCO 값을 쓴다.
월말 값이 그 달의 대표 환율."""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from io import BytesIO, StringIO

import openpyxl
import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_DEPOSITS_URL = "https://www.bcb.gob.bo/webdocs/sector_monetario/Cr%C3%A9ditos%20y%20Dep%C3%B3sitos/OSD/17.%20Dep%C3%B3sitos%20totales%20por%20monedas%20serie.xlsx"
_TCO_CSV_URL = "https://www.bcb.gob.bo/tco_tcreferencial_descargar_csv.php"
_FLOAT_START = date(2026, 6, 26)
_FIXED_RATE = 6.96  # official peg, Nov 2011 - 2026-06-26

_DATE_ROW = 5
_TOTAL_SISTEMA_LABEL = "total sistema"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BOL은 render()로 예금 xlsx + 환율 CSV를 함께 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _find_total_row(ws) -> int | None:
    for r in range(1, ws.max_row + 1):
        label = ws.cell(row=r, column=1).value
        if isinstance(label, str) and label.strip().lower() == _TOTAL_SISTEMA_LABEL:
            return r
    return None


def _extract_series(ws) -> dict[str, float]:
    total_row = _find_total_row(ws)
    if total_row is None:
        return {}

    series = {}
    for c in range(2, ws.max_column + 1):
        date_val = ws.cell(row=_DATE_ROW, column=c).value
        value = ws.cell(row=total_row, column=c).value
        if isinstance(date_val, datetime) and isinstance(value, (int, float)):
            series[f"{date_val.year}-{date_val.month:02d}"] = float(value)
    return series


def _fetch_post_float_rates() -> dict[str, float]:
    """{'YYYY-MM': rate} for month-end cut-off dates from the float onward, using
    the 'TOTAL BANCOS' weighted-average TCO. Returns {} on any failure (caller
    then just skips periods it has no rate for rather than guessing)."""
    try:
        resp = requests.get(
            _TCO_CSV_URL,
            params={"desde": _FLOAT_START.isoformat(), "hasta": date.today().isoformat()},
            headers=_HEADERS,
            timeout=60,
            verify=False,
        )
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig")
    except Exception as e:
        logger.warning("[BOL] TCO 환율 CSV 조회 실패: %s", e)
        return {}

    rates: dict[str, float] = {}  # date -> rate, keep last (month-end) per YYYY-MM
    reader = csv.reader(StringIO(text), delimiter=";")
    for row in reader:
        if len(row) < 3 or row[2] != "TCO":
            continue
        cutoff = row[0].strip()
        # row ends with a trailing ';' (empty last field) followed by the
        # "TOTAL BANCOS" TCO value, so the value is the second-to-last field.
        total_rate_str = row[-2].strip() if len(row) >= 2 and row[-2].strip() else None
        if not total_rate_str:
            continue
        try:
            d = datetime.strptime(cutoff, "%Y-%m-%d").date()
            rate = float(total_rate_str.replace(",", "."))
        except ValueError:
            continue
        period = f"{d.year}-{d.month:02d}"
        # keep the latest cutoff date seen per period (rows are chronological)
        rates[period] = rate
    return rates


def _rate_for_period(period: str, post_float_rates: dict[str, float]) -> float | None:
    year, month = int(period[:4]), int(period[5:7])
    # crude but adequate: anything at/after the float's own month uses the
    # published TCO for that month; everything earlier used the fixed peg.
    if (year, month) < (_FLOAT_START.year, _FLOAT_START.month):
        return _FIXED_RATE
    return post_float_rates.get(period)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        resp = requests.get(_DEPOSITS_URL, headers=_HEADERS, timeout=90, verify=False)
        resp.raise_for_status()
        wb = openpyxl.load_workbook(BytesIO(resp.content), data_only=True)
    except Exception as e:
        logger.exception("[%s] 예금 xlsx 다운로드/파싱 실패: %s", country_code, e)
        return _empty()

    fcd_usd_series = _extract_series(wb["ME"])  # raw USD thousands, needs FX conversion
    td_series = _extract_series(wb["Total"])  # already Bs thousands

    post_float_rates = _fetch_post_float_rates()

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period, td in td_series.items():
        fcd_usd = fcd_usd_series.get(period)
        if fcd_usd is None or td <= 0:
            continue
        rate = _rate_for_period(period, post_float_rates)
        if rate is None:
            logger.warning("[%s] %s 환율을 못 찾아 스킵", country_code, period)
            continue
        fcd = fcd_usd * rate
        if fcd > td:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
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
