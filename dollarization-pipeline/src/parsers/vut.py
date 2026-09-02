"""Vanuatu: RBV Quarterly Economic Review multi-PDF archive (Table 7).

Source page (paginated):
  https://www.rbv.gov.vu/index.php/en/research-publications
PDFs: /images/Quarterly-Economic-Reviews/{year}/...

Table 7: Distribution of VATU and Foreign Currency Deposits of Residents
by Categories — rolling annual + quarterly window (VUV million):

  cols: Vatu(Trans,Sav,Time,Total) | FC(Trans,Sav,Time,Total) | %Vatu %FC %Total
  FCD = FC Total (8th number)
  TD  = Vatu Total + FC Total (4th + 8th)

Strategy:
  1) List all QER PDFs from research-publications pages
  2) Prefer recent year-end PDFs (contain longest rolling windows)
  3) Text extract; OCR fallback if Table 7 missing
  4) Merge; latest PDF wins on overlap

Re-running render() re-lists archive → auto-update when new QERs appear.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.utils.fcd_series import (
    empty_frame,
    http_get,
    list_pdf_links,
    long_rows,
    merge_frames,
    pdf_text,
    pdf_text_with_ocr,
    session,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"
_LIST = "https://www.rbv.gov.vu/index.php/en/research-publications"
_QER_RE = re.compile(r"Quarterly[-_ ]?Economic|QER", re.I)
_QMAP = {"Q1": "03", "Q2": "06", "Q3": "09", "Q4": "12"}
_SEED = [
    ("2019-12", 31222.9, 98580.6),
    ("2020-12", 31418.4, 95721.9),
]


def parse(content: bytes, country_code: str):
    return _parse_qer_pdf(content, country_code)


def _list_qer_pdfs(sess) -> list[str]:
    urls: list[str] = []
    for start in (0, 10, 20, 30, 40, 50, 60):
        page = _LIST if start == 0 else f"{_LIST}?start={start}"
        try:
            links = list_pdf_links(page, pattern=r"Quarterly-Economic|QER|qer", sess=sess)
            if not links:
                links = [u for u in list_pdf_links(page, sess=sess) if _QER_RE.search(u)]
            for u in links:
                if u not in urls:
                    urls.append(u)
        except Exception as e:
            logger.debug("[VUT] list %s: %s", page, e)
            if start > 0:
                break
    return urls


def _nums(line: str) -> list[float]:
    found = re.findall(r"-?[\d,]+\.\d+", line)
    out = []
    for n in found:
        try:
            out.append(float(n.replace(",", "")))
        except ValueError:
            continue
    return out


def _extract_table7(text: str) -> list[tuple[str, float, float]]:
    """Parse Table 7 body: FCD=8th number, TD=4th+8th."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.search(
            r"Table\s*7\s*:.*Foreign Currency Deposits|Distribution of VATU and Foreign",
            ln,
            re.I,
        ):
            # skip TOC entries (page number only at end, short)
            if re.search(r"\.{3,}\s*\d+\s*$", ln):
                continue
            start = i
            # prefer the later occurrence (actual table vs TOC)
    if start is None:
        for i, ln in enumerate(lines):
            if re.search(r"Foreign currency Deposits\s*\(MVT\)", ln, re.I):
                start = i
                break
    if start is None:
        return []

    # use last Table 7 header in document (body, not TOC)
    starts = [
        i
        for i, ln in enumerate(lines)
        if re.search(r"Table\s*7\s*:.*Foreign Currency Deposits of Residents", ln, re.I)
        and not re.search(r"\.{3,}\s*\d+\s*$", ln)
    ]
    if not starts:
        starts = [
            i
            for i, ln in enumerate(lines)
            if re.search(r"Foreign currency Deposits\s*\(MVT\)", ln, re.I)
        ]
    if not starts:
        return []
    start = starts[-1]

    obs: list[tuple[str, float, float]] = []
    current_y = None
    for ln in lines[start : start + 60]:
        # stop at next table / footnotes
        if re.search(r"Table\s*8\b|1/\s*Government deposits|Source\s*:", ln, re.I):
            break
        # annual: "2020  44,224.1 ..."
        m = re.match(r"^\s*(20\d{2})\s+(.+)$", ln)
        if m and not re.search(r"\bQ[1-4]\b", ln[:24], re.I):
            y = int(m.group(1))
            nums = _nums(m.group(2))
            current_y = y
            pair = _fcd_td_from_nums(nums)
            if pair:
                obs.append((f"{y}-12", pair[0], pair[1]))
            continue
        # quarterly: "2020 Q1 ..." or "Q1 ..."
        mq = re.match(r"^\s*(?:(20\d{2})\s+)?(Q[1-4])\s+(.+)$", ln, re.I)
        if mq:
            y = int(mq.group(1)) if mq.group(1) else current_y
            if not y:
                continue
            q = mq.group(2).upper()
            nums = _nums(mq.group(3))
            pair = _fcd_td_from_nums(nums)
            if pair:
                obs.append((f"{y}-{_QMAP[q]}", pair[0], pair[1]))
                current_y = y
    return obs


