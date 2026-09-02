"""Denmark: Danmarks Nationalbank의 Statbank(구형 PC-Axis/StatBank5a ASP 플랫폼, PxWeb API
없음) 테이블 'DNPINDK: Domestic deposits in banks by instrument, data type, domestic sector,
currency and maturity'. 변수 선택 화면이 iframe 안에 있고, 제출 결과도 iframe 안에 인라인
렌더링되며(URL만 saveselections.asp로 보임), CSV 등 내보내기는 <select> 안의 <option>이라
클릭이 아니라 select_option으로 선택해야 다운로드 이벤트가 발생한다 - 그래서 매번
Playwright로 이 상호작용 흐름을 그대로 재현한다.

선택값: Instrument=Deposits in total, Data type=Outstanding amounts (DKK million),
Domestic sector=1000: All domestic sectors(전체 거주자 부문 합계), Currency=Foreign currency
in total(DKK 제외 전체 외화 합계), Maturity=All maturities, Time=전체 월(2003-01~현재).
이렇게 필터링하면 결과 표에 시계열이 'Deposits in total' 행 하나만 남아 FCD 그 자체다.

TD(총예금) = Currency 필터만 'All currencies'(DKK 포함 전체 통화 합계)로 바꿔 동일하게
조회한 값. 같은 select(index 7)에 'All currencies' 옵션이 그대로 존재해 FCD와 완전히
동일한 조회 흐름을 재사용할 수 있다.
"""

import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

TABLE_URL = "https://nationalbanken.statbank.dk/DNPINDK"
_CSV_EXPORT_OPTION_VALUE = "8"  # 'Comma sep. (*.csv)'

_MONTH_COL_RE = re.compile(r'"?(\d{4})M(\d{2})"?')


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("DNK는 render()를 통해 처리한다 (Statbank ASP 폼 자동화 필요)")


def _download_csv(currency_label: str, out_path: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(TABLE_URL, timeout=60000)
        page.wait_for_timeout(2000)

        frame = next(f for f in page.frames if "selectvarval" in f.url)
        selects = frame.query_selector_all("select")
        selects[1].select_option(label="Deposits in total")
        selects[3].select_option(label="Outstanding amounts (DKK million)")
        selects[5].select_option(label="1000: All domestic sectors")
        selects[7].select_option(label=currency_label)
        selects[9].select_option(label="All maturities")
        frame.eval_on_selector_all(
            "select",
            "(sels) => { const m = sels[11]; for (const o of m.options) o.selected = true; "
            "m.dispatchEvent(new Event('change')); }",
        )
        page.wait_for_timeout(500)
        frame.click("input[name=Forward]")
        page.wait_for_timeout(6000)

        result_frame = next(f for f in page.frames if "saveselections" in f.url)
        with page.expect_download(timeout=20000) as dl_info:
            result_frame.select_option(
                f'select:has(option[value="{_CSV_EXPORT_OPTION_VALUE}"])',
                value=_CSV_EXPORT_OPTION_VALUE,
            )
        download = dl_info.value
        download.save_as(out_path)
        browser.close()

    return open(out_path, "rb").read()


def _parse_csv(content: bytes, country_code: str, indicator: str, now: str) -> pd.DataFrame:
    text = content.decode("latin-1")
    lines = [ln for ln in text.splitlines() if ln.strip()]

    header_line = next((ln for ln in lines if "M01" in ln or "M02" in ln), None)
    data_line = next((ln for ln in lines if "Deposits in total" in ln), None)
    if header_line is None or data_line is None:
        logger.warning("[%s] 헤더 또는 'Deposits in total' 데이터 행을 찾지 못함", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    periods = [f"{y}-{m}" for y, m in _MONTH_COL_RE.findall(header_line)]

    import csv as csvlib

    data_cells = next(csvlib.reader(StringIO(data_line)))
    # 'Deposits in total' 라벨 뒤로 오는 숫자 셀들만 값으로 취급.
    label_idx = next(i for i, c in enumerate(data_cells) if c.strip() == "Deposits in total")
    values = data_cells[label_idx + 1:]

    rows = []
    for period, value_str in zip(periods, values):
        value_str = value_str.strip().strip('"')
        if not value_str or value_str in ("..", "-"):
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue
        rows.append({
            "country_code": country_code,
            "year": int(period[:4]),
            "period": period,
            "indicator": indicator,
            "value": round(value, 2),
            "updated_at": now,
        })

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor

    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    # FCD/TD 두 조회는 서로 독립적인 Playwright 세션이라 병렬로 돌려 벽시계 시간을 절반으로 줄인다
    # (각 조회 자체는 폼 상호작용 대기(wait_for_timeout)가 지배적이라 순차 실행 시 2배로 늘어난다).
    with ThreadPoolExecutor(max_workers=2) as executor:
        fcd_future = executor.submit(_download_csv, "Foreign currency in total", "/tmp/dnk_dnpindk_fcd.csv")
        td_future = executor.submit(_download_csv, "All currencies", "/tmp/dnk_dnpindk_td.csv")
        fcd_content = fcd_future.result()
        td_content = td_future.result()

    fcd_df = _parse_csv(fcd_content, country_code, INDICATOR, now)
    td_df = _parse_csv(td_content, country_code, INDICATOR_TD, now)

    return pd.concat([fcd_df, td_df], ignore_index=True).sort_values(["period", "indicator"]).reset_index(drop=True)
