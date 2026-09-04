"""Ghana: Bank of Ghana(BoG) Monetary Survey (wpDataTables).

The page https://www.bog.gov.gh/economic-data/monetary-survey/ provides an
Export (Excel/CSV) button, but the actual source is a MySQL-backed
wpDataTables (serverSide) table with id=22. Export is just the browser's
DataTables plugin downloading the same AJAX response as a file, so here we
call the same endpoint directly instead of using the Export UI.

    GET the page -> nonce (wdtNonceFrontendServerSide_22) + session cookie
    POST /wp-admin/admin-ajax.php?action=get_wdtable&table_id=22
         body: draw/start/length/wdtNonce + DataTables columns[*] parameters
         length=-1 receives the full filtered set (~450 rows, 2000~latest)

SSL: bog.gov.gh has a certificate chain issue, so verify=False is required
(this was the cause of the "connection failed" note in the existing targets
notes).

Row structure (messy labels):
    [Year, Variables, Jan, Feb, ..., Dec]
    Example Variables values:
      "Money Supply Component_Foreign currency deposits (Millions of Ghana Cedis) "
      "Money Supply Component_Demand deposits (Millions of Ghana Cedis)"
      "Money Supply Component_Savings & Time deposits (Millions of Ghana Cedis)"
      "Money Supply_Broad Money (M2) (Millions of Ghana Cedis) "
      "Money Supply_Total Liquidity (M2+) (Millions of Ghana Cedis) "
    -> Mixed prefixes/units/leading-trailing whitespace/double spaces, so we
       normalize before substring matching.

Definition (per Ghanaian monetary-statistics convention; empirically confirmed
      the identities M2+ = M2 + FCD and
      M2+ - Currency = Demand + Savings&Time + FCD):
    FCD = Foreign currency deposits
    TD  = Demand deposits + Savings & Time deposits + FCD
          (excludes currency in circulation; dollarization ratio based on
          deposit balances)
    FCD_TD_RATIO = FCD / TD * 100

When the same Year appears twice (2022: incomplete/revised duplicate rows), we
pick the one with more non-zero months (ties go to the later row). Months with
a value of 0.00 are treated as unreported and skipped.
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
    raise NotImplementedError("GHA is collected via render() using AJAX")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _norm_label(text: str) -> str:
    """Cleans up whitespace/special characters in the label and lowercases it."""
    text = text.replace("\xa0", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _classify_variable(label: str) -> str | None:
    """Classifies the Variables column string as one of fcd / demand / savings_time.
    Similar-sounding keywords like Net Foreign Assets, Govt. Deposits are excluded."""
    s = _norm_label(label)
    # deposit components only (Money Supply Component_... or the same phrasing)
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
    """Duplicate Year rows: prefer the one with more non-zero months; ties favor new (the later row)."""
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
        raise RuntimeError("Empty wpDataTables AJAX response (the URL needs the action/table_id query params)")
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
            # 0.00 is treated as unreported (trailing zeros in recent years)
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
        # fallback for variant nonce naming patterns
        m = re.search(r'wdtNonceFrontendServerSide_\d+"[^>]*value="([^"]+)"', page.text)
    if not m:
        logger.error("[%s] Could not find wpDataTables nonce on the page", country_code)
        return _empty()
    nonce = m.group(1)

    try:
        raw_rows = _fetch_table_rows(session, nonce)
    except Exception as e:
        logger.exception("[%s] Monetary Survey AJAX failed: %s", country_code, e)
        return _empty()

    series = _series_from_rows(raw_rows)
    df = _build_frame(country_code, series)
    if df.empty:
        logger.warning("[%s] Could not build FCD/TD series (matching may have failed)", country_code)
    else:
        logger.info(
            "[%s] %d rows (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    return df
