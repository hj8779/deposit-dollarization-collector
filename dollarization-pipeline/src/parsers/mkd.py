"""North Macedonia: NBRNM PXWeb — Deposits with other depository corporations.

표:
  https://nbstat.nbrm.mk/pxweb/en/MS%20i%20KS/MS%20i%20KS__MS__Monetarni%20i%20kreditni%20agregati/1_DepozitiOstanatiInstiMesecniEN.px/

선택:
  I. TOTAL DEPOSITS (M4)  value=0  → TD
  B. in foreign currency  value=8  → FCD (순수 외화; FX-clause 제외)

Playwright로 다중 선택 후 tableViewLayout2 HTML 표를 파싱한다.
(API v1 는 서버 500 / Cloudflare 로 사용 불가)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import urllib3

from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_PAGE = (
    "https://nbstat.nbrm.mk/pxweb/en/MS%20i%20KS/"
    "MS%20i%20KS__MS__Monetarni%20i%20kreditni%20agregati/"
    "1_DepozitiOstanatiInstiMesecniEN.px/"
)

# Total months to cover (chunked — PXWeb HTML tables truncate if too many cols).
_N_MONTHS = 360
_CHUNK = 100  # months per Show-table request

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MKD는 render()로 PXWeb을 조작한다")


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
        t = v.strip().replace(",", "").replace(" ", "").replace("\xa0", "")
        if t in {"", "-", "…", "...", ".."}:
            return None
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _period_from_label(s: str) -> str | None:
    s = str(s).strip()
    # 2026М06 or 2026M06 (Cyrillic М or Latin M)
    m = re.search(r"(20\d{2})\s*[MМmм]\s*(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"(20\d{2})[-/.](\d{1,2})", s)
    if m:
        return f"{int(m.group(1))}-{int(m.group(2)):02d}"
    return None


def _fetch_html_tables() -> list[pd.DataFrame]:
    """Fetch PXWeb in month chunks so the HTML table is not truncated.

    Selecting 300+ months at once returns a partial window; chunking and
    merging recovers both recent and deep history.
    """
    from playwright.sync_api import sync_playwright

    frames: list[pd.DataFrame] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=_HEADERS["User-Agent"])
            page.goto(_PAGE, timeout=120000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            meta = page.evaluate(
                """() => {
  const selects = document.querySelectorAll('select');
  if (selects.length < 2) throw new Error('expected 2 selects');
  const s1 = selects[1];
  const total = s1.options.length;
  const yearOf = (opt) => {
    const t = (opt.text || opt.label || '').toString();
    const m = t.match(/(20\\d{2}|19\\d{2})/);
    return m ? parseInt(m[1], 10) : null;
  };
  const y0 = yearOf(s1.options[0]);
  const y1 = yearOf(s1.options[total - 1]);
  const newestFirst = (y0 != null && y1 != null) ? (y0 >= y1) : true;
  return {total, newestFirst, y0, y1};
}"""
            )
            total = int(meta["total"])
            newest_first = bool(meta["newestFirst"])
            n = min(_N_MONTHS, total)
            chunk = _CHUNK
            logger.info(
                "[MKD] time options=%d newestFirst=%s cover=%d chunk=%d",
                total,
                newest_first,
                n,
                chunk,
            )

            # indices into option list for the most-recent n months
            if newest_first:
                indices = list(range(0, n))
            else:
                indices = list(range(total - n, total))

            for start in range(0, len(indices), chunk):
                batch = indices[start : start + chunk]
                # re-open query page each chunk (result view loses multi-select UI)
                page.goto(_PAGE, timeout=120000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                page.evaluate(
                    """(batch) => {
  const selects = document.querySelectorAll('select');
  const s0 = selects[0];
  for (const o of s0.options) o.selected = (o.value === '0' || o.value === '8');
  s0.dispatchEvent(new Event('change', {bubbles: true}));
  const s1 = selects[1];
  for (let i = 0; i < s1.options.length; i++) s1.options[i].selected = false;
  for (const i of batch) {
    if (i >= 0 && i < s1.options.length) s1.options[i].selected = true;
  }
  s1.dispatchEvent(new Event('change', {bubbles: true}));
}""",
                    batch,
                )
                page.wait_for_timeout(400)
                page.locator(
                    'input[value="Show table"], button:has-text("Show table")'
                ).first.click()
                page.wait_for_timeout(5000)
                try:
                    page.wait_for_url(re.compile(r"tableViewLayout"), timeout=30000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                html = page.content()
                tables = pd.read_html(StringIO(html))
                if not tables:
                    logger.warning("[MKD] no tables for batch %s", batch[:3])
                    continue
                tables.sort(key=lambda t: t.shape[1] * t.shape[0], reverse=True)
                frames.append(tables[0])
                logger.info(
                    "[MKD] chunk %d–%d → table %s",
                    start,
                    start + len(batch) - 1,
                    tables[0].shape,
                )
        finally:
            browser.close()
    return frames


def _parse_result_table(df: pd.DataFrame, country_code: str) -> pd.DataFrame:
    # Normalize: first column = series label, other columns = periods
    if df.shape[1] < 2 or df.shape[0] < 2:
        logger.error("[%s] unexpected table shape %s", country_code, df.shape)
        return _empty()

    # Column headers may already be period labels
    col_periods: dict[int, str] = {}
    for j, col in enumerate(df.columns):
        if j == 0:
            continue
        per = _period_from_label(col)
        if per:
            col_periods[j] = per

    # If headers are Unnamed, look for a header row inside
    if not col_periods:
        for i in range(min(3, len(df))):
            hits = {}
            for j in range(1, df.shape[1]):
                per = _period_from_label(df.iat[i, j])
                if per:
                    hits[j] = per
            if len(hits) >= 3:
                col_periods = hits
                break

    if not col_periods:
        logger.error("[%s] no period columns in table", country_code)
        return _empty()

    fcd_row = td_row = None
    for i in range(len(df)):
        lab = str(df.iat[i, 0]) if pd.notna(df.iat[i, 0]) else ""
        lab_l = lab.lower().replace("м", "m")
        if "total deposits" in lab_l and ("m4" in lab_l or "a+b" in lab_l or lab_l.strip().startswith("i.")):
            td_row = i
        elif re.search(r"^b\.?\s*in foreign currency", lab_l.strip()) or (
            lab_l.strip() == "b. in foreign currency"
        ):
            fcd_row = i
        elif "in foreign currency" in lab_l and fcd_row is None and "clause" not in lab_l:
            if lab_l.strip().startswith("b"):
                fcd_row = i

    if td_row is None or fcd_row is None:
        # looser match
        for i in range(len(df)):
            lab = str(df.iat[i, 0]).lower() if pd.notna(df.iat[i, 0]) else ""
            if td_row is None and "total deposits" in lab:
                td_row = i
            if fcd_row is None and "foreign currency" in lab and "clause" not in lab:
                fcd_row = i

    if td_row is None or fcd_row is None:
        logger.error(
            "[%s] rows not found fcd=%s td=%s labels=%s",
            country_code,
            fcd_row,
            td_row,
            [str(df.iat[i, 0])[:40] for i in range(min(5, len(df)))],
        )
        return _empty()

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for j, period in col_periods.items():
        fcd = _num(df.iat[fcd_row, j])
        td = _num(df.iat[td_row, j])
        if fcd is None or td is None or td <= 0:
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
        tables = _fetch_html_tables()
        if not tables:
            return _empty()
        frames = [_parse_result_table(t, country_code) for t in tables]
        frames = [f for f in frames if f is not None and not f.empty]
        if not frames:
            return _empty()
        out = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["period", "indicator"], keep="last")
            .sort_values(["period", "indicator"])
            .reset_index(drop=True)
        )
        logger.info(
            "[%s] merged %d rows (%s~%s) from %d chunks",
            country_code,
            len(out),
            out["period"].min(),
            out["period"].max(),
            len(frames),
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
