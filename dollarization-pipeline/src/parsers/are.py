"""UAE: CBUAE Monthly Statistical Bulletin — Table 2 Monetary Survey.

Each bulletin PDF carries a rolling multi-month window of:
  FCD = 'Foreign Currency Deposits'
  TD  = Monetary Deposits + Quasi-Money  (deposit components of M2)

The public site listing is often bot-blocked (403/CF) for plain `requests`, but
**direct /media/... PDF URLs remain downloadable**, and the "Latest Statistics" page
(/en/research-and-statistics/latest-statistics/) is reachable via headless Chromium
(Playwright, same bypass technique used elsewhere in this pipeline) even though it
403s for `requests`. We therefore:
  1) Seed a known set of bulletin media URLs (2022–2026, growing)
  2) Include target['source_url'] if it is a PDF
  3) Discover the newest few issues via the Latest Statistics page (Playwright)
  4) Optionally discover more via DuckDuckGo HTML search
  5) Parse each PDF and merge (later bulletin wins on overlapping periods)
  6) Emit FCD, TD, and FCD_TD_RATIO when both stocks exist

Re-run render() re-tries discovery + known list for auto-update.

Pre-2018 annual extension (added 2026-08-19, user-provided lead): CBUAE Annual
Report PDFs from the 2008-2013 era each carry a "TABLE (A-4): MONETARY SURVEY"
page with the same Foreign Currency Deposits / Monetary Deposits / Quasi-Money
rows, 1-2 year columns per report (current + prior year for comparison), letting
consecutive reports' overlapping years cross-validate each other (confirmed:
2011's 2011 column == 2012's 2011 column == 144,094 / 222,505 / 561,662).
Coverage is spotty — the annex format churned across editions (2008 edition has
severe font-level character-doubling corruption pdfplumber can't cleanly recover
without OCR, not worth it for one boundary year so 2007/2008 are skipped; 2010,
2015, 2017+ editions dropped this table/renamed the annex; 2018+ modern reports
have no statistical annex at all, relying on the separate monthly bulletin
instead) — so this is a small *known-URL* list (not a discovered/paginated
listing: the publications page is Angular-rendered and its filter checkboxes
were not reliably automatable, matching the user's own report of a hover-to-
reveal download button; direct /media/... PDF URLs work fine once known,
same as the bulletins above) covering what was confirmed reachable: 2009, 2011,
2012, 2013 → continuous 2009-2013 (2010 via 2011's prior-year column).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import unquote

import pandas as pd
import pdfplumber
import requests
import urllib3

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

# Direct media PDFs (hash paths are stable once published). Expand as new issues appear.
_KNOWN_PDFS = [
    # 2026
    "https://www.centralbank.ae/media/v24gwbbb/statistical-bulletin-june-2026.pdf",
    "https://www.centralbank.ae/media/r0mirede/statistical-bulletin-may-2026.pdf",
    "https://www.centralbank.ae/media/ntxjmjmt/statistical-bulletin-april-2026.pdf",
    "https://www.centralbank.ae/media/ivbanlja/statistical-bulletin-march-2026.pdf",
    "https://www.centralbank.ae/media/a3tjyw03/statistical-bulletin-february-2026.pdf",
    # 2025
    "https://www.centralbank.ae/media/if2ky4yn/statistical-bulletin-december-2025.pdf",
    "https://www.centralbank.ae/media/yppfkqkx/statistical-bulletin-september-2025.pdf",
    "https://www.centralbank.ae/media/n2tdxmha/statistical-bulletin-august-2025.pdf",
    "https://www.centralbank.ae/media/51klv1ov/statistical-bulletin_june-2025.pdf",
    "https://www.centralbank.ae/media/sorhishu/statistical-bulletin-may-2025.pdf",
    "https://www.centralbank.ae/media/jqbfhs3u/statistical-bulletin-april-2025.pdf",
    "https://www.centralbank.ae/media/slcpkamg/statistical-bulletin-feburary-2025.pdf",  # site typo
    "https://www.centralbank.ae/media/w33fpkm0/statistical-bulletin-january-2025.pdf",
    "https://centralbank.ae/media/r5mhykbr/statistical-bulletin-january-2025.pdf",
    # 2024
    "https://www.centralbank.ae/media/j4ijc3yj/statistical-bulletin-december-2024.pdf",
    "https://centralbank.ae/media/j4ijc3yj/statistical-bulletin-december-2024.pdf",
    "https://www.centralbank.ae/media/0ohlbl2w/statistical-bulletin-november-2024.pdf",
    "https://centralbank.ae/media/nuqhvyhh/statistical-bulletin-october-2024.pdf",
    "https://www.centralbank.ae/media/qhihcawv/statistical-bulletin-september-2024.pdf",
    "https://centralbank.ae/media/foimeuvp/statistical-bulletin_june_2024-v2.pdf",
    "https://www.centralbank.ae/media/dwrngzvo/statistical-bulletin-march-2024.pdf",
    # 2023
    "https://centralbank.ae/media/3vndbzyp/statistical-bulletin-december-2023.pdf",
    "https://centralbank.ae/media/2hqlfxn4/statistical-bulletin-october-2023.pdf",
    "https://centralbank.ae/media/z32dda5y/statistical-bulletin-august-2023_091023.pdf",
    "https://centralbank.ae/media/jnln53n5/statistical-bulletin-january-2023.pdf",
    # 2022
    "https://www.centralbank.ae/media/ay3f3xll/statistical-bulletin-september-2022_031122.pdf",
]

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_HEADER_RE = re.compile(r"^([A-Za-z]{3})[a-z]*\s+(\d{4})\s*\*?$")
_ROW_LABEL = "foreign currency deposits"
_TD_ROW_LABELS = ("monetary deposits", "quasi - money", "quasi money")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
    "Referer": "https://www.centralbank.ae/",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Parse one bulletin PDF into long-form FCD/TD/RATIO rows."""
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = (page.extract_text() or "").lower()
            # "Table 3: Monthly Changes in Factors Affecting Money Supply" has the
            # exact same row labels (incl. "Foreign Currency Deposits", "Quasi -
            # Money") as the real "Table 2: Monetary Survey" stock-level table, but
            # its values are month-over-month deltas (often negative) — skip it so
            # its rows never get parsed as if they were levels.
            if "monthly changes" in page_text:
                continue
            for table in page.extract_tables() or []:
                header_row = None
                for row in table:
                    matches = sum(
                        1 for c in row if c and _MONTH_HEADER_RE.match(str(c).strip())
                    )
                    if matches >= 3:
                        header_row = row
                        break
                if header_row is None:
                    continue

                target_row = next(
                    (
                        row
                        for row in table
                        if any(c and _ROW_LABEL in str(c).lower() for c in row)
                    ),
                    None,
                )
                if target_row is None:
                    continue

                fcd_map = _extract_row_values(target_row, header_row)
                for period, value in fcd_map.items():
                    year = int(period[:4])
                    rows.append(
                        {
                            "country_code": country_code,
                            "year": year,
                            "period": period,
                            "indicator": INDICATOR,  # FCD
                            "value": value,
                            "updated_at": now,
                        }
                    )

                # TD = Monetary Deposits + Quasi-Money
                td_component_sums: dict[str, float] = {}
                td_component_count: dict[str, int] = {}
                for label in _TD_ROW_LABELS:
                    row = next(
                        (
                            r
                            for r in table
                            if any(c and label in str(c).lower() for c in r)
                        ),
                        None,
                    )
                    if row is None:
                        continue
                    for period, value in _extract_row_values(row, header_row).items():
                        td_component_sums[period] = (
                            td_component_sums.get(period, 0.0) + value
                        )
                        td_component_count[period] = (
                            td_component_count.get(period, 0) + 1
                        )

                for period, total in td_component_sums.items():
                    if td_component_count[period] < 2:
                        continue
                    year = int(period[:4])
                    rows.append(
                        {
                            "country_code": country_code,
                            "year": year,
                            "period": period,
                            "indicator": INDICATOR_TD,  # TD
                            "value": round(total, 2),
                            "updated_at": now,
                        }
                    )

    if not rows:
        return _empty()

    df = pd.DataFrame(rows)
    # FCD_TD_RATIO for periods with both
    fcd = {
        r["period"]: r["value"]
        for r in rows
        if r["indicator"] == INDICATOR
    }
    td = {
        r["period"]: r["value"]
        for r in rows
        if r["indicator"] == INDICATOR_TD
    }
    ratio_rows = []
    for period in set(fcd) & set(td):
        if td[period] and td[period] > 0:
            ratio_rows.append(
                {
                    "country_code": country_code,
                    "year": int(period[:4]),
                    "period": period,
                    "indicator": "FCD_TD_RATIO",
                    "value": round((fcd[period] / td[period]) * 100, 4),
                    "updated_at": now,
                }
            )
    if ratio_rows:
        df = pd.concat([df, pd.DataFrame(ratio_rows)], ignore_index=True)
    return (
        df.drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["country_code", "year", "period", "indicator", "value", "updated_at"]
    )