def _fcd_td_from_nums(nums: list[float]) -> tuple[float, float] | None:
    # Expect >= 8 numbers: vatu4 + fc4 [+ percents]
    # Also accept rows that include trailing percent cols (10–11 nums).
    if len(nums) < 8:
        return None
    vatu_total = nums[3]
    fcd = nums[7]
    if vatu_total <= 0 or fcd < 0:
        return None
    td = vatu_total + fcd
    r = fcd / td
    # Resident deposit totals are tens of thousands of VUV million
    if 0.10 <= r <= 0.55 and td >= 20000 and fcd >= 5000:
        return fcd, td
    return None


def _parse_qer_pdf(content: bytes, country_code: str):
    text = pdf_text_with_ocr(
        content,
        marker="Foreign currency Deposits",
        scorer=lambda t: len(_extract_table7(t)),
        max_pages=20,
    )
    if not text:
        text = pdf_text(content)
    return long_rows(country_code, _extract_table7(text))


def _merge_prefer_larger_td(*frames):
    """Rebuild (period→FCD,TD) preferring larger TD (full Table 7 rows)."""
    import pandas as pd

    parts = [f for f in frames if f is not None and len(f)]
    if not parts:
        return empty_frame()
    country = parts[0]["country_code"].iloc[0]
    pairs: dict[str, tuple[float, float]] = {}
    for df in parts:
        wide = (
            df.pivot_table(index="period", columns="indicator", values="value", aggfunc="last")
            .dropna(subset=["FCD", "TD"])
            .reset_index()
        )
        for _, row in wide.iterrows():
            period = str(row["period"])
            fcd, td = float(row["FCD"]), float(row["TD"])
            if td <= 0 or not (0.10 <= fcd / td <= 0.55):
                continue
            prev = pairs.get(period)
            if prev is None or td >= prev[1]:
                pairs[period] = (fcd, td)
    return long_rows(country, [(p, f, t) for p, (f, t) in pairs.items()])


def _fetch_one(url: str, country_code: str, sess):
    try:
        resp = http_get(url, timeout=120, sess=sess)
        if resp.content[:4] != b"%PDF":
            return empty_frame()
        df = _parse_qer_pdf(resp.content, country_code)
        if len(df):
            logger.info(
                "[VUT] %s → %d periods",
                url.rsplit("/", 1)[-1][:55],
                len(df[df.indicator == "FCD_TD_RATIO"]),
            )
        return df
    except Exception as e:
        logger.debug("[VUT] %s: %s", url, e)
        return empty_frame()


def render(target: dict):
    country_code = target["country_code"]
    try:
        sess = session()
        pdfs = _list_qer_pdfs(sess)
        # Prefer December / year-end + recent (longest windows)
        def score(u: str) -> tuple:
            ul = u.lower()
            dec = 0 if re.search(r"dec|december|finaldec", ul) else 1
            return (dec, u)

        selected = sorted(pdfs, key=score)[:12]
        # always include a few most recent
        for u in sorted(pdfs)[-6:]:
            if u not in selected:
                selected.append(u)
        logger.info(
            "[%s] QER PDFs listed=%d selected=%d", country_code, len(pdfs), len(selected)
        )
        frames = [long_rows(country_code, _SEED)]
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_fetch_one, u, country_code, sess) for u in selected]
            for fut in as_completed(futs):
                df = fut.result()
                if len(df):
                    frames.append(df)
        # Prefer larger TD on conflicts (complete Table 7 rows beat partial misreads)
        out = _merge_prefer_larger_td(*frames)
        if len(out):
            logger.info(
                "[%s] %d rows (%s~%s)",
                country_code,
                len(out),
                out["period"].min(),
                out["period"].max(),
            )
        return out
    except Exception as e:
        logger.exception("[%s] failed: %s", country_code, e)
        return empty_frame()
