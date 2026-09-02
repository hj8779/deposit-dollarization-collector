"""Suriname: Central Bank of Suriname (CBvS) 'MonetaryStatistics.xlsx' (Depository Corporations
Survey + Other Depository Corporations Dollarization Ratios 시트).

cbvs.sr 도메인 전체(서브도메인 www/www3 포함, HTML 페이지·이미지 정적 자산 경로 모두)가
Cloudflare 봇 체크(JS challenge)로 보호되어 있어 raw requests는 물론, 안티-디텍션 플래그를 준
Playwright headless Chromium으로도 challenge가 끝없이 재시도되며 통과되지 않는다(확인: 헤더리스
브라우저는 `networkidle`에 결코 도달하지 못하고 45초 타임아웃; `--disable-blink-features=
AutomationControlled` + `navigator.webdriver` 오버라이드를 추가해도 동일).

IMF SDMX API(api.imf.org)의 Depository/Other Depository Corporations Survey(MFS_DC, MFS_ODC)에는
Suriname의 예금 총액(Transferable + Other deposits, 광의통화 포함분)은 매월 존재하지만, 통화별
구분(외화 표시 예금, `_DIC_FC` 계열 인디케이터)은 Suriname에 대해 전혀 보고되지 않는다(빈 데이터셋
확인됨) — 즉 IMF 경로로는 TD는 얻어도 FCD는 얻을 수 없다.

대신 Wayback Machine(web.archive.org)에 CBvS가 실제로 발행한 'MonetaryStatistics.xlsx'가 정기적으로
아카이빙되어 있다(가장 최근 확인된 스냅샷: 2026-07-25, '업데이트: 2026-07-07' 메타데이터 포함,
2006-01 ~ 2026-05월 커버). CDX API로 최신 성공 스냅샷을 조회해 그 시점의 파일을 받아 파싱한다.
이 파일이 CBvS가 실제로 배포한 원본 그대로이므로(단지 접근 경로만 Wayback Machine을 경유) 값 자체를
조작/추정하지 않는다. archive.org는 종종 일시적으로 503을 반환하므로 재시도 로직을 둔다.

파일 내 시트:
  - '3. Dep. Corp. Survey_DCS' ('Table 3'의 신 시트명, 과거 스냅샷은 'Table 3'):
      행 라벨(B열) '   Transferable deposits' + '   Other deposits' 합계 = TD(총예금, SRD 백만).
      (주의: '   Currency outside depository corporations'는 통화이지 예금이 아니므로 제외)
  - '5-2. Dollarization Ratios' (과거 스냅샷은 'Table 5-2'):
      행 라벨(B열) 'Deposit (1)' = 외화예금이 총예금에서 차지하는 비중(%)
      (시트 각주: "Foreign currency deposits in percentage of total deposits.")
  - 두 시트 모두 9행이 날짜 헤더(C열부터 월별 datetime), TD와 ratio는 동일 월 기준.
  - FCD = TD * ratio / 100.

검증: 2017-08 시점 TD=15574.48(=5997.10+9577.39), ratio=69.40% -> FCD≈10,809.4로,
사전 조사에서 확인된 CBvS 발표치(FCD=10,797.2, M2=16,748.0 기준)와 근사 일치
(M2에는 유통 중 통화 등이 추가로 포함되어 완전히 같은 분모는 아님).
"""

import re
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # CDX 조회 후 Wayback Machine에서 파일을 받아야 하므로 단일 파일 다운로드가 아니다.

_ORIGIN_URL = "https://www.cbvs.sr/images/content/statistieken/Database/MonetaryStatistics.xlsx"
_CDX_URL = (
    "https://web.archive.org/cdx/search/cdx"
    "?url=cbvs.sr/images/content/statistieken/Database/MonetaryStatistics.xlsx"
    "&output=json&filter=statuscode:200&collapse=digest"
)
_SNAPSHOT_URL_TMPL = "https://web.archive.org/web/{timestamp}/{original}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

_DCS_SHEET_RE = re.compile(r"dep\.?\s*corp\.?\s*survey|depository corporations survey", re.I)
_RATIO_SHEET_RE = re.compile(r"dollariz", re.I)
_TRANSFERABLE_RE = re.compile(r"^\s*transferable deposits\s*$", re.I)
_OTHER_DEPOSITS_RE = re.compile(r"^\s*other deposits\s*$", re.I)
_DEPOSIT_RATIO_RE = re.compile(r"^\s*deposit\b", re.I)

_LONG_COLUMNS = ["country_code", "year", "period", "indicator", "value", "updated_at"]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SUR은 render()를 통해 처리한다 (Wayback Machine 스냅샷 조회가 필요)")


def _fetch_with_retry(url: str, attempts: int = 5, timeout: int = 60) -> bytes | None:
    for i in range(attempts):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                return resp.content
            logger.info("[SUR] %s -> HTTP %s (시도 %d/%d)", url, resp.status_code, i + 1, attempts)
        except requests.RequestException as exc:
            logger.info("[SUR] %s -> 요청 실패: %s (시도 %d/%d)", url, exc, i + 1, attempts)
        if i < attempts - 1:
            import time

            time.sleep(5 * (i + 1))
    return None


