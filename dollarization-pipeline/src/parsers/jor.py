"""Jordan: CBJ Statistical Database — Deposits by depositor and type.

Portal: https://statisticaldb.cbj.gov.jo/
User-facing category node: Depository Corporations Statistics
  ?node=Z3FiWjk0Yk9WbjlCUFFnUmJUSmdCQT09

The UI's Excel button is a JS form POST, but the same endpoint can be hit directly:

  POST https://statisticaldb.cbj.gov.jo/getExcelFile
  form: documentID=<sectorID>
  (session: hitting /dismissTOU first is recommended)

Documents (type_id=3, matched by name in the getNodeChildren listing):
  FCD  "Deposits in Foreign Currency According to Depositor and Type"
       sectorID V3N0T3A2ZVhkUGFhQ2xQaHEvbUNqUT09
  TD   "Deposits According to Depositor and Type"
       sectorID TzF0YnFWQXBlTzQwcUUyQmNONXNhdz09
       (JD+FC total deposits — dollarization-ratio denominator)

Excel sheet Monthly:
  Year | Month | ... | Total Deposits-(Million J.D.)
  Unit: Million J.D., end of month
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

_BASE = "https://statisticaldb.cbj.gov.jo"
_PAGE = f"{_BASE}/?node=Z3FiWjk0Yk9WbjlCUFFnUmJUSmdCQT09"

# fallback sectorID used if name matching fails (as of 2026)
_FALLBACK = {
    "fcd": "V3N0T3A2ZVhkUGFhQ2xQaHEvbUNqUT09",
    "td": "TzF0YnFWQXBlTzQwcUUyQmNONXNhdz09",
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # Arabic month names sometimes appear
    "كانون الثاني": 1, "شباط": 2, "آذار": 3, "نيسان": 4,
    "أيار": 5, "حزيران": 6, "تموز": 7, "آب": 8,
    "أيلول": 9, "تشرين الأول": 10, "تشرين الثاني": 11, "كانون الأول": 12,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": _PAGE,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("JOR aggregates two getExcelFile downloads via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    try:
        s.get(f"{_BASE}/dismissTOU", timeout=30, verify=False)
    except Exception:
        pass
    try:
        s.post(f"{_BASE}/changeLanguage", data={"language": "en-US"}, timeout=30, verify=False)
    except Exception:
        pass
    return s


def _resolve_document_ids(session: requests.Session) -> dict[str, str]:
    """Find the FCD/TD document sectorIDs by name matching in the getNodeChildren listing."""
    ids = dict(_FALLBACK)
    try:
        resp = session.post(
            f"{_BASE}/getNodeChildren",
            data={"node_id": "x"},
            timeout=60,
            verify=False,
        )
        resp.raise_for_status()
        nodes = resp.json()
    except Exception as e:
        logger.warning("[JOR] getNodeChildren failed, using fallback IDs: %s", e)
        return ids

    if not isinstance(nodes, list):
        return ids

    for item in nodes:
        name = (item.get("name") or "").strip()
        sid = item.get("sectorID")
        if not name or not sid:
            continue
        low = name.lower()
        if "deposits in foreign currency according to depositor" in low:
            ids["fcd"] = sid
        elif low == "deposits according to depositor and type" or (
            "deposits according to depositor and type" in low
            and "foreign" not in low
            and "dinar" not in low
            and "jordanian" not in low
        ):
            ids["td"] = sid
    logger.info("[JOR] document IDs fcd=%s td=%s", ids["fcd"][:16], ids["td"][:16])
    return ids


def _download_excel(session: requests.Session, document_id: str) -> bytes:
    resp = session.post(
        f"{_BASE}/getExcelFile",
        data={"documentID": document_id},
        timeout=120,
        verify=False,
    )
    resp.raise_for_status()
    content = resp.content
    if not (content.startswith(b"PK") or content.startswith(b"\xd0\xcf\x11\xe0")):
        raise RuntimeError(
            f"not excel for {document_id[:20]}… head={content[:40]!r} "
            f"status={resp.status_code} ct={resp.headers.get('content-type')}"
        )
    return content


def _to_float(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().replace(",", "")
        if not t or "%" in t or t in {"-", "–", "—"}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _parse_total_deposits(content: bytes, label: str) -> dict[str, float]:
    """Total Deposits column of the Monthly sheet -> period -> value."""
    try:
        xl = pd.ExcelFile(BytesIO(content))
    except Exception:
        xl = pd.ExcelFile(BytesIO(content), engine="xlrd")

    sheet = "Monthly" if "Monthly" in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)

    # header row: Year / Month / … / Total Deposits
    hdr = None
    tot_col = None
    for i in range(min(10, len(df))):
        labs = [
            str(df.iat[i, j]).strip().lower()
            for j in range(df.shape[1])
            if df.iat[i, j] is not None and not (isinstance(df.iat[i, j], float) and pd.isna(df.iat[i, j]))
        ]
        joined = " | ".join(labs)
        if "year" in joined and "month" in joined:
            hdr = i
            for j in range(df.shape[1]):
                lab = df.iat[i, j]
                if isinstance(lab, str) and "total deposit" in lab.lower():
                    tot_col = j
            break
    if hdr is None or tot_col is None:
        # last column fallback
        if hdr is not None:
            tot_col = df.shape[1] - 1
        else:
            raise RuntimeError(f"{label}: header/total column not found")

    series: dict[str, float] = {}
    for i in range(hdr + 1, len(df)):
        y = df.iat[i, 0]
        m = df.iat[i, 1]
        try:
            year = int(float(y))
        except (TypeError, ValueError):
            continue
        if year < 1980 or year > 2100:
            continue
        if not isinstance(m, str):
            continue
        mon = _MONTHS.get(m.strip().lower()) or _MONTHS.get(m.strip())
        if not mon:
            # try numeric month
            try:
                mon = int(float(m))
                if not (1 <= mon <= 12):
                    continue
            except (TypeError, ValueError):
                continue
        val = _to_float(df.iat[i, tot_col])
        if val is None or val <= 0:
            continue
        series[f"{year}-{mon:02d}"] = val

    logger.info(
        "[JOR] %s: %d months %s~%s",
        label, len(series), min(series) if series else "-", max(series) if series else "-",
    )
    return series


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        session = _session()
        ids = _resolve_document_ids(session)
        fcd_xls = _download_excel(session, ids["fcd"])
        td_xls = _download_excel(session, ids["td"])
        fcd = _parse_total_deposits(fcd_xls, "FCD(FC deposits)")
        td = _parse_total_deposits(td_xls, "TD(all deposits)")
    except Exception as e:
        logger.exception("[%s] download/parse failed: %s", country_code, e)
        return _empty()

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
    out = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] merged %d rows (%s~%s)",
        country_code, len(out), out["period"].min(), out["period"].max(),
    )
    return out
