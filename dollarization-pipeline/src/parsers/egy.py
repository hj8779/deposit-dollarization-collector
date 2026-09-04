"""Egypt: Central Bank of Egypt(CBE), Table "Banking Survey: Deposits (Except CBE)".

An earlier investigation (targets.json notes) claimed that cbe.org.eg returns
"Request Rejected" from its WAF, but in reality that only happens for specific
paths (e.g. /robots.txt); a plain GET with a browser UA header successfully
downloads most pages and attached xlsx files, including
/en/economic-research/time-series and
/en/economic-research/economic-reports/monthly-statistical-bulletin
(Playwright is not required).

The data is assembled from two sources.

1. The Time Series page (category 'Banking Surveys' -> 'Deposits in Local and
   Foreign Currency') has a single xlsx
   ('deposits-in-local-and-foreign-currency-monthly-june-2023.xlsx') containing
   one sheet per fiscal year (Jul-Jun) from 2004-2005 through 2022-2023, giving
   us monthly data from 2004-07 to 2023-06 in one shot.
2. Data after that (2023-07 onward) comes from the Monthly Statistical
   Bulletin's per-issue xlsx files
   ('financial-and-monetary-sector-{issue}.xlsx', sheet 'جدول3'). Each issue
   contains end-of-June snapshots for the last 5 fiscal years plus a rolling
   window of roughly the last 7-13 months, and the rolling window shifts by
   exactly one month for each increment of the issue number (empirically
   confirmed: issue 297's latest month = 2021-10, issue 349's latest month =
   2026-02, a difference of 52 issues = 52 months). We use this property to
   back-calculate "the issue number that should be current right now" from a
   historical reference point (REFERENCE_ISSUE/YEAR/MONTH), search forward and
   backward from that estimate to find the actual latest issue, then walk the
   issue numbers downward from there (each issue -1 month) and keep
   downloading until we reach the point where coverage overlaps with the Time
   Series file's range (2023-06) — since the site only keeps roughly the last
   ~50 issues, older issue numbers 404 anyway.

The two tables share the same row structure (distinguishable by the
capitalization of the government/non-government and currency labels):
    Total Deposits (Including Gov.Deposits)
    Government Deposits
        In local currency / In foreign currencies
    Non-Government Deposits
        In Local Currency
            Public/Private business sector, Household sector,
            Non-resident (external sector), Minus purchased cheques & drafts
        In Foreign Currencies
            (same sub-items as above)

Resident foreign currency deposits (FCD) = "In Foreign Currencies" total -
                     "Non-resident (external sector)"
                     (= sum of Public+Private business+Household minus the
                        purchased cheques/drafts deduction; empirically
                        confirmed that both formulas match to the decimal)
Resident total deposits (TD) = FCD + ("In Local Currency" total -
                     "Non-resident (external sector)")

Both government deposits and non-resident (external sector) deposits are
excluded, since only resident deposits should be counted under this project's
"resident foreign currency deposits" definition.
"""

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd

from src.collectors.base import download
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"  # Multiple files (historical archive + several recent issues) must be merged.

_TS_URL = (
    "https://www.cbe.org.eg/-/media/project/cbe/listing/time-series/banking-survey/"
    "deposits-in-local-and-foreign-currency/deposits-in-local-and-foreign-currency-monthly-june-2023.xlsx"
)
_BULLETIN_URL_TMPL = (
    "https://www.cbe.org.eg/-/media/project/cbe/listing/monthly-statistical-bulletin/"
    "financial/financial-and-monetary-sector-{n}.xlsx"
)
_BULLETIN_SHEET = "جدول3"

# Empirical reference point: issue 297's rolling-window latest month = 2021-10 (verified against issue 349 = 2026-02; 52 issues = 52 months matches)
_REF_ISSUE = 297
_REF_YEAR, _REF_MONTH = 2021, 10

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month_num(text) -> int | None:
    if not isinstance(text, str):
        return None
    key = text.strip().rstrip("#").rstrip(".").strip().lower()[:3]
    return _MONTHS.get(key)


def _find_row(df: pd.DataFrame, col: int, needle: str, start: int = 0) -> int | None:
    for i in range(start, len(df)):
        v = df.iat[i, col]
        if isinstance(v, str) and needle in v:
            return i
    return None


