"""Peru: BCRP estadisticas API — financial system deposits MN + ME.

Series:
  PN00217MM  Ahorro del sistema financiero - Depósitos MN (millones S/)
  PN00224MM  Ahorro del sistema financiero - Depósitos ME (millones US$)
  PN01210PM  Tipo de cambio - promedio del periodo (S/ por US$)

FCD = ME_USD × FX
TD  = MN_Soles + FCD
FCD_TD_RATIO = FCD/TD×100

API: https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json

Historical extension (annual, reported by a user on 2026-08-19): the deposit
(depósitos) series above only goes back to 2021-08. The BCRP Annual Report's
appendix on 'MONETARY ACCOUNTS OF THE DEPOSITORY INSTITUTIONS' (the appendix
number differs by edition — Appendix 60 in the 2020 edition) contains a table with
10 rolling year columns, so the 2020 edition alone covers 2011-2020 (TD='IV.
Monetary liabilities with private sector', FCD='B. Quasi money in foreign
currency' — the table already splits deposit-taking institutions' total monetary
liabilities into local-currency/foreign-currency, the same concept as the monthly
series). Unlike the listing page, this appendix PDF itself is not blocked by
Incapsula (a direct URL request returns 200 OK), but fetching it without a browser
session (cookies) that has passed the Incapsula challenge returns only challenge
HTML, so Playwright must first visit the listing page and then fetch the PDF via
the request API of that same browser context. The table itself comes from a
corrupted PDF where pdfplumber extraction reverses the characters within each line
(token) — reversing the whole line restores the original tokens — so parsing works
by locating anchor tokens (e.g. 'IV.', 'B.'+'Quasi money'+'foreign'+'currency') and
pulling the 10 numbers before/after them.
Added only for years not covered by the monthly series (pre-2021), as
"YYYY-Annual", with no overlapping years."""

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
_API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json"
_MN = "PN00217MM"
_ME = "PN00224MM"
_FX = "PN01210PM"
_ANNUAL_REPORT_PAGE = "https://www.bcrp.gob.pe/en/publications/annual-report/annual-report-2020.html"
_ANNUAL_APPENDIX_URL = "https://www.bcrp.gob.pe/eng-docs/Publications/Annual-Reports/2020/annual-report-2020-8.pdf"
_APPENDIX_PAGE_INDEX = 60  # "Appendix 60: MONETARY ACCOUNTS OF THE DEPOSITORY INSTITUTIONS" in the 2020-edition PDF

_MONTH = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
    "jan": 1, "apr": 4, "aug": 8, "dec": 12,
}

_HEADERS = {"User-Agent": "Mozilla/5.0"}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("PER calls the API via render()")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _fetch(code: str) -> dict[str, float]:
    resp = requests.get(_API.format(code=code), headers=_HEADERS, timeout=60, verify=False)
    resp.raise_for_status()
    data = resp.json()
    out: dict[str, float] = {}
    for p in data.get("periods") or []:
        name = p.get("name") or ""
        vals = p.get("values") or []
        if not vals or vals[0] in (None, "", "n.d.", "n.d"):
            continue
        try:
            out[name] = float(vals[0])
        except (TypeError, ValueError):
            continue
    return out


def _period(name: str) -> str | None:
    # May.2026 / Dic.2024
    m = re.match(r"([A-Za-z]{3})\.?(\d{4})", name.strip())
    if not m:
        return None
    mon = _MONTH.get(m.group(1)[:3].lower())
    if not mon:
        return None
    return f"{int(m.group(2))}-{mon:02d}"


