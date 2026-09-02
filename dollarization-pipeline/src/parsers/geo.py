"""Georgia: National Bank of Georgia(NBG) statistics portal M2.1.

페이지 https://nbg.gov.ge/en/statistics/statistics-data 는 Next.js SPA라 정적 HTML에
엑셀 링크가 없고, 실제 데이터는 다음 REST 경로로 내려온다.

1. 카테고리 목록: GET /gw/api/ct/statistics/data/categories
   (헤더 `Accept-Language: en` 필수 — 없으면 빈 배열 반환)
2. 카테고리별 표 목록: GET /gw/api/ct/statistics/categories/{id}/data
   - id=15 = "Monetary and Financial Statistics"
   - code="M2.1", title="Money Aggregates and Monetary Ratios"
3. 첨부 파일: https://nbg.gov.ge/fm/{URL-encoded path}
   예: .../money-aggregates-and-monetary-ratioseng.xlsx

xlsx 시트 'Monetary Ratios-eng':
    col0  Period (월말/월초 datetime)
    col9  Deposits in Foreign Currency  (= FCD, Million GEL)
    col10 Deposits, Total               (= TD)
    col13 Dollarization Ratio of Deposits, Included in Broad Money, %
          (= FCD/TD*100 과 소수점 오차 수준으로 일치, 실측 확인)

거주자 외화예금 정의: 이 표의 "Deposits in Foreign Currency"는 broad money에 포함되는
은행 외화예금 잔액이며, 동일 표의 달러화율(col13) 산출 분자가 된다.
"""

from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import quote

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_API_BASE = "https://nbg.gov.ge/gw/api/ct"
_FM_BASE = "https://nbg.gov.ge/fm/"
# Monetary and Financial Statistics (M2.x 시리즈)
_CATEGORY_ID = 15
_CODE = "M2.1"
_SHEET = "Monetary Ratios-eng"

_API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en",  # 없으면 categories/data가 빈 배열
    "Referer": "https://nbg.gov.ge/en/statistics/statistics-data",
}

_DOWNLOAD_HEADERS = {
    "User-Agent": _API_HEADERS["User-Agent"],
    "Accept": "*/*",
    "Accept-Language": "en",
    "Referer": "https://nbg.gov.ge/en/statistics/statistics-data",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """M2.1 xlsx 바이트에서 FCD/TD/FCD_TD_RATIO 롱폼을 만든다."""
    now = datetime.now(timezone.utc).isoformat()
    empty = pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )

    try:
        xl = pd.ExcelFile(BytesIO(content))
    except Exception as e:
        logger.error("[%s] xlsx 열기 실패: %s", country_code, e)
        return empty

    sheet = _SHEET if _SHEET in xl.sheet_names else None
    if sheet is None:
        # 영문 시트명 변형 대비
        for name in xl.sheet_names:
            if "monetary" in name.lower() and "ratio" in name.lower():
                sheet = name
                break
    if sheet is None:
        logger.error("[%s] Monetary Ratios 시트를 찾지 못함: %s", country_code, xl.sheet_names)
        return empty

    df = xl.parse(sheet, header=None)
    header_row = _find_header_row(df)
    if header_row is None:
        logger.error("[%s] 헤더 행(Period / Deposits in Foreign Currency)을 찾지 못함", country_code)
        return empty

    fcd_col = _find_col(df, header_row, "Deposits in Foreign Currency")
    td_col = _find_col(df, header_row, "Deposits, Total")
    if fcd_col is None or td_col is None:
        logger.error(
            "[%s] FCD/TD 열 미발견 (fcd_col=%s, td_col=%s)", country_code, fcd_col, td_col
        )
        return empty

    rows = []
    for i in range(header_row + 1, len(df)):
        period_val = df.iat[i, 0]
        period = _to_period(period_val)
        if period is None:
            continue
        try:
            fcd = float(df.iat[i, fcd_col])
            td = float(df.iat[i, td_col])
        except (TypeError, ValueError):
            continue
        if pd.isna(fcd) or pd.isna(td):
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4) if td else None
        for indicator, value in (
            ("FCD", round(fcd, 4)),
            ("TD", round(td, 4)),
            ("FCD_TD_RATIO", ratio),
        ):
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


def _find_header_row(df: pd.DataFrame) -> int | None:
    for i in range(min(10, len(df))):
        for j in range(min(15, df.shape[1])):
            v = df.iat[i, j]
            if isinstance(v, str) and "Deposits in Foreign Currency" in v:
                return i
    return None


def _find_col(df: pd.DataFrame, header_row: int, label: str) -> int | None:
    for j in range(df.shape[1]):
        v = df.iat[header_row, j]
        if isinstance(v, str) and label in v:
            return j
    return None


def _to_period(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return f"{value.year}-{value.month:02d}"
    if hasattr(value, "year") and hasattr(value, "month"):
        try:
            return f"{int(value.year)}-{int(value.month):02d}"
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        # "YYYY-MM" or "YYYY-MM-DD..."
        text = value.strip()
        if len(text) >= 7 and text[4] == "-":
            try:
                year = int(text[:4])
                month = int(text[5:7])
                if 1 <= month <= 12:
                    return f"{year}-{month:02d}"
            except ValueError:
                return None
    return None


def _resolve_m21_file() -> str:
    """API에서 M2.1 항목의 상대 파일 경로를 가져온다. 실패 시 알려진 기본 경로로 폴백."""
    fallback = (
        "სტატისტიკა/monetary_statistics/eng/"
        "money-aggregates-and-monetary-ratioseng.xlsx"
    )
    try:
        resp = requests.get(
            f"{_API_BASE}/statistics/categories/{_CATEGORY_ID}/data",
            headers=_API_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        logger.warning("[GEO] 카테고리 API 실패, 기본 파일 경로 사용: %s", e)
        return fallback

    for item in items or []:
        if str(item.get("code", "")).strip().upper() == _CODE:
            path = (item.get("file") or "").strip()
            if path:
                logger.info(
                    "[GEO] M2.1 파일 확인: %s (update=%s, next=%s)",
                    path, item.get("updateDate"), item.get("nextUpdateDate"),
                )
                return path

    logger.warning("[GEO] M2.1 항목을 API에서 못 찾아 기본 경로 사용")
    return fallback


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    file_path = _resolve_m21_file()
    url = _FM_BASE + quote(file_path, safe="/")
    logger.info("[%s] M2.1 다운로드: %s", country_code, url)
    resp = requests.get(url, headers=_DOWNLOAD_HEADERS, timeout=60)
    resp.raise_for_status()
    content = resp.content
    if not content.startswith(b"PK"):
        logger.error(
            "[%s] xlsx가 아닌 응답(len=%d, head=%r)",
            country_code, len(content), content[:80],
        )
        return pd.DataFrame(
            columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
        )
    return parse(content, country_code)
