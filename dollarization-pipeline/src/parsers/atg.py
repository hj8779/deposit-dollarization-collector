"""Antigua and Barbuda: ECCB Interactive Database, country='Antigua and Barbuda'.
See src/parsers/_eccb_common.py for the shared scraping logic (no SDMX API is available;
this uses a Playwright form query)."""

import pandas as pd

from src.parsers._eccb_common import fetch_fcd

FILE_URL = "__RENDER__"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("ATG is handled via render()")


def render(target: dict) -> pd.DataFrame:
    return fetch_fcd(target["country_code"], "Antigua and Barbuda")