def _find_token_seq(tokens: list[str], seq: list[str]) -> int | None:
    n = len(seq)
    for i in range(len(tokens) - n + 1):
        if tokens[i:i + n] == seq:
            return i
    return None


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _fetch_annual_appendix_pdf() -> bytes | None:
    """A browser session that has already passed the Incapsula challenge is
    required, so Playwright first visits the listing page and then fetches the
    PDF via the request API of that same context."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    )
                )
                page = ctx.new_page()
                # Incapsula's challenge is flaky rather than deterministic — the
                # exact same request sequence sometimes passes, sometimes returns
                # a "just a moment" HTML page (still HTTP 200). Retry a few times
                # with a fresh page load rather than trusting a single attempt.
                for attempt in range(4):
                    page.goto(_ANNUAL_REPORT_PAGE, timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000 + attempt * 2000)
                    resp = ctx.request.get(_ANNUAL_APPENDIX_URL, timeout=60000)
                    body = resp.body()
                    if resp.status == 200 and body[:4] == b"%PDF":
                        return body
                    logger.debug("[PER] annual appendix attempt %d: not a PDF (%d bytes)", attempt, len(body))
                return None
            finally:
                browser.close()
    except Exception:
        return None


def _parse_annual_appendix(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber
    from io import BytesIO

    now = datetime.now(timezone.utc).isoformat()
    with pdfplumber.open(BytesIO(content)) as pdf:
        if _APPENDIX_PAGE_INDEX >= len(pdf.pages):
            return _empty()
        text = pdf.pages[_APPENDIX_PAGE_INDEX].extract_text() or ""

    # This PDF has characters reversed line-by-line (per token) on pdfplumber
    # extraction — reversing the whole line restores the original tokens (label
    # word order is a separate issue and doesn't affect value extraction).
    tokens = [line[::-1] for line in text.split("\n")]

    fcd_anchor = _find_token_seq(tokens, ["currency", "foreign", "in", "Quasi money", "B."])
    td_anchor = None
    for i in range(2, len(tokens)):
        if tokens[i] == "IV." and tokens[i - 1] == "Monetary" and tokens[i - 2] == "liabilities":
            td_anchor = i
            break
    if fcd_anchor is None or td_anchor is None:
        logger.warning("[%s] annual appendix anchor tokens not found", country_code)
        return _empty()

    fcd_vals = [_to_float(t) for t in tokens[fcd_anchor - 10:fcd_anchor]]
    td_vals = [_to_float(t) for t in tokens[td_anchor + 1:td_anchor + 11]]
    if any(v is None for v in fcd_vals) or any(v is None for v in td_vals):
        logger.warning("[%s] annual appendix value parsing failed", country_code)
        return _empty()

    years: list[int] = []
    for i, t in enumerate(tokens):
        if t == "2/" and i + 1 < len(tokens) and re.match(r"^20\d{2}$", tokens[i + 1] or ""):
            j = i + 1
            while len(years) < 10 and j < len(tokens):
                if re.match(r"^20\d{2}$", tokens[j]):
                    years.append(int(tokens[j]))
                    j += 1
                elif tokens[j] == "2/":
                    j += 1
                else:
                    break
            break
    if len(years) != 10:
        logger.warning("[%s] annual appendix year header parsing failed: %s", country_code, years)
        return _empty()

    rows = []
    for year, fcd, td in zip(years, fcd_vals, td_vals):
        if td <= 0 or fcd < 0:
            continue
        ratio = round((fcd / td) * 100, 4)
        for indicator, value in (("FCD", round(fcd, 4)), ("TD", round(td, 4)), ("FCD_TD_RATIO", ratio)):
            rows.append({
                "country_code": country_code, "year": year, "period": f"{year}-Annual",
                "indicator": indicator, "value": value, "updated_at": now,
            })
    return pd.DataFrame(rows) if rows else _empty()


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        mn = _fetch(_MN)
        me = _fetch(_ME)
        fx = _fetch(_FX)
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for name, me_usd in me.items():
            if name not in mn or name not in fx:
                continue
            period = _period(name)
            if not period:
                continue
            fcd = me_usd * fx[name]
            td = mn[name] + fcd
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
        monthly_years = {int(p[:4]) for p in {r["period"] for r in rows}}

        try:
            pdf_content = _fetch_annual_appendix_pdf()
            if pdf_content:
                annual = _parse_annual_appendix(pdf_content, country_code)
                for r in annual.to_dict(orient="records"):
                    if r["year"] in monthly_years:
                        continue  # don't overwrite years with monthly observations with annual-report values
                    rows.append(r)
                if not annual.empty:
                    logger.info(
                        "[%s] annual appendix %d rows (%s)",
                        country_code, len(annual), sorted(annual["period"].unique()),
                    )
        except Exception as e:
            logger.warning("[%s] annual appendix extension failed: %s", country_code, e)

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
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
