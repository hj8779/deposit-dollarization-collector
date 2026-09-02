"""Madagascar: BFM / IMF FSAP FCD/TD.

공개 가능 자료:
  - IMF FSSA 2016: Foreign currency deposits / total deposits (2008–2015, %)
  - BFM Annual Report: Dépôts en devises des résidents (FCD stock) — TD 동시 표 불완전

최신 월별 FCD+TD 동일 표가 BFM 사이트에서 확인되지 않아,
IMF FSAP 연간 비율을 FCD_TD_RATIO 로만 수록할 수 있는 경우에도
파이프라인 관례상 FCD/TD 절대액이 없으면 빈 프레임을 반환한다.

status=failed: 최신 결합 시계열 부재.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

# IMF FSSA historical ratios (percent) — retained for documentation / future use
_IMF_FSAP_RATIOS = {
    "2008-12": 21.0,
    "2009-12": 19.4,
    "2010-12": 21.5,
    "2011-12": 19.5,
    "2012-12": 19.2,
    "2013-12": 16.6,
    "2014-12": 18.1,
    "2015-12": 17.7,
}

_BFM_AR = (
    "https://www.banky-foibe.mg/admin/wp-content/uploads/2020/06/Rapport-annuel-2019.pdf"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MDG는 render()로 처리한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        # Probe BFM AR for joint FCD/TD table; currently not reliable enough
        try:
            resp = requests.get(_BFM_AR, headers=_HEADERS, timeout=90, verify=False)
            logger.info(
                "[%s] BFM AR 2019 reachable=%s bytes=%d (no paired FCD/TD parser)",
                country_code,
                resp.status_code == 200 and resp.content[:4] == b"%PDF",
                len(resp.content),
            )
        except Exception as e:
            logger.warning("[%s] BFM AR: %s", country_code, e)

        logger.error(
            "[%s] no machine-readable paired FCD+TD series "
            "(IMF FSAP has ratio-only 2008-2015; BFM monthly TD not linked)",
            country_code,
        )
        # Optionally expose ratio-only as synthetic: FCD=ratio, TD=100
        # Disabled — would break absolute-level consumers.
        return _empty()
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
