"""World Bank API 연동 모듈.

targets.json에 소스가 없는(No Standalone Source) 국가나, 자체 수집값 검증용 보조 데이터로
World Bank Open Data API(https://api.worldbank.org/v2)를 사용한다.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.worldbank.org/v2"


def fetch_indicator(country_code: str, indicator: str, per_page: int = 100) -> pd.DataFrame:
    """World Bank 지표 데이터를 롱폼 DataFrame으로 반환한다.

    반환 컬럼: [country_code, year, period, indicator, value, updated_at]
    """
    url = f"{BASE_URL}/country/{country_code}/indicator/{indicator}"
    params = {"format": "json", "per_page": per_page}

    logger.info("[%s] World Bank API 조회: %s", country_code, indicator)
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    if len(payload) < 2 or not payload[1]:
        logger.warning("[%s] World Bank API 데이터 없음: %s", country_code, indicator)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    records = payload[1]
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "country_code": country_code,
            "year": int(r["date"]),
            "period": "Annual",
            "indicator": indicator,
            "value": r["value"],
            "updated_at": now,
        }
        for r in records
        if r.get("value") is not None
    ]
    return pd.DataFrame(rows)
