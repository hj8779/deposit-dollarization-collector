"""Hong Kong: HKMA Monthly Statistical Bulletin Table 2.2.1 (T020201.xls).

페이지:
  https://www.hkma.gov.hk/eng/data-publications-and-research/data-and-statistics/economic-financial-data-for-hong-kong/#financialSector
직접 파일:
  https://www.hkma.gov.hk/media/eng/doc/market-data-and-statistics/monthly-statistical-bulletin/T020201.xls

이전 실패 사유(요약 표의 'Foreign currency reserve assets' = 외환보유고)와 달리,
이 표는 통화공급(Money supply)을 HK$/F.C./Total 로 분해한다.

시트:
  - 'T2.2.1 (new series)' : 1997-04~최신 (권장 연속 시계열)
  - 'T2.2.1 (old series)' : ~2002 전후까지 구 시계열 (1984-12~)

표 제목: Adjusted for foreign currency swap deposits
  - HK$ 열: 외화 swap 예금 포함(주2)
  - F.C. 열: 외화 swap 예금 제외(주3)
  - 단위: HK$ million

지표 (M2 기준 — 예금성 광의통화, 홍콩 달러화 연구에서 표준):
  FCD = M2 F.C.   (외화 부문)
  TD  = M2 Total  (= M2 HK$ + M2 F.C., 실측 항등)
  FCD_TD_RATIO = FCD/TD*100

병합: 1997-04 이전은 old, 이후는 new(신시리즈 우선).
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # referer 포함 다운로드는 render()에서

_XLS_URL = (
    "https://www.hkma.gov.hk/media/eng/doc/market-data-and-statistics/"
    "monthly-statistical-bulletin/T020201.xls"
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": (
        "https://www.hkma.gov.hk/eng/data-publications-and-research/"
        "data-and-statistics/economic-financial-data-for-hong-kong/"
    ),
}


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _month_num(text) -> int | None:
    if not isinstance(text, str):
        return None
    return _MONTHS.get(text.strip().lower()[:3])


def _to_year(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit() and len(text) == 4:
            y = int(text)
            return y if 1900 <= y <= 2100 else None
        return None
    try:
        y = int(float(value))
    except (TypeError, ValueError):
        return None
    return y if 1900 <= y <= 2100 else None


def _find_header_row(df: pd.DataFrame) -> int | None:
    for i in range(min(20, len(df))):
        for j in range(min(15, df.shape[1])):
            v = df.iat[i, j]
            if isinstance(v, str) and v.strip().upper() in {"F.C.", "F.C", "FC"}:
                return i
    return None


def _m2_columns(df: pd.DataFrame, header_row: int) -> tuple[int, int] | None:
    """헤더 행에서 M2 블록의 F.C. / Total 열 인덱스를 찾는다.

    new series: ... M1(HK,FC,Tot) M2(HK,FC,Tot) M3(HK,FC,Tot)
    old series: 열 간격이 더 넓음(사이 빈 열).
    M2 라벨은 보통 header_row-2 에 있다.
    """
    # M2 라벨 열 찾기
    m2_label_col = None
    for r in range(max(0, header_row - 3), header_row):
        for j in range(df.shape[1]):
            v = df.iat[r, j]
            if isinstance(v, str) and v.strip().upper().startswith("M2"):
                m2_label_col = j
                break
        if m2_label_col is not None:
            break
    if m2_label_col is None:
        return None

    # 헤더 행에서 m2_label_col 근처 오른쪽으로 HK$ / F.C. / Total 순
    fc_col = tot_col = None
    for j in range(m2_label_col, min(df.shape[1], m2_label_col + 8)):
        v = df.iat[header_row, j]
        if not isinstance(v, str):
            continue
        key = v.strip().upper().replace(" ", "")
        if key.startswith("F.C") or key in {"FC", "F.C."}:
            fc_col = j
        elif key == "TOTAL" and fc_col is not None and tot_col is None:
            tot_col = j
            break
    if fc_col is None or tot_col is None:
        return None
    return fc_col, tot_col


def _parse_sheet(df: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """period -> (fcd, td) from one sheet."""
    header_row = _find_header_row(df)
    if header_row is None:
        return {}
    cols = _m2_columns(df, header_row)
    if cols is None:
        return {}
    fc_col, tot_col = cols

    out: dict[str, tuple[float, float]] = {}
    year: int | None = None
    for i in range(header_row + 1, len(df)):
        y = _to_year(df.iat[i, 0])
        if y is not None:
            year = y
        month = _month_num(df.iat[i, 1])
        if year is None or month is None:
            continue
        try:
            fcd = float(df.iat[i, fc_col])
            td = float(df.iat[i, tot_col])
        except (TypeError, ValueError):
            continue
        if pd.isna(fcd) or pd.isna(td) or td <= 0:
            continue
        period = f"{year}-{month:02d}"
        out[period] = (fcd, td)
    return out


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    try:
        xl = pd.ExcelFile(BytesIO(content), engine="xlrd")
    except Exception:
        try:
            xl = pd.ExcelFile(BytesIO(content))
        except Exception as e:
            logger.error("[%s] xls 열기 실패: %s", country_code, e)
            return _empty()

    sheets = xl.sheet_names
    old_name = next((s for s in sheets if "old" in s.lower()), None)
    new_name = next((s for s in sheets if "new" in s.lower()), None)

    merged: dict[str, tuple[float, float]] = {}

    if old_name:
        part = _parse_sheet(xl.parse(old_name, header=None))
        # new series 시작(1997-04) 이전만 채택
        part = {p: v for p, v in part.items() if p < "1997-04"}
        logger.info(
            "[%s] old series: %d개월 %s~%s",
            country_code, len(part),
            min(part) if part else "-", max(part) if part else "-",
        )
        merged.update(part)

    if new_name:
        part = _parse_sheet(xl.parse(new_name, header=None))
        logger.info(
            "[%s] new series: %d개월 %s~%s",
            country_code, len(part),
            min(part) if part else "-", max(part) if part else "-",
        )
        merged.update(part)  # 신시리즈가 겹침 구간 덮어씀
    elif not merged and sheets:
        # 시트명 변형 대비: 첫 시트만
        part = _parse_sheet(xl.parse(sheets[0], header=None))
        merged.update(part)

    if not merged:
        return _empty()

    rows = []
    for period in sorted(merged):
        fcd, td = merged[period]
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in (
            ("FCD", round(fcd, 4)),
            ("TD", round(td, 4)),
            ("FCD_TD_RATIO", ratio),
        ):
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })
    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def render(target: dict) -> pd.DataFrame:
    """FILE_URL 고정이지만 referer·헤더가 필요하면 여기로 우회."""
    country_code = target["country_code"]
    url = _XLS_URL
    logger.info("[%s] T020201 다운로드: %s", country_code, url)
    resp = requests.get(url, headers=_HEADERS, timeout=90)
    resp.raise_for_status()
    if not resp.content.startswith(b"\xd0\xcf\x11\xe0") and not resp.content.startswith(b"PK"):
        logger.error("[%s] 엑셀이 아닌 응답 len=%d", country_code, len(resp.content))
        return _empty()
    df = parse(resp.content, country_code)
    if not df.empty:
        logger.info(
            "[%s] %d행 (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    return df
