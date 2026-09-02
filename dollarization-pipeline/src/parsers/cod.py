"""Congo (DRC): Banque Centrale du Congo(BCC) 신형 통계 사이트
(bcc.cd/statistiques/secteur-monetaire/depots)의 "Dépôts : Secteur monétaire" 위젯.

이 페이지는 Next.js RSC로 서버에서 렌더링될 때 전체 시계열 데이터를 HTML 안에
`self.__next_f.push([1,"..."])` 스트리밍 청크로 그대로 심어놓는다(별도 API 호출 없이
정적 HTML만 받아도 전체 데이터가 들어있음 - CSV/XLSX 내보내기 버튼도 이미 로드된 이
데이터를 클라이언트에서 파일로 변환하는 것으로 보임). 청크를 모두 이어붙여
unicode-escape로 디코드한 뒤, `"period":"YYYY-MM"...{"depots--mn":X,"depots--me":Y}`
패턴으로 월별 관측치를 직접 추출한다.

mn = monnaie nationale(자국통화), me = monnaie étrangère(외화) = FCD. TD = mn + me
(=depots--total-depots 값과 정확히 일치함을 확인). 단위는 페이지 설명에 명시된 대로
"백만 미국 달러"(2010-12부터 월간) - 콩고프랑이 아니라 달러 표시라 화폐 개혁/환율 이슈
없이 시계열이 그대로 이어짐.

2010-12 이전은 이 위젯에 데이터가 없다(연차보고서 Tableau 4.2를 개별적으로 찾아야 함 -
web/src/lib/manualUpdateCountries.ts에 half_manual로 등록, 대시보드에서 수동 입력 대상).

www.bcc.cd는 TLS 인증서 체인이 불완전해(중간 인증서 누락으로 추정) Python 기본 인증서
번들(certifi)로 검증 실패한다(curl은 시스템 신뢰 저장소가 달라 통과) - verify=False 필요.
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
    raise NotImplementedError("COD는 render()로 페이지에 심어진 스트리밍 데이터를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    resp = requests.get(_PAGE_URL, headers=_HEADERS, timeout=60, verify=False)
    resp.raise_for_status()

    chunks = _NEXT_F_CHUNK_RE.findall(resp.text)
    if not chunks:
        logger.warning("[%s] __next_f 스트리밍 청크를 찾지 못함 (페이지 구조 변경?)", country_code)
        return _empty()

    combined = "".join(chunks).encode().decode("unicode_escape")
    matches = _DEPOSIT_RE.findall(combined)
    if not matches:
        logger.warning("[%s] depots--mn/me 패턴을 찾지 못함", country_code)
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
