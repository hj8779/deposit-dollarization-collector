"""Thailand: Bank of Thailand statistics portal, table EC_MB_004_S2 "Monetary
Aggregates and Components" (app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=7).

ASP.NET WebForms 포스트백 페이지라 일반 requests로는 못 받고 Playwright로 브라우저
조작이 필요하다: 기본 화면은 최근 6개월만 보여주는데, 'From' 연/월 드롭다운(#drpFromYear,
#drpFromMonth)을 2003년 1월(이 표의 시작월)로 설정하고 #btnSubmit을 눌러 전체 기간을
로드한 뒤, CSV 내보내기 버튼(#imbExportText, ASP.NET 이미지버튼이라 클릭하면 바로
다운로드가 시작됨)을 눌러 받는다.

TD = Broad Money(1행) − Currency outside DCs & Central Gov.(3행) (= Transferable
Deposits + Quasi-money, 즉 현금을 제외한 전체 예금성 부채. Broad Money 산식과 정확히
일치함을 확인). FCD = 'Foreign Currency Deposits' 두 행의 합(상업은행 몫 + specialized
banks 몫 - 이 표는 예금기관 유형별로 같은 라벨의 행이 반복되는 구조라 첫 두 개를 그대로
합산). 월간, 2003-01부터. 단위 백만 바트."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_REPORT_URL = "https://app.bot.or.th/BTWS_STAT/statistics/BOTWEBSTAT.aspx?reportID=7&language=ENG"
_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
_PERIOD_HEADER_RE = re.compile(r"([A-Z]{3})\s+(\d{4})")


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("THA는 render()로 Playwright를 통해 CSV를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _download_csv() -> str | None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(_REPORT_URL, timeout=45000, wait_until="networkidle")
            page.wait_for_timeout(1500)
            page.select_option("#drpFromYear", "2003xxxx")
            page.select_option("#drpFromMonth", "xxxx01xx")
            page.click("#btnSubmit")
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_selector("#imbExportText", timeout=10000)
            page.wait_for_timeout(1000)
            with page.expect_download(timeout=20000) as dl_info:
                page.click("#imbExportText")
            download = dl_info.value
            path = download.path()
            if not path:
                return None
            with open(path, "rb") as f:
                return f.read().decode("utf-8-sig")
        except Exception:
            logger.warning("[THA] BOT 포털 다운로드 실패", exc_info=True)
            return None
        finally:
            browser.close()


def _parse_csv(text: str, country_code: str) -> pd.DataFrame:
    rows = list(csv.reader(StringIO(text)))
    header_row = None
    for r in rows:
        if len(r) > 2 and _PERIOD_HEADER_RE.search(r[2] or ""):
            header_row = r
            break
    if header_row is None:
        return _empty()

    periods = []
    for cell in header_row[2:]:
        m = _PERIOD_HEADER_RE.search(cell)
        if not m:
            periods.append(None)
            continue
        month = _MONTHS.get(m.group(1))
        year = int(m.group(2))
        periods.append(f"{year}-{month:02d}" if month else None)

    def find_row(label: str) -> list[str] | None:
        for r in rows:
            if len(r) > 1 and r[1].strip() == label:
                return r[2:]
        return None

    def find_all_rows(label: str) -> list[list[str]]:
        return [r[2:] for r in rows if len(r) > 1 and r[1].strip() == label]

    broad_money = find_row("Broad Money (1+2)")
    currency = find_row("1.1 Currency outside DCs & Central Gov.")
    fcd_rows = find_all_rows("Foreign Currency Deposits")
    if not broad_money or not currency or not fcd_rows:
        logger.warning("[%s] 필요한 행을 못 찾음 (broad_money=%s currency=%s fcd_rows=%d)",
                        country_code, bool(broad_money), bool(currency), len(fcd_rows))
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    out_rows = []
    for i, period in enumerate(periods):
        if not period:
            continue
        try:
            bm = float(broad_money[i])
            cur = float(currency[i])
            fcd = sum(float(fr[i]) for fr in fcd_rows if i < len(fr) and fr[i] not in ("", None))
        except (ValueError, IndexError):
            continue
        td = bm - cur
        if td <= 0:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
            out_rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })

    if not out_rows:
        return _empty()

    out = (
        pd.DataFrame(out_rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    text = _download_csv()
    if not text:
        return _empty()
    return _parse_csv(text, country_code)
