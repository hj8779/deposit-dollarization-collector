"""Greece: Bank of Greece deposits-by-sector Excel (3 files, merged).

페이지: https://www.bankofgreece.gr/en/statistics/monetary-and-banking-statistics/deposits

Akamai가 단순 requests/Playwright 기본 헤더를 403으로 차단한다. 실측으로
`Accept-Encoding: gzip, deflate, br` (br 포함) + 브라우저형 Sec-Fetch 헤더를
넣으면 RelatedDocuments/*.xls 가 200으로 내려온다(br 없으면 403).

파일 구성 (모두 outstanding, end-of-period, EUR millions):
1. Deposits_sector_98-00.xls  (1998-03~2000-12)
   - 민간 거주자(1.2)를 드라크마 / 유로·유로지역통화 / 기타통화로 분해
   - 그리스 유로 도입(2001) 이전이므로 자국통화=드라크마
   - FCD = In EUR and euro-area currencies + In other currencies
   - TD  = Corporations and Households (1.2)
2. Deposits_sector.xls  (2001-01~2021-12)
   - FCD = In other currencies (1.2.ν), 자국통화=euro
   - TD  = Corporations and Households private sector (1.2)
3. Deposits_sector_new.xls  (2019-01~최신)
   - 동일 라벨/코드 체계, 최신 구간

겹치는 기간(2019~2021)은 신파일 값을 우선(소폭 개정 반영). 정부 부문은
통화별 분해가 없어 민간(private sector) 거주자 예금만 집계한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PAGE = "https://www.bankofgreece.gr/en/statistics/monetary-and-banking-statistics/deposits"
_BASE = "https://www.bankofgreece.gr/RelatedDocuments"

# (url, era)  era: pre_euro | modern. 병합 시 리스트 뒤쪽이 앞쪽을 덮어쓴다.
_SOURCES: list[tuple[str, str]] = [
    (f"{_BASE}/Deposits_sector_98-00.xls", "pre_euro"),
    (f"{_BASE}/Deposits_sector.xls", "modern"),
    (f"{_BASE}/Deposits_sector_new.xls", "modern"),
]

# Akamai: Accept-Encoding 에 br 이 없으면 403
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Referer": _PAGE,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("GRC는 render()로 3개 파일을 병합한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=90)
    resp.raise_for_status()
    content = resp.content
    if not content.startswith(b"\xd0\xcf\x11\xe0") and not content.startswith(b"PK"):
        raise RuntimeError(
            f"엑셀이 아닌 응답(status 헤더 통과 가능, len={len(content)}, head={content[:60]!r})"
        )
    return content


def _norm(text: str) -> str:
    return " ".join(str(text).replace("\xa0", " ").split()).strip().lower()


def _to_period(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp) or hasattr(value, "year"):
        try:
            return f"{int(value.year)}-{int(value.month):02d}"
        except (TypeError, ValueError):
            return None
    return None


def _find_date_row(df: pd.DataFrame) -> int | None:
    for i in range(min(8, len(df))):
        for j in range(1, min(6, df.shape[1])):
            if _to_period(df.iat[i, j]) is not None:
                return i
    return None


def _find_row_by_code(df: pd.DataFrame, code: str) -> int | None:
    """col0 코드 정확 매칭(공백 무시). 첫 Domestic 구간 매치만 반환."""
    target = code.strip()
    for i in range(len(df)):
        v = df.iat[i, 0]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        if str(v).strip() == target:
            return i
    return None


def _find_row_by_label(df: pd.DataFrame, *needles: str, start: int = 0) -> int | None:
    wanted = [_norm(n) for n in needles]
    for i in range(start, len(df)):
        v = df.iat[i, 1] if df.shape[1] > 1 else df.iat[i, 0]
        if not isinstance(v, str):
            continue
        s = _norm(v)
        if all(n in s for n in wanted):
            return i
    return None


def _extract_series(df: pd.DataFrame, row: int, date_row: int) -> dict[str, float]:
    out: dict[str, float] = {}
    for j in range(2, df.shape[1]):
        period = _to_period(df.iat[date_row, j])
        if period is None:
            continue
        try:
            val = float(df.iat[row, j])
        except (TypeError, ValueError):
            continue
        if pd.isna(val):
            continue
        out[period] = val
    return out


def _parse_file(content: bytes, era: str) -> dict[str, tuple[float, float]]:
    """period -> (fcd, td)."""
    try:
        xl = pd.ExcelFile(BytesIO(content), engine="xlrd")
    except Exception:
        xl = pd.ExcelFile(BytesIO(content))

    sheet = "Stocks" if "Stocks" in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)
    date_row = _find_date_row(df)
    if date_row is None:
        raise ValueError("날짜 헤더 행 없음")

    # TD: private sector total (code 1.2)
    td_row = _find_row_by_code(df, "1.2")
    if td_row is None:
        td_row = _find_row_by_label(df, "corporations and households")
    if td_row is None:
        raise ValueError("민간 예금 합계 행(1.2) 없음")

    if era == "modern":
        # FCD: 1.2.ν In other currencies (유로 도입 후 외화)
        fcd_row = _find_row_by_code(df, "1.2.ν") or _find_row_by_code(df, "1.2.v")
        if fcd_row is None:
            fcd_row = _find_row_by_label(df, "in other currencies", start=td_row)
        if fcd_row is None:
            raise ValueError("외화예금 행(1.2.ν) 없음")
        fcd_s = _extract_series(df, fcd_row, date_row)
        td_s = _extract_series(df, td_row, date_row)
        return {p: (fcd_s[p], td_s[p]) for p in fcd_s if p in td_s and td_s[p]}

    # pre_euro: FCD = 유로·유로지역 + 기타통화 (드라크마 제외)
    eur_row = _find_row_by_code(df, "1.2.ε") or _find_row_by_code(df, "1.2.e")
    if eur_row is None:
        eur_row = _find_row_by_label(df, "in eur", start=td_row)
    other_row = _find_row_by_code(df, "1.2.ν") or _find_row_by_code(df, "1.2.v")
    if other_row is None:
        other_row = _find_row_by_label(df, "in other currencies", start=td_row)
    if eur_row is None or other_row is None:
        raise ValueError(f"pre-euro 통화 분해 행 없음 (eur={eur_row}, other={other_row})")

    eur_s = _extract_series(df, eur_row, date_row)
    other_s = _extract_series(df, other_row, date_row)
    td_s = _extract_series(df, td_row, date_row)
    out: dict[str, tuple[float, float]] = {}
    for p, td in td_s.items():
        if p not in eur_s or p not in other_s or not td:
            continue
        out[p] = (eur_s[p] + other_s[p], td)
    return out


def _build_frame(country_code: str, series: dict[str, tuple[float, float]]) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period in sorted(series):
        fcd, td = series[period]
        if td <= 0:
            continue
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
    if not rows:
        return _empty()
    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    merged: dict[str, tuple[float, float]] = {}

    for url, era in _SOURCES:
        try:
            content = _download(url)
            part = _parse_file(content, era)
        except Exception as e:
            logger.exception("[%s] 파일 실패 %s: %s", country_code, url, e)
            continue
        if not part:
            logger.warning("[%s] 빈 시계열: %s", country_code, url)
            continue
        periods = sorted(part)
        logger.info(
            "[%s] %s (%s): %d개월 %s~%s",
            country_code, url.rsplit("/", 1)[-1], era,
            len(part), periods[0], periods[-1],
        )
        merged.update(part)  # 뒤 소스가 겹치는 기간을 덮어씀

    if not merged:
        return _empty()

    df = _build_frame(country_code, merged)
    logger.info(
        "[%s] 병합 %d행 (%s~%s)",
        country_code, len(df),
        df["period"].min() if not df.empty else "-",
        df["period"].max() if not df.empty else "-",
    )
    return df
