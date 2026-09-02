"""United Kingdom: Bank of England 'Interactive Database'(IADB, boeapps/database) 통계 시리즈.

https://www.bankofengland.co.uk/statistics/tables#m4 의 'A7.1 - Liquid assets outside M4'
표에서 'Foreign currency deposits at UK MFIs' 열의 EC 코드를 확인했다: LPMVYAY
(짧은 코드 VYAY). 사전조사에서 제시된 VSUC/VSUF/VSUG/VWNI는 실측 결과 전부 오답으로 확인됨
(VWNI='Sterling deposits at Channel Islands and IoM institutions', VSUC='Non-residents'
sterling deposits at banks in the BIS area', VSUF/VSUG='Gilts maturing within 1 year / 1-5
years' 등, 모두 FCD와 무관한 같은 표의 다른 열이었다). 실제 확인된 시리즈:

    LPMVYAY = "Monthly amounts outstanding of monetary financial institutions' all foreign
               currency deposits from private sector (in sterling millions) NSA"   -> FCD
    LPMVRJX = "...sterling retail deposits (excluding notes and coin) from private sector..." NSA
    LPMVRJV = "...sterling wholesale M4 liabilities to private sector..." NSA

VRJX+VRJV = M4에서 notes/coin을 제외한, private sector가 보유한 파운드화 예금 총액(=A2.2.1
'Components of M4' 표의 retail+wholesale deposits 합, M4 자체 코드 AUYM과는 notes&coin
차이만큼만 다름을 실측으로 확인). FCD와 정의(scope: M4 private sector = 가계+PNFC+OFC)가
일치하므로 TD = VRJX + VRJV + VYAY(전 통화 예금 총액)로 구성한다.

다운로드 방식: IADB의 옛 CSV export 엔드포인트(_iadb-fromshowcolumns.asp?csv.x=yes&...)는
현재 "Invalid series code value supplied" 에러만 반환해 더 이상 동작하지 않는다(사전조사가
언급한 CSV 직다운로드는 이제 막힘). 대신 통계 페이지의 'View chart' 링크가 실제로 쓰는
fromshowcolumns.asp(EC 코드에 LPM 접두어 필요)에 SeriesCodes를 콤마로 여러 개 넘기면 한 번의
GET 요청으로 각 시리즈가 열로 묶인 HTML 표(<table id="stats-table">)를 돌려준다. 이 표를
정규식으로 파싱한다(별도 JS 렌더링/Playwright 불필요, requests로 충분).
"""

import re
from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SERIES = ["LPMVYAY", "LPMVRJX", "LPMVRJV"]  # FCD, sterling retail deposits, sterling wholesale deposits

FILE_URL = (
    "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"
    "?Travel=NIxAZxSUx&FromSeries=1&ToSeries=50&DAT=RNG"
    "&FD=1&FM=Jan&FY=1980&TD=31&TM=Dec&TY=2030&FNY=Y"
    "&CSVF=TT&html.x=66&html.y=26"
    f"&SeriesCodes={','.join(_SERIES)}&UsingCodes=Y&Filter=N&title=GBR_FCD&VPD=Y"
)

# "30 Jun 82" 같은 영국식 2자리 연도 날짜 뒤에 시리즈 개수만큼(FCD, 예금-소매, 예금-도매) 셀이 온다.
# 값이 없는 초기 구간은 "n/a"로 채워진다.
_ROW_RE = re.compile(
    r"<tr><td[^>]*>(\d{1,2} [A-Za-z]{3} \d{2})</td>"
    r"<td[^>]*>([\d,]+|n/a)</td><td[^>]*>([\d,]+|n/a)</td><td[^>]*>([\d,]+|n/a)</td></tr>"
)


def _to_float(token: str) -> float | None:
    if token == "n/a":
        return None
    return float(token.replace(",", ""))


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    html = content.decode("utf-8", errors="ignore")
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for date_str, fcd_raw, retail_raw, wholesale_raw in _ROW_RE.findall(html):
        fcd = _to_float(fcd_raw)
        retail = _to_float(retail_raw)
        wholesale = _to_float(wholesale_raw)
        if fcd is None or retail is None or wholesale is None:
            continue  # 세 시리즈 중 하나라도 결측이면(초기 구간 등) 그 달은 스킵

        dt = datetime.strptime(date_str, "%d %b %y")
        year, period = dt.year, f"{dt.year}-{dt.month:02d}"

        td = round(retail + wholesale + fcd, 2)
        ratio = round((fcd / td) * 100, 2) if td else None

        for indicator, value in (("FCD", round(fcd, 2)), ("TD", td), ("FCD_TD_RATIO", ratio)):
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
        logger.warning("[%s] BoE IADB 응답에서 파싱된 행 없음", country_code)

    return pd.DataFrame(rows, columns=["country_code", "year", "period", "indicator", "value", "updated_at"])
