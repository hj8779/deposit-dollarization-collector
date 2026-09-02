"""Albania: Bank of Albania 'Sectoral balance sheet of Deposit money banks' 대화형 통계 페이지.

체크박스 트리에서 항목을 고르고 'Show values'를 누르면(2단계):
  1) 먼저 기간(From/To) 선택 UI가 나타남 -> From을 최초 가용월(Dec 2006)로 설정 후
  2) 'Show values'를 다시 누르면 결과가 **새 탭**(?mode=alone)으로 열리고, 그 안에
     실제 값이 담긴 HTML 표가 있음(코드/라벨 뒤에 월별 컬럼이 탭으로 구분됨).

지표 선택: LIABILITIES(부채) 쪽 'Deposits included in broad money'의 통화별 외화 항목 2개
  - 2.1.1.2 Transferable deposits, In foreign currency  (checkbox id=85581)
  - 2.1.2.2 Other deposits, In foreign currency          (checkbox id=85601)
FCD = 2.1.1.2 + 2.1.2.2 (광의통화에 포함되는 은행 외화예금 총액, 백만 Lek)

TD(총예금) = 2.1 Deposits included in broad money (checkbox id=85573), 상위 합계 항목을 그대로 선택.
2.1 = 2.1.1(Transferable deposits) + 2.1.2(Other deposits) 각각의 국내통화+외화 합계이므로
FCD의 상위 총합에 해당함을 결과표에서 실측 확인(2.1 = 2.1.1 + 2.1.2, 2.1.1 = 2.1.1.1 + 2.1.1.2 등).

체크박스 id가 숫자로 시작해 CSS ID 셀렉터(#85581)를 못 쓰므로 속성 셀렉터([id="85581"])를 쓴다.
"""

import re
from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_FCD_CODES = {"2.1.1.2", "2.1.2.2"}
_TD_CODE = "2.1"
_CHECKBOX_IDS = ["85573", "85581", "85601"]

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_PERIOD_RE = re.compile(r"^([A-Za-z]{3})\s*(\d{4})$")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("ALB는 render()를 통해 처리한다 (Playwright 폼 + 새 탭 방식)")


def render(target: dict) -> pd.DataFrame:
    from playwright.sync_api import sync_playwright

    country_code = target["country_code"]
    url = target["source_url"]
    now = datetime.now(timezone.utc).isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            page.locator("#id_select_clear_all").click(force=True)
            page.wait_for_timeout(300)
            for cb_id in _CHECKBOX_IDS:
                page.locator(f'[id="{cb_id}"]').click(force=True)
            page.wait_for_timeout(300)

            # 1차 클릭: 기간 선택 UI 노출
            page.get_by_text("Show values", exact=True).click(force=True)
            page.wait_for_timeout(2000)
            page.locator("select[name=periudha_nga]").select_option(index=0, force=True)  # 최초 가용월
            page.wait_for_timeout(500)

            # 2차 클릭: 결과가 새 탭으로 열림
            with context.expect_page(timeout=15000) as new_page_info:
                page.get_by_text("Show values", exact=True).first.click(force=True)
            result_page = new_page_info.value
            result_page.wait_for_load_state("networkidle")
            result_page.wait_for_timeout(2000)

            table = result_page.locator("table").nth(1)
            lines = table.inner_text().splitlines()
        finally:
            browser.close()

    if not lines:
        logger.warning("[%s] 결과 표를 찾지 못함", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    header = [c.strip() for c in lines[0].split("\t")]
    periods: dict[int, tuple[int, int]] = {}  # col_idx -> (year, month)
    for i, cell in enumerate(header):
        m = _PERIOD_RE.match(cell)
        if not m:
            continue
        month = _MONTHS.get(m.group(1).lower())
        if month:
            periods[i] = (int(m.group(2)), month)

    fcd_totals: dict[int, float] = {}
    td_totals: dict[int, float] = {}
    for line in lines[1:]:
        cells = [c.strip().replace("\xa0", " ").strip() for c in line.split("\t")]
        if not cells:
            continue
        code = cells[0].strip()
        if code in _FCD_CODES:
            target = fcd_totals
        elif code == _TD_CODE:
            target = td_totals
        else:
            continue
        for i, raw in enumerate(cells):
            if i not in periods:
                continue
            raw = raw.replace(",", "").replace("\xa0", "")
            if not raw or raw in ("-", "n.a.", ".."):
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            target[i] = target.get(i, 0.0) + value

    rows = []
    for i, (year, month) in periods.items():
        period = f"{year}-{month:02d}"
        if i in fcd_totals:
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": INDICATOR,
                "value": round(fcd_totals[i], 2),
                "updated_at": now,
            })
        if i in td_totals:
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": INDICATOR_TD,
                "value": round(td_totals[i], 2),
                "updated_at": now,
            })

    return pd.DataFrame(rows).sort_values("period").reset_index(drop=True) if rows else pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )
