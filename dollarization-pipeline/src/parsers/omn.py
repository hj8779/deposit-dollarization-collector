"""Oman: CBO Quarterly Bulletin — Breakdown of Private Sector Deposits.

Source PDFs (filename tokens vary by era / case):
  https://cbo.gov.om/sites/assets/Documents/English/Publications/QuarterlyBulletins/
    {YYYY}/QB{March|Mar|June|Jun|Sep|Sept|September|Dec|December}{YYYY}[En|EN].pdf

Table: "Breakdown of Private Sector Deposits" (Rial Omani Million)
  Blocks: Demand | Saving | Time | Commercial Prepayment | **Total Deposits**
  Each block: Rial Omani | Foreign Currency | Total
  FCD = Total Deposits → Foreign Currency
  TD  = Total Deposits → Total
  FCD_TD_RATIO = FCD / TD * 100

Each QB carries a multi-year rolling window of quarterly points. We download
many issues, parse all rows, and keep the latest bulletin's value per period.

Pre-2021 bulletins are often image-only (scanned); those fall back to
pdftoppm + tesseract OCR on candidate pages when available.

This replaces the old monthly ratio-only synthetic series (FCD=ratio, TD=100).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber
import requests
import urllib3

from src.utils.fcd_series import empty_frame, long_rows, merge_frames
from src.utils.logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

_QB_BASE = (
    "https://cbo.gov.om/sites/assets/Documents/English/Publications/"
    "QuarterlyBulletins"
)
_LIST_PAGE = "https://cbo.gov.om/Pages/QuarterlyBulletins.aspx"

# Quarter label → calendar month (end of quarter)
_Q_TO_MONTH = {
    "qi": 3,
    "q1": 3,
    "qii": 6,
    "q2": 6,
    "qiii": 9,
    "q3": 9,
    "qiv": 12,
    "q4": 12,
}

# Preferred month tokens first (long names often used post-2023; short earlier)
_MONTH_TOKENS: list[tuple[str, int]] = [
    ("March", 3),
    ("Mar", 3),
    ("June", 6),
    ("Jun", 6),
    ("September", 9),
    ("Sep", 9),
    ("Sept", 9),
    ("December", 12),
    ("Dec", 12),
]

# Per-quarter preferred token order by observed CBO naming
_QUARTER_TOKEN_ORDER: dict[int, list[str]] = {
    3: ["March", "Mar"],
    6: ["June", "Jun"],
    9: ["Sep", "Sept", "September"],
    12: ["Dec", "December"],
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

# Prefer "12525.7" as one token (not 125 + 25.7)
_NUM_RE = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
# Clean digital text + OCR variants (QIl, Qui, Qill, QU, …)
_ROW_RE = re.compile(
    r"\b("
    r"Q\s*I{1,3}|Q\s*IV|Q\s*[1-4]|"
    r"QIl+|Qll+|Ql|"  # QII / QI with l↔I confusion
    r"Qill+|Qui+|QUI+|"  # QIII
    r"Qu|QU"  # often OCR of QII
    r")\b(.*)$",
    re.I,
)
_YEAR_LINE_RE = re.compile(r"(?:^|\D)(20\d{2})(?:\D|$)")
_TITLE_RE = re.compile(
    r"Breakdown\s+of\s+Private\s+Sector\s+Deposits",
    re.I,
)
_SECTION_HINT_RE = re.compile(
    r"Private\s+Sector\s+Deposits|Total\s+Deposits|Foreign\s+Currency",
    re.I,
)

# Sequential quarter after a year header (for OCR-garbled labels)
_Q_SEQ = ("qi", "qii", "qiii", "qiv")


def _normalize_quarter(label: str) -> str | None:
    """Map clean or OCR-noisy quarter tokens → qi|qii|qiii|qiv."""
    s = re.sub(r"\s+", "", (label or "").upper())
    # l (ell) / 1 misread as I
    s = s.replace("L", "I").replace("1", "I")
    # collapse repeated I
    if s in ("QI", "Q"):
        return "qi"
    if s in ("QII", "Q2", "QU"):  # QU often = QII in tesseract
        return "qii"
    if s in ("QIII", "Q3", "QUI"):
        return "qiii"
    if s in ("QIV", "Q4"):
        return "qiv"
    # QI{1,3} exact
    if re.fullmatch(r"QI{1,3}", s):
        return {1: "qi", 2: "qii", 3: "qiii"}[s.count("I")]
    if re.fullmatch(r"Q[1-4]", s):
        return {"1": "qi", "2": "qii", "3": "qiii", "4": "qiv"}[s[1]]
    return None


def parse(content: bytes, country_code: str):
    """Parse one quarterly bulletin PDF → long-form FCD/TD/RATIO."""
    return _parse_pdf(content, country_code, source_label="pdf", allow_ocr=True)


def _empty():
    return empty_frame()


def _nums(chunk: str) -> list[float]:
    out: list[float] = []
    for p in _NUM_RE.findall(chunk):
        try:
            out.append(float(p.replace(",", "")))
        except ValueError:
            continue
    return out


def _extract_obs(text: str, *, ocr_loose: bool = False) -> list[tuple[str, float, float]]:
    """Return (period, fcd, td) from Breakdown of Private Sector Deposits text."""
    if not text:
        return []

    # Prefer the *data* table, not the TOC entry. Score candidate windows.
    low = text.lower()
    starts = [m.start() for m in re.finditer(
        r"breakdown\s+of\s+private\s+sector\s+deposits", low
    )]
    if not starts:
        # Fall back to any private-sector deposits + quarter rows
        starts = [m.start() for m in re.finditer(r"private\s+sector\s+deposits", low)]
    if not starts:
        starts = [0]

    best_obs: dict[str, tuple[float, float]] = {}
    best_score = -1
    for start in starts:
        chunk = text[start : start + 20_000]
        obs = _extract_obs_from_chunk(chunk, ocr_loose=ocr_loose)
        # Prefer windows that also mention the unit / total deposits
        score = len(obs)
        cl = chunk.lower()
        if "rial omani million" in cl or "total deposits" in cl:
            score += 5
        if "demand" in cl and "saving" in cl:
            score += 3
        # TOC-only windows have page numbers but few 15-number rows
        if score > best_score:
            best_score = score
            best_obs = obs

    # Also try whole text if title search failed to score
    if best_score < 2:
        obs = _extract_obs_from_chunk(text, ocr_loose=ocr_loose)
        if len(obs) > best_score:
            best_obs = obs

    return [(p, best_obs[p][0], best_obs[p][1]) for p in sorted(best_obs)]


def _extract_obs_from_chunk(
    chunk: str, *, ocr_loose: bool = False
) -> dict[str, tuple[float, float]]:
    year: int | None = None
    seq_i = 0  # next expected quarter index after year header
    obs: dict[str, tuple[float, float]] = {}
    for line in chunk.splitlines():
        ls = line.strip()
        if not ls:
            continue
        # Year header alone, or OCR junk around year: "® 2012 @" / "2010"
        ym = re.fullmatch(r"(20\d{2})", ls)
        if ym:
            year = int(ym.group(1))
            seq_i = 0
            continue
        # short line with a year and little else (OCR year banners)
        if len(ls) <= 24:
            ym2 = _YEAR_LINE_RE.search(ls)
            if ym2 and len(_nums(ls)) <= 1:
                year = int(ym2.group(1))
                seq_i = 0
                continue

        # year on same line: "2020 QIII 3179.3 ..."
        m2 = re.search(
            r"(20\d{2})\s+(Q[^\s]{0,6})\b(.*)$",
            line,
            re.I,
        )
        qlab_raw: str | None = None
        nums: list[float] = []
        if m2 and _normalize_quarter(m2.group(2)):
            year = int(m2.group(1))
            seq_i = 0
            qlab_raw = m2.group(2)
            nums = _nums(m2.group(3))
        else:
            m = _ROW_RE.search(line)
            if m:
                qlab_raw = m.group(1)
                nums = _nums(m.group(2))
            else:
                # bare data line (label lost to OCR)
                nums = _nums(line)
                min_n = 14 if ocr_loose else 15
                if len(nums) < min_n or year is None:
                    continue
                qlab_raw = None

        if year is None:
            continue

        qkey = _normalize_quarter(qlab_raw) if qlab_raw else None
        # OCR often turns QII→Qi / Qu / Ql; prefer sequence after first row
        weak = bool(
            qlab_raw
            and re.fullmatch(r"Qi|Qu|QU|Ql|Qtr|Qiu|Quit", qlab_raw or "", re.I)
        )
        if qkey is None or (weak and seq_i > 0):
            if seq_i < 4:
                qkey = _Q_SEQ[seq_i]
            elif qkey is None:
                continue
        mon = _Q_TO_MONTH.get(qkey or "")
        if not mon:
            continue

        fcd_td = _pick_fcd_td(nums, ocr_loose=ocr_loose)
        if fcd_td is None:
            continue
        fcd, td = fcd_td
        period = f"{year}-{mon:02d}"
        obs[period] = (fcd, td)
        # advance sequence (wrap within year)
        try:
            seq_i = _Q_SEQ.index(qkey) + 1
        except ValueError:
            seq_i += 1
        if seq_i >= 4:
            seq_i = 0
    return obs


def _pick_fcd_td(nums: list[float], *, ocr_loose: bool = False) -> tuple[float, float] | None:
    """Total Deposits last trio = RO, FC, Total → FCD / TD.

    Canonical digital rows have exactly 15 amounts (5 blocks × RO/FC/Total).
    Other monetary tables often have 16–18 numbers and must not be accepted
    via a loose last-trio fallback. OCR may drop one mid-row token → 14 nums;
    then last-two (FC, Total) is allowed when ``ocr_loose``.
    """
    if len(nums) > 16:
        return None
    candidates: list[tuple[float, float]] = []
    if len(nums) >= 15:
        candidates.append((nums[13], nums[14]))
    if ocr_loose and len(nums) >= 14:
        candidates.append((nums[-2], nums[-1]))
    if not candidates and len(nums) >= 15:
        candidates.append((nums[-2], nums[-1]))

    seen: set[tuple[float, float]] = set()
    for fcd, td in candidates:
        key = (round(fcd, 4), round(td, 4))
        if key in seen:
            continue
        seen.add(key)
        if td <= 0 or fcd < 0:
            continue
        if fcd > td * 1.02:
            continue
        # private deposits OMR mn: ~3k–50k (2010s–2020s)
        if td < 2_000 or td > 80_000:
            continue
        if fcd < 50 or fcd > 40_000:
            continue
        ratio = fcd / td
        if ratio < 0.03 or ratio > 0.45:
            continue
        return fcd, td
    return None


def _score_obs_page(text: str, obs: list[tuple[str, float, float]]) -> float:
    """Rank candidate pages — prefer titled private-sector breakdown with 15 cols."""
    if not obs:
        return -1.0
    score = float(len(obs))
    low = text.lower()
    if "breakdown of private sector deposits" in low:
        score += 100.0
    elif "private sector deposits" in low and "rial omani million" in low:
        score += 50.0
    if "demand" in low and "saving" in low and "time" in low:
        score += 20.0
    # penalize balance-sheet pages that also have quarter rows
    if "combined balance sheet" in low or "monetary survey" in low:
        score -= 40.0
    # reward realistic levels (FCD thousands, not zeros)
    fcds = [f for _, f, _ in obs]
    tds = [t for _, _, t in obs]
    if fcds and min(fcds) > 100:
        score += 10.0
    if tds and min(tds) > 5_000:
        score += 10.0
    # mean ratio around 10–20%
    ratios = [f / t for f, t in zip(fcds, tds) if t > 0]
    if ratios:
        mean_r = sum(ratios) / len(ratios)
        if 0.05 <= mean_r <= 0.30:
            score += 15.0
    return score


def _pdf_text_full(content: bytes) -> str:
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        try:
            r = subprocess.run(
                ["pdftotext", "-layout", path, "-"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.stdout and len(r.stdout) > 500:
                return r.stdout
        finally:
            os.unlink(path)
    except Exception:
        pass
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        return ""


def _pdf_pages_text(content: bytes) -> list[str]:
    pages: list[str] = []
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
    except Exception:
        pass
    if pages:
        return pages
    # pdftotext page-split fallback
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            path = tmp.name
        try:
            r = subprocess.run(
                ["pdftotext", "-layout", path, "-"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.stdout:
                pages = r.stdout.split("\f")
        finally:
            os.unlink(path)
    except Exception:
        pass
    return pages


def _ocr_pages(content: bytes, page_from: int, page_to: int, dpi: int = 220) -> str:
    """OCR PDF pages [page_from, page_to] (1-indexed) via pdftoppm + tesseract.

    CBO pre-2021 tables are often typeset landscape-on-portrait; tesseract only
    recovers digits after a 270° rotation. Try 0° and 270° and keep the best.
    """
    if not _which("pdftoppm") or not _which("tesseract"):
        return ""
    try:
        from PIL import Image
    except ImportError:
        Image = None  # type: ignore

    best = ""
    best_score = -1
    with tempfile.TemporaryDirectory(prefix="omn_ocr_") as td:
        pdf_path = Path(td) / "in.pdf"
        pdf_path.write_bytes(content)
        prefix = str(Path(td) / "p")
        try:
            subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-r",
                    str(dpi),
                    "-f",
                    str(page_from),
                    "-l",
                    str(page_to),
                    str(pdf_path),
                    prefix,
                ],
                capture_output=True,
                timeout=180,
                check=False,
            )
        except Exception as e:
            logger.debug("[OMN] pdftoppm failed: %s", e)
            return ""

        rotations = (0, 270) if Image is not None else (0,)
        for img_path in sorted(Path(td).glob("p*.png")):
            try:
                base = Image.open(img_path) if Image is not None else None
            except Exception:
                base = None
            for ang in rotations:
                try:
                    if base is not None and ang:
                        rot_path = Path(td) / f"{img_path.stem}_r{ang}.png"
                        base.rotate(ang, expand=True).save(rot_path)
                        target = rot_path
                    else:
                        target = img_path
                    r = subprocess.run(
                        [
                            "tesseract",
                            str(target),
                            "stdout",
                            "-l",
                            "eng",
                            "--psm",
                            "6",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    t = r.stdout or ""
                except Exception:
                    continue
                # score: decimal tokens + year hits + quarter labels
                sc = len(re.findall(r"\d+\.\d+", t))
                sc += 5 * len(set(re.findall(r"\b20\d{2}\b", t)))
                sc += 2 * len(re.findall(r"\bQ[I1l]{1,3}\b", t, re.I))
                if "private sector" in t.lower() or "total deposits" in t.lower():
                    sc += 50
                if sc > best_score:
                    best_score = sc
                    best = t
    return best


def _which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def _is_mostly_scanned(pages: list[str], content_len: int = 0) -> bool:
    # CBO 2015–2018 QBs are ~12–15 MB image-heavy PDFs (TOC text only).
    if content_len >= 8_000_000:
        return True
    if not pages:
        return True
    rich = sum(1 for p in pages if len(p) > 400)
    return rich < max(3, len(pages) // 10)


def _parse_pdf(
    content: bytes,
    country_code: str,
    source_label: str = "",
    allow_ocr: bool = False,
):
    # 1) page-by-page text — score pages so Monetary Survey etc. lose to
    #    "Breakdown of Private Sector Deposits" (exactly 15 numeric cols).
    pages = _pdf_pages_text(content)
    rows: list[tuple[str, float, float]] = []
    best_score = -1.0
    for t in pages:
        if not t or len(t) < 80:
            continue
        if not re.search(r"\bQI{1,3}\b|\bQIV\b|\bQ[1-4]\b", t, re.I):
            continue
        # skip pages without any 15-number rows and without title/hint
        maxn = max((len(_nums(line)) for line in t.splitlines()), default=0)
        titled = bool(_TITLE_RE.search(t))
        hinted = bool(_SECTION_HINT_RE.search(t))
        if not titled and not hinted and maxn < 15:
            continue
        found = _extract_obs(t)
        if not found:
            continue
        sc = _score_obs_page(t, found)
        if sc > best_score:
            best_score = sc
            rows = found

    # 2) full-text with multi-title scoring
    if best_score < 50:
        full = _pdf_text_full(content)
        found = _extract_obs(full)
        sc = _score_obs_page(full, found) if found else -1.0
        if sc > best_score:
            best_score = sc
            rows = found

    # 3) OCR fallback for scanned bulletins (pre-2021 era) — opt-in (slow)
    #    Table 9 is typically printed p.16–18 → PDF pages ~19–24.
    if best_score < 50 and allow_ocr and _is_mostly_scanned(pages, len(content)):
        n_pages = len(pages) if pages else 40
        # Narrow first (page 21 is Table 9 in QBMarch2015); widen only if needed
        for lo, hi in ((21, 21), (20, 22), (19, 24)):
            if lo > n_pages + 5:
                continue
            ocr_text = _ocr_pages(content, lo, min(hi, max(n_pages, hi)))
            if not ocr_text:
                continue
            found = _extract_obs(ocr_text, ocr_loose=True)
            sc = _score_obs_page(ocr_text, found) if found else -1.0
            logger.info(
                "[OMN] OCR pages %d-%d → %d obs score=%.1f (%s)",
                lo,
                hi,
                len(found),
                sc,
                source_label or "pdf",
            )
            if sc > best_score:
                best_score = sc
                rows = found
            if len(rows) >= 18:  # ~2010–2014 full quarters
                break

    if not rows:
        return _empty()
    df = long_rows(country_code, rows)
    logger.info(
        "[OMN] %s → %d rows (%s~%s) score=%.1f",
        source_label or "pdf",
        len(df),
        df["period"].min(),
        df["period"].max(),
        best_score,
    )
    return df


def _name_variants(year: int, month_token: str) -> list[str]:
    """Generate filename variants for one quarter (En suffix order preferred)."""
    tokens = []
    for m in (
        month_token,
        month_token.capitalize(),
        month_token.upper(),
        month_token.lower(),
    ):
        if m not in tokens:
            tokens.append(m)
    names: list[str] = []
    # Prefer En/EN (post-2021) then bare (2015–2018)
    for m in tokens:
        for en in ("En", "EN", "", "en"):
            names.append(f"QB{m}{year}{en}.pdf")
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _probe_url(url: str, sess: requests.Session) -> bytes | None:
    try:
        r = sess.get(url, timeout=90, verify=False)
        if r.status_code != 200:
            return None
        if r.content[:4] != b"%PDF" or len(r.content) < 50_000:
            return None
        return r.content
    except Exception:
        return None


def _exists_url(url: str, sess: requests.Session) -> bool:
    """Cheap existence check; fall back to ranged GET."""
    try:
        r = sess.head(url, timeout=20, verify=False, allow_redirects=True)
        if r.status_code == 200:
            cl = int(r.headers.get("Content-Length") or 0)
            ct = (r.headers.get("Content-Type") or "").lower()
            if cl >= 50_000 or "pdf" in ct:
                return True
        if r.status_code not in (403, 405, 501, 200):
            return False
    except Exception:
        pass
    try:
        r = sess.get(
            url,
            timeout=30,
            verify=False,
            headers={**_HEADERS, "Range": "bytes=0-7"},
        )
        if r.status_code in (200, 206) and (
            r.content[:4] == b"%PDF" or b"%PDF" in r.content[:8]
        ):
            return True
    except Exception:
        return False
    return False


def _discover_urls(start_year: int = 2015, end_year: int | None = None) -> list[str]:
    """Discover existing QB PDF URLs with minimal requests (1–N per quarter)."""
    end_year = end_year or datetime.now(timezone.utc).year
    sess = requests.Session()
    sess.headers.update(_HEADERS)
    found: list[str] = []
    # hub scrape first
    for u in _list_from_hub():
        found.append(u)

    for y in range(start_year, end_year + 1):
        for mon, tokens in _QUARTER_TOKEN_ORDER.items():
            hit = False
            for tok in tokens:
                for name in _name_variants(y, tok):
                    u = f"{_QB_BASE}/{y}/{name}"
                    if _exists_url(u, sess):
                        found.append(u)
                        hit = True
                        logger.info("[OMN] found %s", name)
                        break
                if hit:
                    break
            # no hit for this quarter — continue

    # de-dupe case-insensitively; prefer En over bare when both exist later via size
    seen: set[str] = set()
    uniq: list[str] = []
    for u in found:
        k = u.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(u)
    logger.info("[OMN] discovered %d QB URLs", len(uniq))
    return uniq


def _list_from_hub() -> list[str]:
    """Best-effort scrape of QuarterlyBulletins hub HTML for PDF links."""
    out: list[str] = []
    try:
        r = requests.get(_LIST_PAGE, headers=_HEADERS, timeout=40, verify=False)
        if r.status_code != 200:
            return out
        for href in re.findall(
            r'href=["\']([^"\']*QuarterlyBulletins/[^"\']+\.pdf)["\']',
            r.text,
            re.I,
        ):
            out.append(urljoin(_LIST_PAGE, href))
        # also absolute paths in scripts / JSON
        for href in re.findall(
            r'(https?://[^"\'\s]+QuarterlyBulletins/[^"\'\s]+\.pdf)',
            r.text,
            re.I,
        ):
            out.append(href)
    except Exception as e:
        logger.debug("[OMN] hub: %s", e)
    return out


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=90, verify=False)
        if r.status_code != 200:
            return None
        if r.content[:4] != b"%PDF" or len(r.content) < 50_000:
            return None
        return r.content
    except Exception:
        return None


def _key_from_url(u: str) -> str | None:
    m = re.search(r"/(\d{4})/QB([A-Za-z]+)(\d{4})", u)
    if not m:
        return None
    mon = m.group(2).lower()
    y = m.group(3)
    for tok, mm in _MONTH_TOKENS:
        if mon.startswith(tok.lower()[:3]) or mon == tok.lower():
            return f"{y}-{mm:02d}"
    # Sept special
    if mon.startswith("sept"):
        return f"{y}-09"
    return f"{y}-{mon}"


def render(target: dict):
    country_code = target["country_code"]
    try:
        urls = _discover_urls(2015)
        if not urls:
            logger.error("[%s] no quarterly bulletin URLs found", country_code)
            return _empty()

        frames = []
        # Separate small/text PDFs from large scanned ones
        text_urls: list[str] = []
        scan_urls: list[str] = []
        # Quick size probe via HEAD Content-Length when possible
        sess = requests.Session()
        sess.headers.update(_HEADERS)
        for u in urls:
            size = 0
            try:
                r = sess.head(u, timeout=15, verify=False, allow_redirects=True)
                size = int(r.headers.get("Content-Length") or 0)
            except Exception:
                pass
            # scanned QBs are ~12–15 MB; text ones ~1–5 MB
            if size >= 8_000_000:
                scan_urls.append(u)
            else:
                text_urls.append(u)

        def one(u: str, allow_ocr: bool = False):
            content = _download(u)
            if not content:
                return None, u
            # if we classified as text but it's huge scanned, re-route
            if not allow_ocr and len(content) >= 8_000_000:
                return None, u  # handle in OCR pass
            df = _parse_pdf(
                content,
                country_code,
                source_label=u.rsplit("/", 1)[-1],
                allow_ocr=allow_ocr,
            )
            if df is None or df.empty:
                return None, u
            return df, u

        hits = 0
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = [ex.submit(one, u, False) for u in text_urls]
            for fut in as_completed(futs):
                df, u = fut.result()
                if df is not None and not df.empty:
                    frames.append(df)
                    hits += 1
                    logger.info(
                        "[OMN] ok %s periods=%d (%s~%s)",
                        u.rsplit("/", 1)[-1],
                        df["period"].nunique(),
                        df["period"].min(),
                        df["period"].max(),
                    )

        # Extend history with scanned early bulletins (OCR).
        # 2015 March Table 9 carries 2010 QI … 2015 QI — text QBs only start ~2015.
        min_period = (
            min(str(d["period"].min()) for d in frames) if frames else "9999"
        )
        if min_period > "2010-03" and scan_urls:
            # Prefer earliest March/Dec issues for longest back-fill
            scan_urls_sorted = sorted(scan_urls, key=lambda x: _key_from_url(x) or x)
            by_year: dict[str, str] = {}
            for u in scan_urls_sorted:
                k = _key_from_url(u) or ""
                y = k[:4] if k else u
                # prefer March (full year window in early QBs)
                name = u.rsplit("/", 1)[-1].lower()
                if y not in by_year or "mar" in name:
                    by_year[y] = u
            # 2015 March is the key 2010 backfill source
            ocr_targets = list(by_year.values())[:4]
            logger.info(
                "[OMN] OCR pass on %d scanned QBs (min_period=%s)",
                len(ocr_targets),
                min_period,
            )
            with ThreadPoolExecutor(max_workers=2) as ex:
                futs = [ex.submit(one, u, True) for u in ocr_targets]
                for fut in as_completed(futs):
                    df, u = fut.result()
                    if df is not None and not df.empty:
                        frames.append(df)
                        hits += 1
                        logger.info(
                            "[OMN] ok-OCR %s periods=%d (%s~%s)",
                            u.rsplit("/", 1)[-1],
                            df["period"].nunique(),
                            df["period"].min(),
                            df["period"].max(),
                        )

        if not frames:
            logger.error("[%s] no quarterly bulletins parsed", country_code)
            return _empty()

        # later max-period frames win on overlap
        frames.sort(key=lambda d: str(d["period"].max()))
        out = merge_frames(*frames)
        logger.info(
            "[%s] merged %d rows (%s~%s) from %d PDFs",
            country_code,
            len(out),
            out["period"].min() if len(out) else "-",
            out["period"].max() if len(out) else "-",
            hits,
        )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return _empty()
