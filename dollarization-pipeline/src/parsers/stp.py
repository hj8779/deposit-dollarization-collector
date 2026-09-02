"""Sao Tome and Principe: Banco Central de S. Tomé e Príncipe (BCSTP) 웹사이트
'Banco Central > Estatísticas Monetárias e Financeiras' 섹션에서 직접 배포하는
xlsx 파일 'Depósitos Bancários por moeda e tipo_2018-2026.xlsx' 하나를 사용한다.

이 파일은 매월 갱신되며 시트 'DEPÓSITOS BANCÁRIOS'에 상업은행 예금을
거주자/비거주자 x 통화(자국통화/외화) x 부문(공공/비금융법인/가계/비영리단체)별로
분해한 표를 담고 있다(단위: Milhões nDb, 즉 2018년 재화폐화(1000 STD=1 STN) 이후의
신 도브라 백만 단위). 파일 자체가 2018-01부터 시작하므로 재화폐화로 인한 단위
불연속 문제를 자연히 피한다(그 이전 데이터는 이 파일에 없음).

행 구조(라벨은 열 C, 값은 열 D부터 월별로 이어짐, 헤더 날짜는 행 6):
    (1) Residentes                    <- 거주자 예금 총액(자국통화+외화) = TD로 사용
        (1.1) Moeda Nacional          <- 거주자, 자국통화
        (1.2) Moeda Estrangeira       <- 거주자, 외화                    = FCD로 사용
    (2) Não Residentes                <- 비거주자 예금(제외)
    TOTAL((1)+(2))                    <- 거주자+비거주자 합계(제외, 본 프로젝트는 거주자만 대상)

라벨 문자열은 파일마다 선행 공백/들여쓰기가 조금씩 다를 수 있어(예: ' (1) Residentes',
'         (1.1) Moeda Nacional') 정규식으로 괄호 안 번호만 매칭해 탐색하고, 고정 행
번호에 의존하지 않는다. 헤더 행도 '연-월 형태의 datetime 값이 다수 나오는 첫 행'을
탐색해서 찾는다(향후 파일 레이아웃이 한두 행 밀려도 견고하도록).

주의: (1) Residentes 자체는 국제수지 관점의 '총예금'이 아니라 '거주자 예금'만을
가리킨다. 비거주자 예금까지 포함한 은행 전체 예금 총액을 원하면 TOTAL((1)+(2)) 행을
쓰면 되지만, 본 프로젝트의 FCD/TD 지표는 '거주자 외화예금 비중'을 보는 것이 목적이므로
TD도 거주자 기준(행 (1))으로 맞춘다.

과거 확장(2026-08-19 사용자 제보): BCSTP가 별도로 'Agregados Monetários_2001-2026.xlsx'
(통화총량 시계열, 2001-12부터 매월)를 배포한다. 시트 'AGREGADOS MONETÁRIOS'의
M3(=M2+외화예금) - M0의 'Moeda em Circulação'(유통현금) = TD, 'Depósitos em Moeda
Estrangeira' 행 = FCD. 이 파일은 위 예금상세 파일과 달리 **거주자만이 아니라 은행
시스템 전체 기준**이라 개념이 살짝 다르다(2018-01 교차검증: 이 파일 기준 ratio≈28.9%
vs 상세 파일(거주자 전용) 기준 26.57% — 같은 자릿수대로 근접하나 동일하지는 않음).
그래서 상세 파일이 커버하지 않는 2018-01 이전 구간에만 이 통화총량 파일을 보조로 써서
연장한다(겹치는 달은 상세 파일 값을 우선)."""

import re
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_DETAIL_URL = (
    "https://www.bcstp.st/Upload/New_DOC/ES/"
    "Dep%C3%B3sitos%20Banc%C3%A1rios%20por%20moeda%20e%20tipo_2018-2026.xlsx"
)
_AGGREGATES_URL = (
    "https://www.bcstp.st/Upload/New_DOC/ES/"
    "Agregados%20Monet%C3%A1rios_2001-2026.xlsx"
)

_SHEET_NAME = "DEPÓSITOS BANCÁRIOS"
_TD_LABEL_RE = re.compile(r"^\(1\)\s*Residentes")
_FCD_LABEL_RE = re.compile(r"^\(1\.2\)\s*Moeda Estrangeira")

_AGG_SHEET_NAME = "AGREGADOS MONETÁRIOS"
_AGG_LABEL_COL = 2  # column B
_AGG_M3_LABEL_RE = re.compile(r"^M3\b")
_AGG_CURRENCY_LABEL_RE = re.compile(r"^Moeda em Circula")
_AGG_FCD_LABEL_RE = re.compile(r"^Dep[oó]sitos em Moeda Estrangeira")
_LABEL_COL = 3  # column C
_FIRST_DATA_COL = 4  # column D


def _find_header_row(ws) -> int:
    for r in range(1, ws.max_row + 1):
        date_count = sum(
            1
            for c in range(_FIRST_DATA_COL, ws.max_column + 1)
            if isinstance(ws.cell(row=r, column=c).value, datetime)
        )
        if date_count >= 3:
            return r
    raise ValueError("날짜 헤더 행을 찾지 못했습니다")


def _find_label_row(ws, pattern: re.Pattern, max_row: int) -> int | None:
    for r in range(1, max_row + 1):
        label = ws.cell(row=r, column=_LABEL_COL).value
        if isinstance(label, str) and pattern.match(label.strip()):
            return r
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("STP는 render()로 상세/총량 xlsx 두 개를 합친다")


