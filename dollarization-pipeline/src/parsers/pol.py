"""Poland: nbp.pl is fully protected by Incapsula (all paths tested return the same
6183-byte "Pardon Our Interruption" JS challenge page, including static-looking
archive URLs, the Polish-language mirror, and even Wayback Machine snapshots of the
page). Confirmed blocked via: plain requests with full browser headers, headless
Chromium (Playwright, with anti-automation flags, up to 20s wait), and WebFetch.

static.nbp.pl (the file-serving subdomain) itself is NOT blocked (200 on root), but
without being able to load the archive listing page we don't have the actual xlsx
filenames to guess at — NBP's file naming doesn't follow an obvious year-based
convention we could brute-force.

이전 버전은 IMF/BIS 등에서 인용한 몇 개 연도의 비율을 TD=100(가짜 분모)/FCD=비율 형태로
저장해 실측 예금 데이터처럼 보이게 했으나 NBP 원출처가 아니고 TD가 조작된 값이라는 지적을
받아 DB에서 삭제하고 파서를 빈 결과로 되돌림(2026-08-18). 사용자가 실제 파일 URL을
확인해서 알려주면 바로 파서를 붙일 수 있음."""

from __future__ import annotations

import pandas as pd

FILE_URL = "__RENDER__"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("POL는 render()로 처리한다")


def render(target: dict) -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])
