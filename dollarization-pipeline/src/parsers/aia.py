"""Anguilla: ECCB Interactive Database, country='Anguilla'.
See src/parsers/_eccb_common.py for the shared scraping logic (there's no SDMX API — this
queries a Playwright-driven form)."""

import pandas as pd

from src.parsers._eccb_common import fetch_fcd

FILE_URL = "__RENDER__"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("AIA is handled via render()")


def render(target: dict) -> pd.DataFrame:
    return fetch_fcd(target["country_code"], "Anguilla")
