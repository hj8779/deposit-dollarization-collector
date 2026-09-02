"""Mauritius: Bank of Mauritius — Monetary Developments PDFs.

목록(페이지네이션 page=0..N):
  https://www.bom.mu/publications-and-statistics/statistics/monetary-and-financial-statistics/depository-corporation-survey?page=N
링크 텍스트가 "Monetary Developments: <Month> <Year>" 형태인 것만 골라 쓴다(제목 표기가
"MAY 2008"처럼 대문자거나 "December 2008"처럼 일반 표기인 두 가지가 섞여 있음 - 정규식은
대소문자 무관하게 매칭).

표 "COMPONENTS AND SOURCES OF BROAD MONEY LIABILITIES"는 시기별로 세 가지 상태가 섞여
있음(문서 하나씩 실제로 열어 텍스트 추출 가능 여부/라벨을 확인함):
  - 2008~2011: 텍스트 추출 가능, 구형 라벨(아래 OLD).
  - 2012~2020: 표가 이미지로 스캔되어 있어 텍스트 추출이 안 됨(페이지 2가 비어 있음) →
    OCR 필요. 라벨은 2018년경까지 구형(OLD), 이후 신형(NEW)으로 섞여 있음.
  - 2021~현재: 텍스트 추출 가능, 신형 라벨(NEW).

OLD 라벨: '2. Transferable Deposits' / '1. Savings Deposits' / '2. Time Deposits' /
          '3. Foreign Currency Deposits' (Narrow Money 밑에 있는 'II. Quasi-Money
          Liabilities (1+2+3)' 총계행은 OCR에서 자주 깨져 안 쓰고, 대신 네 항목을 직접
          더한다: TD = Transferable + Savings + Time + FCD)
NEW 라벨: 'II. Deposit Liabilities'(총계) / 'II.2. Foreign Currency Deposits' (TD = 총계
          그대로, FCD는 그 하위 항목)

OCR은 pytesseract, psm 6(균일 텍스트 블록 가정)이 표 형태에서 라벨/숫자 정렬을 가장 잘
보존함(기본 psm 3은 표를 여러 블록으로 쪼개 라벨과 숫자 열이 분리되어 나오는 경우가 있음).
라벨 자체가 OCR로 깨져 인식이 안 되는 파일(예: 2018-01, 2018-09)은 신뢰할 수 있는 값을
만들 수 없어 건너뛴다(숫자 줄 순서로 위치 추정하는 방식은 한 줄이라도 밀리면 잘못된 값이
조용히 들어갈 위험이 있어 채택하지 않음).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import pandas as pd
import pdfplumber
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_LIST_PAGE = (
    "https://www.bom.mu/publications-and-statistics/statistics/"
    "monetary-and-financial-statistics/depository-corporation-survey"
)
_MAX_LIST_PAGES = 40  # 확인 시점 기준 마지막 페이지=33; 여유를 두고 순회

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_LINK_RE = re.compile(
    r'href="([^"]+\.pdf)">\s*Monetary Developments:\s*([A-Za-z]+)\s+(\d{4})\s*</a>', re.I
)


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MUS는 render()로 Monetary Developments PDF를 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _list_issues() -> list[tuple[str, str]]:
    """[(period, pdf_url), ...] — 목록 페이지네이션을 끝까지 순회해 실제 게시된 링크만 모은다."""
    out: list[tuple[str, str]] = []
    for page_no in range(_MAX_LIST_PAGES):
        url = _LIST_PAGE if page_no == 0 else f"{_LIST_PAGE}?page={page_no}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=20, verify=False)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        matches = _LINK_RE.findall(resp.text)
        if not matches:
            continue
        for href, mon_s, year_s in matches:
            month = _MONTH_MAP.get(mon_s.lower())
            if not month:
                continue
            period = f"{int(year_s)}-{month:02d}"
            out.append((period, urljoin(url, href)))
    dedup = {period: url for period, url in out}  # 뒤 페이지가 갱신본일 가능성 낮음, 순서 무관
    logger.info("[MUS] 목록에서 Monetary Developments %d건 발견 (%s~%s)",
                len(dedup), min(dedup) if dedup else "-", max(dedup) if dedup else "-")
    return sorted(dedup.items())


def _pdf_text(content: bytes) -> str:
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        try:
            r = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=60)
            if r.stdout:
                return r.stdout
        finally:
            import os
            os.unlink(path)
    except Exception:
        pass
    with pdfplumber.open(BytesIO(content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _ocr_table_page(content: bytes) -> str | None:
    import pytesseract

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            page = pdf.pages[1] if len(pdf.pages) > 1 else pdf.pages[0]
            img = page.to_image(resolution=350).original
            return pytesseract.image_to_string(img, config="--psm 6")
    except Exception:
        logger.warning("[MUS] OCR 실패", exc_info=True)
        return None


def _num_after(text: str, label: str) -> float | None:
    """label이 포함된 줄에서, 그 뒤에 오는 첫 숫자(콤마 또는 3자리 그룹 공백 구분)를 뽑는다.
    OCR 결과는 '62 551'(공백으로 쪼개진 천단위)일 수도, '62,551'(콤마 보존)일 수도 있어
    둘 다 처리한다."""
    for line in text.splitlines():
        idx = line.lower().find(label.lower())
        if idx == -1:
            continue
        rest = line[idx + len(label):].strip()
        toks = rest.split()
        if not toks:
            continue
        first = toks[0].replace(",", "")
        if not re.fullmatch(r"-?\d+\.?\d*", first):
            continue
        if re.fullmatch(r"-?\d{1,3}", first) and len(toks) > 1 and re.fullmatch(r"\d{3}", toks[1]):
            first += toks[1]
        try:
            return float(first)
        except ValueError:
            continue
    return None


def _extract_new_format(text: str) -> tuple[float, float] | None:
    """(fcd, td) — 'II. Deposit Liabilities' 총계 + 'Foreign Currency Deposits' 하위 항목."""
    fcd = _num_after(text, "Foreign Currency Deposits")
    td = _num_after(text, "Deposit Liabilities")
    if fcd is None or td is None or td <= 0:
        return None
    return fcd, td


def _extract_old_format(text: str) -> tuple[float, float] | None:
    """(fcd, td) — Transferable + Savings + Time + FCD 직접 합산(총계행 라벨은 OCR로 자주
    깨져 신뢰하지 않음)."""
    fcd = _num_after(text, "Foreign Currency Deposits")
    transferable = _num_after(text, "Transferable Deposits")
    savings = _num_after(text, "Savings Deposits")
    time_dep = _num_after(text, "Time Deposits")
    if None in (fcd, transferable, savings, time_dep):
        return None
    td = transferable + savings + time_dep + fcd
    if td <= 0:
        return None
    return fcd, td


def _extract_fcd_td(text: str) -> tuple[float, float] | None:
    return _extract_new_format(text) or _extract_old_format(text)


def _parse_pdf(content: bytes, period: str, country_code: str) -> pd.DataFrame:
    text = _pdf_text(content)
    result = _extract_fcd_td(text)
    if result is None:
        ocr_text = _ocr_table_page(content)
        if ocr_text:
            result = _extract_fcd_td(ocr_text)
    if result is None:
        logger.warning("[%s] FCD/TD 라벨을 못 찾음: %s", country_code, period)
        return _empty()

    fcd, td = result
    year = int(period[:4])
    ratio = round((fcd / td) * 100, 4)
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {"country_code": country_code, "year": year, "period": period, "indicator": ind, "value": val, "updated_at": now}
        for ind, val in (("FCD", round(fcd, 4)), ("TD", round(td, 4)), ("FCD_TD_RATIO", ratio))
    ]
    return pd.DataFrame(rows)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        issues = _list_issues()
        if not issues:
            logger.error("[%s] 목록에서 발행본을 찾지 못함", country_code)
            return _empty()

        def _one(period: str, url: str) -> pd.DataFrame | None:
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=60, verify=False)
                if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
                    return None
                return _parse_pdf(resp.content, period, country_code)
            except Exception:
                logger.warning("[%s] %s 처리 실패", country_code, period, exc_info=True)
                return None

        frames: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(_one, period, url): period for period, url in issues}
            for fut in as_completed(futs):
                df = fut.result()
                if df is not None and not df.empty:
                    frames.append(df)

        if not frames:
            return _empty()

        out = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] %d rows (%s~%s) from %d/%d issues",
            country_code, len(out), out["period"].min(), out["period"].max(),
            len(frames), len(issues),
        )
        return out
    except Exception:
        logger.exception("[%s] failed", country_code)
        return _empty()
