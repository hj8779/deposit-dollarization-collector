"""India: RBI Handbook of Statistics — FCNR(B) / Aggregate Deposits.

Handbook of Statistics on the Indian Economy
  https://rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook%20of%20Statistics%20on%20Indian%20Economy

사용 표 (연간, 3월말 잔액, ₹ Crore):
  Table 140 – Non-Resident Deposits Outstanding - Rupees
      FCD = FCNR(B)  (외화 비거주 예금; 실질 FCD에 가장 가까운 항목)
      NRE/NRO는 루피 계좌이므로 FCD에 포함하지 않음
  Table 41  – Scheduled Commercial Banks - Select Aggregates
      TD  = Aggregate Deposits (Demand + Time)

비고:
- 인도 공식 통계에서 FCNR(B)는 종종 USD로, 총예금은 INR로 발표된다.
  동일 통화 비율을 위해 루피 표(Table 140)와 Aggregate Deposits(Table 41)를 짝짓는다.
- 회계연도 라벨 `YYYY-(YY+1)` (Table 41) → 기말 연도 `YYYY+1`의 3월 (`{end}-03`).
- Table 140 연도 `YYYY` = end-March YYYY → `{YYYY}-03`.
- Handbook PDF 해시/파일명은 발행마다 바뀌므로 목록 페이지에서 Table 번호로 URL을 해석한다.
- dataful.in 등은 유료/로그인 제약이 있어 공식 RBI Handbook PDF를 1차 소스로 사용.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pdfplumber
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_HANDBOOK_PAGE = (
    "https://rbi.org.in/Scripts/AnnualPublications.aspx"
    "?head=Handbook%20of%20Statistics%20on%20Indian%20Economy"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://rbi.org.in/",
}

# Table number -> (title substring to disambiguate, series role)
_TABLES = {
    140: ("Non-Resident Deposits Outstanding - Rupees", "fcd"),
    41: ("Scheduled Commercial Banks - Select Aggregates", "td"),
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("IND는 render()로 Handbook Table 41/140 PDF를 합산한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise RuntimeError(f"not pdf: {url} head={resp.content[:40]!r}")
    return resp.content


def _discover_table_pdfs() -> dict[int, str]:
    """Handbook 목록 HTML에서 Table N PDF 직링크를 찾는다."""
    resp = requests.get(_HANDBOOK_PAGE, headers=_HEADERS, timeout=90, verify=False)
    resp.raise_for_status()
    html = resp.text

    # RBI HTML은 단일 따옴표 href 사용
    pattern = re.compile(
        r"Table\s+(\d+)\s*:\s*([^<]+)</td>.*?"
        r"href=['\"](https://rbidocs\.rbi\.org\.in/rdocs/Publications/PDFs/[^'\"]+\.PDF)['\"]",
        re.I | re.S,
    )
    found: dict[int, list[tuple[str, str]]] = {}
    for m in pattern.finditer(html):
        num = int(m.group(1))
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        href = m.group(3)
        found.setdefault(num, []).append((title, href))

    urls: dict[int, str] = {}
    for num, (title_key, _role) in _TABLES.items():
        cands = found.get(num) or []
        pick = None
        for title, href in cands:
            if title_key.lower() in title.lower():
                pick = href
                break
        if pick is None and cands:
            # 번호만 일치하는 첫 후보 (제목 변형 대비)
            pick = cands[0][1]
        if pick is None:
            # fallback: 파일명 prefix {num}T_
            m2 = re.search(
                rf"https://rbidocs\.rbi\.org\.in/rdocs/Publications/PDFs/{num}T_[A-Z0-9]+\.PDF",
                html,
                re.I,
            )
            if m2:
                pick = m2.group(0)
        if pick:
            urls[num] = pick
            logger.info("[IND] Table %s -> %s", num, pick.split("/")[-1])
        else:
            logger.error("[IND] Table %s PDF link not found on handbook page", num)
    return urls


def _pdf_text(content: bytes, max_pages: int | None = None) -> str:
    parts: list[str] = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        pages = pdf.pages if max_pages is None else pdf.pages[:max_pages]
        for page in pages:
            t = page.extract_text() or ""
            parts.append(t)
    return "\n".join(parts)


def _to_float(token: str) -> float | None:
    t = token.strip().replace(",", "").replace(" ", "")
    if t in {"", "-", "–", "—", "na", "n.a.", "N.A."}:
        return None
    # 괄호 메모 행 제외: (20366984)
    if t.startswith("(") and t.endswith(")"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _parse_fcnr_b_table140(content: bytes) -> dict[str, float]:
    """Table 140: year, FCNR(A), FCNR(B), ... → period end-March -> FCNR(B)."""
    text = _pdf_text(content)
    series: dict[str, float] = {}
    # 행 예: 2026 - 33756 98564 - 33334 - - 165654  (USD 표)
    # 행 예: 2026 - 319514 932947 - 315523 - - 1567984 (INR 표)
    # FCNR(B)는 3번째 데이터 열(헤더 기준 col 3); 연도 다음 '-' (FCNR A) 다음 값
    row_re = re.compile(
        r"^(?P<year>19\d{2}|20\d{2})\s+"
        r"(?P<a>-|[\d,]+)\s+"
        r"(?P<b>-|[\d,]+)\s+",
        re.M,
    )
    for m in row_re.finditer(text):
        year = int(m.group("year"))
        if year < 1990 or year > 2100:
            continue
        fcd = _to_float(m.group("b"))
        if fcd is None or fcd <= 0:
            continue
        # 합리적 범위: crore 단위 FCNR(B) (수천~수십만). USD 표(만 단위) 오탐 방지 위해
        # 동일 연도에 큰 값(루피) 우선 — 호출자가 Table 140만 넘김.
        period = f"{year}-03"
        series[period] = fcd
    return series


def _parse_aggregate_deposits_table41(content: bytes) -> dict[str, float]:
    """Table 41 1페이지(예금 열): fiscal year, Demand, Time, Aggregate Deposits.

    2페이지는 Investments/Credit 열이므로 제외한다. 페이지1 말미
    '(Continued)' 이후 잔여 메모 행도 스킵.
    """
    text = _pdf_text(content, max_pages=1)
    # Continued 표기 이후(다음 장 안내/각주) 절단
    cut = re.search(r"\(Continued", text, re.I)
    if cut:
        text = text[: cut.start()]

    series: dict[str, float] = {}
    # 행 예: 2024-25 2698049 19882552 22580601 311466 ...
    row_re = re.compile(
        r"^(?P<y1>19\d{2}|20\d{2})-(?P<y2>\d{2})\s+"
        r"(?P<demand>[\d,]+)\s+"
        r"(?P<time>[\d,]+)\s+"
        r"(?P<agg>[\d,]+)\b",
        re.M,
    )
    for m in row_re.finditer(text):
        y1 = int(m.group("y1"))
        y2 = int(m.group("y2"))
        # 인도 회계연도 YYYY-(YY+1) 기말은 항상 y1+1년 3월
        expected_yy = (y1 + 1) % 100
        if y2 != expected_yy:
            logger.warning(
                "[IND] unexpected FY label %s-%02d (expected %s-%02d)",
                y1, y2, y1, expected_yy,
            )
        end_year = y1 + 1

        demand = _to_float(m.group("demand"))
        time_dep = _to_float(m.group("time"))
        agg = _to_float(m.group("agg"))
        if agg is None or agg <= 0 or demand is None or time_dep is None:
            continue
        # Demand+Time ≈ Aggregate (예금 섹션 sanity; 투자 페이지 오탐 방지)
        if abs((demand + time_dep) - agg) > max(1.0, 0.02 * agg):
            continue
        if end_year < 1960 or end_year > 2100:
            continue
        period = f"{end_year:04d}-03"
        series[period] = agg
    return series


def _build_frame(country_code: str, fcd: dict[str, float], td: dict[str, float]) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    periods = sorted(set(fcd) & set(td))
    rows = []
    for period in periods:
        fv, tv = fcd[period], td[period]
        if tv <= 0:
            continue
        year = int(period[:4])
        ratio = round((fv / tv) * 100, 4)
        for indicator, value in (
            ("FCD", round(fv, 4)),
            ("TD", round(tv, 4)),
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
    try:
        urls = _discover_table_pdfs()
    except Exception as e:
        logger.exception("[%s] handbook page scrape failed: %s", country_code, e)
        return _empty()

    fcd_url = urls.get(140)
    td_url = urls.get(41)
    if not fcd_url or not td_url:
        logger.error("[%s] missing table urls: %s", country_code, urls)
        return _empty()

    try:
        fcd_pdf = _download(fcd_url)
        fcd = _parse_fcnr_b_table140(fcd_pdf)
        logger.info(
            "[%s] FCNR(B) Table140: %d years %s~%s",
            country_code, len(fcd), min(fcd) if fcd else "-", max(fcd) if fcd else "-",
        )
    except Exception as e:
        logger.exception("[%s] Table 140 failed: %s", country_code, e)
        return _empty()

    try:
        td_pdf = _download(td_url)
        td = _parse_aggregate_deposits_table41(td_pdf)
        logger.info(
            "[%s] Aggregate Deposits Table41: %d years %s~%s",
            country_code, len(td), min(td) if td else "-", max(td) if td else "-",
        )
    except Exception as e:
        logger.exception("[%s] Table 41 failed: %s", country_code, e)
        return _empty()

    df = _build_frame(country_code, fcd, td)
    if not df.empty:
        logger.info(
            "[%s] merged %d rows (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    else:
        logger.error("[%s] no overlapping periods FCD=%s TD=%s", country_code, list(fcd)[:3], list(td)[:3])
    return df
