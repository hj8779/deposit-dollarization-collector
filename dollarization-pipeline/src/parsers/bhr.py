"""Bahrain: CBB(Central Bank of Bahrain) Publications 페이지 'Statistical Bulletin' 섹션에
매월 별도 xlsx(2016-12~)/xls(2010-12~2015-12, 연말판만) 파일이 게시된다. 2020-01 이후는
매달 파일이 있지만 그 이전(2010-12~2019-12)은 12월(연말)판만 남아있다 — 즉 2020년 이후는
월별, 그 이전은 연 1개 스냅샷만 확보 가능. 2010-12 이전(2001~2009)은 xls/xlsx가 없고 PDF만
있는데, 아래 설명대로 PDF도 함께 수집해 확장한다.

시트: 'Deposit Liabilities to Non-Banks' 표(제목 텍스트로 매 파일마다 동적으로 시트를 찾는다 —
tab 번호가 시기별로 다르다: 2010~2015년엔 '17'/'18', 2016~2023년엔 '18', 2026년엔 '19' 등 표가
하나씩 추가/삭제되며 뒤로 밀림). 참고로 tab '17'은 시기에 따라 전혀 다른 표('Assets by
Currency' 등)일 수 있으므로 반드시 제목으로 찾아야 한다.

2010-12 이전(월별 xls/xlsx가 없는 구간)은 같은 'Statistical Bulletin' 섹션에 게시된 PDF(파일명이
'MSB-Dec2011.pdf' / 'QSB Dec 2007.pdf' / 'dec_2001.pdf' 등 극도로 불규칙 — 월/연도 표기 방식이
파일마다 달라 파일명으로는 기간을 신뢰할 수 없음)에서 추출한다. 다행히 표 자체는 xlsx와 완전히
동일한 구조로 텍스트 추출이 가능하고(pdfplumber의 extract_tables()가 병합-헤더 4행 + 연간 블록 +
분기 블록 + 월간 블록, 총 7행으로 깔끔하게 뽑아냄), 각 셀 안에 줄바꿈으로 여러 기간의 값이 들어있는
구조(예: 월간 블록 한 셀에 'Dec.\nJan.\nFeb....' 13줄)다. 표의 마지막 행이 항상 월간 블록이므로 그
행만 사용한다. 각 PDF의 월간 블록은 발행월 기준 직전 13개월을 담고 있어(연말판만 있어도 해당
연도 전체가 확보됨), 아카이브에 올라온 PDF를 전부 순회하면 기간이 자연히 겹치며 채워진다 —
xlsx/xls 쪽 값이 있는 기간은 그대로 우선하고(더 신뢰도 높은 최신 포맷), PDF는 xlsx/xls로 커버되지
않는 기간만 보충한다.

컬럼 구성(2001년부터 지금까지 동일하게 안정적):
    General Government  BD, FC
    Private Sector Demand   BD, FC
    Private Sector Savings  BD, FC
    Private Sector Time 1/  BD, FC
    (그 뒤로 Total, Foreign Deposits, Total Deposits 컬럼이 이어지나 사용하지 않음)
각 항목의 라벨(Demand/Savings/Time)이 있는 컬럼이 바로 그 항목의 BD 컬럼이고, 그 다음 컬럼이
FC 컬럼이다 — 라벨 텍스트로 매 파일마다 동적으로 컬럼을 찾는다(고정 인덱스를 쓰면 안 됨. 예전엔
Government 유무 등으로 컬럼이 밀릴 수 있음이 다른 표(시트 '3')에서도 확인됨).

TD(총예금) = Private Sector(Demand+Savings+Time)의 BD+FC 합계. General Government는 민간부문이
아니므로 제외(FCD와 scope 일치). FCD = 위 세 항목의 FC 합계(구 파서는 Demand FC만 사용했는데,
Savings/Time도 이 표에서는 통화별로 분리되어 있으므로 훨씬 더 정확한 총 FCD를 얻을 수 있다).

행 구조: 연간(col0=연도, col1=공백) / 분기(col1='Q1'..'Q4', 연도는 Q1행에만, 이후 forward-fill) /
월간(col1='Jan.'..'Dec.', 마찬가지로 연도 forward-fill)이 한 시트에 순서대로 이어진다.
이 파서는 월간 행만 뽑는다(연/분기는 스킵 — 월간이 없는 과거 12월판만 있는 해는 자연히 그 해
12월의 '월간' 행 하나만 잡힌다).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

PUBLICATIONS_URL = "https://www.cbb.gov.bh/publications/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_TITLE = "deposit liabilities to non-banks"
_TITLE_SCAN_ROWS = 8
_HEADER_SCAN_ROWS = range(0, 16)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_LINK_RE = re.compile(r'href="([^"]+\.xlsx?)"')
_PDF_LINK_RE = re.compile(r'href="([^"]+\.pdf)"')


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("BHR은 render()를 통해 처리한다 (매월/매년 게시되는 파일을 전부 순회)")


def _collect_bulletin_links() -> list[str]:
    response = requests.get(PUBLICATIONS_URL, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    html = response.text

    start = html.find('<h2 id="Statistical Bulletin"')
    if start == -1:
        return []
    end = html.find("<h2", start + 10)
    section = html[start:end] if end != -1 else html[start:]

    seen = set()
    links = []
    for url in _LINK_RE.findall(section):
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def _collect_pdf_links() -> list[str]:
    response = requests.get(PUBLICATIONS_URL, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    html = response.text

    start = html.find('<h2 id="Statistical Bulletin"')
    if start == -1:
        return []
    end = html.find("<h2", start + 10)
    section = html[start:end] if end != -1 else html[start:]

    seen = set()
    links = []
    for url in _PDF_LINK_RE.findall(section):
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def _clean_number(text: str) -> float | None:
    text = text.strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_pdf(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber

    now = datetime.now(timezone.utc).isoformat()
    empty = pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            table = None
            for page in pdf.pages:
                text = (page.extract_text() or "").lower()
                if _TITLE not in text:
                    continue
                tables = page.extract_tables()
                if tables and len(tables[0]) >= 5:
                    table = tables[0]
                    break
    except Exception:
        logger.warning("[%s] PDF 파싱 실패, 스킵", country_code)
        return empty

    if table is None:
        return empty

    monthly_row = table[-1]
    if not monthly_row or monthly_row[0] is None:
        return empty

    # 컬럼: 0=기간, 1/2=Government BD/FC, 3/4=Demand BD/FC, 5/6=Savings BD/FC, 7/8=Time BD/FC
    needed_idx = [3, 4, 5, 6, 7, 8]
    if max(needed_idx) >= len(monthly_row) or any(monthly_row[i] is None for i in needed_idx):
        return empty

    period_lines = str(monthly_row[0]).split("\n")
    value_cols = [str(monthly_row[i]).split("\n") for i in needed_idx]
    n = len(period_lines)
    if any(len(vc) != n for vc in value_cols):
        return empty

    rows = []
    current_year = None
    for i, line in enumerate(period_lines):
        m = re.match(r"^\s*(\d{4})\s+(.+?)\.?\s*$", line)
        if m:
            current_year = int(m.group(1))
            month_token = m.group(2)
        else:
            month_token = line
        if current_year is None:
            continue

        month_key = month_token.strip().rstrip(".").lower()[:3]
        month = _MONTHS.get(month_key)
        if month is None:
            continue

        values = [_clean_number(vc[i]) for vc in value_cols]
        if any(v is None for v in values):
            continue
        demand_bd_v, demand_fc_v, savings_bd_v, savings_fc_v, time_bd_v, time_fc_v = values

        fcd = demand_fc_v + savings_fc_v + time_fc_v
        td = demand_bd_v + demand_fc_v + savings_bd_v + savings_fc_v + time_bd_v + time_fc_v
        period = f"{current_year}-{month:02d}"

        rows.append({
            "country_code": country_code, "year": current_year, "period": period,
            "indicator": INDICATOR, "value": round(float(fcd), 4), "updated_at": now,
        })
        rows.append({
            "country_code": country_code, "year": current_year, "period": period,
            "indicator": INDICATOR_TD, "value": round(float(td), 4), "updated_at": now,
        })

    return pd.DataFrame(rows)


def _grid_from_xlsx(content: bytes) -> dict[str, list[list]]:
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    grids = {}
    for name in wb.sheetnames:
        ws = wb[name]
        grids[name] = [
            [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
            for r in range(1, ws.max_row + 1)
        ]
    return grids


def _grid_from_xls(content: bytes) -> dict[str, list[list]]:
    import xlrd

    wb = xlrd.open_workbook(file_contents=content)
    grids = {}
    for name in wb.sheet_names():
        ws = wb.sheet_by_name(name)
        grids[name] = [
            [ws.cell_value(r, c) if ws.cell_value(r, c) != "" else None for c in range(ws.ncols)]
            for r in range(ws.nrows)
        ]
    return grids


def _find_target_grid(grids: dict[str, list[list]]) -> list[list] | None:
    for grid in grids.values():
        for row in grid[:_TITLE_SCAN_ROWS]:
            if not row:
                continue
            cell = str(row[0] or "").strip().lower()
            if _TITLE in cell:
                return grid
    return None


def _find_columns(grid: list[list]) -> dict[str, int] | None:
    cols: dict[str, int] = {}
    for r in _HEADER_SCAN_ROWS:
        if r >= len(grid):
            break
        row = grid[r]
        for c, value in enumerate(row):
            label = str(value or "").strip().lower()
            if label == "demand" and "demand" not in cols:
                cols["demand"] = c
            elif label == "savings" and "savings" not in cols:
                cols["savings"] = c
            elif label.startswith("time") and "time" not in cols:
                cols["time"] = c
        if len(cols) == 3:
            break
    if len(cols) != 3:
        return None
    return cols


def _parse_workbook(content: bytes, country_code: str, is_xls: bool) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()

    try:
        grids = _grid_from_xls(content) if is_xls else _grid_from_xlsx(content)
    except Exception:
        logger.warning("[%s] 워크북 파싱 실패, 스킵", country_code)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    grid = _find_target_grid(grids)
    if grid is None:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    cols = _find_columns(grid)
    if cols is None:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    demand_bd, savings_bd, time_bd = cols["demand"], cols["savings"], cols["time"]

    rows = []
    current_year = None
    for row in grid:
        if not row:
            continue
        year_cell = row[0] if len(row) > 0 else None
        month_cell = row[1] if len(row) > 1 else None

        if isinstance(year_cell, (int, float)):
            current_year = int(year_cell)

        if not isinstance(month_cell, str):
            continue
        month_key = month_cell.strip().rstrip(".").lower()[:3]
        month = _MONTHS.get(month_key)
        if month is None or current_year is None:
            continue

        needed = [demand_bd, demand_bd + 1, savings_bd, savings_bd + 1, time_bd, time_bd + 1]
        if max(needed) >= len(row):
            continue
        values = [row[i] for i in needed]
        if not all(isinstance(v, (int, float)) for v in values):
            continue
        demand_bd_v, demand_fc_v, savings_bd_v, savings_fc_v, time_bd_v, time_fc_v = values

        fcd = demand_fc_v + savings_fc_v + time_fc_v
        td = demand_bd_v + demand_fc_v + savings_bd_v + savings_fc_v + time_bd_v + time_fc_v
        period = f"{current_year}-{month:02d}"

        rows.append({
            "country_code": country_code, "year": current_year, "period": period,
            "indicator": INDICATOR, "value": round(float(fcd), 4), "updated_at": now,
        })
        rows.append({
            "country_code": country_code, "year": current_year, "period": period,
            "indicator": INDICATOR_TD, "value": round(float(td), 4), "updated_at": now,
        })

    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    links = _collect_bulletin_links()
    logger.info("[%s] Statistical Bulletin 파일 %d개 발견", country_code, len(links))

    frames = []
    for url in links:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=30)
            response.raise_for_status()
        except Exception:
            logger.warning("[%s] 다운로드 실패, 스킵: %s", country_code, url)
            continue

        df = _parse_workbook(response.content, country_code, is_xls=url.lower().endswith(".xls"))
        if not df.empty:
            frames.append(df)

    if not frames:
        xlsx_df = pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])
    else:
        # links는 최신 파일이 먼저 나오므로, 동일 기간이 여러 파일에 걸쳐 있으면(개정치 반영 위해)
        # 더 최근에 게시된 파일 쪽 값을 우선한다.
        xlsx_df = pd.concat(frames, ignore_index=True)
        xlsx_df = xlsx_df.drop_duplicates(subset=["period", "indicator"], keep="first")

    covered_periods = set(xlsx_df["period"]) if not xlsx_df.empty else set()

    pdf_links = _collect_pdf_links()
    logger.info("[%s] Statistical Bulletin PDF 파일 %d개 발견(2010-12 이전 보충용)", country_code, len(pdf_links))

    pdf_frames = []
    for url in pdf_links:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=30)
            response.raise_for_status()
        except Exception:
            logger.warning("[%s] PDF 다운로드 실패, 스킵: %s", country_code, url)
            continue

        df = _parse_pdf(response.content, country_code)
        if not df.empty:
            pdf_frames.append(df)

    if pdf_frames:
        pdf_df = pd.concat(pdf_frames, ignore_index=True)
        pdf_df = pdf_df.drop_duplicates(subset=["period", "indicator"], keep="first")
        # xlsx/xls가 이미 커버하는 기간은 그쪽이 더 신뢰도 높은 최신 포맷이므로 덮어쓰지 않는다.
        pdf_df = pdf_df[~pdf_df["period"].isin(covered_periods)]
        merged = pd.concat([xlsx_df, pdf_df], ignore_index=True)
    else:
        merged = xlsx_df

    if merged.empty:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    return merged.sort_values(["period", "indicator"]).reset_index(drop=True)