def _list_snapshots() -> list[tuple[str, str]]:
    """CDX API로 (timestamp, original_url) 목록을 최신순으로 반환한다."""
    raw = _fetch_with_retry(_CDX_URL, attempts=5, timeout=30)
    if raw is None:
        return []
    import json

    rows = json.loads(raw.decode("utf-8", errors="ignore"))
    if not rows or len(rows) < 2:
        return []
    header, *data = rows
    ts_idx = header.index("timestamp")
    orig_idx = header.index("original")
    snapshots = [(r[ts_idx], r[orig_idx]) for r in data]
    snapshots.sort(key=lambda x: x[0], reverse=True)
    return snapshots


def _find_row(ws, pattern: re.Pattern, label_col: int = 2) -> int | None:
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=label_col).value
        if v and pattern.match(str(v)):
            return r
    return None


def _find_sheet(wb, pattern: re.Pattern):
    for name in wb.sheetnames:
        if pattern.search(name):
            return wb[name]
    return None


def _header_dates(ws, header_row: int, start_col: int = 3) -> dict[int, datetime]:
    dates = {}
    for c in range(start_col, ws.max_column + 1):
        v = ws.cell(row=header_row, column=c).value
        if isinstance(v, datetime):
            dates[c] = v
    return dates


def _parse_workbook(content: bytes, country_code: str) -> pd.DataFrame:
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)

    dcs_ws = _find_sheet(wb, _DCS_SHEET_RE)
    ratio_ws = _find_sheet(wb, _RATIO_SHEET_RE)
    if dcs_ws is None or ratio_ws is None:
        logger.warning(
            "[SUR] 필요한 시트를 찾지 못함 (dcs=%s, ratio=%s), 시트 목록: %s",
            dcs_ws is not None, ratio_ws is not None, wb.sheetnames,
        )
        return pd.DataFrame(columns=_LONG_COLUMNS)

    transferable_row = _find_row(dcs_ws, _TRANSFERABLE_RE)
    other_row = _find_row(dcs_ws, _OTHER_DEPOSITS_RE)
    ratio_row = _find_row(ratio_ws, _DEPOSIT_RATIO_RE)
    if not (transferable_row and other_row and ratio_row):
        logger.warning(
            "[SUR] 필요한 행을 찾지 못함 (transferable=%s, other=%s, ratio=%s)",
            transferable_row, other_row, ratio_row,
        )
        return pd.DataFrame(columns=_LONG_COLUMNS)

    # 날짜 헤더 행(두 시트 모두 동일한 레이아웃: 9행에서 시작하는 것이 표준이나,
    # 스냅샷마다 안내 문구 줄 수가 달라질 수 있어 datetime 셀이 나오는 행을 직접 탐색한다.
    def _find_header_row(ws) -> int | None:
        for r in range(1, min(20, ws.max_row) + 1):
            if isinstance(ws.cell(row=r, column=3).value, datetime):
                return r
        return None

    dcs_header_row = _find_header_row(dcs_ws)
    ratio_header_row = _find_header_row(ratio_ws)
    if dcs_header_row is None or ratio_header_row is None:
        logger.warning("[SUR] 날짜 헤더 행을 찾지 못함")
        return pd.DataFrame(columns=_LONG_COLUMNS)

    dcs_dates = _header_dates(dcs_ws, dcs_header_row)
    ratio_dates = _header_dates(ratio_ws, ratio_header_row)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for col, dt in dcs_dates.items():
        ratio_col = next((c for c, d in ratio_dates.items() if d.year == dt.year and d.month == dt.month), None)
        if ratio_col is None:
            continue

        transferable = dcs_ws.cell(row=transferable_row, column=col).value
        other = dcs_ws.cell(row=other_row, column=col).value
        ratio = ratio_ws.cell(row=ratio_row, column=ratio_col).value
        if transferable is None or other is None or ratio is None:
            continue
        if not all(isinstance(v, (int, float)) for v in (transferable, other, ratio)):
            continue

        td = round(transferable + other, 4)
        fcd = round(td * ratio / 100, 4)
        period = f"{dt.year}-{dt.month:02d}"

        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", round(ratio, 4))):
            rows.append({
                "country_code": country_code,
                "year": dt.year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    df = pd.DataFrame(rows, columns=_LONG_COLUMNS)
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    df = df.sort_values(["period", "indicator"]).reset_index(drop=True)
    return df


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    snapshots = _list_snapshots()
    if not snapshots:
        logger.warning("[%s] Wayback Machine CDX 조회 실패 또는 스냅샷 없음", country_code)
        return pd.DataFrame(columns=_LONG_COLUMNS)

    for timestamp, original in snapshots:
        url = _SNAPSHOT_URL_TMPL.format(timestamp=timestamp, original=original)
        content = _fetch_with_retry(url, attempts=5, timeout=90)
        if content is None:
            logger.info("[%s] 스냅샷 %s 다운로드 실패, 다음 스냅샷 시도", country_code, timestamp)
            continue
        try:
            df = _parse_workbook(content, country_code)
        except Exception:
            logger.exception("[%s] 스냅샷 %s 파싱 실패, 다음 스냅샷 시도", country_code, timestamp)
            continue
        if not df.empty:
            logger.info("[%s] 스냅샷 %s(원본 %s) 파싱 성공, %d행", country_code, timestamp, original, len(df))
            return df

    logger.warning("[%s] 모든 스냅샷에서 파싱 실패", country_code)
    return pd.DataFrame(columns=_LONG_COLUMNS)
