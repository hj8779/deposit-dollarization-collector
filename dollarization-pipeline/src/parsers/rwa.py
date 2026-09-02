"""Rwanda: National Bank of Rwanda(BNR) 'Depository Corporations Survey' XLSX.

bnr.rw는 React SPA(정적 HTML에 데이터/파일 링크 없음)라 원래 저장돼 있던
`https://www.bnr.rw/index.php?id=46`는 더 이상 유효하지 않다. 실제 데이터는 SPA가 호출하는
JSON 엔드포인트 뒤에 있다:

    GET https://www.bnr.rw/mstat
        -> [{"name": "Depository corporation survey <Month> <Year>",
             "file": "/documents/Depository_corporation_survey_<Month>_<Year>.xlsx",
             "category_id": 16, ...},
            {"name": "Central bank survey ...", ...},
            {"name": "Other depository corporation survey ...", ...}]

이 엔드포인트는 페이지네이션/과거이력 없이 항상 "현재 게시된 최신 파일 3종"만 반환한다. 그 중
이름이 'Depository corporation survey'로 시작하는 항목(전체 예금취급기관 통합 서베이,
category_id=16)의 xlsx를 받는다.

다만 파일 URL 자체(`/documents/Depository_corporation_survey_<Mon>_<year>.xlsx`)는 예측 가능한
패턴이고, 실측 결과 /mstat이 더 이상 나열하지 않는 과거 달의 파일도 서버에는 최근 ~12개월
가량은 그대로 남아있음을 확인했다(2015~2024년 옛 파일은 이미 삭제돼 없음 — 완전한 과거 아카이브는
아니고 딱 최근 롤링 구간만). 그래서 /mstat 최신 항목뿐 아니라 최근 24개월치 URL을 직접 패턴으로
만들어 존재 여부를 확인·다운로드한다 — 파이프라인이 매달 정확히 실행되지 않아도 그 사이 빠진
달을 이 방식으로 메울 수 있다.

xlsx는 시트 'DCs' 1개, 헤더 행(월말 날짜, datetime)이 가로로 나열되고 그 아래 행 라벨(1열)에
계정과목이 들여쓰기로 위계 표시된다. 필요한 두 행:
    'Deposits'                    (Broad money M2의 'Money M1' 하위, 'Currency in circulation'
                                    다음 행) = TD(총예금, 거주자 예금취급기관 대상 전체 통화)
    'Foreign currency deposits'   (위 'Deposits' 아래, Rwf 예금과의 통화별 분해) = FCD
주의: 'Deposits'라는 라벨이 표 상단(Central government (net) 하위, row15 부근)에도 별도로
나오는데 이는 정부의 중앙은행 예금(자산 측 상계 항목)이라 TD가 아니다. 그래서 앵커로 먼저
'Money M1' 라벨을 찾고 그 다음에 나오는 'Deposits' 행만 TD로 채택한다.

값 단위는 Frw billion. 실측 검증(2024-12-31 컬럼): TD=4,850.81, FCD=1,855.60
(ratio≈38.25%) — NISR 'Rwanda Statistical Yearbook 2025'가 보고한 2024-06 스냅샷
(TD=4,850.810bn, FCD=1,855.597bn, 38.25%)과 소수점 수준까지 일치. 즉 같은 계열의 데이터이며
BNR 원본이 월별(실측 파일 기준 2024-12~2026-05, 일부 월 공백)로 더 세밀하다.

파일이 매월 교체되며 오래된 파일 URL은 결국 사라지므로(연도별 아카이브 없음), 이 파서는 /mstat의
최신 항목 + 최근 24개월 URL 패턴 프로브를 함께 수집한다. 파이프라인이 주기적으로 재실행되면서
윈도우가 이동해도 upsert로 시계열이 누적된다.
"""

import json
from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd
import urllib3

from src.collectors.base import download

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_MSTAT_URL = "https://www.bnr.rw/mstat"
_BASE_URL = "https://www.bnr.rw"
_SHEET_NAME = "DCs"