def _extract_row_values(row: list, header_row: list) -> dict[str, float]:
    values: dict[str, float] = {}
    for i, cell in enumerate(header_row):
        if not cell:
            continue
        m = _MONTH_HEADER_RE.match(str(cell).strip())
        if not m or i >= len(row):
            continue
        month = _MONTH_MAP.get(m.group(1).lower())
        year = int(m.group(2))
        if month is None:
            continue
        raw = row[i]
        if not raw:
            continue
        raw = str(raw).replace(",", "").strip()
        if not raw or not re.match(r"^-?\d+(\.\d+)?$", raw):
            continue
        values[f"{year}-{month:02d}"] = float(raw)
    return values


def _normalize_url(u: str) -> str:
    u = u.strip()
    if u.startswith("http://"):
        u = "https://" + u[len("http://") :]
    if u.startswith("https://centralbank.ae/"):
        u = "https://www.centralbank.ae/" + u[len("https://centralbank.ae/") :]
    return u


def _discover_pdfs_via_ddg(limit: int = 40) -> list[str]:
    """Best-effort discovery; listing pages are often CF-blocked."""
    out: list[str] = []
    queries = [
        "site:centralbank.ae/media statistical-bulletin filetype:pdf",
        "site:centralbank.ae statistical-bulletin-2025 filetype:pdf",
        "site:centralbank.ae statistical-bulletin-2024 filetype:pdf",
        "site:centralbank.ae statistical-bulletin-2026 filetype:pdf",
    ]
    try:
        sess = requests.Session()
        sess.headers.update(_HEADERS)
        for q in queries:
            try:
                r = sess.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": q},
                    timeout=35,
                )
                if r.status_code != 200:
                    continue
                for enc in re.findall(r"uddg=([^&\"]+)", r.text):
                    u = unquote(enc).split("&")[0]
                    if "centralbank.ae" in u and ".pdf" in u.lower():
                        if re.search(r"statistical[-_]?bulletin", u, re.I):
                            out.append(_normalize_url(u))
                for m in re.findall(
                    r"https?://(?:www\.)?centralbank\.ae/media/[a-z0-9]+/"
                    r"statistical[-_]bulletin[^\"\s<>]+\.pdf",
                    r.text,
                    re.I,
                ):
                    out.append(_normalize_url(m))
            except Exception as e:
                logger.debug("[ARE] ddg query fail: %s", e)
    except Exception as e:
        logger.debug("[ARE] ddg session fail: %s", e)

    # de-dupe preserve order
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq[:limit]


