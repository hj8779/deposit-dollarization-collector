"""Papua New Guinea: Bank of PNG (bankpng.gov.pg) is Cloudflare-blocked (managed
challenge, "Just a moment..." — confirmed still blocking even headless Chromium via
Playwright, not just plain requests). No machine-readable FCD/TD source has been
found.

이전 버전은 S&P Global 등 2차 출처에서 인용한 FCD/TD 비율 몇 개를
TD=100(가짜 분모)/FCD=비율 형태로 저장해 실제 예금 잔액 데이터처럼 보이게 만들었으나,
BPNG가 직접 공개한 수치가 아니고(2차 인용, 검증 불가) TD 값 자체가 조작된 placeholder라
데이터베이스에 '수집된 실측치'처럼 남아있는 게 오해를 부른다는 지적을 받아 제거함.
BPNG 접근이 가능해지거나 진짜 공개 소스를 찾기 전까지는 빈 결과를 반환한다(수동 입력
대상 - web/src/lib/manualUpdateCountries.ts 등록 검토)."""

from __future__ import annotations

import pandas as pd

FILE_URL = "__RENDER__"


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("PNG는 render()로 처리한다")


def render(target: dict) -> pd.DataFrame:
    return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])
