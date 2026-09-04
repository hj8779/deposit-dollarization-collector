"""Papua New Guinea: Bank of PNG (bankpng.gov.pg) is Cloudflare-blocked (managed
challenge, "Just a moment..." — confirmed still blocking even headless Chromium via
Playwright, not just plain requests). No machine-readable FCD/TD source has been
found.

A previous version stored a handful of FCD/TD ratios cited from secondary sources
like S&P Global as TD=100 (a fake denominator)/FCD=ratio, making them look like
actual deposit-balance data. This was removed after review flagged that the figures
were never published directly by BPNG (secondary citation, unverifiable) and the TD
value itself was a fabricated placeholder, so leaving it in the database as if it
were a "collected observation" was misleading. Until BPNG access becomes possible or
a genuine public source is found, this returns an empty result (candidate for
manual entry — consider registering it in web/src/lib/manualUpdateCountries.ts)."""

from __future__ import annotations

import pandas as pd

FILE_URL = "__RENDER__"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("PNG is handled via render()")


def render(target: dict) -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])
