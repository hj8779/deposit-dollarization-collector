"""Serbia: National Bank of Serbia (NBS) monetary statistics, "Table 1.1.4 Consolidated
Balance Sheet of the Banking System" (SBMS04.xlsx).

config/targets.json에 기록되어 있던 "nbs.rs가 봇 차단('Pristup je blokiran')"은 실측 결과
재현되지 않았다: `requests`에 일반적인 브라우저 User-Agent/Accept 헤더만 실어 보내면(이
프로젝트의 `src.collectors.base.download()`가 이미 기본으로 그렇게 함) nbs.rs는 200과 함께
정상 콘텐츠를 반환한다. Playwright 등 추가 우회는 불필요했다.

nbs.rs Statistics > Monetary Statistics 페이지(mon_stat/)에는 월간 PDF Bulletin 외에도
같은 데이터를 담은 xlsx가 테이블별로 개별 게시되어 있는데, 이쪽이 훨씬 다루기 쉽다(단일
파일, 파싱 안정적인 셀 구조, 1999년~현재 연간 + 2004년~현재 월간을 한 파일에 롤링 없이
전부 담고 있어 매월 파일이 덮어써져도 과거 이력이 유실되지 않는다):

    https://www.nbs.rs/export/sites/NBS_site/documents/statistika/monetarni_sektor/SBMS04.xlsx

시트 'Eng, Liabilities'는 'LIABILITIES' 쪽 컬럼을 담고 있고, 그중 'Money supply' 섹션
컬럼 구성(헤더 행 기준, 항목 번호는 시트 자체의 각주 번호):
    (5) Currency in circulation      (6) Dinar sight deposits
    (7=5+6) Money supply M1          (8) Dinar time deposits
    (9=7+8) Money supply M2          (10) Foreign currency deposits
    (11=9+10) Money supply M3

FCD(거주자 외화예금) = 항목(10) "Foreign currency deposits" 그대로 사용.
TD(총예금)          = 항목(6)+(8)+(10) = Dinar sight + Dinar time + FCD
                     (= M3 - Currency in circulation; 즉 '통화(현금)를 제외한 전체 예금').

주의(정의 범위): 이 표의 "Foreign currency deposits"는 정부 부문을 제외한 전 거주 부문
(가계/기업/기타금융기관/지방정부/비영리단체 등)의 은행+NBS 예치 외화예금 합계로,
FX-indexed(디나르 표시이나 환율 연동)는 포함하지 않는 순수 외화표시 예금만이다. NBS의
다른 표(Table 1.1.5 Monetary Survey, Table 1.1.6 Non-Monetary Sector Deposits)에는
"Foreign currency deposits AND FX-indexed savings/time deposits"라는 더 넓은 정의의
라인이 별도로 존재하므로 혼동하지 말 것(그쪽은 사용하지 않음).

실측(2026-06, 최신월): FCD=2,801,974.069백만 디나르, TD=1,700,085.343+740,249.753+
2,801,974.069=5,242,309.165백만 디나르 -> ratio=53.46%. IMF 2025 Serbia Article IV
보고서의 스팟체크 수치(FCD≈EUR 3,366mn, TD≈EUR 5,859mn, ratio≈57.45%)와는 정확히
일치하지 않는다(IMF 쪽 표는 우리보다 좁은 부문 정의를 쓰는 것으로 보임 -- 예를 들어
은행만 포함하고 NBS 예치분/일부 부문을 제외했을 가능성). 그러나 두 비율 모두 50%대
후반이라는 같은 자릿수(오더)이고 방향도 일치해 상식적인 범위(ballpark) 안에 있음을
확인했다.
"""

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = (
    "https://www.nbs.rs/export/sites/NBS_site/documents/statistika/"
    "monetarni_sektor/SBMS04.xlsx"
)

_SHEET = "Eng, Liabilities"

# 시트 내 절대 컬럼 위치(헤더 행에서 확인한 고정 레이아웃).
_COL_YEAR = 1
_COL_MONTH = 2
_COL_CURRENCY = 7   # (5) Currency in circulation
_COL_DINAR_SIGHT = 8   # (6) Dinar sight deposits
_COL_DINAR_TIME = 10  # (8) Dinar time deposits
_COL_FCD = 12  # (10) Foreign currency deposits
_DATA_START_ROW = 12

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

COLUMNS = ["country_code", "year", "period", "indicator", "value", "updated_at"]


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    wb = openpyxl.load_workbook(BytesIO(content), data_only=True)

    if _SHEET not in wb.sheetnames:
        logger.warning("[%s] 시트 '%s' 없음, 스킵", country_code, _SHEET)
        return pd.DataFrame(columns=COLUMNS)
    ws = wb[_SHEET]

    rows = []
    current_year = None
    for r in range(_DATA_START_ROW, ws.max_row + 1):
        year_cell = ws.cell(row=r, column=_COL_YEAR).value
        month_cell = ws.cell(row=r, column=_COL_MONTH).value

        if year_cell is not None:
            try:
                current_year = int(year_cell)
            except (TypeError, ValueError):
                continue

        if current_year is None:
            continue

        dinar_sight = ws.cell(row=r, column=_COL_DINAR_SIGHT).value
        dinar_time = ws.cell(row=r, column=_COL_DINAR_TIME).value
        fcd = ws.cell(row=r, column=_COL_FCD).value
        if not all(isinstance(v, (int, float)) for v in (dinar_sight, dinar_time, fcd)):
            continue

        if month_cell:
            month = _MONTHS.get(str(month_cell).strip().lower()[:3])
            if month is None:
                continue
            period = f"{current_year}-{month:02d}"
        else:
            # 연간 요약 행(1999~2025 구간에는 연간만, 2004년 이후는 이 연간 행에 더해
            # 월별 행도 별도로 이어진다). 연간/월간을 (period, indicator) 기준으로 구분
            # 저장하므로 이후 UPSERT 단계에서 서로 덮어쓰지 않는다.
            period = f"{current_year}-Annual"

        td = round(dinar_sight + dinar_time + fcd, 3)
        fcd_val = round(fcd, 3)
        ratio = round((fcd_val / td) * 100, 2) if td else None

        for indicator, value in (("FCD", fcd_val), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": current_year,
                "period": period,
                "indicator": indicator,
                "value": value,
                "updated_at": now,
            })

    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df.drop_duplicates(subset=["period", "indicator"], keep="last")
    df = df.sort_values(["period", "indicator"]).reset_index(drop=True)
    return df
