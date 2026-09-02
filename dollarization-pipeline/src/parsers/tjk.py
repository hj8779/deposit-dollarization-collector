"""Tajikistan: National Bank of Tajikistan(NBT) "Banking Statistics Bulletin" PDF들.

이전 조사에서는 Monetary Survey / Financial Corporations Survey 파일만 확인했는데
거기엔 예금이 "DEPOSITS" 한 줄 집계로만 잡혀 통화별 분해가 없었다(막다른 길). 이번에
nbt.tj/en/statistics/statistical_bulletin.php ("Banking statistics bulletin")를 추가로
찾았고, 여기서 매달(주로 12월호에 그 해 1~12월 누적) 발행하는 PDF 안에
"Structure of outstanding savings (deposits) in credit financial institutions" 표
(러시아어 제목 "Структура остатков сбережений (депозитов) в кредитных...организациях")
에 다음 행이 있다:

    1.   Всего депозитов / Total deposits              -> TD
    1.1. в национальной валюте / In domestic currency
    1.2. в иностранной валюте / In foreign currency     -> FCD

2025-12-31 값(TD=33,895,226.6천 소모니, FCD=12,730,085.1천 소모니, FCD/TD=37.6%)이
보도자료(nbt.tj/en/news/618354/, TD≈33.9bn TJS, FX share 37.5%)와 사실상 일치해
이 표가 실제 신뢰 가능한 시계열임을 확인했다.

수집 절차:
1. statistical_bulletin.php 목록 페이지에서 *.pdf 링크와 그 옆 텍스트("Last issue of
   2024", "Issue of 2026, May №5 (370)" 등)를 모두 모아 연도를 추출한다(연도 없는
   항목은 skip). 링크 목록은 발행할 때마다 최신호로 갱신되므로 URL을 하드코딩하지 않고
   매번 동적으로 읽는다.
2. 각 PDF를 pdftotext -layout 으로 텍스트화한다(pdfplumber.extract_text()는 이 PDF들의
   특정 폰트에서 문자가 뒤집혀 나오는 경우가 있어 pdftotext가 더 안정적 — 표준 OCR
   폴백 대상은 아니고, 단순 레이아웃 재구성 이슈라 pdftotext -layout으로 충분함).
3. "остатков сбережений (депозитов) в кредитн" 표 제목이 나오는 지점을 모두 찾고(목차에도
   같은 문구가 나오므로 중복), 그 아래에서 "1. Всего депозитов"(총계),
   "1.1. в национальной валюте"(자국통화), "1.2. в иностранной валюте"(외화) 세 행을
   파싱해 domestic+foreign≈total 검증을 통과하는 표만 채택한다.
4. 표 헤더 행(컬럼)은 연도(예: '2019')뿐인 경우(월별 12칸)도 있고, 과거 연혁 + 당해년도가
   섞인 경우(예: '2012' '2013' ... '2017' 'I' 'II' ... 'XII')도 있다 — 오래된 회보일수록
   "누적연혁 N개 + 당해년도 월별 12개"식으로 컬럼이 늘어난다. 로마숫자(I~XII) 컬럼은 그
   회보의 해당 연도 월별 값으로, 4자리 연도 컬럼은 그 해 12월(연말 잔액) 값으로 처리한다.
5. 일부 회보(2020년 12월호, 2011~2015년 일부)는 폰트 인코딩이 깨져 pdftotext로도 정상
   텍스트가 나오지 않는다 — 이런 실패 건은 조용히 skip한다(회보별로 최대 하나씩만
   있으므로 몇 개 연도가 통째로 빠질 수 있음. 그래도 최근 회보에 누적된 과거 연혁 컬럼
   덕에 2012년부터 연말 스냅샷은 대부분 복구 가능).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

BULLETIN_LIST_URL = "https://nbt.tj/en/statistics/statistical_bulletin.php"

_ROMAN = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}

_HEADING_RE = re.compile(
    r"остатков сбережений\s*\(депозитов\)\s*в кредитн", re.IGNORECASE
)
_YEAR_IN_TEXT_RE = re.compile(r"(?:Last issue of|Issue of)\s*(\d{4})", re.IGNORECASE)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("TJK는 render()로 여러 회보 PDF를 순회한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _discover_bulletin_urls() -> list[tuple[int, str]]:
    """목록 페이지에서 (연도, PDF절대URL) 쌍을 모두 찾는다."""
    html = download(BULLETIN_LIST_URL).decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        text = a.get_text(" ", strip=True)
        m = _YEAR_IN_TEXT_RE.search(text)
        if not m:
            continue
        year = int(m.group(1))
        url = urljoin(BULLETIN_LIST_URL, href)
        if url in seen:
            continue
        seen.add(url)
        out.append((year, url))
    return out


def _pdf_text(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        path = tmp.name
    try:
        r = subprocess.run(
            ["pdftotext", "-layout", path, "-"],
            capture_output=True, text=True, timeout=120,
        )
        return r.stdout or ""
    finally:
        os.unlink(path)


def _split_cols(line: str) -> list[str]:
    return [t for t in re.split(r"\s{2,}", line.strip()) if t]


def _to_float(tok: str) -> float:
    return float(tok.replace(" ", "").replace(",", "."))


# 정상적인 값은 최대 수천만~수억(천 소모니 단위, 2026년 5월 기준 총예금 ~3,520만천 소모니)
# 수준이다. 일부 오래된(2016년 이전) 회보는 컬럼 사이 공백이 2칸 미만이라 정규식이 여러
# 숫자를 하나의 토큰으로 붙여 읽는 경우가 있는데, 그 결과는 자릿수가 비정상적으로 커지므로
# (예: 1.68e+41) 자릿수 상한으로 걸러낸다.
_MAX_DIGITS = 9  # 999,999,999천 소모니(=TJS ~1조)까지 허용, 실제 최대치보다 넉넉히 크게 잡음


def _plausible_token(tok: str) -> bool:
    int_part = re.split(r"[.,]", tok)[0]
    digits = re.sub(r"[^\d]", "", int_part)
    return 0 < len(digits) <= _MAX_DIGITS


def _find_header_cols(window: str) -> list[str] | None:
    for line in window.split("\n"):
        if "Description" not in line:
            continue
        cols = []
        for tok in _split_cols(line):
            t = tok.strip("/").strip()
            if t in _ROMAN or re.match(r"^(19|20)\d{2}$", t):
                cols.append(t)
        return cols or None
    return None


def _find_value_row(window: str, prefix: str, keyword: str) -> list[str] | None:
    for line in window.split("\n"):
        stripped = line.strip()
        if stripped.startswith(prefix) and keyword in line:
            toks = _split_cols(stripped)
            nums = [t for t in toks if re.match(r"^-?[\d ]*\d(?:[.,]\d+)?$", t) and any(c.isdigit() for c in t)]
            if nums:
                return nums
    return None


def _extract_table(text: str) -> tuple[list[str], list[str], list[str], list[str]] | None:
    """(header_cols, total, domestic, foreign) 를 반환. 실패 시 None."""
    matches = list(_HEADING_RE.finditer(text))
    for m in reversed(matches):  # 목차보다 실제 표(대개 뒤쪽)를 우선 시도
        window = text[m.end(): m.end() + 4000]
        header = _find_header_cols(window)
        total = _find_value_row(window, "1.", "Всего депозитов")
        domestic = _find_value_row(window, "1.1.", "национальной валюте")
        foreign = _find_value_row(window, "1.2.", "иностранной валюте")
        if not (header and total and domestic and foreign):
            continue
        if not (len(total) == len(domestic) == len(foreign)):
            continue
        if len(header) < len(total):
            continue
        header = header[: len(total)]
        if not all(_plausible_token(tok) for tok in (*total, *domestic, *foreign)):
            # 컬럼 사이 공백이 2칸 미만이라 숫자 여러 개가 한 토큰으로 붙어버린 경우
            # (자릿수가 비정상적으로 큼) -- 이 표는 신뢰할 수 없으므로 다음 후보를 시도한다.
            continue
        try:
            ok = all(
                abs(_to_float(d) + _to_float(f) - _to_float(t)) < max(1.0, 0.01 * abs(_to_float(t)))
                for d, f, t in zip(domestic, foreign, total)
            )
        except ValueError:
            ok = False
        if ok:
            return header, total, domestic, foreign
    return None


def _rows_from_bulletin(bulletin_year: int, text: str, country_code: str, now: str) -> list[dict]:
    extracted = _extract_table(text)
    if extracted is None:
        return []
    header, total, domestic, foreign = extracted
    rows = []
    for col, t_tok, f_tok in zip(header, total, foreign):
        if not (_plausible_token(t_tok) and _plausible_token(f_tok)):
            continue
        try:
            td = _to_float(t_tok)
            fcd = _to_float(f_tok)
        except ValueError:
            continue
        if td <= 0 or fcd < 0 or fcd > td * 1.05:
            continue
        if col in _ROMAN:
            year, period = bulletin_year, f"{bulletin_year}-{_ROMAN[col]:02d}"
        elif re.match(r"^(19|20)\d{2}$", col):
            year, period = int(col), f"{col}-12"
        else:
            continue
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in (("FCD", round(fcd, 2)), ("TD", round(td, 2)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": period,
                "indicator": indicator, "value": value, "updated_at": now,
            })
    return rows


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()
    try:
        bulletins = _discover_bulletin_urls()
    except Exception as e:
        logger.exception("[%s] failed to list statistical bulletins: %s", country_code, e)
        return _empty()

    if not bulletins:
        logger.error("[%s] no bulletin links discovered", country_code)
        return _empty()

    all_rows: list[dict] = []
    for bulletin_year, url in bulletins:
        try:
            content = download(url)
            if not content.startswith(b"%PDF"):
                continue
            text = _pdf_text(content)
            if not text.strip():
                logger.warning("[%s] empty text extraction for %s (year=%s), skipping", country_code, url, bulletin_year)
                continue
            rows = _rows_from_bulletin(bulletin_year, text, country_code, now)
            if not rows:
                logger.warning("[%s] could not locate/parse deposits-by-currency table in %s (year=%s)", country_code, url, bulletin_year)
                continue
            all_rows.extend(rows)
            logger.info("[%s] parsed %d rows from bulletin year=%s (%s)", country_code, len(rows), bulletin_year, url)
        except Exception as e:
            logger.warning("[%s] failed on bulletin year=%s (%s): %s", country_code, bulletin_year, url, e)
            continue

    if not all_rows:
        logger.error("[%s] no bulletins parsed successfully", country_code)
        return _empty()

    out = (
        pd.DataFrame(all_rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info("[%s] %d rows total (%s~%s)", country_code, len(out), out["period"].min(), out["period"].max())
    return out
