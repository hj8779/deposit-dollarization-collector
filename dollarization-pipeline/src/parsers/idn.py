"""Indonesia: Bank Indonesia SEKI tables I.21 / I.22 / I.23.

SEKI: https://www.bi.go.id/en/statistik/ekonomi-keuangan/seki/Default.aspx
Monetary Sector > I. MONEY AND BANKING

  I.21  Outstanding demand deposits (Giro) in Rupiah and foreign currency
        https://www.bi.go.id/SEKI/tabel/TABEL1_21.xls
  I.22  Outstanding saving deposits (Tabungan) Rupiah & foreign currency
        https://www.bi.go.id/SEKI/tabel/TABEL1_22.xls
  I.23  Outstanding time deposits (Deposito) Rupiah & foreign currency
        https://www.bi.go.id/SEKI/tabel/TABEL1_23.xls

각 파일은 연대별 시트 + 최신 롤링 시트(1.xx_1). 시트마다 상단 총계 행:
  'Rupiah' — 루피아 예금 합계
  'Valas'  — 외화 예금 합계 (구르드 환산이 아니라 Rp 환산 외화 잔액)
  (1.xx_2 시트는 Memo/정부·비거주자 항목이라 제외)

FCD = Valas(I.21) + Valas(I.22) + Valas(I.23)
TD  = (Rupiah+Valas) of I.21 + I.22 + I.23
단위: Miliar Rp (십억 루피아). 실측 2026-06 FCD ≈ 1,606.2 조 Rp (기사 DPK Valas와 일치).
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_TABLES = {
    "demand": "https://www.bi.go.id/SEKI/tabel/TABEL1_21.xls",
    "saving": "https://www.bi.go.id/SEKI/tabel/TABEL1_22.xls",
    "time": "https://www.bi.go.id/SEKI/tabel/TABEL1_23.xls",
}
_PAGE = "https://www.bi.go.id/en/statistik/ekonomi-keuangan/seki/Default.aspx"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        1,
    )
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("IDN는 render()로 I.21/I.22/I.23 세 파일을 합산한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
    resp.raise_for_status()
    content = resp.content
    if not content.startswith(b"\xd0\xcf\x11\xe0") and not content.startswith(b"PK"):
        raise RuntimeError(f"not excel: {url} head={content[:40]!r}")
    return content


def _to_period_cell(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        return None
    if hasattr(value, "year") and hasattr(value, "month"):
        try:
            y, m = int(value.year), int(value.month)
            if 1980 <= y <= 2100 and 1 <= m <= 12:
                return f"{y}-{m:02d}"
        except (TypeError, ValueError):
            return None
    return None


def _periods_from_sheet(df: pd.DataFrame) -> dict[int, str]:
    """열 인덱스 -> 'YYYY-MM'.

    SEKI 최근 시트는 연도 라벨이 해당 연 *1월*이 아니라 마지막 관측월
    (예: 2026이 Jun 열, 2024가 Dec 열)에만 붙는 경우가 있다.
    연도 셀을 단순 forward-fill 하면 중간 월이 이전 연도로 잘못 붙거나
    누락되므로, 월 약어 순서(Dec→Jan 등 month wrap)로 연도를 증가시킨다.
    1월 열의 연도 라벨만 신뢰해 재설정한다.
    """
    # 1) datetime 헤더 행
    for i in range(min(12, len(df))):
        hits: dict[int, str] = {}
        for j in range(2, df.shape[1]):
            p = _to_period_cell(df.iat[i, j])
            if p:
                hits[j] = p
        if len(hits) >= 3:
            return hits
    # 2) 연도 행 + 바로 아래 월 약어 행 (월 순서 기반 연도 증가)
    for i in range(min(10, len(df))):
        ymap: dict[int, int] = {}
        for j in range(2, df.shape[1]):
            v = df.iat[i, j]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            if isinstance(v, str) and not v.strip():
                continue
            try:
                y = int(float(v))
            except (TypeError, ValueError):
                continue
            if 1980 <= y <= 2100:
                ymap[j] = y
        if not ymap or i + 1 >= len(df):
            continue
        mmap: dict[int, int] = {}
        for j in range(2, df.shape[1]):
            v = df.iat[i + 1, j]
            if isinstance(v, str):
                key = v.strip()[:3]
                if key in _MONTHS:
                    mmap[j] = _MONTHS[key]
        if len(mmap) < 3:
            continue

        periods: dict[int, str] = {}
        current_year: int | None = None
        prev_month: int | None = None
        for j in range(2, df.shape[1]):
            if j not in mmap:
                continue
            m = mmap[j]
            if j in ymap and m == 1:
                # 1월에 붙은 연도 라벨만 확정 앵커
                current_year = ymap[j]
            elif current_year is None:
                before = [c for c in ymap if c <= j]
                current_year = ymap[max(before)] if before else ymap[min(ymap)]
            elif prev_month is not None and m < prev_month:
                # Dec→Jan (또는 연말 wrap): 연도 +1
                # (비-1월 연도 라벨은 무시 — 최근 시트에서 Jun/Dec에 붙는 오류 방지)
                if j in ymap and m == 1:
                    current_year = ymap[j]
                else:
                    current_year += 1
            periods[j] = f"{current_year}-{m:02d}"
            prev_month = m
        if periods:
            return periods
    return {}


def _extract_rupiah_valas(content: bytes) -> dict[str, tuple[float, float]]:
    """시트들을 순회하며 period -> (Rupiah, Valas). 뒤 시트가 앞 시트를 덮어씀."""
    xl = pd.ExcelFile(BytesIO(content), engine="xlrd")
    series: dict[str, tuple[float, float]] = {}
    for sheet in xl.sheet_names:
        if sheet.endswith("_2"):
            continue  # memo / 비거주·정부 메모
        df = xl.parse(sheet, header=None)
        periods = _periods_from_sheet(df)
        if not periods:
            continue
        label_col = None
        for c in (2, 1):
            if c >= df.shape[1]:
                continue
            labs = [
                df.iat[i, c].strip()
                for i in range(len(df))
                if isinstance(df.iat[i, c], str)
            ]
            if "Rupiah" in labs and "Valas" in labs:
                label_col = c
                break
        if label_col is None:
            continue
        rupiah_row = valas_row = None
        for i in range(len(df)):
            lab = df.iat[i, label_col]
            if not isinstance(lab, str):
                continue
            s = lab.strip()
            if s == "Rupiah" and rupiah_row is None:
                rupiah_row = i
            elif s == "Valas" and valas_row is None:
                valas_row = i
        # 본표 총계는 상단(대략 15행 이내)
        if rupiah_row is None or valas_row is None or rupiah_row > 15:
            continue
        for j, period in periods.items():
            try:
                r = float(df.iat[rupiah_row, j])
                v = float(df.iat[valas_row, j])
            except (TypeError, ValueError):
                continue
            if r == 0 and v == 0:
                continue
            series[period] = (r, v)
    return series


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
    parts: dict[str, dict[str, tuple[float, float]]] = {}

    for kind, url in _TABLES.items():
        try:
            content = _download(url)
            series = _extract_rupiah_valas(content)
            parts[kind] = series
            if series:
                logger.info(
                    "[%s] %s: %d months %s~%s",
                    country_code, kind, len(series), min(series), max(series),
                )
            else:
                logger.warning("[%s] %s: no series extracted", country_code, kind)
        except Exception as e:
            logger.exception("[%s] %s download/parse failed: %s", country_code, kind, e)

    if len(parts) < 3:
        logger.error("[%s] need all of demand/saving/time, got %s", country_code, list(parts))
        return _empty()

    periods = sorted(set.intersection(*(set(s) for s in parts.values())))
    merged: dict[str, tuple[float, float]] = {}
    for p in periods:
        fcd = sum(parts[k][p][1] for k in parts)
        td = sum(parts[k][p][0] + parts[k][p][1] for k in parts)
        merged[p] = (fcd, td)

    df = _build_frame(country_code, merged)
    if not df.empty:
        logger.info(
            "[%s] merged %d rows (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    return df
