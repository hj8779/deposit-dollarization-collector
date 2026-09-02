"""Montserrat: ECCB Interactive Database, country='Montserrat'.
공용 스크래핑 로직은 src/parsers/_eccb_common.py 참고 (SDMX API는 존재하지 않음, Playwright 폼 조회)."""

import pandas as pd

from src.parsers._eccb_common import fetch_fcd

FILE_URL = "__RENDER__"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("MSR은 render()를 통해 처리한다")


def render(target: dict) -> pd.DataFrame:
    return fetch_fcd(target["country_code"], "Montserrat")
