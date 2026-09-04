"""Poland: nbp.pl is fully protected by Incapsula (all paths tested return the same
6183-byte "Pardon Our Interruption" JS challenge page, including static-looking
archive URLs, the Polish-language mirror, and even Wayback Machine snapshots of the
page). Confirmed blocked via: plain requests with full browser headers, headless
Chromium (Playwright, with anti-automation flags, up to 20s wait), and WebFetch.

static.nbp.pl (the file-serving subdomain) itself is NOT blocked (200 on root), but
without being able to load the archive listing page we don't have the actual xlsx
filenames to guess at — NBP's file naming doesn't follow an obvious year-based
convention we could brute-force.

A previous version stored a few years of ratios cited from IMF/BIS etc. as
TD=100 (a fake denominator)/FCD=ratio, making them look like actual deposit data.
This was removed after review flagged that these weren't from the original NBP
source and TD was a fabricated value, so the rows were deleted from the DB and the
parser reverted to returning an empty result (2026-08-18). If the user confirms and
provides the actual file URL, the parser can be wired up immediately."""

from __future__ import annotations

import pandas as pd

FILE_URL = "__RENDER__"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("POL is handled via render()")


def render(target: dict) -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])