_EMPTY_COLUMNS = ["country_code", "year", "period", "indicator", "value", "updated_at"]


def _find_row(ws, label: str, start_row: int = 1):
    for r in range(start_row, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and v.strip() == label:
            return r
    return None


def _find_header_row(ws) -> int | None:
    for r in range(1, min(15, ws.max_row) + 1):
        count = sum(
            1
            for c in range(2, ws.max_column + 1)
            if isinstance(ws.cell(row=r, column=c).value, datetime)
        )
        if count >= 2:
            return r
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    empty = pd.DataFrame(columns=_EMPTY_COLUMNS)

    try:
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    except Exception as e:
        logger.error("[%s] xlsx 열기 실패: %s", country_code, e)
        return empty

    ws = wb[_SHEET_NAME] if _SHEET_NAME in wb.sheetnames else wb.active

    header_row = _find_header_row(ws)
    if header_row is None:
        logger.error("[%s] 날짜 헤더 행을 찾지 못함", country_code)
        return empty

    m1_row = _find_row(ws, "Money M1")
    td_row = _find_row(ws, "Deposits", start_row=(m1_row or 1) + 1)
    fcd_row = _find_row(ws, "Foreign currency deposits", start_row=(td_row or header_row) + 1)

    if td_row is None or fcd_row is None:
        logger.error(
            "[%s] TD/FCD 행 미발견 (m1_row=%s, td_row=%s, fcd_row=%s)",
            country_code, m1_row, td_row, fcd_row,
        )
        return empty

    rows = []
    for c in range(2, ws.max_column + 1):
        date_val = ws.cell(row=header_row, column=c).value
        if not isinstance(date_val, datetime):
            continue
        td_val = ws.cell(row=td_row, column=c).value
        fcd_val = ws.cell(row=fcd_row, column=c).value
        if not isinstance(td_val, (int, float)) or not isinstance(fcd_val, (int, float)):
            continue

        period = f"{date_val.year}-{date_val.month:02d}"
        year = date_val.year
        fcd = round(float(fcd_val), 2)
        td = round(float(td_val), 2)
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

    if not rows:
        return empty
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["period", "indicator"], keep="last")
    return out.sort_values(["period", "indicator"]).reset_index(drop=True)


# NISR Statistical Yearbook 2025 — BANKING and FINANCE Table 12.1.1
# June-end Deposits / Foreign currency deposits (Rwf billion), cols 2018–2024
_YEARBOOK_URL = (
    "http://www.statistics.gov.rw/sites/default/files/documents/2026-01/"
    "Rwanda_Statistical_Yearbook_2025.xlsx"
)
_YEARBOOK_YEARS = list(range(2018, 2025))  # June snapshots


def _from_yearbook(country_code: str) -> pd.DataFrame:
    """Longer annual June series from NISR yearbook (auto-fetched each run)."""
    empty = pd.DataFrame(columns=_EMPTY_COLUMNS)
    try:
        content = download(_YEARBOOK_URL)
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
        ws = wb["BANKING and FINANCE"] if "BANKING and FINANCE" in wb.sheetnames else None
        if ws is None:
            return empty
        td_row = fcd_row = None
        for r in range(1, ws.max_row + 1):
            v = ws.cell(row=r, column=1).value
            if not isinstance(v, str):
                continue
            lab = v.strip()
            if lab == "Deposits" and td_row is None:
                # prefer the broad-money deposits block near Foreign currency deposits
                # check next few rows for FC deposits label
                for rr in range(r + 1, min(r + 6, ws.max_row + 1)):
                    vv = ws.cell(row=rr, column=1).value
                    if isinstance(vv, str) and "Foreign currency deposits" in vv:
                        td_row, fcd_row = r, rr
                        break
            if lab == "Foreign currency deposits" and fcd_row is None:
                fcd_row = r
        if td_row is None or fcd_row is None:
            return empty
        def _num(v):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.replace(",", "").strip())
                except ValueError:
                    return None
            return None

        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for i, year in enumerate(_YEARBOOK_YEARS):
            col = i + 2  # col B = 2018
            td = _num(ws.cell(row=td_row, column=col).value)
            fcd = _num(ws.cell(row=fcd_row, column=col).value)
            if td is None or fcd is None or td <= 0:
                continue
            period = f"{year}-06"
            ratio = round((fcd / td) * 100, 4)
            for indicator, value in (
                ("FCD", round(fcd, 4)),
                ("TD", round(td, 4)),
                ("FCD_TD_RATIO", ratio),
            ):
                rows.append(
                    {
                        "country_code": country_code,
                        "year": year,
                        "period": period,
                        "indicator": indicator,
                        "value": value,
                        "updated_at": now,
                    }
                )
        if not rows:
            return empty
        return pd.DataFrame(rows)
    except Exception as e:
        logger.warning("[%s] yearbook: %s", country_code, e)
        return empty