def _parse_detail(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    columns = ["country_code", "year", "period", "indicator", "value", "updated_at"]

    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    if _SHEET_NAME not in wb.sheetnames:
        logger.warning("[%s] 시트 '%s'를 찾지 못했습니다 (시트 목록: %s)", country_code, _SHEET_NAME, wb.sheetnames)
        return pd.DataFrame(columns=columns)
    ws = wb[_SHEET_NAME]

    header_row = _find_header_row(ws)
    td_row = _find_label_row(ws, _TD_LABEL_RE, ws.max_row)
    fcd_row = _find_label_row(ws, _FCD_LABEL_RE, ws.max_row)

    if td_row is None or fcd_row is None:
        logger.warning("[%s] TD(%s)/FCD(%s) 라벨 행을 찾지 못했습니다", country_code, td_row, fcd_row)
        return pd.DataFrame(columns=columns)

    # 실제로 값이 채워진 마지막 열까지만 순회한다.
    last_col = _FIRST_DATA_COL - 1
    for c in range(_FIRST_DATA_COL, ws.max_column + 1):
        if ws.cell(row=header_row, column=c).value is not None:
            last_col = c

    rows = []
    for c in range(_FIRST_DATA_COL, last_col + 1):
        date_val = ws.cell(row=header_row, column=c).value
        if not isinstance(date_val, datetime):
            continue
        td_val = ws.cell(row=td_row, column=c).value
        fcd_val = ws.cell(row=fcd_row, column=c).value
        if td_val is None or fcd_val is None:
            continue

        year = date_val.year
        period = f"{year}-{date_val.month:02d}"
        td = round(float(td_val), 4)
        fcd = round(float(fcd_val), 4)
        ratio = round((fcd / td) * 100, 2) if td else None

        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    return pd.DataFrame(rows, columns=columns)


def _find_agg_label_row(ws, pattern: re.Pattern) -> int | None:
    for r in range(1, ws.max_row + 1):
        label = ws.cell(row=r, column=_AGG_LABEL_COL).value
        if isinstance(label, str) and pattern.match(label.strip()):
            return r
    return None


def _parse_aggregates(content: bytes, country_code: str) -> pd.DataFrame:
    """'Agregados Monetários' 통화총량 파일 — 은행 시스템 전체 기준(거주자 한정 아님).
    TD = M3 - Moeda em Circulação, FCD = Depósitos em Moeda Estrangeira."""
    now = datetime.now(timezone.utc).isoformat()
    columns = ["country_code", "year", "period", "indicator", "value", "updated_at"]

    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    if _AGG_SHEET_NAME not in wb.sheetnames:
        logger.warning("[%s] 시트 '%s'를 찾지 못했습니다 (시트 목록: %s)", country_code, _AGG_SHEET_NAME, wb.sheetnames)
        return pd.DataFrame(columns=columns)
    ws = wb[_AGG_SHEET_NAME]

    header_row = None
    for r in range(1, min(10, ws.max_row) + 1):
        if sum(1 for c in range(3, ws.max_column + 1) if isinstance(ws.cell(row=r, column=c).value, datetime)) >= 3:
            header_row = r
            break
    m3_row = _find_agg_label_row(ws, _AGG_M3_LABEL_RE)
    currency_row = _find_agg_label_row(ws, _AGG_CURRENCY_LABEL_RE)
    fcd_row = _find_agg_label_row(ws, _AGG_FCD_LABEL_RE)
    if not (header_row and m3_row and currency_row and fcd_row):
        logger.warning(
            "[%s] 통화총량 파일 행 미발견 (header=%s m3=%s currency=%s fcd=%s)",
            country_code, header_row, m3_row, currency_row, fcd_row,
        )
        return pd.DataFrame(columns=columns)

    rows = []
    for c in range(3, ws.max_column + 1):
        date_val = ws.cell(row=header_row, column=c).value
        if not isinstance(date_val, datetime):
            continue
        m3 = ws.cell(row=m3_row, column=c).value
        currency = ws.cell(row=currency_row, column=c).value
        fcd_val = ws.cell(row=fcd_row, column=c).value
        if not all(isinstance(v, (int, float)) for v in (m3, currency, fcd_val)):
            continue

        year = date_val.year
        period = f"{year}-{date_val.month:02d}"
        td = round(m3 - currency, 4)
        fcd = round(float(fcd_val), 4)
        if td <= 0 or fcd < 0:
            continue
        ratio = round((fcd / td) * 100, 2)

        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    return pd.DataFrame(rows, columns=columns)


def render(target: dict) -> pd.DataFrame:
    import requests

    country_code = target["country_code"]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}

    frames = []
    try:
        resp = requests.get(_AGGREGATES_URL, headers=headers, timeout=90, verify=False)
        resp.raise_for_status()
        agg = _parse_aggregates(resp.content, country_code)
        if not agg.empty:
            logger.info("[%s] 통화총량 %d rows (%s~%s)", country_code, len(agg), agg["period"].min(), agg["period"].max())
            frames.append(agg)
    except Exception as e:
        logger.warning("[%s] 통화총량 파일 실패: %s", country_code, e)

    try:
        resp = requests.get(_DETAIL_URL, headers=headers, timeout=90, verify=False)
        resp.raise_for_status()
        detail = _parse_detail(resp.content, country_code)
        if not detail.empty:
            logger.info("[%s] 상세 %d rows (%s~%s)", country_code, len(detail), detail["period"].min(), detail["period"].max())
            frames.append(detail)
    except Exception as e:
        logger.warning("[%s] 상세 파일 실패: %s", country_code, e)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    # 통화총량 먼저, 상세 파일 나중 concat → drop_duplicates(keep='last')로
    # 겹치는 달(2018-01~)은 거주자-기준 상세 값이 우선하도록.
    out = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] merged %d rows (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
