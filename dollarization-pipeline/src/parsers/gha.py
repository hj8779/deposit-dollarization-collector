"""Ghana: Bank of Ghana(BoG) Monetary Survey (wpDataTables).

페이지 https://www.bog.gov.gh/economic-data/monetary-survey/ 는 Export(Excel/CSV)
버튼을 제공하지만, 실제 소스는 MySQL 기반 wpDataTables(serverSide) 테이블
id=22 이다. Export는 브라우저 DataTables 플러그인이 같은 AJAX 응답을 파일로
내려받는 것뿐이라, 여기서는 Export UI 대신 동일 엔드포인트를 직접 호출한다.

    GET  페이지 → nonce(wdtNonceFrontendServerSide_22) + 세션 쿠키
    POST /wp-admin/admin-ajax.php?action=get_wdtable&table_id=22
         body: draw/start/length/wdtNonce + DataTables columns[*] 파라미터
         length=-1 로 필터된 전체(약 450행, 2000~최신) 수신

SSL: bog.gov.gh 인증서 체인 문제로 verify=False 가 필요하다
(기존 targets 메모의 '접속 실패' 원인이었음).

행 구조 (지저분한 라벨):
    [Year, Variables, Jan, Feb, ..., Dec]
    Variables 예:
      "Money Supply Component_Foreign currency deposits (Millions of Ghana Cedis) "
      "Money Supply Component_Demand deposits (Millions of Ghana Cedis)"
      "Money Supply Component_Savings & Time deposits (Millions of Ghana Cedis)"
      "Money Supply_Broad Money (M2) (Millions of Ghana Cedis) "
      "Money Supply_Total Liquidity (M2+) (Millions of Ghana Cedis) "
    → 접두사/단위/앞뒤 공백/이중 공백이 섞여 있어 정규화 후 부분 매칭.

정의 (가나 통화통계 관례, 실측으로 M2+ = M2 + FCD 및
      M2+ - Currency = Demand + Savings&Time + FCD 항등식 확인):
    FCD = Foreign currency deposits
    TD  = Demand deposits + Savings & Time deposits + FCD
          (통화유통액 제외, 예금 잔액 기준 달러화율)
    FCD_TD_RATIO = FCD / TD * 100

동일 Year 가 두 번 나오는 경우(2022: 미완/개정 중복 행)는 비제로 월 수가 더 많은
쪽(동률이면 나중 행)을 채택한다. 값이 0.00 인 월은 미공시로 보고 건너뛴다.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PAGE_URL = "https://www.bog.gov.gh/economic-data/monetary-survey/"
_AJAX_URL = (
    "https://www.bog.gov.gh/wp-admin/admin-ajax.php"
    "?action=get_wdtable&table_id=22"
)
_TABLE_ID = 22
_N_COLS = 14  # Year, Variables, Jan..Dec

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.bog.gov.gh",
    "Referer": _PAGE_URL,
}

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("GHA는 render()로 AJAX 수집한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _norm_label(text: str) -> str:
    """라벨 공백/특수문자 정리 후 소문자화."""
    text = text.replace("\xa0", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _classify_variable(label: str) -> str | None:
    """Variables 열 문자열을 fcd / demand / savings_time 중 하나로 분류.
    Net Foreign Assets, Govt. Deposits 등 유사 키워드는 제외."""
    s = _norm_label(label)
    # 예금 구성요소만 (Money Supply Component_... 또는 동일 문구)
    if "foreign currency deposit" in s:
        return "fcd"
    if "demand deposit" in s:
        return "demand"
    if "savings" in s and "time deposit" in s:
        return "savings_time"
    return None


def _parse_number(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text == "" or text.lower() in {"nan", "none", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _nonzero_count(months: list[float | None]) -> int:
    return sum(1 for v in months if v is not None and v != 0.0)


def _pick_better(old: list[float | None], new: list[float | None]) -> list[float | None]:
    """중복 Year 행: 비제로 월이 더 많은 쪽, 동률이면 new(나중 행) 우선."""
    if _nonzero_count(new) >= _nonzero_count(old):
        return new
    return old


def _fetch_table_rows(session: requests.Session, nonce: str) -> list[list]:
    data = {
        "draw": "1",
        "start": "0",
        "length": "-1",
        "wdtNonce": nonce,
        "search[value]": "",
        "search[regex]": "false",
        "order[0][column]": "0",
        "order[0][dir]": "asc",
    }
    for i in range(_N_COLS):
        data[f"columns[{i}][data]"] = str(i)
        data[f"columns[{i}][name]"] = ""
        data[f"columns[{i}][searchable]"] = "true"
        data[f"columns[{i}][orderable]"] = "true"
        data[f"columns[{i}][search][value]"] = ""
        data[f"columns[{i}][search][regex]"] = "false"

    resp = session.post(_AJAX_URL, data=data, timeout=120)
    resp.raise_for_status()
    if not resp.content:
        raise RuntimeError("wpDataTables AJAX 빈 응답 (URL에 action/table_id 쿼리 필요)")
    payload = resp.json()
    rows = payload.get("data") or []
    logger.info(
        "[GHA] wpDataTables table_id=%s recordsTotal=%s recordsFiltered=%s got=%d",
        _TABLE_ID,
        payload.get("recordsTotal"),
        payload.get("recordsFiltered"),
        len(rows),
    )
    return rows


def _series_from_rows(rows: list[list]) -> dict[str, dict[str, list[float | None]]]:
    """year -> {fcd|demand|savings_time -> [12 months]}."""
    out: dict[str, dict[str, list[float | None]]] = {}
    for row in rows:
        if not row or len(row) < 3:
            continue
        year = str(row[0]).strip()
        if not re.fullmatch(r"\d{4}", year):
            continue
        kind = _classify_variable(str(row[1]))
        if kind is None:
            continue
        months = [_parse_number(row[i]) if i < len(row) else None for i in range(2, 14)]
        # pad/truncate to 12
        months = (months + [None] * 12)[:12]
        bucket = out.setdefault(year, {})
        if kind in bucket:
            bucket[kind] = _pick_better(bucket[kind], months)
        else:
            bucket[kind] = months
    return out


def _build_frame(country_code: str, series: dict[str, dict[str, list[float | None]]]) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for year in sorted(series):
        parts = series[year]
        fcd_m = parts.get("fcd")
        dem_m = parts.get("demand")
        sav_m = parts.get("savings_time")
        if not fcd_m or not dem_m or not sav_m:
            continue
        for mi in range(12):
            fcd = fcd_m[mi]
            dem = dem_m[mi]
            sav = sav_m[mi]
            # 0.00 은 미공시(최근 연도 trailing zero)로 취급
            if fcd is None or dem is None or sav is None:
                continue
            if fcd == 0.0 or dem == 0.0 or sav == 0.0:
                continue
            td = dem + sav + fcd
            if td <= 0:
                continue
            period = f"{year}-{mi + 1:02d}"
            ratio = round((fcd / td) * 100, 4)
            for indicator, value in (
                ("FCD", round(fcd, 4)),
                ("TD", round(td, 4)),
                ("FCD_TD_RATIO", ratio),
            ):
                rows.append({
                    "country_code": country_code,
                    "year": int(year),
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
    session = requests.Session()
    session.verify = False
    session.headers.update(_HEADERS)

    page = session.get(_PAGE_URL, timeout=60)
    page.raise_for_status()
    m = re.search(
        rf'id="wdtNonceFrontendServerSide_{_TABLE_ID}"[^>]*value="([^"]+)"',
        page.text,
    )
    if not m:
        # 이름 패턴 변형 대비
        m = re.search(r'wdtNonceFrontendServerSide_\d+"[^>]*value="([^"]+)"', page.text)
    if not m:
        logger.error("[%s] wpDataTables nonce를 페이지에서 찾지 못함", country_code)
        return _empty()
    nonce = m.group(1)

    try:
        raw_rows = _fetch_table_rows(session, nonce)
    except Exception as e:
        logger.exception("[%s] Monetary Survey AJAX 실패: %s", country_code, e)
        return _empty()

    series = _series_from_rows(raw_rows)
    df = _build_frame(country_code, series)
    if df.empty:
        logger.warning("[%s] FCD/TD 시리즈를 만들지 못함 (매칭 실패 가능)", country_code)
    else:
        logger.info(
            "[%s] %d행 (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    return df
