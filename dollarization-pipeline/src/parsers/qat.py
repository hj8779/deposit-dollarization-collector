"""Qatar: QCB "Banks Monthly Statement" (BMS) HTML publications
(qcb.gov.qa/en/pages/publication.aspx?indexselect=1 → 'Banks Monthly Statement'
menu item; the URL param doesn't change the page, the link must be clicked so
Playwright is needed to enumerate the actual per-month file list).

각 월 .htm/.html 파일에 은행 통합 대차대조표 표(Liabilities)가 있고, 그중 두 번째 표
(index 1)의 'Customer Deposits' 행에 'Grand Total' 아래 LC(자국통화)/FC(외화)/Total
열이 있다. 2012-12 이전(2007-01~2011-12)은 표 형식이 완전히 달라(코드번호+병합셀) 이
파서가 지원하지 않음 - 자동으로 건너뜀.

TD = Grand Total Total. FCD = Grand Total FC (2019년 이전 일부 파일엔 FC 열이 중복으로
나와 첫 번째 FC 열을 쓴다). 기간은 파일 내용의 표 제목("Liabilities As At YYYY/M ...")에서
추출 - 파일명 패턴이 시기별로 제각각이라(6%20-%202026.html, MBS_March-2024.html,
202212.htm 등) 파일명 대신 문서 내용에서 직접 연월을 읽는다. 단위 천 카타르 리얄."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PUBLICATION_PAGE = "https://www.qcb.gov.qa/en/pages/publication.aspx?indexselect=1"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

_TITLE_DATE_RE = re.compile(r"As At (\d{4})/(\d{1,2})")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("QAT는 render()로 BMS 목록을 순회한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _list_bms_urls() -> list[str]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(_PUBLICATION_PAGE, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            page.click('text="Banks Monthly Statement"')
            page.wait_for_timeout(3000)
            hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            return sorted({h for h in hrefs if "PublicationFilesReportsAndStatementsGovernance" in h and re.search(r"\.html?$", h, re.I)})
        finally:
            browser.close()


def _parse_bms(content: bytes, country_code: str) -> pd.DataFrame:
    try:
        tables = pd.read_html(BytesIO(content))
    except Exception:
        return _empty()
    if len(tables) < 2:
        return _empty()

    t = tables[1]
    title = str(t.iloc[0, 0])
    m = _TITLE_DATE_RE.search(title)
    if not m:
        return _empty()
    year, month = int(m.group(1)), int(m.group(2))
    period = f"{year}-{month:02d}"

    header_row1 = t.iloc[1].astype(str)
    header_row2 = t.iloc[2].astype(str)
    fc_cols = [c for c in t.columns if header_row1.get(c) == "Grand Total" and header_row2.get(c) == "FC"]
    total_cols = [c for c in t.columns if header_row1.get(c) == "Grand Total" and header_row2.get(c) == "Total"]
    if not fc_cols or not total_cols:
        return _empty()

    deposit_rows = t[t[0].astype(str).str.contains("Customer Deposits", na=False)]
    if deposit_rows.empty:
        return _empty()
    row = deposit_rows.iloc[0]

    try:
        fcd = float(row[fc_cols[0]])
        td = float(row[total_cols[0]])
    except (ValueError, TypeError):
        return _empty()
    if td <= 0:
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    ratio = round((fcd / td) * 100, 4)
    rows = [
        {"country_code": country_code, "year": year, "period": period, "indicator": ind, "value": val, "updated_at": now}
        for ind, val in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio))
    ]
    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        urls = _list_bms_urls()
    except Exception:
        logger.exception("[%s] BMS 목록 조회 실패", country_code)
        return _empty()

    logger.info("[%s] BMS 파일 %d건 발견", country_code, len(urls))

    frames = []
    for url in urls:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=60, verify=False)
            resp.raise_for_status()
            df = _parse_bms(resp.content, country_code)
            if not df.empty:
                frames.append(df)
        except Exception:
            logger.warning("[%s] %s 처리 실패", country_code, url, exc_info=True)

    if not frames:
        return _empty()

    out = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
