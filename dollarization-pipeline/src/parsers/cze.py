"""Czechia: ČNB(Česká národní banka)의 ARAD 시계열 시스템(cnb.cz/arad, Angular SPA).
'Monetary and financial statistics > Monetary statistics > A. Statistics of monetary
developments in the CR > Deposits with MFIs' 트리 노드(treeId=8165396) 안에 예금을
통화(Instrument currency: CZK/All foreign currencies)와 거래상대 부문(Counterpart sector
residents)으로 나눈 지표들이 있다.

'All foreign currencies'(D21856) x 'Levels'(D21657, 잔액 기준)로 필터링하면 지표가 정확히
4개뿐이다: Financial institutions except MFIs(S.124~129, 보험/연금 포함), Insurance
corporations and pension funds(S.128+S.129), Households and NPISH(S.14+S.15), Non-financial
corporations(S.11). 이 중 'Financial institutions except MFIs'가 이미 'Insurance and pension
funds'를 포함하는 상위 집합이라(코드 자체가 S.124+S.125+S.126+S.127+S.128+S.129로 명시)
겹치지 않게 세 개만 더한다:
    FCD = SMV10M108013(Financial institutions except MFIs) + SMV10M107013(Households+NPISH)
          + SMV10M106013(Non-financial corporations)
정부 부문(General/Central government)은 이 통화(외화) 조합에서 지표 자체가 없다(count=0,
정부의 외화예금이 사실상 없거나 별도 미공개로 추정) - 그래서 위 세 부문이 사실상 거주자
외화예금 전체를 커버한다.

TD(총예금) = 같은 트리에서 통화 필터를 'All currencies'(D21666)로, 지표 특성을 'Types
total'(D21676, 만기/유형 구분 없는 합계)로 바꿔 같은 3개 부문 코드의 '011' 접미사 버전을
합산한다(FX 버전은 '013' 접미사, 이 트리에서 우연히 만기 구분이 없어 Types total 없이도
자동으로 합계였음을 실측 확인. All currencies 버전은 만기별로 나뉜 지표가 별도로 존재해
Types total 필터가 반드시 필요함):
    TD = SMV10M108011(Financial institutions except MFIs) + SMV10M107011(Households+NPISH)
         + SMV10M106011(Non-financial corporations)
(all currencies, Types total, Levels 조합에서 8개 부문 지표만 남음을 실측 확인했고, 그 중
FCD와 동일한 3개 부문만 사용한다.)

ARAD는 진짜 REST API(/aradb/api/v13/...)가 있지만, 지표 데이터 조회 엔드포인트
(indicators-data-by-codes)는 URL 쿼리에 지표 코드를 직접 넣어 단독 호출하면 매번
'Přístup byl zablokován'(접근 차단) 페이지를 돌려준다(WAF가 이 패턴을 세션 밖 직접 호출로
보고 차단하는 것으로 추정). 반면 Playwright로 실제 UI 흐름(트리 탐색 -> 필터 선택 -> 지표
3개 체크 -> '표로 보기' 아이콘 클릭)을 그대로 재현하면 정상 응답한다 - 그래서 매번 이
과정을 자동화해서 응답 JSON을 가로챈다.
"""

from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

ARAD_URL = "https://www.cnb.cz/arad/#/en/indicators"
_FCD_CODES = ["SMV10M108013", "SMV10M107013", "SMV10M106013"]
_TD_CODES = ["SMV10M108011", "SMV10M107011", "SMV10M106011"]

