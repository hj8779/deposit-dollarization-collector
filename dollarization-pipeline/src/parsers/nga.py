"""Nigeria: CBN Statistics Data Browser — bank analytical balance sheet.

API (statistics.cbn.gov.ng):
  POST /data-browser/search-data-by-table
  Table 25: Commercial & Non Interest Banks Analytical Balance Sheet
    1048 DEMAND DEPOSITS
    1054 TIME AND SAVINGS DEPOSITS
    1063 FOREIGN CURRENCY DEPOSITS

FCD = FOREIGN CURRENCY DEPOSITS
TD  = DEMAND + TIME AND SAVINGS + FOREIGN CURRENCY DEPOSITS
단위: Naira Million, 월별.

batch2 권장 A.4.2 와 동일 계열(상업·비이자은행 부채 예금 구성).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_API = "https://statistics.cbn.gov.ng/data-browser/search-data-by-table"
_TABLE_ID = 25
_IND_FCD = 1063
_IND_DEMAND = 1048
_IND_TS = 1054

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://statistics.cbn.gov.ng/data-browser",
}

_MONTH = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("NGA는 render()로 Data Browser API를 호출한다")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().replace(",", "").replace(" ", "")
        if t in {"", "-", "–", "—", "na", "n/a", "nan"}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _fetch_table_html(start: str, end: str) -> str:
    data = {
        "model.TableId": _TABLE_ID,
        "model.StartDate": start,
        "model.EndDate": end,
        "model.IndicatorIds[0]": _IND_FCD,
        "model.IndicatorIds[1]": _IND_DEMAND,
        "model.IndicatorIds[2]": _IND_TS,
    }
    resp = requests.post(_API, headers=_HEADERS, data=data, timeout=180, verify=False)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("IsSuccessful"):
        raise RuntimeError(payload.get("Error") or "CBN API unsuccessful")
    html = payload.get("TableView") or ""
    if not html or "<table" not in html.lower():
        raise RuntimeError("CBN API returned empty TableView")
    return html


def _periods_from_columns(df: pd.DataFrame) -> list[str]:
    """Map multi-index / flat columns to YYYY-MM period labels."""
    periods: list[str] = []
    cols = list(df.columns)
    for c in cols:
        if isinstance(c, tuple):
            y, m = str(c[0]), str(c[1])
            if y.lower().startswith("indicator") or y.lower().startswith("unnamed"):
                periods.append("")
                continue
            mon = _MONTH.get(m[:3].lower())
            try:
                year = int(re.search(r"(20\d{2}|19\d{2})", y).group(1))  # type: ignore[union-attr]
            except Exception:
                periods.append("")
                continue
            periods.append(f"{year}-{mon:02d}" if mon else "")
        else:
            s = str(c)
            m = re.match(r"(20\d{2})-(\d{2})", s)
            periods.append(m.group(0) if m else "")
    return periods


def _series_from_row(row: pd.Series, periods: list[str]) -> dict[str, float]:
    """Extract period->value, tolerating a leading label cell that shifted values."""
    vals = list(row.values)
    # drop leading non-numeric labels until we hit numbers
    nums: list[float | None] = []
    started = False
    for v in vals:
        n = _num(v)
        if n is None:
            if started:
                nums.append(None)
            # skip leading labels
            continue
        started = True
        nums.append(n)
    # align with period columns that are non-empty
    per_list = [p for p in periods if p]
    out: dict[str, float] = {}
    for i, p in enumerate(per_list):
        if i < len(nums) and nums[i] is not None:
            out[p] = nums[i]  # type: ignore[assignment]
    return out


def _label_of_row(row: pd.Series) -> str:
    for v in row.values:
        if isinstance(v, str) and re.search(
            r"deposit|demand|time|foreign|saving", v, re.I
        ):
            return v.strip().upper()
    # fallback first string
    for v in row.values:
        if isinstance(v, str) and v.strip() and v.strip().lower() not in {
            "indicators", "nan"
        }:
            return v.strip().upper()
    return ""


def _parse_table_html(html: str, country_code: str) -> pd.DataFrame:
    # Prefer multi-header (year, month)
    try:
        df = pd.read_html(StringIO(html))[0]
    except Exception:
        df = pd.read_html(StringIO(html), header=None)[0]

    periods = _periods_from_columns(df)
    if sum(1 for p in periods if p) < 3:
        # try header=None and rebuild from first rows
        raw = pd.read_html(StringIO(html), header=None)[0]
        # row0 years, row1 months, data from row2
        years_row = raw.iloc[0].tolist()
        months_row = raw.iloc[1].tolist() if len(raw) > 1 else []
        periods = [""]
        for j in range(1, raw.shape[1]):
            y = years_row[j] if j < len(years_row) else None
            m = months_row[j] if j < len(months_row) else None
            try:
                year = int(re.search(r"(20\d{2}|19\d{2})", str(y)).group(1))  # type: ignore
                mon = _MONTH.get(str(m)[:3].lower())
                periods.append(f"{year}-{mon:02d}" if mon else "")
            except Exception:
                periods.append("")
        df = raw.iloc[2:].reset_index(drop=True)

    series: dict[str, dict[str, float]] = {}
    for i in range(len(df)):
        row = df.iloc[i]
        lab = _label_of_row(row)
        if not lab:
            continue
        data = _series_from_row(row, periods)
        if not data:
            continue
        if "FOREIGN CURRENCY" in lab:
            series["FCD"] = data
        elif "DEMAND" in lab:
            series["DEMAND"] = data
        elif "TIME" in lab and "SAVING" in lab:
            series["TS"] = data

    if "FCD" not in series or "DEMAND" not in series or "TS" not in series:
        logger.error(
            "[%s] missing series keys=%s", country_code, list(series.keys())
        )
        return _empty()

    periods_all = sorted(
        set(series["FCD"]) | set(series["DEMAND"]) | set(series["TS"])
    )
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period in periods_all:
        fcd = series["FCD"].get(period)
        demand = series["DEMAND"].get(period)
        ts = series["TS"].get(period)
        if fcd is None or demand is None or ts is None:
            continue
        td = demand + ts + fcd
        if td <= 0:
            continue
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in (
            ("FCD", round(fcd, 4)),
            ("TD", round(td, 4)),
            ("FCD_TD_RATIO", ratio),
        ):
            rows.append(
                {
                    "country_code": country_code,
                    "year": year,
                    "period": period,
                    "indicator": indicator,
                    "value": value,
                    "updated_at": now,
                }
            )
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
        country_code,
        len(out),
        out["period"].min(),
        out["period"].max(),
    )
    return out


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        # API accepts ISO dates. Table 25 시계열은 DB상 대체로 2019말 전후로
        # 끊기므로 장기 구간 + 최근 구간을 병합해 최대한 확보한다.
        year = datetime.now().year
        frames: list[pd.DataFrame] = []
        for start, end in (
            ("2005-01-01", f"{year}-12-31"),
            ("2015-01-01", f"{year}-12-31"),
            ("2018-01-01", f"{year}-12-31"),
        ):
            try:
                html = _fetch_table_html(start, end)
                df = _parse_table_html(html, country_code)
                if not df.empty:
                    frames.append(df)
            except Exception as e:
                logger.warning("[NGA] window %s~%s: %s", start, end, e)
        if not frames:
            return _empty()
        out = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] merged %d rows (%s~%s)",
            country_code,
            len(out),
            out["period"].min(),
            out["period"].max(),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
