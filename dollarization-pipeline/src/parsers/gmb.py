"""Gambia: CBG Macroeconomic Data Warehouse (DataWarehousePro).

포털: https://app.datawarehousepro.com/go/cbg
(Central Bank of The Gambia Macroeconomic Data Warehouse)

Monetary Survey(MON)의 Quasi money·예금 항목은 민간/공공 구분만 있고 통화(외화) 분해가
없다. Balance of Payments의 Currency and deposits 는 대외부문 항목이라 거주자 FCD와
다르다. 거주자 외화 관련으로 가장 직접적인 공개 시계열은 Financial Sector(FIN) >
Commercial Banks > Financial soundness indicators 의 다음 지표다.

    mnemonic  fcdlttlcb
    이름      19. Foreign-currency-denominated liabilities to total liabilities
    API       GET /guest/getMnemonicData/cbg/FIN/fcdlttlcb
    주기      분기(Q), 실측 관측 2007Q3~2023Q3 (메타 first_observation=2000Q1이나
              실제 data 배열은 2007Q3부터)
    단위 메타 mill. Of GMD 로 표기되어 있으나 값은 비율(%) — 제목이
              liabilities to total liabilities 이고 표본(2022Q4=34.62 등)과 일치

동일 카테고리 18번(fcdlttlocb, 외화표시대출/총대출)은 대출 측면 보조 지표라 기본
수집 대상에서 제외(필요 시 확장 가능).

이 파이프라인에서는 절대 잔액 FCD·TD 를 복원할 분모·분자가 없어
indicator=FCD_TD_RATIO 만 적재한다(부채 기준 달러화율 프록시). 순수 예금 달러화율과
정의가 다를 수 있음을 adapter notes에 명시.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_ACCOUNT = "cbg"
_DATABANK = "FIN"
_MNEMONIC = "fcdlttlcb"  # FC-denominated liabilities / total liabilities (%)
_API = (
    f"https://app.datawarehousepro.com/guest/getMnemonicData/"
    f"{_ACCOUNT}/{_DATABANK}/{_MNEMONIC}"
)
_PORTAL = "https://app.datawarehousepro.com/go/cbg"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": _PORTAL,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("GMB는 render()로 Data Warehouse API를 호출한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _period_from_label(label: str) -> tuple[int, str] | None:
    """'2007Q3' / '2007-Q3' / '2007 Q3' → (2007, '2007-Q3')."""
    text = str(label).strip().upper().replace(" ", "")
    m = re.fullmatch(r"(\d{4})-?Q([1-4])", text)
    if not m:
        return None
    year, q = int(m.group(1)), int(m.group(2))
    return year, f"{year}-Q{q}"


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    try:
        resp = requests.get(_API, headers=_HEADERS, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.exception("[%s] Data Warehouse API 실패: %s", country_code, e)
        return _empty()

    if not isinstance(payload, dict) or "data" not in payload:
        logger.error("[%s] 예상치 못한 응답: %s", country_code, str(payload)[:200])
        return _empty()

    rows = []
    for point in payload.get("data") or []:
        label = point.get("description")
        parsed = _period_from_label(label) if label else None
        if parsed is None:
            continue
        year, period = parsed
        try:
            value = float(point.get("value"))
        except (TypeError, ValueError):
            continue
        if value != value:  # NaN
            continue
        rows.append({
            "country_code": country_code,
            "year": year,
            "period": period,
            "indicator": "FCD_TD_RATIO",
            "value": round(value, 4),
            "updated_at": now,
        })

    if not rows:
        logger.warning("[%s] 관측치 없음 (mnemonic=%s)", country_code, _MNEMONIC)
        return _empty()

    df = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] %s (%s): %d분기 %s~%s (unit meta=%s; 값은 비율%%)",
        country_code,
        payload.get("name_of_series"),
        _MNEMONIC,
        len(df),
        df["period"].min(),
        df["period"].max(),
        payload.get("unit_of_measure"),
    )
    return df