_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _probe_recent_months(country_code: str, months: int = 24) -> pd.DataFrame:
    """Directly guess `/documents/Depository_corporation_survey_<Mon>_<year>.xlsx`
    URLs for the last N months (server keeps ~12 months of these even after /mstat
    stops listing them) so gaps from irregular pipeline runs get filled in."""
    import requests

    empty = pd.DataFrame(columns=_EMPTY_COLUMNS)
    now = datetime.now(timezone.utc)
    frames = []
    y, m = now.year, now.month
    for _ in range(months):
        url = f"{_BASE_URL}/documents/Depository_corporation_survey_{_MONTH_NAMES[m - 1]}_{y}.xlsx"
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        try:
            resp = requests.get(url, timeout=30, verify=False, headers={"Referer": _MSTAT_URL})
            if resp.status_code == 200 and resp.content[:2] == b"PK":
                df = parse(resp.content, country_code)
                if len(df):
                    frames.append(df)
        except Exception:
            continue
    if not frames:
        return empty
    return pd.concat(frames, ignore_index=True)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    empty = pd.DataFrame(columns=_EMPTY_COLUMNS)
    frames = []

    # 1) Live BNR mstat rolling monthly window
    try:
        listing = json.loads(download(_MSTAT_URL).decode("utf-8"))
        survey = next(
            (
                item
                for item in listing
                if str(item.get("name", "")).strip().lower().startswith(
                    "depository corporation survey"
                )
            ),
            None,
        )
        if survey and survey.get("file"):
            file_url = _BASE_URL + survey["file"]
            logger.info("[%s] Depository Corporations Survey: %s", country_code, file_url)
            content = download(file_url, referer=_MSTAT_URL)
            live = parse(content, country_code)
            if len(live):
                frames.append(live)
    except Exception as e:
        logger.error("[%s] /mstat 실패: %s", country_code, e)

    # 1b) Backfill recent months whose file fell off /mstat's "latest 3" but is
    # still reachable by predictable URL.
    try:
        probed = _probe_recent_months(country_code)
        if len(probed):
            frames.append(probed)
            logger.info(
                "[%s] URL probe %d rows (%s~%s)",
                country_code, len(probed), probed["period"].min(), probed["period"].max(),
            )
    except Exception as e:
        logger.warning("[%s] URL probe 실패: %s", country_code, e)

    # 2) NISR yearbook annual June series (extends history; re-fetched each run)
    yb = _from_yearbook(country_code)
    if len(yb):
        frames.append(yb)
        logger.info(
            "[%s] yearbook %d rows (%s~%s)",
            country_code,
            len(yb),
            yb["period"].min(),
            yb["period"].max(),
        )

    if not frames:
        return empty
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["period", "indicator"], keep="last")
    out = out.sort_values(["period", "indicator"]).reset_index(drop=True)
    logger.info(
        "[%s] %d rows (%s~%s)",
        country_code,
        len(out),
        out["period"].min(),
        out["period"].max(),
    )
    return out