def _find_indices(df: pd.DataFrame, label_col: int):
    """Finds the row indices for the currency/residency total rows under 'Non-Government
    Deposits', in document order. Labels carry footnote markers (+, ++), so substring
    matching is used."""
    ng = _find_row(df, label_col, "Non-Government Deposits")
    if ng is None:
        return None
    local_total = _find_row(df, label_col, "In Local Currency", ng + 1)
    if local_total is None:
        return None
    local_nonres = _find_row(df, label_col, "Non-resident (external sector)", local_total + 1)
    if local_nonres is None:
        return None
    fc_total = _find_row(df, label_col, "In Foreign Currencies", local_nonres + 1)
    if fc_total is None:
        return None
    fc_nonres = _find_row(df, label_col, "Non-resident (external sector)", fc_total + 1)
    if fc_nonres is None:
        return None
    return local_total, local_nonres, fc_total, fc_nonres


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])


def _build_rows(country_code: str, periods_values: list[tuple[str, float, float]]) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for period, fcd, td in periods_values:
        year = int(period[:4])
        ratio = round((fcd / td) * 100, 4) if td else None
        for indicator, value in (("FCD", fcd), ("TD", td), ("FCD_TD_RATIO", ratio)):
            if value is None:
                continue
            rows.append({
                "country_code": country_code,
                "year": year,
                "period": period,
                "indicator": indicator,
                "value": round(value, 2) if indicator != "FCD_TD_RATIO" else value,
                "updated_at": now,
            })
    return pd.DataFrame(rows)


def _parse_timeseries(content: bytes, country_code: str) -> pd.DataFrame:
    xl = pd.ExcelFile(BytesIO(content))
    periods_values = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, header=None)
        title_row = _find_row(df, 0, "Banking Survey")
        if title_row is None:
            continue
        month_row = title_row + 1
        idx = _find_indices(df, 0)
        if idx is None:
            continue
        local_total, local_nonres, fc_total, fc_nonres = idx

        last_year = None
        for col in range(2, df.shape[1]):
            y = df.iat[title_row, col]
            if pd.notna(y):
                try:
                    last_year = int(y)
                except (TypeError, ValueError):
                    pass
            month = _month_num(df.iat[month_row, col])
            if month is None or last_year is None:
                continue
            try:
                fcd = df.iat[fc_total, col] - df.iat[fc_nonres, col]
                td_fc_part = fcd
                td = (df.iat[local_total, col] - df.iat[local_nonres, col]) + td_fc_part
            except TypeError:
                continue
            if pd.isna(fcd) or pd.isna(td):
                continue
            periods_values.append((f"{last_year}-{month:02d}", float(fcd), float(td)))

    if not periods_values:
        return _empty()
    return _build_rows(country_code, periods_values)


def _parse_bulletin(content: bytes, country_code: str) -> tuple[pd.DataFrame, set[str]]:
    """Returns: (long-form DataFrame, set of periods in the rolling-window range).

    The table starts with end-of-June snapshots for the last 5 fiscal years (the
    annual anchor section, all 'June'), followed by a rolling window of the most
    recent several months. Since the anchor section is always pinned to the same
    5 past fiscal years' Junes (i.e. its coverage barely changes as the issue
    number advances), using the anchor section to decide in render() whether we've
    reached the point where it overlaps with the Time Series archive would cause a
    false positive and stop right at the first issue. So we distinguish the anchor
    section from the rolling-window section and use only the rolling-window
    section's periods for the overlap check (the rolling window is considered to
    start at the first 'non-June' month column that appears after the anchor
    section)."""
    try:
        xl = pd.ExcelFile(BytesIO(content))
    except Exception:
        return _empty(), set()
    if _BULLETIN_SHEET not in xl.sheet_names:
        return _empty(), set()
    df = xl.parse(_BULLETIN_SHEET, header=None)

    unit_row = _find_row(df, 2, "LE mn")
    if unit_row is None:
        return _empty(), set()
    year_row = unit_row + 1
    month_row = unit_row + 3

    idx = _find_indices(df, 1)
    if idx is None:
        return _empty(), set()
    local_total, local_nonres, fc_total, fc_nonres = idx

    periods_values = []
    rolling_periods = set()
    last_year = None
    in_annual_anchor = True
    for col in range(2, df.shape[1]):
        y = df.iat[year_row, col]
        if pd.notna(y):
            try:
                last_year = int(y)
            except (TypeError, ValueError):
                pass
        month = _month_num(df.iat[month_row, col])
        if month is None or last_year is None:
            continue
        if in_annual_anchor and month != 6:
            in_annual_anchor = False
        try:
            fcd = df.iat[fc_total, col] - df.iat[fc_nonres, col]
            td = (df.iat[local_total, col] - df.iat[local_nonres, col]) + fcd
        except TypeError:
            continue
        if pd.isna(fcd) or pd.isna(td):
            continue
        period = f"{last_year}-{month:02d}"
        periods_values.append((period, float(fcd), float(td)))
        if not in_annual_anchor:
            rolling_periods.add(period)

    if not periods_values:
        return _empty(), set()
    return _build_rows(country_code, periods_values), rolling_periods


