"""ECCU 8개국(AIA, ATG, DMA, GRD, MSR, KNA, LCA, VCT) 공용: ECCB(Eastern Caribbean Central Bank)
'Summarized Monetary Survey > Interactive Database' 쿼리 폼.

원래 지시문은 `sdmx.eccb-centralbank.org`의 공개 SDMX REST API를 가정했지만, 해당 도메인은
DNS조차 해석되지 않는(NXDOMAIN) 존재하지 않는 엔드포인트였다. 실제로는 다음 URL의
'Interactive Database'가 진짜 데이터 소스이며, Laravel 기반 폼(POST /search, CSRF 토큰 +
암호화된 hidden 필드 동반)을 통해서만 조회 가능하다. 폼이 부트스트랩 모달(#modify) 안에
select2 멀티셀렉트로 구성되어 있어, requests로 폼을 직접 흉내내기보다 Playwright로 실제
UI 흐름(모달 열기 -> 국가 선택 -> 지표 선택 -> 제출)을 재현하는 편이 훨씬 안정적이다.

폼 상호작용 시 주의점(직접 겪은 함정들):
  - select2 드롭다운을 연 뒤 아무 데나(page.mouse.click) 클릭하면 부트스트랩 모달 자체가
    닫혀버린다(배경 클릭 = 모달 dismiss). 모달 '안쪽'의 비활성 영역(.modal-header)을 클릭해야
    드롭다운만 닫히고 모달은 유지된다.
  - country_code 멀티셀렉트에는 'ECCU'(전지역 합계)가 기본 선택되어 있다. 특정 국가를
    추가로 선택하면 결과 표에 '국가, ECCU' 순서로 두 세트가 나란히 나온다.
  - 결과 표(두 번째 <table>)의 데이터 행은 [지표명, 단위, 연도1-국가, 연도1-ECCU,
    연도2-국가, 연도2-ECCU, ...] 순서. 기본 조회 기간은 최근 5개년(연간)이라 START_DATE를
    직접 조정해 2000년부터 받아온다.
  - start_date 입력창은 readonly(직접 타이핑 불가)이고 bootstrap-datepicker
    (minViewMode=2, 연 단위 선택만 허용, 실제 허용범위는 1975~2029)로 뒤덮여 있다. 이 달력을
    UI 클릭(연도 그리드 탐색)으로 조작하면 클릭 이벤트가 씹혀 값이 갱신되지 않는 경우가 잦았다
    (bootstrap-datepicker가 클릭을 씹는 게 아니라, `input.value`를 JS로 바꿔도 HTML의
    `value` *속성*은 그대로라 `get_attribute('value')`로는 확인 자체가 안 됐던 것 -
    실제로는 `input_value()`로 읽어야 라이브 값이 보인다). 가장 안정적인 방법은 UI를 아예
    건드리지 않고 jQuery 플러그인의 공개 API를 직접 호출하는 것:
    `jQuery('#start_date').datepicker('setDate', new Date(2000,0,1))`.
"""

from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

QUERY_URL = (
    "https://www.eccb-centralbank.org/statistics-category/"
    "monetary-and-financial-statistics/summarized-monetary-survey/a"
)

# TD(총예금, 광의통화(M2)에 포함되는 예금 전체) = 아래 3개 지표의 합
# (국내통화 이체성예금 + 국내통화 기타예금 + 외화예금). 실측으로 세 행이 서로 겹치지 않는
# 별개 구성요소임을 확인했다(ECCB 결과표에 'Total Deposits' 같은 합계 행은 별도로 없음).
_TD_COMPONENT_LABELS = [
    "Transferable Deposits, In National Currency",
    "Other Deposits, In National Currency",
    "Foreign Currency Deposits",
]


def fetch_fcd(country_code: str, country_label: str) -> pd.DataFrame:
    from playwright.sync_api import sync_playwright

    now = datetime.now(timezone.utc).isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
        try:
            page.goto(QUERY_URL, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(1500)
            page.get_by_text("Modify", exact=True).click()
            page.wait_for_timeout(1000)

            modal_safe_spot = page.locator(".modal-header, .modal-title").first

            # 기본 조회 기간(최근 5개년)이 아니라 2000년부터 받아오도록 시작일을 조정한다.
            # readonly 달력 위젯이라 UI 클릭 대신 jQuery 플러그인 API를 직접 호출한다.
            page.evaluate("window.jQuery('#start_date').datepicker('setDate', new Date(2000, 0, 1))")
            page.wait_for_timeout(300)

            page.locator("#country_code + span.select2 .select2-selection").first.click()
            page.wait_for_timeout(300)
            page.locator(".select2-results__option").filter(has_text=country_label).first.click(force=True)
            page.wait_for_timeout(300)
            modal_safe_spot.click(force=True)
            page.wait_for_timeout(500)

            page.locator("#indicator-rows + span.select2 .select2-selection").first.click()
            page.wait_for_timeout(500)
            for label in _TD_COMPONENT_LABELS:
                page.locator(".select2-results__option").filter(has_text=label).first.click(force=True)
                page.wait_for_timeout(300)
            modal_safe_spot.click(force=True)
            page.wait_for_timeout(500)

            submit_btn = page.locator("form#frmModifyTable button[type=submit]")
            with page.expect_navigation(timeout=20000):
                submit_btn.first.click(force=True)
            page.wait_for_timeout(2000)

            years = [
                int(y) for y in page.locator("table").nth(0).locator("thead, tr").first.inner_text().split()
                if y.strip().isdigit() and len(y.strip()) == 4
            ]

            result_table = page.locator("table").nth(1)
            table_lines = result_table.inner_text().splitlines()
        finally:
            browser.close()

    row_texts: dict[str, str] = {}
    for line in table_lines:
        for label in _TD_COMPONENT_LABELS:
            if line.strip().startswith(label):
                row_texts[label] = line
                break

    if len(row_texts) != len(_TD_COMPONENT_LABELS) or not years:
        logger.warning("[%s] ECCB 조회 결과에서 예금 지표 행을 모두 찾지 못함 (%d/%d)",
                        country_code, len(row_texts), len(_TD_COMPONENT_LABELS))
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    # label -> {year: value}, 국가 값은 짝수 인덱스(country, ECCU 순서로 반복)
    values_by_label: dict[str, dict[int, float]] = {}
    for label, row_text in row_texts.items():
        tokens = row_text.split("\t")
        values = [t.replace(",", "") for t in tokens[2:]]  # [지표명, 단위, v1_country, v1_eccu, v2_country, ...]
        per_year: dict[int, float] = {}
        for i, year in enumerate(years):
            idx = i * 2
            if idx >= len(values):
                break
            try:
                per_year[year] = float(values[idx])
            except ValueError:
                continue
        values_by_label[label] = per_year

    rows = []
    for year in years:
        component_values = [values_by_label[label].get(year) for label in _TD_COMPONENT_LABELS]
        fcd_value = values_by_label["Foreign Currency Deposits"].get(year)
        if fcd_value is not None:
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": f"{year}-Annual",
                "indicator": INDICATOR,
                "value": fcd_value,
                "updated_at": now,
            })
        if all(v is not None for v in component_values):
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": f"{year}-Annual",
                "indicator": INDICATOR_TD,
                "value": round(sum(component_values), 2),
                "updated_at": now,
            })

    return pd.DataFrame(rows)
