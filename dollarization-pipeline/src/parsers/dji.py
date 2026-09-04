"""Djibouti: PDFs posted on the Banque Centrale de Djibouti (BCD) 'Dépôts des banques' page
(banque-centrale.dj/depots-des-banques/). In each PDF's '3 - VENTILATION PAR DEVISES DES
DEPOTS' (deposit breakdown by currency) table, FCD = the sum of the 'Dollars des Etats-Unis
(USD)' + 'Autres devises' (other foreign currencies) rows ('Francs Djibouti (FDJ)' is excluded
since it's the domestic currency).

TD (total deposits) = the same table's 'Total' row (sum of FDJ + USD + Autres devises). The
TOTAL row's top is already included in the label boundary calculation (so that the OTHER row's
value range doesn't incorrectly swallow values belonging to the earlier part of TOTAL), so the
value is simply pulled with _values_for("TOTAL").

This table groups digits with a thousands-separator space (e.g. '212 382' = 212,382), and
since consecutive values on the same line are all space-separated, text alone can't tell where
one number ends and the next begins (e.g. '212 382 213 384 213 584 ...' is, in order, 212382,
213384, 213584, ... but is ambiguous from text parsing alone since everything is
space-delimited). On top of that, the table layout differs subtly from file to file: in some
files the header is split across two lines (recent quarter on the first line, older quarters
on the second), and the data is split the same way before/after the label; in others, the
label and values sit on the same line.

So instead of working line-by-line on text, the table is reconstructed using pdfplumber's word
coordinates (extract_words, x0): the x0 coordinates of the header row's period tokens (e.g.
'mars-21', 'Sept. 2017', 'déc-20' — the notation varies by file) are used as column reference
points, each data-number word is assigned to the column with the nearest x0 (multiple words
assigned to the same column are concatenated in ascending x0 order, e.g. '212'+'382' ->
212382), and values are reconstructed per column. This approach simultaneously resolves both
the ambiguity of space-separated numbers and the file-to-file variation in line-break
placement.

The quarterly series starts at 2017-03. The earlier period (2009-2016) is backfilled from the
annual reports (banque-centrale.dj/rapports-annuel-de-la-banque/)'s 'Evolution/Composantes de
la masse monétaire' table (a 5-year rolling window per report, with the table layout existing
in two variants across reports): the 'Dépôts en devises' (=FCD) row and the 'Dépôts à vue' +
'Dépôts sur livrets' (or the older notation 'Autres dépôts à vue FDJ') + 'Dépôts à terme' +
'Dépôts en devises' (=TD) rows are extracted, and only the pre-2017 period is backfilled (2017
onward is skipped since the quarterly data is already more granular, to avoid duplicate
inserts). The table comes in two layouts (one where the year header row has the same top as
'Composantes', and an older Annexe-table variant that labels the 'other deposits' row
'Autres'), so instead of matching the 'Composantes' text, the header is located as the row
(the topmost group on the page) with 3 or more consecutive 4-digit year tokens at the same
top, and the second deposit row falls back to searching for the 'Autres' label when no
'livrets' label is found — supporting both layouts.
"""

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

LIST_URL = "https://banque-centrale.dj/depots-des-banques/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_SECTION_TITLE_RE = re.compile(r"ventilation\s+par\s+devises", re.I)
# pdfplumber's extract_words() splits labels into individual words like
# 'Dollars'/'des'/'Etats-Unis'/'(USD)', so instead of matching the full phrase within one
# word, anchor on just the distinguishing first word.
_USD_LABEL_RE = re.compile(r"^dollars$", re.I)
_OTHER_LABEL_RE = re.compile(r"^autres$", re.I)
_FDJ_LABEL_RE = re.compile(r"^francs$", re.I)
_TOTAL_RE = re.compile(r"^total$", re.I)

