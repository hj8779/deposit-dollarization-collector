"""Bangladesh: Bangladesh Bank 'Time Series Data' 통합 XLSX(econdata 페이지 안에 특별한 안내 없이
박혀 있는 직접 링크: /econdata/time_series_data1972-2024.xlsx). 다운로드 URL에 직접 GET을 하면
봇 방어 챌린지(TSPD) HTML이 내려오므로 Playwright로 실제 다운로드 이벤트를 받아야 한다
(page.goto()가 다운로드 시작 시 예외를 던지는 것도 Playwright의 정상 동작이라 감안해야 함).

시트 'Table IA' 안에 서로 다른 시대의 소표(sub-table) 5개가 세로로 이어붙어 있고, 표마다
컬럼 구성이 전혀 다르다(연도가 지날수록 컬럼이 늘어난다). '외화예금' 항목은 세 번째~다섯 번째
소표에만 있고(첫 번째/두 번째 소표=1971-72~1987-88에는 이 항목 자체가 없음), 라벨도 시대별로
다르다:
    소표3(1988-89~2019-20): 'Foreign Currency Deposit Liabilities'
    소표4(2020-21):          'Short Term FC Deposit Liabilities'
    소표5(2021-22~2023-24):  'Short Term FC Deposit Liabilities'

주의: 세 소표 모두 우연히 같은 컬럼(39번, 엑셀 열 AM)에 위치하지만, **컬럼 인덱스를 고정값으로
쓰면 안 된다.** 두 번째 소표(DMBs Borrowings, 1972-73~1987-88)는 컬럼 39가 하필 'From
Inter-Banks'(은행간 차입금 - 외화예금과 무관)라서, 인덱스만 믿고 전 구간을 긁으면 1974~1987년치가
완전히 엉뚱한 지표 값으로 섞여 들어간다(실제로 처음엔 이렇게 구현했다가 잘못된 값을 걸러내며
발견했다). 그래서 매 소표마다 헤더 텍스트('Foreign Currency Deposit'/'FC Deposit'을 포함하는 셀)를
직접 찾아 그 열 번호를 쓰고, 해당 헤더가 없는 소표는 건너뛴다.

기간은 방글라데시 회계연도(7월~익년6월, 'YYYY-YY' 또는 최근엔 'P'=잠정치 접미사)라 정확한
월 단위 매핑이 안 되므로 시작연도 기준 '{year}-Annual'로 표기한다.

TD(총예금) = 'Total Deposit Liabilities (37+38)' 열. 세 소표 모두 FCD 헤더 바로 다음 열
(col+1)에 위치하며, 수식 그대로 col37(DMBs Deposits, 자국통화 예금) + col38(FCD) 합계다.
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_SHEET_NAME = "Table IA"
_FY_RE = re.compile(r"^(\d{4})-\d{2}P?\s*$")
_HEADER_RE = re.compile(r"foreign currency deposit|fc deposit", re.I)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BGD는 render()를 통해 처리한다 (다운로드에 Playwright 필요)")


def _download_xlsx(country_code: str) -> bytes:
    from playwright.sync_api import sync_playwright

    file_url = "https://www.bb.org.bd/econdata/time_series_data1972-2024.xlsx"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        )
        page = context.new_page()
        try:
            with page.expect_download(timeout=30000) as dl_info:
                try:
                    page.goto(file_url, timeout=30000)
                except Exception:
                    pass  # 다운로드가 시작되면 goto()가 예외를 던지는 게 Playwright 정상 동작
            download = dl_info.value
            path = f"/tmp/{country_code.lower()}_time_series.xlsx"
            download.save_as(path)
        finally:
            browser.close()

    return open(path, "rb").read()


def render(target: dict) -> pd.DataFrame:
    import openpyxl

    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    content = _download_xlsx(country_code)
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    ws = wb[_SHEET_NAME]

    # 1) 'Foreign Currency Deposit' / 'FC Deposit' 헤더가 등장하는 (행, 열) 전부 찾는다.
    header_hits = []
    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            if isinstance(v, str) and _HEADER_RE.search(v):
                header_hits.append((r, c))

    if not header_hits:
        logger.warning("[%s] 'Foreign Currency Deposit' 헤더를 찾지 못함", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    # 1-1) 'Total Deposit Liabilities' 헤더(FCD 헤더 바로 다음 열)도 찾는다.
    td_col_by_header_row: dict[int, int] = {}
    for header_row, col in header_hits:
        next_header = ws.cell(row=header_row, column=col + 1).value
        if isinstance(next_header, str) and "total" in next_header.lower() and "deposit" in next_header.lower():
            td_col_by_header_row[header_row] = col + 1

    # 2) 각 헤더 아래로 내려가며 회계연도 행(col1)을 만나는 동안 해당 열의 값을 수집.
    #    'Note:'/'Source:' 등 각주 행에서 멈춘다.
    rows = []
    for header_row, col in header_hits:
        td_col = td_col_by_header_row.get(header_row)
        r = header_row + 1
        while r <= ws.max_row:
            label = ws.cell(row=r, column=1).value
            if isinstance(label, str) and label.strip().lower().startswith(("note", "source")):
                break
            if isinstance(label, str):
                m = _FY_RE.match(label.strip())
                if m:
                    year = int(m.group(1))
                    period = f"{year}-Annual"
                    value = ws.cell(row=r, column=col).value
                    if isinstance(value, (int, float)):
                        rows.append({
                            "country_code": country_code,
                            "year": year,
                            "period": period,
                            "indicator": INDICATOR,
                            "value": round(float(value), 2),
                            "updated_at": now,
                        })
                    if td_col is not None:
                        td_value = ws.cell(row=r, column=td_col).value
                        if isinstance(td_value, (int, float)):
                            rows.append({
                                "country_code": country_code,
                                "year": year,
                                "period": period,
                                "indicator": INDICATOR_TD,
                                "value": round(float(td_value), 2),
                                "updated_at": now,
                            })
            r += 1
            if r - header_row > 60:  # 안전장치: 소표 하나가 이렇게 길 리 없음
                break

    if not rows:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    df = pd.DataFrame(rows).drop_duplicates(subset=["period", "indicator"], keep="last")
    return df.sort_values("period").reset_index(drop=True)
