"""Mexico: Banxico SIE CF664 — commercial bank deposit instruments by currency.

페이지:
  https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=19&idCuadro=CF664&accion=consultarCuadro&locale=es

Cuentas activas:
  Demand total  SF129082  Depósitos de exigibilidad inmediata
  Demand FC     SF129118  Moneda extranjera
  Time total    SF129224  Depósitos a plazo
  Time FC       SF129260  Moneda extranjera

FCD = demand_fc + time_fc
TD  = demand_total + time_total
단위: miles de pesos (표에 표시된 숫자 그대로)

HTML 페이지는 최근 3개월 관측치를 포함한다.
BANXICO_TOKEN / SIE_TOKEN 이 있으면 SIE-API로 2011-04 이후 전체 시계열을 받는다.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_PAGE = (
    "https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do"
    "?sector=19&idCuadro=CF664&accion=consultarCuadro&locale=es"
)
_API = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/{ids}/datos/{start}/{end}"

_SERIES = {
    "demand_total": "SF129082",
    "demand_fc": "SF129118",
    "time_total": "SF129224",
    "time_fc": "SF129260",
}

_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MEX는 render()로 SIE 페이지/API를 호출한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _token() -> str | None:
    return os.environ.get("BANXICO_TOKEN") or os.environ.get("SIE_TOKEN")


def _num_commas(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _scrape_html() -> dict[str, dict[str, float]]:
    """series_id -> {period: value} from CF664 page (last ~3 months)."""
    resp = requests.get(_PAGE, headers=_HEADERS, timeout=120, verify=False)
    resp.raise_for_status()
    text = resp.text
    out: dict[str, dict[str, float]] = {sid: {} for sid in _SERIES.values()}

    for m in re.finditer(
        r'id="tablaObservaciones_([^"]+)"[^>]*>(.*?)</table>',
        text,
        re.S | re.I,
    ):
        oid, block = m.group(1), m.group(2)
        sid_m = re.search(r"(SF\d+)", oid)
        if not sid_m:
            continue
        sid = sid_m.group(1)
        if sid not in out:
            continue
        clean = re.sub(r"<[^>]+>", " ", block)
        clean = re.sub(r"&[a-z]+;", " ", clean)
        clean = re.sub(r"\s+", " ", clean)
        # months + values: Mar 2026 Abr 2026 May 2026 8,741,...
        months = re.findall(
            r"(Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sep|Oct|Nov|Dic)\s+(20\d{2})",
            clean,
            re.I,
        )
        nums = re.findall(r"(\d{1,3}(?:,\d{3})+)", clean)
        if not months or not nums:
            continue
        # numbers after month headers; take last len(months) numbers
        vals = nums[-len(months):] if len(nums) >= len(months) else nums
        for (mon_s, year_s), num_s in zip(months, vals):
            mon = _MONTHS.get(mon_s.lower()[:3])
            if not mon:
                continue
            v = _num_commas(num_s)
            if v is None:
                continue
            period = f"{int(year_s)}-{mon:02d}"
            out[sid][period] = v
    return out


def _api_series(token: str) -> dict[str, dict[str, float]]:
    ids = ",".join(_SERIES.values())
    url = _API.format(ids=ids, start="2011-04-01", end="2030-12-01")
    headers = dict(_HEADERS)
    headers["Bmx-Token"] = token
    resp = requests.get(url, headers=headers, timeout=120, verify=False)
    resp.raise_for_status()
    data = resp.json()
    out: dict[str, dict[str, float]] = {sid: {} for sid in _SERIES.values()}
    for ser in data.get("bmx", {}).get("series", []):
        sid = ser.get("idSerie")
        if sid not in out:
            continue
        for d in ser.get("datos", []):
            # fecha dd/mm/yyyy
            fecha = d.get("fecha", "")
            m = re.match(r"(\d{2})/(\d{2})/(\d{4})", fecha)
            if not m:
                continue
            period = f"{m.group(3)}-{m.group(2)}"
            try:
                out[sid][period] = float(str(d.get("dato", "")).replace(",", ""))
            except ValueError:
                continue
    return out


def _build(series_maps: dict[str, dict[str, float]], country_code: str) -> pd.DataFrame:
    d_tot = series_maps.get(_SERIES["demand_total"], {})
    d_fc = series_maps.get(_SERIES["demand_fc"], {})
    t_tot = series_maps.get(_SERIES["time_total"], {})
    t_fc = series_maps.get(_SERIES["time_fc"], {})
    periods = sorted(set(d_tot) & set(d_fc) & set(t_tot) & set(t_fc))
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period in periods:
        fcd = d_fc[period] + t_fc[period]
        td = d_tot[period] + t_tot[period]
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


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        token = _token()
        if token:
            try:
                maps = _api_series(token)
                out = _build(maps, country_code)
                if not out.empty:
                    return out
                logger.warning("[%s] API empty, fallback HTML", country_code)
            except Exception as e:
                logger.warning("[%s] API failed: %s; HTML fallback", country_code, e)
        maps = _scrape_html()
        return _build(maps, country_code)
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