_PERIOD_RE = re.compile(
    r"^(?P<mon>[A-Za-zéû]+)\.?[-\s]?(?P<year>\d{2,4})$"
)
_MONTHS = {
    "jan": 1, "janv": 1, "fev": 2, "fevr": 2, "févr": 2, "feb": 2,
    "mar": 3, "mars": 3, "avr": 4, "avril": 4,
    "mai": 5, "juin": 6, "jun": 6, "juil": 7, "jul": 7,
    "aou": 8, "aoû": 8, "aout": 8, "août": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12, "déc": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("DJI is handled via render() (needs to walk the post listing)")


def _collect_pdf_links() -> list[str]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(LIST_URL, timeout=60000)
        page.wait_for_timeout(2000)
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        browser.close()

    return sorted({h for h in hrefs if "depot" in h.lower() and h.lower().endswith(".pdf")})


def _period_to_yyyymm(token: str) -> str | None:
    m = _PERIOD_RE.match(token.strip().rstrip("."))
    if not m:
        return None
    month = _MONTHS.get(m.group("mon").strip().lower()[:4]) or _MONTHS.get(m.group("mon").strip().lower()[:3])
    if month is None:
        return None
    year = int(m.group("year"))
    if year < 100:
        year += 2000
    return f"{year}-{month:02d}"


_MONTH_ONLY_RE = re.compile(r"^[A-Za-zéû]+\.?$")
_YEAR_ONLY_RE = re.compile(r"^(19|20)\d{2}$")


def _extract_period_columns(header_words: list[dict]) -> list[tuple[float, str]]:
    """Extracts header period tokens as a list of (x0, 'YYYY-MM'). Handles both cases where
    month/year are joined in one word (e.g. 'mars-21') and where they're separate
    space-delimited words (e.g. 'Mars.' + '2019')."""
    ordered = sorted(header_words, key=lambda w: w["x0"])
    columns: list[tuple[float, str]] = []
    used_idx: set[int] = set()

    for i, w in enumerate(ordered):
        if i in used_idx:
            continue
        period = _period_to_yyyymm(w["text"])
        if period:
            columns.append((w["x0"], period))
            continue
        if _MONTH_ONLY_RE.match(w["text"]) and i + 1 < len(ordered):
            nxt = ordered[i + 1]
            if _YEAR_ONLY_RE.match(nxt["text"]):
                period = _period_to_yyyymm(f"{w['text']}{nxt['text']}")
                if period:
                    columns.append((w["x0"], period))
                    used_idx.add(i + 1)
    return columns


def _nearest_column(x0: float, columns: list[tuple[float, str]]) -> int:
    best_idx, best_dist = 0, float("inf")
    for i, (col_x0, _) in enumerate(columns):
        dist = abs(col_x0 - x0)
        if dist < best_dist:
            best_idx, best_dist = i, dist
    return best_idx


def _parse_pdf(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber
    from io import BytesIO

    now = datetime.now(timezone.utc).isoformat()
    rows_out = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not _SECTION_TITLE_RE.search(text):
                continue

            all_words = page.extract_words()
            # 0. Tables 1/2/3 (by deposit type / by depositor sector / by currency) appear
            #    together on the same page, and tables 1 and 2 reuse the same period header
            #    (e.g. 'Juin-25'), which could cause confusion — so only words below the point
            #    where the '3 - VENTILATION PAR DEVISES' title appears are treated as belonging
            #    to this table.
            devises_title_words = [w for w in all_words if w["text"].upper().startswith("DEVISES")]
            if not devises_title_words:
                continue
            section_top = min(w["top"] for w in devises_title_words)
            words = [w for w in all_words if w["top"] >= section_top]

            # 1. Define columns from header period tokens (deduplicated, ordered by top
            #    (ascending = higher up first), then by x0 for ties). The header region runs
            #    from the top where 'Selon les devises' appears down to just before the first
            #    currency label.
            # The 'Total' row can also have its values split before/after the label just like
            # the other currency rows (e.g. the most recent quarter's total appears before the
            # 'Total' label), so TOTAL is also treated as one of the labels and included in the
            # boundary calculation, to prevent the OTHER row's value range from incorrectly
            # swallowing values belonging to the earlier part of Total.
            label_tops_by_kind = {
                "FDJ": [w["top"] for w in words if _FDJ_LABEL_RE.search(w["text"])],
                "USD": [w["top"] for w in words if _USD_LABEL_RE.search(w["text"])],
                "OTHER": [w["top"] for w in words if _OTHER_LABEL_RE.search(w["text"])],
                "TOTAL": [w["top"] for w in words if _TOTAL_RE.match(w["text"])],
            }
            if not label_tops_by_kind["USD"] or not label_tops_by_kind["OTHER"]:
                logger.warning("[%s] Could not find USD/Autres devises label", country_code)
                continue
            first_label_top = min(min(v) for v in label_tops_by_kind.values() if v)

            header_candidates = [w for w in words if w["top"] < first_label_top]
            columns = _extract_period_columns(header_candidates)
            if not columns:
                continue
            columns.sort(key=lambda c: c[0])  # ascending x0 = chronological order (left=older, right=most recent)
            n_periods = len(columns)

            # 2. List the labels in top order, and split the value region using the midpoint
            #    between adjacent label tops as the boundary. Depending on the file, a row's
            #    values may be split before the label line (older format: most recent quarter
            #    appears first) and after it (older quarters); the midpoint-boundary approach
            #    automatically assigns values to the "nearest label" regardless of which side
            #    they're on, handling both layouts.
            all_label_tops = sorted(
                (top, kind) for kind, tops in label_tops_by_kind.items() for top in tops
            )
            section_end = max(w["top"] for w in words) + 1

            boundaries = [min(w["top"] for w in header_candidates)]
            for i in range(len(all_label_tops) - 1):
                boundaries.append((all_label_tops[i][0] + all_label_tops[i + 1][0]) / 2)
            boundaries.append(section_end)

            def _values_for(kind: str) -> list[float] | None:
                idx = next((i for i, (_, k) in enumerate(all_label_tops) if k == kind), None)
                if idx is None:
                    return None
                lo, hi = boundaries[idx], boundaries[idx + 1]
                value_words = [
                    w for w in words
                    if lo <= w["top"] < hi and re.fullmatch(r"-?[\d]+", w["text"])
                ]
                if not value_words:
                    return None

                buckets: dict[int, list[tuple[float, str]]] = {}
                for w in value_words:
                    col_idx = _nearest_column(w["x0"], columns)
                    buckets.setdefault(col_idx, []).append((w["x0"], w["text"]))

                values = [None] * n_periods
                for col_idx, items in buckets.items():
                    items.sort(key=lambda t: t[0])
                    combined = "".join(t[1] for t in items)
                    try:
                        values[col_idx] = float(combined)
                    except ValueError:
                        pass
                return values

            usd_vals = _values_for("USD")
            other_vals = _values_for("OTHER")
            total_vals = _values_for("TOTAL")
            if usd_vals is None or other_vals is None:
                logger.warning("[%s] Could not find USD/Autres devises values", country_code)
                continue

            for i, period in enumerate(p for _, p in columns):
                usd = usd_vals[i] if i < len(usd_vals) else None
                other = other_vals[i] if i < len(other_vals) else None
                if usd is None or other is None:
                    continue
                rows_out.append({
                    "country_code": country_code,
                    "year": int(period[:4]),
                    "period": period,
                    "indicator": INDICATOR,
                    "value": round(usd + other, 2),
                    "updated_at": now,
                })

                total = total_vals[i] if total_vals is not None and i < len(total_vals) else None
                if total is not None:
                    rows_out.append({
                        "country_code": country_code,
                        "year": int(period[:4]),
                        "period": period,
                        "indicator": INDICATOR_TD,
                        "value": round(total, 2),
                        "updated_at": now,
                    })

    return pd.DataFrame(rows_out)


# --- Annual reports (for backfilling 2009-2016) ---------------------------------------------

ANNUAL_REPORTS_URL = "https://banque-centrale.dj/rapports-annuel-de-la-banque/"
# The first year the quarterly series starts. From this year onward, the quarterly data is
# already more granular, so annual-report values are not inserted (to avoid duplicates).
_QUARTERLY_SERIES_START_YEAR = 2017

_YEAR_TOKEN_RE = re.compile(r"^(19|20)\d{2}$")
_VUE_LABEL_RE = re.compile(r"^vue$")
_LIVRETS_LABEL_RE = re.compile(r"^livrets$")
_AUTRES_LABEL_RE = re.compile(r"^Autres$")
_TERME_LABEL_RE = re.compile(r"^terme$")
_DEVISES_LABEL_RE = re.compile(r"^devises$")
_NUM_TOKEN_RE = re.compile(r"\d{1,3}(\.\d{3})*|\d+")


def _collect_annual_report_links() -> list[str]:
    response = requests.get(ANNUAL_REPORTS_URL, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    candidates = set(re.findall(
        r"https://banque-centrale\.dj/wp-content/uploads/[^\"'\s]+\.pdf", response.text,
    ))
    return sorted(
        url for url in candidates
        if "rapport" in url.lower() and "annuel" in url.lower()
    )


def _extract_masse_monetaire_table(page) -> dict | None:
    """Locates the 5-year 'Evolution/Composantes de la masse monétaire' table on a page and
    returns it as {year(str): {'vue','second'(livrets/autres),'terme','devises'} integer
    values}. Returns None if the table can't be found or values are incomplete."""
    words = page.extract_words()

    year_tokens = [w for w in words if _YEAR_TOKEN_RE.match(w["text"])]
    if not year_tokens:
        return None
    year_tokens.sort(key=lambda w: w["top"])
    groups: list[list[dict]] = []
    for w in year_tokens:
        for g in groups:
            if abs(g[0]["top"] - w["top"]) < 3:
                g.append(w)
                break
        else:
            groups.append([w])
    groups = [g for g in groups if len(g) >= 3]
    if not groups:
        return None
    header_group = min(groups, key=lambda g: g[0]["top"])
    header_top = header_group[0]["top"]
    columns = sorted((w["x0"], w["text"]) for w in header_group)
    n = len(columns)

    def first_after(pattern: re.Pattern, after_top: float, before_top: float | None = None) -> float | None:
        cands = [
            w for w in words
            if pattern.match(w["text"]) and w["top"] > after_top and (before_top is None or w["top"] < before_top)
        ]
        return min(cands, key=lambda w: w["top"])["top"] if cands else None

    vue_top = first_after(_VUE_LABEL_RE, header_top)
    devises_top = first_after(_DEVISES_LABEL_RE, header_top)
    terme_top = first_after(_TERME_LABEL_RE, header_top, devises_top)
    if vue_top is None or terme_top is None or devises_top is None:
        return None
    second_top = first_after(_LIVRETS_LABEL_RE, vue_top, terme_top)
    if second_top is None:
        second_top = first_after(_AUTRES_LABEL_RE, vue_top, terme_top)
    if second_top is None:
        return None

    def nearest_col(x0: float) -> int:
        return min(range(n), key=lambda i: abs(columns[i][0] - x0))

    def values_for(label_top: float) -> list[int | None]:
        toks = [
            w for w in words
            if abs(w["top"] - label_top) <= 6 and _NUM_TOKEN_RE.fullmatch(w["text"])
        ]
        buckets: dict[int, list[dict]] = {}
        for w in toks:
            buckets.setdefault(nearest_col(w["x0"]), []).append(w)
        vals: list[int | None] = [None] * n
        for c, items in buckets.items():
            items.sort(key=lambda w: w["x0"])
            try:
                vals[c] = int("".join(w["text"].replace(".", "") for w in items))
            except ValueError:
                pass
        return vals

    vue_vals = values_for(vue_top)
    second_vals = values_for(second_top)
    terme_vals = values_for(terme_top)
    devises_vals = values_for(devises_top)
    if any(v is None for v in vue_vals + second_vals + terme_vals + devises_vals):
        return None

    return {
        year: {"vue": vue_vals[i], "second": second_vals[i], "terme": terme_vals[i], "devises": devises_vals[i]}
        for i, (_, year) in enumerate(columns)
    }


def _parse_annual_report(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber
    from io import BytesIO

    now = datetime.now(timezone.utc).isoformat()
    rows_out = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            tl = text.lower()
            if "devises" not in tl or "terme" not in tl or "vue" not in tl:
                continue
            table = _extract_masse_monetaire_table(page)
            if not table:
                continue
            for year_str, vals in table.items():
                year = int(year_str)
                if year >= _QUARTERLY_SERIES_START_YEAR:
                    continue
                period = f"{year}-Annual"
                fcd = vals["devises"]
                td = vals["vue"] + vals["second"] + vals["terme"] + vals["devises"]
                rows_out.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": INDICATOR, "value": float(fcd), "updated_at": now,
                })
                rows_out.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": INDICATOR_TD, "value": float(td), "updated_at": now,
                })
            break  # only one table handled per page (structure/% tables on the same page are skipped)

    return pd.DataFrame(rows_out)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    links = _collect_pdf_links()
    logger.info("[%s] Found %d Depots des banques PDFs", country_code, len(links))

    frames = []
    for url in links:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=60)
            response.raise_for_status()
        except Exception:
            logger.warning("[%s] Download failed, skipping: %s", country_code, url)
            continue

        df = _parse_pdf(response.content, country_code)
        if not df.empty:
            frames.append(df)
        logger.info("[%s] %s -> %d periods", country_code, url.rsplit("/", 1)[-1], len(df))

    try:
        annual_links = _collect_annual_report_links()
        logger.info("[%s] Found %d annual reports (for pre-2017 backfill)", country_code, len(annual_links))
        for url in annual_links:
            try:
                response = requests.get(url, headers=_HEADERS, timeout=60)
                response.raise_for_status()
            except Exception:
                logger.warning("[%s] Annual report download failed, skipping: %s", country_code, url)
                continue
            df = _parse_annual_report(response.content, country_code)
            if not df.empty:
                frames.append(df)
            logger.info("[%s] %s -> %d rows (annual)", country_code, url.rsplit("/", 1)[-1], len(df))
    except Exception:
        logger.warning("[%s] Annual report collection step failed, using quarterly data only", country_code, exc_info=True)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="last")
    return merged.sort_values("period").reset_index(drop=True)
