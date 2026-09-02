"""Korea (Republic of): BOK ECOS 예금은행 총수신(말잔).

API (sample 키로 기간 청크 조회; 선택적으로 ECOS_API_KEY 환경변수 사용):
  https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/{start}/{end}/104Y013/M/{from}/{to}/{item}

통계: 104Y013 예금은행 총수신(말잔), 단위 십억원
  FCD  BCB2 외화예금
  TD   BCB1 원화예금 + BCB2 외화예금   (예금 합계; CD·금융채 등 수신합계 BCB8 제외)

FCD_TD_RATIO = FCD/TD*100
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_STAT = "104Y013"
_ITEM_KRW = "BCB1"  # 원화예금
_ITEM_FC = "BCB2"  # 외화예금
_API_TMPL = (
    "https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/"
    "{start}/{end}/{stat}/M/{pfrom}/{pto}/{item}"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*",
}

# sample 키는 요청당 최대 10건 → 월 단위 10개월씩 슬라이스
_CHUNK_MONTHS = 10
_START_YEAR = 1995
_START_MONTH = 1


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("KOR는 render()로 ECOS API를 호출한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _api_key() -> str:
    return os.environ.get("ECOS_API_KEY") or os.environ.get("BOK_API_KEY") or "sample"


def _ym_iter(y0: int, m0: int, y1: int, m1: int):
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _add_months(y: int, m: int, n: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) + n
    return idx // 12, idx % 12 + 1


def _chunks(y0: int, m0: int, y1: int, m1: int, size: int):
    cur_y, cur_m = y0, m0
    while (cur_y, cur_m) <= (y1, m1):
        end_y, end_m = _add_months(cur_y, cur_m, size - 1)
        if (end_y, end_m) > (y1, m1):
            end_y, end_m = y1, m1
        yield cur_y, cur_m, end_y, end_m
        cur_y, cur_m = _add_months(end_y, end_m, 1)


def _fetch_item(item: str, key: str) -> dict[str, float]:
    """period YYYY-MM -> value."""
    now = datetime.now(timezone.utc)
    y1, m1 = now.year, now.month
    out: dict[str, float] = {}
    # real key: larger page size; sample: 10
    page_size = 10000 if key != "sample" else 10
    chunk = 100 if key != "sample" else _CHUNK_MONTHS

    for y0, m0, ye, me in _chunks(_START_YEAR, _START_MONTH, y1, m1, chunk):
        pfrom = f"{y0}{m0:02d}"
        pto = f"{ye}{me:02d}"
        url = _API_TMPL.format(
            key=key, start=1, end=page_size, stat=_STAT,
            pfrom=pfrom, pto=pto, item=item,
        )
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=60, verify=False)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("[KOR] fetch %s %s-%s failed: %s", item, pfrom, pto, e)
            continue
        ss = data.get("StatisticSearch")
        if not ss or "row" not in ss:
            # empty or error
            continue
        for row in ss["row"]:
            t = str(row.get("TIME", ""))
            if len(t) != 6:
                continue
            period = f"{t[:4]}-{t[4:6]}"
            try:
                out[period] = float(row["DATA_VALUE"])
            except (TypeError, ValueError, KeyError):
                continue
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    key = _api_key()
    logger.info("[%s] ECOS key=%s stat=%s", country_code, key[:6] + "...", _STAT)
    try:
        fcd_map = _fetch_item(_ITEM_FC, key)
        krw_map = _fetch_item(_ITEM_KRW, key)
        if not fcd_map or not krw_map:
            logger.error("[%s] empty series fcd=%d krw=%d", country_code, len(fcd_map), len(krw_map))
            return _empty()

        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for period in sorted(set(fcd_map) & set(krw_map)):
            fcd = fcd_map[period]
            krw = krw_map[period]
            td = fcd + krw
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
        out = (
            pd.DataFrame(rows)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] %d rows (%s~%s)",
            country_code, len(out), out["period"].min(), out["period"].max(),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
