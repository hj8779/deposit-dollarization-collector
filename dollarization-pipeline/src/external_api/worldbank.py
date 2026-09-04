"""World Bank API integration module.

Uses the World Bank Open Data API (https://api.worldbank.org/v2) as a fallback
for countries with no source in targets.json (No Standalone Source), and as
supplementary data for validating our own collected values.
"""

from datetime import datetime, timezone

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.worldbank.org/v2"


def fetch_indicator(country_code: str, indicator: str, per_page: int = 100) -> pd.DataFrame:
    """Return World Bank indicator data as a long-form DataFrame.

    Returned columns: [country_code, year, period, indicator, value, updated_at]
    """
    url = f"{BASE_URL}/country/{country_code}/indicator/{indicator}"
    params = {"format": "json", "per_page": per_page}

    logger.info("[%s] Querying World Bank API: %s", country_code, indicator)
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    if len(payload) < 2 or not payload[1]:
        logger.warning("[%s] No data from World Bank API: %s", country_code, indicator)
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
