"""Malawi: sheet 'Depository Corporations Survey', row3=날짜 헤더(col B~),
row29='Foreign currency denominated deposits'.

TD(총예금) = row26(Demand Deposits) + row28(Time and savings deposits) + row29(FCD).
실측 검증: M1(row24)=Currency(row25)+Demand(row26), QM(row27)=Time(row28)+FCD(row29),
Broad Money(row17)=Currency(row18)+Transferable(row19)+Other(row20)+Securities(row21)+
Liabilities to other sectors(row22) 항등식이 모두 성립함을 확인했다.

과거 확장(연간, 2026-08-19 사용자 제보): DCS 기반 위 시리즈는 2018-04부터만 있다.
RBM Annual Reports(https://www.rbm.mw/Publications/AnnualReports/, 하단 페이지네이션이
JS라 Playwright로 클릭 필요) 부록의 'Table N: Commercial Banks: Assets and Liabilities
(K'mn)' 표에 연도별 7개년 롤링 컬럼이 있고 '1.4 Private sector deposits'(TD)/
'1.4.3 Foreign Currency deposits'(FCD) 행이 그대로 있어, 2018년판(2012-2018 커버)과
2025년판(2019-2025 커버) 딱 2개 보고서만으로 2012-2025 전체를 커버한다(사용자가 알려준
2016~2025년판 10개 중 실제로 필요한 건 양끝 2개뿐). 'Commercial Banks'(이 표) vs
'Depository Corporations'(DCS, RBM 포함 전체 예금취급기관) 범위가 살짝 달라 2018년 값이
정확히 일치하진 않음(연차보고서 TD=978,375/FCD=187,762→ratio 19.19% vs DCS
TD=1,008,469/FCD=199,884→ratio 19.82%, 근접하나 동일하진 않음) — 그래서 DCS가 커버하는
2018-04 이후는 DCS를 우선하고, 그 이전(2012~2017)에만 연차보고서 값을 쓴다."""

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD

FILE_URL = "__RENDER__"

_ANNUAL_REPORT_PDFS = [
    "https://www.rbm.mw/Home/GetContentFile/?ContentID=29891",  # 2018 report: 2012-2018
    "https://www.rbm.mw/Home/GetContentFile/?ContentID=63680",  # 2025 report: 2019-2025
]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    ws = wb["Depository Corporations Survey"]
    now = datetime.now(timezone.utc).isoformat()

    HEADER_ROW = 3
    FCD_ROW = 29
    DEMAND_ROW = 26
    TIME_SAVINGS_ROW = 28
    FIRST_DATA_COL = 2

    rows = []
    for c in range(FIRST_DATA_COL, ws.max_column + 1):
        date = ws.cell(row=HEADER_ROW, column=c).value
        if date is None:
            break
        if not isinstance(date, datetime):
            continue
        period = f"{date.year}-{date.month:02d}"

        fcd = ws.cell(row=FCD_ROW, column=c).value
        if isinstance(fcd, (int, float)):
            rows.append({
                "country_code": country_code,
                "year": date.year,
                "period": period,
                "indicator": INDICATOR,
                "value": float(fcd),
                "updated_at": now,
            })

        demand = ws.cell(row=DEMAND_ROW, column=c).value
        time_savings = ws.cell(row=TIME_SAVINGS_ROW, column=c).value
        if isinstance(fcd, (int, float)) and isinstance(demand, (int, float)) and isinstance(time_savings, (int, float)):
            rows.append({
                "country_code": country_code,
                "year": date.year,
                "period": period,
                "indicator": INDICATOR_TD,
                "value": float(demand) + float(time_savings) + float(fcd),
                "updated_at": now,
            })
    return pd.DataFrame(rows)


import re

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE_MARKER_RE = re.compile(r"Commercial Banks:\s*Assets and Liabilities", re.I)
_YEAR_HEADER_RE = re.compile(r"(?:^|\bLIABILITIES\s+)((?:20\d{2}\s*){2,8})$")
_TD_LABEL_RE = re.compile(r"^1\.4\s+Private sector deposits")
_FCD_LABEL_RE = re.compile(r"^1\.4\.3\s+Foreign Currency deposits")
_NUM_RE = re.compile(r"-?[\d,]+\.\d+|-")


def _parse_annual_report(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber
    from io import BytesIO as _BIO

    now = datetime.now(timezone.utc).isoformat()
    with pdfplumber.open(_BIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not (_TABLE_MARKER_RE.search(text) and "Foreign Currency deposits" in text):
                continue
            lines = text.splitlines()
            years: list[int] | None = None
            for line in lines:
                m = _YEAR_HEADER_RE.search(line.strip())
                if m:
                    years = [int(y) for y in re.findall(r"20\d{2}", m.group(1))]
                    break
            if not years:
                continue
            n = len(years)

            def row_vals(pattern: re.Pattern) -> list[float] | None:
                for line in lines:
                    if pattern.match(line.strip()):
                        nums = [
                            (0.0 if t == "-" else float(t.replace(",", "")))
                            for t in _NUM_RE.findall(line)
                        ]
                        if len(nums) >= n:
                            return nums[-n:]
                return None

            td_vals = row_vals(_TD_LABEL_RE)
            fcd_vals = row_vals(_FCD_LABEL_RE)
            if not (td_vals and fcd_vals):
                continue

            rows = []
            for year, td, fcd in zip(years, td_vals, fcd_vals):
                if td <= 0 or fcd < 0:
                    continue
                period = f"{year}-12"
                ratio = round((fcd / td) * 100, 4)
                for indicator, value in ((INDICATOR, round(fcd, 4)), (INDICATOR_TD, round(td, 4)), ("FCD_TD_RATIO", ratio)):
                    rows.append({
                        "country_code": country_code, "year": year, "period": period,
                        "indicator": indicator, "value": value, "updated_at": now,
                    })
            if rows:
                return pd.DataFrame(rows)
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
    frames = []

    for url in _ANNUAL_REPORT_PDFS:
        try:
            resp = requests.get(url, headers=headers, timeout=120, verify=False)
            resp.raise_for_status()
            ar = _parse_annual_report(resp.content, country_code)
            if not ar.empty:
                logger.info("[%s] annual %s -> %s", country_code, url.split("ContentID=")[-1], sorted(ar["period"].unique()))
                frames.append(ar)
        except Exception as e:
            logger.warning("[%s] annual report 실패: %s", country_code, e)

    src = target.get("source_url")
    if src:
        try:
            resp = requests.get(src, headers=headers, timeout=90, verify=False)
            resp.raise_for_status()
            dcs = parse(resp.content, country_code)
            if not dcs.empty:
                logger.info("[%s] DCS %d rows (%s~%s)", country_code, len(dcs), dcs["period"].min(), dcs["period"].max())
                frames.append(dcs)
        except Exception as e:
            logger.warning("[%s] DCS xlsx 실패: %s", country_code, e)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    # 연차보고서 먼저, DCS 나중 concat → drop_duplicates(keep='last')로
    # 겹치는 달(2018-04~)은 더 정밀한 DCS 값이 우선하도록.
    out = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] merged %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
