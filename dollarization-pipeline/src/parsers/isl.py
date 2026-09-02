"""Iceland: CBI Databank monetary deposits — sheet III (by currency).

UI: https://databank.is/report/monetary?page=FINSTATS.MONETARY.DEPOSITS.TABLE
우상단 Excel 버튼은 SPA/JS지만, 실제 파일 URL은 번역 키로 공개된다.

  GET https://databank.is/api/translation/en
  key  FINSTATS.MONETARY.DEPOSITS.EXCEL
  →   https://sedlabanki.is/library?itemid=...

Excel 시트:
  III  Innlán eftir gjaldmiðlum / Deposits by currencies
       단위: m.kr. (백만 ISK), 월말
       행 (라벨 col B, 시계열 col C~):
         Innlán alls / Deposits total          → TD
         Erlendir gjaldmiðlar / Foreign currencies → FCD
         (하위의 통화별 분해·Unspecified·거주/비거주 세부 블록은 무시)

FCD_TD_RATIO = FCD / TD * 100

시계열: 실측 1993-09 ~ 파일 최신월 (예: 2026-06).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PAGE = "https://databank.is/report/monetary?page=FINSTATS.MONETARY.DEPOSITS.TABLE"
_TRANSLATION_API = "https://databank.is/api/translation/en"
_EXCEL_KEY = "FINSTATS.MONETARY.DEPOSITS.EXCEL"
# 번역 API 장애 시 폴백 (itemid는 간헐 갱신될 수 있음)
_FALLBACK_EXCEL = (
    "https://sedlabanki.is/library?itemid=19c3efc3-28e8-4850-a4ef-9795b5ca5cde"
)
_SHEET = "III"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://databank.is/",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("ISL는 render()로 번역 API→Excel을 받는다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _resolve_excel_url() -> str:
    try:
        resp = requests.get(_TRANSLATION_API, headers=_HEADERS, timeout=60, verify=False)
        resp.raise_for_status()
        data = resp.json()
        url = data.get(_EXCEL_KEY) if isinstance(data, dict) else None
        if isinstance(url, str) and url.startswith("http"):
            logger.info("[ISL] excel url from translation: %s", url)
            return url
        logger.warning("[ISL] translation key %s missing/invalid", _EXCEL_KEY)
    except Exception as e:
        logger.warning("[ISL] translation API failed: %s", e)
    logger.info("[ISL] using fallback excel url")
    return _FALLBACK_EXCEL


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=120, verify=False, allow_redirects=True)
    resp.raise_for_status()
    content = resp.content
    if not (content.startswith(b"PK") or content.startswith(b"\xd0\xcf\x11\xe0")):
        # databank proxy fallback
        try:
            pr = requests.post(
                "https://databank.is/api/download",
                json={"url": url},
                headers={**_HEADERS, "Content-Type": "application/json"},
                timeout=120,
                verify=False,
            )
            pr.raise_for_status()
            content = pr.content
        except Exception as e:
            raise RuntimeError(
                f"not excel: {url} head={resp.content[:40]!r}; proxy failed: {e}"
            ) from e
    if not (content.startswith(b"PK") or content.startswith(b"\xd0\xcf\x11\xe0")):
        raise RuntimeError(f"not excel after download: head={content[:40]!r}")
    return content


def _label_at(df: pd.DataFrame, row: int) -> str:
    parts = []
    for j in range(min(3, df.shape[1])):
        v = df.iat[row, j]
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " | ".join(parts)


def _find_row(df: pd.DataFrame, must_contain: list[str], must_not: list[str] | None = None) -> int | None:
    must_not = must_not or []
    for i in range(len(df)):
        lab = _label_at(df, i).lower()
        if not lab:
            continue
        if all(m.lower() in lab for m in must_contain) and not any(
            x.lower() in lab for x in must_not
        ):
            return i
    return None


def _periods_from_row(df: pd.DataFrame, row: int) -> dict[int, str]:
    periods: dict[int, str] = {}
    for j in range(2, df.shape[1]):
        v = df.iat[row, j]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        if hasattr(v, "year") and hasattr(v, "month"):
            try:
                y, m = int(v.year), int(v.month)
                if 1980 <= y <= 2100 and 1 <= m <= 12:
                    periods[j] = f"{y}-{m:02d}"
            except (TypeError, ValueError):
                continue
        elif isinstance(v, str):
            # 1993M09 / 1993-09 / 1993-09-30
            m = re.fullmatch(r"(\d{4})M(\d{2})", v.strip(), re.I)
            if m:
                periods[j] = f"{int(m.group(1))}-{int(m.group(2)):02d}"
                continue
            m = re.match(r"(\d{4})-(\d{2})", v.strip())
            if m:
                periods[j] = f"{int(m.group(1))}-{int(m.group(2)):02d}"
    return periods


def _to_float(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().replace(",", "").replace(" ", "")
        if t in {"", "-", "–", "—"}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _parse_sheet_iii(content: bytes, country_code: str) -> pd.DataFrame:
    try:
        xl = pd.ExcelFile(BytesIO(content))
    except Exception as e:
        logger.error("[%s] excel open failed: %s", country_code, e)
        return _empty()

    sheet = _SHEET if _SHEET in xl.sheet_names else None
    if sheet is None:
        # fallback: sheet with 'III' or deposits-by-currency title
        for name in xl.sheet_names:
            if name.strip().upper() == "III" or "III" == name.strip():
                sheet = name
                break
    if sheet is None:
        logger.error("[%s] sheet III missing: %s", country_code, xl.sheet_names)
        return _empty()

    df = xl.parse(sheet, header=None)

    # date header row: first row with ≥3 datetime/month cells
    date_row = None
    periods: dict[int, str] = {}
    for i in range(min(20, len(df))):
        p = _periods_from_row(df, i)
        if len(p) >= 3:
            date_row, periods = i, p
            break
    if not periods:
        logger.error("[%s] no period header on sheet III", country_code)
        return _empty()

    td_row = _find_row(df, ["deposits total"]) or _find_row(df, ["innlán alls"])
    fcd_row = _find_row(
        df,
        ["foreign currenc"],
        must_not=["unspecified", "ótilgr", "euro", "dollar", "pound", "yen", "krone", "franc"],
    )
    # 첫 번째 Foreign currencies 행이 총계(Deposits total 바로 아래)
    if fcd_row is None:
        fcd_row = _find_row(df, ["erlendir gjaldmiðlar"], must_not=["ótilgr"])

    if td_row is None or fcd_row is None:
        logger.error(
            "[%s] label rows not found td=%s fcd=%s (date_row=%s)",
            country_code, td_row, fcd_row, date_row,
        )
        return _empty()

    # FCD 행이 TD 총계 블록 안(거주/비거주 세부분 앞)에 오도록 보정
    if fcd_row < td_row:
        # 총계 이후 첫 foreign currencies
        for i in range(td_row + 1, min(td_row + 15, len(df))):
            lab = _label_at(df, i).lower()
            if "foreign currenc" in lab and "unspecified" not in lab and "ótilgr" not in lab:
                fcd_row = i
                break
            if "erlendir gjaldmiðlar" in lab and "ótilgr" not in lab:
                fcd_row = i
                break

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for j, period in periods.items():
        fcd = _to_float(df.iat[fcd_row, j])
        td = _to_float(df.iat[td_row, j])
        if fcd is None or td is None or td <= 0:
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
        "[%s] sheet III: %d rows (%s~%s) td_row=%s fcd_row=%s",
        country_code, len(out), out["period"].min(), out["period"].max(), td_row, fcd_row,
    )
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        url = _resolve_excel_url()
        content = _download(url)
        return _parse_sheet_iii(content, country_code)
    except Exception as e:
        logger.exception("[%s] render failed: %s", country_code, e)
        return _empty()
