"""Taiwan: Central Bank of the Republic of China (Taiwan, CBC) 공식 오픈데이터 CSV
'All Currency Institutions Deposit'(전 금융기관 예금) 월별 시계열.

data.gov.tw 데이터셋 6534("전체통화기관존款")가 실제로 배포하는 리소스는 data.gov.tw
자체가 아니라 CBC(중앙은행) 사이트에 직접 호스팅된 CSV다:

    https://www.cbc.gov.tw/public/data/OpenData/經研處/EF03M01.csv  (월별, 1987M05~)
    https://www.cbc.gov.tw/public/data/OpenData/經研處/EF03Y01.csv  (연도별)

월별 파일 하나로 1987년부터 현재까지 전 구간이 다 들어있어 아카이브 순회가 필요 없다
(단일 파일 다운로드, `FILE_URL` 방식). 기존 targets.json 메모에 남아있던 "SSL/접속 실패"는
`https://www.cbc.gov.tw/en/cp-902-123617-370e1-2.html`(PDF 게시물 목록 페이지) 기준이었고,
CSV 다운로드 자체는 특별한 헤더/TLS 설정 없이 정상 접속된다(2026-08 기준 확인).

컬럼 구성(BOM 붙은 UTF-8, 헤더 1행):
    월                                              -> "YYYYMmm" (예: "2023M12")
    貨幣機構存款-合計-期底餘額-億元                    -> 총예금(TD) 기말잔액, 億元(1億=1e8 NTD)
    貨幣機構存款-企業及個人存款-外匯存款-期底餘額-億元   -> 기업+개인의 외화예금(FCD) 기말잔액
    (나머지는 YoY 증가율 및 세부 항목 - 사용하지 않음)

단위는 億元(1億元=1e8 NTD)를 그대로 유지한다(다른 국가 파서들처럼 자국 통화 원단위를 그대로
싣는 관례). FCD_TD_RATIO도 함께 계산해 abw.py와 동일한 3-지표(FCD/TD/FCD_TD_RATIO) 컨벤션을
따른다.

검증: 2023M12 FCD=89,717억元(=8,971.7十億元), TD=594,271억元 -> FCD/TD=15.10%.
사전 조사 메모("CBC 자체 공표 비율 2023≈15.17%")와 거의 일치(공표 반올림/개정판 차이로 추정).
2024M12 FCD/TD=14.41%, 2025M12(최신) FCD/TD=13.73%로 조사 메모(14.52%/13.82%)와도 근접해
데이터 신뢰도를 확인했다.

CBC 사이트 인증서에 결함이 있어(Missing Subject Key Identifier) 기본 SSL 컨텍스트로는
`certificate verify failed`가 발생한다(curl은 관대하게 통과하지만 Python의 기본
verify=True 경로는 실패; kor.py/jpn.py가 쓰는 것과 동일한 verify=False 우회 패턴을 따른다).
`src.collectors.base.download()`는 verify 옵션이 없으므로 단일 파일임에도 `__RENDER__` +
자체 requests 세션으로 처리한다.
"""

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.collectors.base import INDICATOR
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_CSV_URL = "https://www.cbc.gov.tw/public/data/OpenData/%E7%B6%93%E7%A0%94%E8%99%95/EF03M01.csv"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

_PERIOD_COL = "月"
_TD_COL = "貨幣機構存款-合計-期底餘額-億元"
_FCD_COL = "貨幣機構存款-企業及個人存款-外匯存款-期底餘額-億元"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    df = pd.read_csv(BytesIO(content), encoding="utf-8-sig")

    missing = [c for c in (_PERIOD_COL, _TD_COL, _FCD_COL) if c not in df.columns]
    if missing:
        logger.warning("[%s] 예상 컬럼 없음: %s", country_code, missing)
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    rows = []
    for _, r in df.iterrows():
        raw_period = str(r[_PERIOD_COL]).strip()
        if "M" not in raw_period:
            continue
        try:
            year_str, month_str = raw_period.split("M")
            year, month = int(year_str), int(month_str)
        except ValueError:
            continue

        td_val, fcd_val = r[_TD_COL], r[_FCD_COL]
        if not isinstance(td_val, (int, float)) or pd.isna(td_val):
            continue
        if not isinstance(fcd_val, (int, float)) or pd.isna(fcd_val):
            continue

        period = f"{year}-{month:02d}"
        td = round(float(td_val), 2)
        fcd = round(float(fcd_val), 2)
        ratio = round((fcd / td) * 100, 2) if td else None

        for indicator, value in ((INDICATOR, fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
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
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    out = pd.DataFrame(rows).drop_duplicates(subset=["period", "indicator"], keep="last")
    return out.sort_values(["period", "indicator"]).reset_index(drop=True)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    response = requests.get(_CSV_URL, headers=_HEADERS, timeout=30, verify=False)
    response.raise_for_status()
    return parse(response.content, country_code)
