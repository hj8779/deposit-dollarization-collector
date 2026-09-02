"""Guinea: Banque Centrale de la République de Guinée(BCRG) Situation Monétaire intégrée.

Bulletin Statistiques는 중단되었고, 현재 구현은 Séries monétaires.xls 경로만 담당한다.
최신 구간 보완용 PDF 2종(분기 Rapport sur la Politique Monétaire, 연간 Rapport Annuel)은
config/targets.json 의 pending_parsers(status=todo)에 표시해 두었으며 추후 구현 예정.

소스 페이지(오타 URL 그대로 사용):
    https://www.bcrg-guinee.org/satistiques/series-statistiques/
    → "Situation Monétaire intégrée" 링크
    → Séries monétaires.xls (legacy OLE .xls)

파일 URL은 페이지에 하드코딩되어 있으며(uploads/2020/02/...), 동일 경로 파일이
주기적으로 갱신된다. render()는 페이지에서 링크를 다시 찾고, 실패 시 알려진 경로로
폴백한다.

시트 'SMI' (Situation Monétaire Intégrée), 단위: milliards de GNF
    row3  월별 날짜 헤더 (2011-10-01 ~ …, 월초 표기)
    row22 Monnaie en circulation
    row23 Dépôts à vue gnf
    row24 Dépôts à terme gnf
    row25 Dépôts en devises          ← FCD
    row26 ( en millions de dollars )  # FCD의 USD 환산, 사용 안 함

FCD = Dépôts en devises
TD  = Dépôts à vue gnf + Dépôts à terme gnf + Dépôts en devises
      (통화유통 제외, 예금 잔액 기준 달러화율)
FCD_TD_RATIO = FCD / TD * 100
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import pandas as pd
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PAGE_URL = "https://www.bcrg-guinee.org/satistiques/series-statistiques/"
_FALLBACK_XLS = (
    "https://www.bcrg-guinee.org/wp-content/uploads/2020/02/"
    "S%C3%A9ries-mon%C3%A9taires.xls"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE_URL,
}


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _norm(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    # strip accents for robust matching
    for a, b in (
        ("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ù", "u"), ("ô", "o"),
        ("î", "i"), ("ç", "c"),
    ):
        text = text.replace(a, b)
    return text


def _find_label_row(df: pd.DataFrame, *needles: str) -> int | None:
    """col0 라벨에서 needles 전부(정규화 부분일치)를 포함하는 첫 행."""
    wanted = [_norm(n) for n in needles]
    for i in range(df.shape[0]):
        v = df.iat[i, 0]
        if not isinstance(v, str):
            continue
        s = _norm(v)
        if all(n in s for n in wanted):
            return i
    return None


def _to_period(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return f"{value.year}-{value.month:02d}"
    if hasattr(value, "year") and hasattr(value, "month"):
        try:
            return f"{int(value.year)}-{int(value.month):02d}"
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if len(text) >= 7 and text[4] == "-":
            try:
                y, m = int(text[:4]), int(text[5:7])
                if 1 <= m <= 12:
                    return f"{y}-{m:02d}"
            except ValueError:
                return None
    return None


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Situation Monétaire intégrée .xls 바이트 → FCD/TD/FCD_TD_RATIO 롱폼."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        xl = pd.ExcelFile(BytesIO(content), engine="xlrd")
    except Exception:
        try:
            xl = pd.ExcelFile(BytesIO(content))
        except Exception as e:
            logger.error("[%s] xls 열기 실패: %s", country_code, e)
            return _empty()

    sheet = "SMI" if "SMI" in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)

    fcd_row = _find_label_row(df, "depots en devises")
    if fcd_row is None:
        fcd_row = _find_label_row(df, "depot", "devises")
    vue_row = _find_label_row(df, "depots a vue")
    terme_row = _find_label_row(df, "depots a terme")
    # USD 환산 행(바로 아래)과 혼동 방지: 'millions de dollars' 제외
    if fcd_row is not None:
        label = str(df.iat[fcd_row, 0])
        if "dollar" in _norm(label):
            fcd_row = None

    if fcd_row is None or vue_row is None or terme_row is None:
        logger.error(
            "[%s] 라벨 행 미발견 fcd=%s vue=%s terme=%s",
            country_code, fcd_row, vue_row, terme_row,
        )
        return _empty()

    # 날짜 헤더 행: 첫 datetime 이 있는 행
    date_row = None
    for i in range(min(8, len(df))):
        for j in range(1, min(5, df.shape[1])):
            if _to_period(df.iat[i, j]) is not None:
                date_row = i
                break
        if date_row is not None:
            break
    if date_row is None:
        logger.error("[%s] 날짜 헤더 행을 찾지 못함", country_code)
        return _empty()

    rows = []
    for j in range(1, df.shape[1]):
        period = _to_period(df.iat[date_row, j])
        if period is None:
            continue
        try:
            fcd = float(df.iat[fcd_row, j])
            vue = float(df.iat[vue_row, j])
            terme = float(df.iat[terme_row, j])
        except (TypeError, ValueError):
            continue
        if pd.isna(fcd) or pd.isna(vue) or pd.isna(terme):
            continue
        td = vue + terme + fcd
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
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["period", "indicator"], keep="last")
    return out.sort_values(["period", "indicator"]).reset_index(drop=True)


def _resolve_xls_url(session: requests.Session) -> str:
    """목록 페이지에서 Situation Monétaire / Séries monétaires 링크를 찾는다."""
    try:
        resp = session.get(_PAGE_URL, timeout=45)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.warning("[GIN] 목록 페이지 실패, 폴백 URL 사용: %s", e)
        return _FALLBACK_XLS

    # href + anchor text 쌍
    candidates: list[str] = []
    for m in re.finditer(
        r'href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        re.I | re.S,
    ):
        href, text = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        href_l, text_l = href.lower(), _norm(text)
        if any(k in href_l for k in ["series-monetaires", "s%c3%a9ries-mon", "monetaires.xls", "monétaires.xls"]):
            candidates.append(href)
            continue
        if "situation monetaire" in text_l or "series monetaire" in text_l:
            if href_l.endswith((".xls", ".xlsx")) or "upload" in href_l:
                candidates.append(href)

    # bare .xls links with monetaire in path
    if not candidates:
        for m in re.finditer(r'href=["\']([^"\']+\.xls[x]?)["\']', html, re.I):
            href = m.group(1)
            if "monet" in href.lower() or "mon%c3%a9t" in href.lower():
                candidates.append(href)

    if candidates:
        url = urljoin(_PAGE_URL, candidates[0])
        logger.info("[GIN] 페이지에서 xls 링크 발견: %s", url)
        return url

    logger.warning("[GIN] 페이지에서 xls 링크 미발견, 폴백 URL 사용")
    return _FALLBACK_XLS


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    session = requests.Session()
    session.headers.update(_HEADERS)

    xls_url = _resolve_xls_url(session)
    logger.info("[%s] Situation Monétaire 다운로드: %s", country_code, xls_url)
    resp = session.get(xls_url, timeout=60)
    resp.raise_for_status()
    content = resp.content
    # OLE Compound File magic
    if not (content[:4] == b"\xd0\xcf\x11\xe0" or content[:2] == b"PK"):
        logger.error(
            "[%s] 엑셀이 아닌 응답(len=%d, head=%r)",
            country_code, len(content), content[:40],
        )
        return _empty()

    df = parse(content, country_code)
    if not df.empty:
        logger.info(
            "[%s] %d행 (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    return df