def _estimate_latest_issue() -> int:
    now = datetime.now(timezone.utc)
    months_since_ref = (now.year - _REF_YEAR) * 12 + (now.month - _REF_MONTH)
    return _REF_ISSUE + months_since_ref


def _issue_exists(n: int) -> bytes | None:
    """A nonexistent issue number 302-redirects to /en/page-not-found, and that
    page itself returns HTTP 200 HTML, which makes requests think it succeeded.
    We have to verify the magic bytes to confirm it's really an xlsx (a zip file,
    starting with 'PK') to avoid this false positive."""
    try:
        content = download(_BULLETIN_URL_TMPL.format(n=n))
    except Exception:
        return None
    if not content.startswith(b"PK"):
        return None
    return content


def _find_actual_latest_issue(guess: int) -> tuple[int, bytes] | None:
    """Searches around the estimated issue number (guess) to find the largest
    issue number that actually exists. Tries a few numbers above and below to
    absorb publication delays / estimation error."""
    content = _issue_exists(guess)
    if content is not None:
        # Check a few numbers above guess too, in case the estimate came in low
        n = guess
        best_n, best_content = n, content
        for candidate in range(guess + 1, guess + 6):
            c = _issue_exists(candidate)
            if c is None:
                break
            best_n, best_content = candidate, c
        return best_n, best_content

    # If guess doesn't exist, search downward (in case the estimate came in high)
    for candidate in range(guess - 1, guess - 12, -1):
        c = _issue_exists(candidate)
        if c is not None:
            return candidate, c
    return None


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]
    frames = []

    try:
        ts_content = download(_TS_URL)
        ts_df = _parse_timeseries(ts_content, country_code)
    except Exception as e:
        logger.warning("[%s] Failed to download/parse Time Series archive: %s", country_code, e)
        ts_df = _empty()

    if not ts_df.empty:
        frames.append(ts_df)
        logger.info(
            "[%s] Time Series archive: %d rows (%s~%s)",
            country_code, len(ts_df), ts_df["period"].min(), ts_df["period"].max(),
        )
    covered_periods = set(ts_df["period"]) if not ts_df.empty else set()

    guess = _estimate_latest_issue()
    found = _find_actual_latest_issue(guess)
    if found is None:
        logger.warning("[%s] Could not find the latest Monthly Statistical Bulletin issue (estimated issue=%d)", country_code, guess)
    else:
        latest_issue, latest_content = found
        logger.info("[%s] Latest Monthly Statistical Bulletin issue = issue %d", country_code, latest_issue)

        bulletin_frames = []
        n = latest_issue
        content = latest_content
        consecutive_fail = 0
        tries = 0
        reached_overlap = False
        while consecutive_fail < 3 and tries < 80 and not reached_overlap:
            tries += 1
            if content is None:
                content = _issue_exists(n)
            if content is None:
                consecutive_fail += 1
                n -= 1
                content = None
                continue
            consecutive_fail = 0
            df_b, rolling_periods = _parse_bulletin(content, country_code)
            content = None
            if not df_b.empty:
                bulletin_frames.append(df_b)
                # Overlap detection only considers the rolling-window section (the
                # annual anchor section is always pinned to the same past 5 years'
                # Junes, so it would appear to overlap ts_df from the very first
                # issue and trigger a premature stop).
                if rolling_periods and rolling_periods & covered_periods:
                    reached_overlap = True
            n -= 1

        if bulletin_frames:
            # Concatenated in descending issue-number order (most recent issue
            # first), so the later drop_duplicates(keep="first") picks the most
            # recently revised value for any given period.
            bulletin_df = pd.concat(bulletin_frames, ignore_index=True)
            frames.append(bulletin_df)
            logger.info(
                "[%s] %d Monthly Statistical Bulletin issues yielded %d additional rows",
                country_code, len(bulletin_frames), len(bulletin_df),
            )

    if not frames:
        return _empty()

    merged = pd.concat(frames, ignore_index=True)
    # ts_df (the fiscal-year archive, containing finalized values) was appended first, so overlapping periods prefer the ts_df value.
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="first")
    merged = merged.sort_values(["period", "indicator"]).reset_index(drop=True)
    return merged