_LATEST_STATS_PAGE = "https://www.centralbank.ae/en/research-and-statistics/latest-statistics/"


def _discover_pdfs_via_latest_stats_page() -> list[str]:
    """CBUAE's listing pages 403 plain `requests` (Cloudflare bot check), but a
    headless-Chromium fetch of the "Latest Statistics" page gets through and
    reliably surfaces the newest 2-3 bulletins — use it to keep _KNOWN_PDFS
    fresh automatically instead of relying solely on manual seeding."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
            try:
                page = browser.new_page(user_agent=_HEADERS["User-Agent"])
                page.goto(_LATEST_STATS_PAGE, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            finally:
                browser.close()
    except Exception as e:
        logger.debug("[ARE] latest-statistics page fetch fail: %s", e)
        return []
    return [
        _normalize_url(h)
        for h in hrefs
        if re.search(r"statistical[-_]bulletin.*\.pdf$", h, re.I)
    ]


def _list_pdf_urls(target: dict) -> list[str]:
    urls: list[str] = []
    src = target.get("source_url") or ""
    if src.lower().endswith(".pdf"):
        urls.append(_normalize_url(src))
    for u in _KNOWN_PDFS:
        urls.append(_normalize_url(u))
    try:
        urls.extend(_discover_pdfs_via_latest_stats_page())
    except Exception:
        pass
    try:
        urls.extend(_discover_pdfs_via_ddg())
    except Exception:
        pass
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


_ANNUAL_REPORT_PDFS = [
    "https://www.centralbank.ae/media/phgb4hyj/cbuae-annual-report-2009-en.pdf",
    "https://www.centralbank.ae/media/rm4nllqg/cbuae-annual-report-2011-en.pdf",
    "https://www.centralbank.ae/media/k2knanz4/cbuae-annual-report-2012-en.pdf",
    "https://www.centralbank.ae/media/cz1laszo/cbuae-annual-report-2013-en.pdf",
]


def _annual_survey_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _parse_annual_survey(content: bytes, country_code: str) -> pd.DataFrame:
    """Parse "TABLE (A-4): MONETARY SURVEY" out of a CBUAE Annual Report PDF."""
    now = datetime.now(timezone.utc).isoformat()
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "monetary survey" not in text.lower():
                continue
            lines = text.splitlines()
            years: list[str] | None = None
            for line in lines:
                m = re.match(r"^(?:Item\s+)?((?:20\d{2}\*?\s*){1,6})$", line.strip())
                if m:
                    found = re.findall(r"20\d{2}", m.group(1))
                    if found:
                        years = found
                        break
            if not years:
                continue
            n = len(years)

            def row_vals(label: str) -> list[float] | None:
                key = _annual_survey_key(label)
                for line in lines:
                    if _annual_survey_key(line.strip()).startswith(key):
                        nums = re.findall(r"-?[\d,]+(?:\.\d+)?", line)
                        if len(nums) >= n:
                            return [float(x.replace(",", "")) for x in nums[-n:]]
                return None

            fcd = row_vals("Foreign Currency Deposits")
            md = row_vals("Monetary Deposits")
            qm = row_vals("Quasi-Money")
            if not (fcd and md and qm):
                continue

            rows = []
            for year, f, m_, q in zip(years, fcd, md, qm):
                td = m_ + q
                if td <= 0:
                    continue
                ratio = round((f / td) * 100, 4)
                for indicator, value in (
                    (INDICATOR, round(f, 4)),
                    (INDICATOR_TD, round(td, 4)),
                    ("FCD_TD_RATIO", ratio),
                ):
                    rows.append({
                        "country_code": country_code,
                        "year": int(year),
                        "period": f"{year}-Annual",
                        "indicator": indicator,
                        "value": value,
                        "updated_at": now,
                    })
            if rows:
                return pd.DataFrame(rows)
    return _empty()


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=90, verify=False)
        if r.status_code != 200:
            return None
        if r.content[:4] != b"%PDF":
            return None
        return r.content
    except Exception as e:
        logger.debug("[ARE] download %s: %s", url[-50:], e)
        return None


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    urls = _list_pdf_urls(target)
    logger.info("[%s] bulletin PDF candidates=%d", country_code, len(urls))

    frames: list[pd.DataFrame] = []

    def one(u: str) -> pd.DataFrame:
        content = _download(u)
        if not content:
            return _empty()
        try:
            df = parse(content, country_code)
            if not df.empty:
                logger.info(
                    "[%s] %s → %d rows (%s~%s)",
                    country_code,
                    u.rsplit("/", 1)[-1][:50],
                    len(df),
                    df["period"].min(),
                    df["period"].max(),
                )
            return df
        except Exception as e:
            logger.debug("[%s] parse %s: %s", country_code, u[-40:], e)
            return _empty()

    with ThreadPoolExecutor(max_workers=4) as ex:
        for df in ex.map(one, urls):
            if df is not None and not df.empty:
                frames.append(df)

    for u in _ANNUAL_REPORT_PDFS:
        content = _download(u)
        if not content:
            continue
        try:
            df = _parse_annual_survey(content, country_code)
            if not df.empty:
                logger.info(
                    "[%s] annual %s → %d rows (%s)",
                    country_code, u.rsplit("/", 1)[-1][:40], len(df),
                    ", ".join(sorted(df["period"].unique())),
                )
                frames.append(df)
        except Exception as e:
            logger.debug("[%s] annual parse %s: %s", country_code, u[-40:], e)

    if not frames:
        logger.error("[%s] no bulletin PDFs parsed", country_code)
        return _empty()

    out = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["period", "indicator"], keep="last")
        .sort_values(["period", "indicator"])
        .reset_index(drop=True)
    )
    logger.info(
        "[%s] merged %d rows (%s~%s) from %d PDFs",
        country_code,
        len(out),
        out["period"].min(),
        out["period"].max(),
        len(frames),
    )
    return out
