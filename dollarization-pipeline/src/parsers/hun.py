"""Hungary: MNB monstatpubl — consolidated MFI liabilities (Table 3.2).

소스 엑셀:
  https://statisztika.mnb.hu/timeseries/0708-monstatpubl-enxls.xls
상세 페이지:
  https://statisztika.mnb.hu/timeseries/data-10957
  "Balance sheets of monetary financial institutions and monetary aggregates"

파일 내 여러 표 중 **Table 3.2** (Consolidated balance sheet of MFIs
S.121+S.122+S.123, Liabilities, end of period) 를 사용한다.
- 타 MFI 간 예금이 상계된 거주자 예금
- Other MFIs 단독 표(2.a.2)보다 고객예금 달러화에 적합

시트 헤더 구조 (HUF billions):
  Deposits of residents (col2 TOTAL)
    Central government: HUF (col4), Foreign currency (col5)
    Other residents:
      Overnight: HUF (col8), Foreign currency (col9)
      Agreed maturity: HUF (col11), Foreign currency (col12)

FCD = CG FC + Overnight FC + Agreed-maturity FC  (col5+col9+col12)
TD  = Deposits of residents total                 (col2)
FCD_TD_RATIO = FCD/TD*100

시계열: 1998-01 ~ 파일 최신월 (실측 2026-06), 월말 잔액.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_XLS_URL = "https://statisztika.mnb.hu/timeseries/0708-monstatpubl-enxls.xls"
_PAGE = "https://statisztika.mnb.hu/timeseries/data-10957"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}

_SHEET = "Table 3.2"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    empty = pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )
    try:
        xl = pd.ExcelFile(BytesIO(content), engine="xlrd")
    except Exception:
        try:
            xl = pd.ExcelFile(BytesIO(content))
        except Exception as e:
            logger.error("[%s] xls 열기 실패: %s", country_code, e)
            return empty

    sheet = _SHEET if _SHEET in xl.sheet_names else None
    if sheet is None:
        # 변형: 'Table 3.2' / '3.2' 등
        for name in xl.sheet_names:
            if "3.2" in name.replace(" ", "") or name.strip().endswith("3.2"):
                sheet = name
                break
    if sheet is None:
        logger.error("[%s] Table 3.2 시트 없음: %s", country_code, xl.sheet_names[:10])
        return empty

    df = xl.parse(sheet, header=None)
    cols = _locate_columns(df)
    if cols is None:
        logger.error("[%s] HUF/Foreign currency 열 매핑 실패", country_code)
        return empty
    td_col, fcd_cols = cols

    rows = []
    for i in range(len(df)):
        period = _to_period(df.iat[i, 0])
        if period is None:
            continue
        try:
            td = float(df.iat[i, td_col])
            fcd = 0.0
            for c in fcd_cols:
                v = df.iat[i, c]
                if v is None or (isinstance(v, float) and pd.isna(v)) or v == "-":
                    raise ValueError("missing FC")
                fcd += float(v)
        except (TypeError, ValueError):
            continue
        if pd.isna(td) or td <= 0:
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
        return empty
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["period", "indicator"], keep="last")
    return out.sort_values(["period", "indicator"]).reset_index(drop=True)


def _to_period(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "year") and hasattr(value, "month"):
        try:
            return f"{int(value.year)}-{int(value.month):02d}"
        except (TypeError, ValueError):
            return None
    return None


def _locate_columns(df: pd.DataFrame) -> tuple[int, list[int]] | None:
    """Deposits of residents 총액 열 + FC 구성 열(CG FC, overnight FC, maturity FC).

    고정 인덱스 폴백: td=2, fcd=[5,9,12] (MNB 현재 레이아웃).
    """
    # 'Deposits of residents' 라벨이 있는 열 찾기 (보통 col2 위 헤더)
    # 데이터 열: col2 = total deposits of residents (row with date has numbers)
    # FC 열: 헤더 행에서 'Foreign currency' 이고 Deposits of residents 블록 안

    # 헤더 행들
    fc_cols: list[int] = []
    for i in range(min(20, len(df))):
        for j in range(df.shape[1]):
            v = df.iat[i, j]
            if isinstance(v, str) and v.strip().lower() == "foreign currency":
                fc_cols.append(j)

    # 고유 유지 순서
    seen = set()
    fc_unique = []
    for c in fc_cols:
        if c not in seen:
            seen.add(c)
            fc_unique.append(c)

    # Deposits of residents 블록의 FC만: 보통 처음 3개 (CG, overnight, maturity)
    # debt securities 쪽 FC(c19 등)는 예금 아님 — col index 기준으로 작은 쪽
    deposit_fc = [c for c in fc_unique if c <= 14]
    if len(deposit_fc) >= 3:
        deposit_fc = deposit_fc[:3]
    elif len(deposit_fc) < 1:
        deposit_fc = [5, 9, 12]  # fallback

    # TD column: first numeric column after date that matches deposits total
    # Standard layout col2
    td_col = 2
    # verify header
    for i in range(min(15, len(df))):
        v = df.iat[i, 2] if df.shape[1] > 2 else None
        if isinstance(v, str) and "deposit" in v.lower() and "resident" in v.lower():
            td_col = 2
            break
        v1 = df.iat[i, 1] if df.shape[1] > 1 else None
        if isinstance(v1, str) and "deposit" in v1.lower() and "resident" in v1.lower():
            # value still under col2 in data rows
            td_col = 2
            break

    return td_col, deposit_fc


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    logger.info("[%s] monstatpubl 다운로드: %s", country_code, _XLS_URL)
    resp = requests.get(_XLS_URL, headers=_HEADERS, timeout=120)
    resp.raise_for_status()
    content = resp.content
    if not content.startswith(b"\xd0\xcf\x11\xe0") and not content.startswith(b"PK"):
        logger.error("[%s] 엑셀이 아닌 응답 len=%d", country_code, len(content))
        return pd.DataFrame(
            columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
        )
    df = parse(content, country_code)
    if not df.empty:
        logger.info(
            "[%s] %d행 (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    return df
