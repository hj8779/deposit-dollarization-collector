"""PLACEHOLDER — previous version returned fabricated seed/research-ratio data
(TD=100 synthetic denominator or uncited secondary-source stocks) presented as if
collected. Removed 2026-08-18 pending a real, verifiable public source. Returns
empty until rebuilt."""

from __future__ import annotations

import pandas as pd

FILE_URL = "__RENDER__"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("stub")


def render(target: dict) -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])