_MONTHS = {
    "01": 1, "02": 2, "03": 3, "04": 4, "05": 5, "06": 6,
    "07": 7, "08": 8, "09": 9, "10": 10, "11": 11, "12": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("CZE는 render()를 통해 처리한다 (ARAD SPA UI 흐름 재현 필요)")


def _fetch_indicator_data(
    currency_label: str, codes: list[str], extra_filter_labels: list[str] | None = None
) -> dict:
    import json as jsonlib

    from playwright.sync_api import sync_playwright

    captured = {}

    def on_response(response):
        if "indicators-data-by-codes" in response.url:
            captured["body"] = response.text()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("response", on_response)
        page.goto(ARAD_URL, timeout=60000)
        page.wait_for_timeout(2000)
        try:
            page.click("text=I AGREE!", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(500)
        page.click("text=Statistical data")
        page.wait_for_timeout(1200)
        page.click("text=Monetary and financial statistics")
        page.wait_for_timeout(1200)
        page.click("text=Monetary statistics")
        page.wait_for_timeout(1200)
        page.click("text=A. Statistics of monetary developments in the CR")
        page.wait_for_timeout(1200)
        page.click("text=Deposits with MFIs")
        page.wait_for_timeout(2000)
        page.click(f"text={currency_label}", timeout=5000)
        page.wait_for_timeout(1200)
        page.click("text=Levels", timeout=5000)
        page.wait_for_timeout(1200)
        for label in extra_filter_labels or []:
            page.click(f"text={label}", timeout=5000)
            page.wait_for_timeout(1200)
        for code in codes:
            page.click(f"label[for={code}]", force=True)
            page.wait_for_timeout(300)
        page.click("text=Selected indicators")
        page.wait_for_timeout(1500)
        page.click(".icon.h-primary", force=True)
        page.wait_for_timeout(3000)
        browser.close()

    if "body" not in captured:
        raise RuntimeError("ARAD indicators-data-by-codes 응답을 가로채지 못함")
    return jsonlib.loads(captured["body"])


def _totals_from_indicators(indicators: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for ind in indicators:
        for snap in ind["snapshots_data"]:
            for period_str, value in snap["chart_data"]:
                mm, yyyy = period_str.split(".")
                month = _MONTHS.get(mm)
                if month is None or not isinstance(value, (int, float)):
                    continue
                period = f"{yyyy}-{mm}"
                totals[period] = totals.get(period, 0.0) + float(value)
    return totals


def render(target: dict) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor

    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    # FCD/TD 두 조회는 서로 독립적인 ARAD SPA 트리 탐색이라 병렬로 돌려 벽시계 시간을 절반으로
    # 줄인다(각 조회 자체가 다단계 트리 클릭 + wait_for_timeout이 지배적이라 순차 실행 시
    # 40초 이상 걸려 짧은 하드 타임아웃(예: --timeout-sec 10)에서 죽기 쉽다).
    with ThreadPoolExecutor(max_workers=2) as executor:
        fcd_future = executor.submit(_fetch_indicator_data, "All foreign currencies", _FCD_CODES)
        td_future = executor.submit(
            _fetch_indicator_data, "All currencies", _TD_CODES, extra_filter_labels=["Types total"]
        )
        fcd_payload = fcd_future.result()
        try:
            td_payload = td_future.result()
        except Exception as e:
            logger.warning("[%s] TD 조회 실패: %s", country_code, e)
            td_payload = None

    fcd_indicators = fcd_payload["data"][0]["indicators"]
    found_codes = {ind["code"] for ind in fcd_indicators}
    if found_codes != set(_FCD_CODES):
        logger.warning("[%s] 예상한 지표 코드와 다름: %s", country_code, found_codes)

    fcd_totals = _totals_from_indicators(fcd_indicators)
    rows = [
        {
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": INDICATOR,
            "value": round(value, 2),
            "updated_at": now,
        }
        for period, value in fcd_totals.items()
    ]

    if td_payload is not None:
        td_indicators = td_payload["data"][0]["indicators"]
        found_td_codes = {ind["code"] for ind in td_indicators}
        if found_td_codes != set(_TD_CODES):
            logger.warning("[%s] TD 예상 지표 코드와 다름: %s", country_code, found_td_codes)
        td_totals = _totals_from_indicators(td_indicators)
        rows.extend(
            {
                "country_code": country_code,
                "year": int(period[:4]),
                "period": period,
                "indicator": INDICATOR_TD,
                "value": round(value, 2),
                "updated_at": now,
            }
            for period, value in td_totals.items()
        )

    return pd.DataFrame(rows).sort_values(["period", "indicator"]).reset_index(drop=True)
