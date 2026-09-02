"""Mozambique: Banco de Moçambique — depósitos da economia por moeda.

Post-2007 (MN/ME by institutional sector):
  Page: .../serie-longa-depositos-totais/  (Ficheiros tab)
  Excel: /media/ynbeqizp/pt_169_serie-depositos-totais-from-2007.xls
  Sheets: Dep SNF, DepIFNM, Dep F&ISFL
    cols: period | … | Total MN | Total ME   (header row MN/ME under Total)
  FCD = Σ ME across the three sectors
  TD  = Σ (MN+ME) across the three sectors
  (excludes Administração Local — no currency split; ~0.4% of total)

Pre-2007 (Monetary Panorama old series):
  Page: .../monetary-panorama-old-series/
  Excel: /media/h4tlxd0d/15_13_lnk_pt_panorama.xls
  Sheet: Panorama Monetário
  TD  = |Total de Depositos|
  FCD = |Memo: Depositos Totais em M.E.|
  Units: millions of *old* meticais → divide by 1000 for million new MZN
  (1000 old MT = 1 MZN from July 2006; series stays in old units through end)

Merge: pre fills through 2006-12; post wins from 2007-01.
Unit stored: **million MZN**.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urljoin

import pandas as pd
import requests
import urllib3

from src.utils.fcd_series import empty_frame, long_rows, merge_frames
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_PAGE_POST = (
    "https://www.bancomoc.mz/en/areas-of-expertise/statistics/"
    "statistical-domains-and-indicators/monetary-statistics/"
    "serie-longa-depositos-totais/"
)
_PAGE_PRE = (
    "https://www.bancomoc.mz/en/areas-of-expertise/statistics/"
    "statistical-domains-and-indicators/monetary-statistics/"
    "monetary-panorama-old-series/"
)
_URL_POST = (
    "https://www.bancomoc.mz/media/ynbeqizp/"
    "pt_169_serie-depositos-totais-from-2007.xls"
)
_URL_PRE = (
    "https://www.bancomoc.mz/media/h4tlxd0d/15_13_lnk_pt_panorama.xls"
)

_POST_SHEETS = ("Dep SNF", "DepIFNM", "Dep F&ISFL")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    """Parse whichever workbook is passed (sniff by sheet names)."""
    xl = _open_xl(content)
    names = [str(n) for n in xl.sheet_names]
    if any("Dep" in n for n in names):
        return _parse_post(xl, country_code)
    return _parse_pre(xl, country_code)


def _empty() -> pd.DataFrame:
    return empty_frame()


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=120, verify=False)
        if r.status_code != 200 or len(r.content) < 5_000:
            return None
        return r.content
    except Exception as e:
        logger.debug("[MOZ] download %s: %s", url[-50:], e)
        return None


def _open_xl(content: bytes) -> pd.ExcelFile:
    bio = BytesIO(content)
    try:
        return pd.ExcelFile(bio, engine="xlrd")
    except Exception:
        bio.seek(0)
        return pd.ExcelFile(bio)


def _period_from(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        ts = pd.Timestamp(v)
        if pd.isna(ts):
            return None
        return f"{ts.year}-{ts.month:02d}"
    except Exception:
        s = str(v).strip()
        m = re.match(r"(\d{4})-(\d{2})", s)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return None


def _find_mn_me_cols(df: pd.DataFrame) -> tuple[int, int] | None:
    """Locate Total-block MN / ME columns from header rows."""
    for r in range(min(12, len(df))):
        row = [str(x).strip().upper() if pd.notna(x) else "" for x in df.iloc[r].tolist()]
        # look for ... MN ME under Total (last MN/ME pair)
        mn_idx = [i for i, v in enumerate(row) if v == "MN"]
        me_idx = [i for i, v in enumerate(row) if v == "ME"]
        if mn_idx and me_idx:
            # prefer the Total pair: last MN that has ME immediately after
            for i in reversed(mn_idx):
                if i + 1 in me_idx or (i + 1 < len(row) and row[i + 1] == "ME"):
                    return i, i + 1
            return mn_idx[-1], me_idx[-1]
    return None


def _parse_post_sheet(df: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """period → (fcd_me, td_mn+me) for one sector sheet."""
    cols = _find_mn_me_cols(df)
    if not cols:
        return {}
    mn_c, me_c = cols
    # period column: first datetime-like in left columns
    out: dict[str, tuple[float, float]] = {}
    for i in range(len(df)):
        period = None
        for c in range(min(3, df.shape[1])):
            period = _period_from(df.iloc[i, c])
            if period:
                break
        if not period:
            continue
        try:
            mn = float(pd.to_numeric(df.iloc[i, mn_c], errors="coerce"))
            me = float(pd.to_numeric(df.iloc[i, me_c], errors="coerce"))
        except (TypeError, ValueError):
            continue
        if pd.isna(mn) or pd.isna(me):
            continue
        td = mn + me
        if td <= 0:
            continue
        out[period] = (me, td)
    return out


def _parse_post(xl: pd.ExcelFile, country_code: str) -> pd.DataFrame:
    agg: dict[str, list[float]] = {}
    used = 0
    for sh in _POST_SHEETS:
        if sh not in xl.sheet_names:
            # fuzzy match
            match = next((n for n in xl.sheet_names if sh[:6].lower() in str(n).lower()), None)
            if not match:
                logger.warning("[MOZ] post sheet missing: %s", sh)
                continue
            sh = match
        df = pd.read_excel(xl, sheet_name=sh, header=None)
        part = _parse_post_sheet(df)
        if not part:
            logger.warning("[MOZ] no rows in sheet %s", sh)
            continue
        used += 1
        for p, (me, td) in part.items():
            if p not in agg:
                agg[p] = [0.0, 0.0]
            agg[p][0] += me
            agg[p][1] += td
    if not agg or used == 0:
        return _empty()
    obs = []
    for p in sorted(agg):
        fcd, td = agg[p]
        if td <= 0 or fcd < 0 or fcd > td * 1.05:
            continue
        if td < 100 or td > 50_000_000:
            continue
        ratio = fcd / td
        if ratio > 0.95 or ratio < 0.02:
            continue
        obs.append((p, fcd, td))
    if not obs:
        return _empty()
    out = long_rows(country_code, obs)
    logger.info(
        "[MOZ] post-2007 → %d rows (%s~%s) from %d sheets",
        len(out),
        out["period"].min(),
        out["period"].max(),
        used,
    )
    return out


def _parse_pre(xl: pd.ExcelFile, country_code: str) -> pd.DataFrame:
    df = pd.read_excel(xl, sheet_name=0, header=None)
    # date row
    date_row = None
    for r in range(min(8, len(df))):
        hits = sum(1 for v in df.iloc[r, 2:12] if _period_from(v))
        if hits >= 3:
            date_row = r
            break
    if date_row is None:
        logger.warning("[MOZ] pre: no date row")
        return _empty()

    def find_row(*needles: str) -> int | None:
        for i in range(len(df)):
            blob = " ".join(
                str(df.iloc[i, c])
                for c in range(min(4, df.shape[1]))
                if pd.notna(df.iloc[i, c])
            ).lower()
            if all(n.lower() in blob for n in needles):
                return i
        return None

    td_row = find_row("total de depositos") or find_row("total of deposits")
    fcd_row = find_row("depositos totais em m.e") or find_row(
        "total deposits in f/c"
    )
    if td_row is None:
        logger.warning("[MOZ] pre: Total de Depositos row not found")
        return _empty()
    if fcd_row is None:
        # sum demand+notice+time foreign currency rows
        d_me = find_row("depositos a ordem")  # then moeda estrangeira under it — fragile
        logger.warning("[MOZ] pre: memo FCD row not found")
        return _empty()

    dates = [_period_from(v) for v in df.iloc[date_row, 3:]]
    td = pd.to_numeric(df.iloc[td_row, 3:], errors="coerce")
    fcd = pd.to_numeric(df.iloc[fcd_row, 3:], errors="coerce")

    obs: list[tuple[str, float, float]] = []
    for p, t, f in zip(dates, td, fcd):
        if not p or pd.isna(t) or pd.isna(f):
            continue
        # liability sign convention → absolute; old MT → million new MZN
        t_f = abs(float(t)) / 1000.0
        f_f = abs(float(f)) / 1000.0
        if t_f <= 0 or f_f < 0 or f_f > t_f * 1.05:
            continue
        if t_f < 100 or t_f > 50_000_000:
            continue
        ratio = f_f / t_f
        if ratio < 0.05 or ratio > 0.90:
            continue
        # only keep pre-2007 (post series preferred from 2007)
        if p >= "2007-01":
            continue
        obs.append((p, f_f, t_f))

    if not obs:
        return _empty()
    out = long_rows(country_code, obs)
    logger.info(
        "[MOZ] pre-2007 panorama → %d rows (%s~%s)",
        len(out),
        out["period"].min(),
        out["period"].max(),
    )
    return out


def _discover_post_url() -> str:
    """Prefer live Ficheiros link; fall back to known media path."""
    try:
        r = requests.get(_PAGE_POST, headers=_HEADERS, timeout=40, verify=False)
        if r.status_code == 200:
            for href in re.findall(
                r'href=["\']([^"\']*serie-depositos[^"\']*\.xls)["\']',
                r.text,
                re.I,
            ):
                return urljoin(_PAGE_POST, href)
            for href in re.findall(
                r'href=["\']([^"\']+/media/[^"\']+\.xls)["\']', r.text, re.I
            ):
                if "deposit" in href.lower() or "serie" in href.lower():
                    return urljoin(_PAGE_POST, href)
    except Exception as e:
        logger.debug("[MOZ] discover post: %s", e)
    return _URL_POST


def _discover_pre_url() -> str:
    try:
        r = requests.get(_PAGE_PRE, headers=_HEADERS, timeout=40, verify=False)
        if r.status_code == 200:
            for href in re.findall(
                r'href=["\']([^"\']*panorama[^"\']*\.xls)["\']', r.text, re.I
            ):
                return urljoin(_PAGE_PRE, href)
    except Exception as e:
        logger.debug("[MOZ] discover pre: %s", e)
    return _URL_PRE


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    try:
        frames = []
        pre_url = _discover_pre_url()
        post_url = _discover_post_url()
        logger.info("[MOZ] pre=%s", pre_url)
        logger.info("[MOZ] post=%s", post_url)

        pre_b = _download(pre_url)
        if pre_b:
            try:
                frames.append(_parse_pre(_open_xl(pre_b), country_code))
            except Exception as e:
                logger.warning("[MOZ] pre parse: %s", e)

        post_b = _download(post_url)
        if post_b:
            try:
                frames.append(_parse_post(_open_xl(post_b), country_code))
            except Exception as e:
                logger.warning("[MOZ] post parse: %s", e)

        frames = [f for f in frames if f is not None and not f.empty]
        if not frames:
            logger.error("[%s] no Bancomoc excel series parsed", country_code)
            return _empty()
        # post last → wins on 2007 overlap
        out = merge_frames(*frames)
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
