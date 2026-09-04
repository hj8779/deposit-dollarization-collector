"""Honduras: BCH Panorama de las Sociedades de Depósito (MFSM).

Source page:
  https://www.bch.hn/estadisticas-y-publicaciones-economicas/sector-monetario/panorama-financiero
File (SharePoint document library LIBPANORAMA FINANCIERO):
  Panorama de las Sociedades de Depósito.xls
  — Consolidated balance sheet of deposit-taking institutions (banks and other
    deposit-taking corporations). Chosen as the primary source because it covers
    resident deposits more broadly than the commercial-banks-only table.

Sheet 'socdep', units: millones de lempiras (HNL).
Within the header (rows 9-10), the DSA (Dinero en Sentido Amplio / broad money) block:

  col13  Billetes y monedas en poder del público
  col14  Depósitos transferibles — MN (moneda nacional / domestic currency)
  col15  Depósitos transferibles — ME (moneda extranjera / foreign currency)
  col16  Otros depósitos — MN
  col17  Otros depósitos — ME
  col18  Valores C/P — MN
  col19  Valores C/P — ME
  col20  DSA total  (= 13..19, confirmed as an identity empirically)

FCD = transferibles ME + otros depósitos ME  (col15+col17)
TD  = all deposits MN+ME                     (col14+15+16+17)
     (excludes currency in circulation and securities; dollarization ratio based on deposit balances)

Dates: mix of 'dic-01' strings and datetime values. Early records are year-end (dic)
only, later ones are monthly.

Because the page is a SharePoint SPA, the static HTML has almost no links, so the
document listing is rendered via Playwright to locate the 'Sociedades de Depósito'
xls, falling back to a known path if that fails.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import unquote, urljoin

import pandas as pd
import requests
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PAGE = (
    "https://www.bch.hn/estadisticas-y-publicaciones-economicas/"
    "sector-monetario/panorama-financiero"
)
_FALLBACK_XLS = (
    "https://www.bch.hn/estadisticos/EF/LIBPANORAMA%20FINANCIERO/"
    "Panorama%20de%20las%20Sociedades%20de%20Dep%C3%B3sito.xls"
)

_MONTHS_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
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
    now = datetime.now(timezone.utc).isoformat()
    empty = pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )
    try:
        xl = pd.ExcelFile(BytesIO(content), engine="xlrd")
    except Exception:
        try:
            xl = pd.ExcelFile(BytesIO(content))
        except Exception as e:
            logger.error("[%s] Failed to open xls: %s", country_code, e)
            return empty

    sheet = "socdep" if "socdep" in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet, header=None)

    # Find the MN/ME header row
    me_row = None
    for i in range(min(20, len(df))):
        vals = [str(df.iat[i, j]).strip().upper() if pd.notna(df.iat[i, j]) else "" for j in range(df.shape[1])]
        if vals.count("ME") >= 2 and vals.count("MN") >= 2:
            me_row = i
            break
    if me_row is None:
        logger.error("[%s] MN/ME header row not found", country_code)
        return empty

    # Row with the Depósitos transferibles / Otros depósitos labels (usually me_row-1)
    label_row = me_row - 1
    # Column positions: the first 'ME' pair is transferibles, the next is otros
    me_cols = [j for j in range(df.shape[1]) if isinstance(df.iat[me_row, j], str) and df.iat[me_row, j].strip().upper() == "ME"]
    mn_cols = [j for j in range(df.shape[1]) if isinstance(df.iat[me_row, j], str) and df.iat[me_row, j].strip().upper() == "MN"]
    if len(me_cols) < 2 or len(mn_cols) < 2:
        logger.error("[%s] Not enough MN/ME columns mn=%s me=%s", country_code, mn_cols, me_cols)
        return empty

    # Confirm transferibles/otros via labels where possible
    transf_me = me_cols[0]
    otros_me = me_cols[1]
    transf_mn = mn_cols[0]
    otros_mn = mn_cols[1]
    for j in mn_cols + me_cols:
        # The parent label is usually only present in the block's starting column
        pass
    # Search the label row for 'transferible' / 'otros dep'
    for j in range(df.shape[1]):
        v = df.iat[label_row, j]
        if not isinstance(v, str):
            continue
        s = v.lower()
        if "transferible" in s:
            # MN,ME start from this column
            if j in mn_cols:
                transf_mn = j
            # ME is often at j+1
            if j + 1 < df.shape[1] and j + 1 in me_cols:
                transf_me = j + 1
            elif j in me_cols:
                transf_me = j
        if "otros dep" in s or (s.strip().startswith("otros") and "dep" in s):
            if j in mn_cols:
                otros_mn = j
            if j + 1 < df.shape[1] and j + 1 in me_cols:
                otros_me = j + 1
            elif j in me_cols:
                otros_me = j

    rows = []
    for i in range(me_row + 1, len(df)):
        period = _to_period(df.iat[i, 0])
        if period is None:
            continue
        try:
            fcd = float(df.iat[i, transf_me]) + float(df.iat[i, otros_me])
            td = (
                float(df.iat[i, transf_mn])
                + float(df.iat[i, transf_me])
                + float(df.iat[i, otros_mn])
                + float(df.iat[i, otros_me])
            )
        except (TypeError, ValueError):
            continue
        if pd.isna(fcd) or pd.isna(td) or td <= 0:
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
        return empty
    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def _to_period(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp) or (hasattr(value, "year") and hasattr(value, "month") and not isinstance(value, str)):
        try:
            return f"{int(value.year)}-{int(value.month):02d}"
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip().lower().replace(" ", "")
        m = re.match(r"([a-záéíóú]{3})-(\d{2,4})", text)
        if not m:
            return None
        mon = _MONTHS_ES.get(m.group(1)[:3])
        if mon is None:
            # accent-stripped keys already; try normalize
            key = (
                m.group(1)
                .replace("á", "a").replace("é", "e").replace("í", "i")
                .replace("ó", "o").replace("ú", "u")
            )[:3]
            mon = _MONTHS_ES.get(key)
        if mon is None:
            return None
        y = int(m.group(2))
        if y < 100:
            y += 2000 if y < 70 else 1900
        return f"{y}-{mon:02d}"
    return None


def _resolve_xls_url() -> str:
    """Use Playwright to find the Sociedades de Depósito xls link on the page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _FALLBACK_XLS

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            page.goto(_PAGE, timeout=90000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            links = page.eval_on_selector_all(
                "a",
                "els => els.map(e => ({href: e.href || '', text: (e.innerText || '').trim()}))",
            )
            browser.close()
    except Exception as e:
        logger.warning("[HND] Page render failed, using fallback URL: %s", e)
        return _FALLBACK_XLS

    candidates = []
    for item in links or []:
        href = (item.get("href") or "").strip()
        if not href.lower().startswith("http"):
            continue
        text = (item.get("text") or "").lower()
        href_l = unquote(href).lower()
        blob = f"{text} {href_l}"
        if ".xls" not in href_l:
            continue
        # Target: "Panorama de las Sociedades de Depósito" (consolidated PSD)
        # Exclude: Otras Sociedades de Depósito, Bancos Comerciales, and other sub-sector tables
        if "otras sociedades" in blob:
            continue
        if "banco comercial" in blob or "bancos comercial" in blob:
            continue
        if "organizaciones de desarrollo" in blob:
            continue
        if "cooperativa" in blob or "seguro" in blob or "pensi" in blob:
            continue
        if "compa" in blob and "financiera" in blob:  # compañías financieras
            continue
        if "banco central" in blob:
            continue
        score = 0
        if "sociedades de dep" in blob:
            score += 20
        if "panorama" in blob:
            score += 5
        # Bonus if the full phrase 'sociedades de depósito' appears in the filename
        if re.search(r"sociedades[_%20 ]+de[_%20 ]+dep", href_l):
            score += 10
        if score > 0:
            candidates.append((score, href.split("?")[0]))

    if candidates:
        candidates.sort(key=lambda x: (-x[0], x[1]))
        url = candidates[0][1]
        logger.info("[HND] Selected xls from page: %s", url)
        return url

    logger.warning("[HND] No suitable xls link found, using fallback URL")
    return _FALLBACK_XLS


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    url = _resolve_xls_url()
    content = None
    for candidate in (url, _FALLBACK_XLS):
        if not candidate.lower().startswith("http"):
            continue
        try:
            logger.info("[%s] Downloading Panorama Sociedades de Depósito: %s", country_code, candidate)
            resp = requests.get(candidate, headers=_HEADERS, timeout=120, verify=False)
            resp.raise_for_status()
            if resp.content.startswith(b"\xd0\xcf\x11\xe0") or resp.content.startswith(b"PK"):
                content = resp.content
                break
            logger.warning("[%s] Response is not an Excel file, len=%d", country_code, len(resp.content))
        except Exception as e:
            logger.warning("[%s] Download failed (%s): %s", country_code, candidate, e)
    if content is None:
        return pd.DataFrame(
            columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
        )
    df = parse(content, country_code)
    if not df.empty:
        logger.info(
            "[%s] %d rows (%s~%s)",
            country_code, len(df), df["period"].min(), df["period"].max(),
        )
    return df
