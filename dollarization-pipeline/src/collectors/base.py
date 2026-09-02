import importlib
from abc import ABC, abstractmethod
from types import ModuleType

import pandas as pd
import requests

LONG_FORMAT_COLUMNS = ["country_code", "year", "period", "indicator", "value", "updated_at"]
# Canonical long-form indicators: FCD | TD | FCD_TD_RATIO
# FCD_TD_RATIO is always percent (0–100), i.e. (FCD/TD)*100 — not a 0–1 fraction.
INDICATOR = "FCD"
INDICATOR_FCD = "FCD"
INDICATOR_TD = "TD"
INDICATOR_RATIO = "FCD_TD_RATIO"

# 일부 사이트가 기본 UA/Accept 헤더 요청을 차단(403/406)하므로 브라우저에 가까운 헤더를 사용한다.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def download(url: str, referer: str | None = None) -> bytes:
    headers = dict(_HEADERS)
    if referer:
        headers["Referer"] = referer
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.content


def render_page(url: str, wait_ms: int = 2500):
    """Playwright(Chromium)로 페이지를 렌더링하고 Page 객체를 반환한다.
    호출자가 browser.close()까지 책임진다(with 문으로 감싸 사용)."""
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch()
    page = browser.new_page(user_agent=_HEADERS["User-Agent"])
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(wait_ms)
    return playwright, browser, page


def find_page_text_via_ocr(
    pdf,
    marker: str,
    max_pages: int = 8,
    resolution: int = 200,
    rotations: tuple[int, ...] = (0, 90, 180, 270),
    scorer=None,
) -> str | None:
    """표준 OCR 폴백: pdfplumber.extract_text()로는 텍스트를 못 읽는 PDF(글자 인코딩이
    깨졌거나 페이지가 실제로는 뒤집혀 렌더링되는 등)에 사용한다.

    앞쪽 max_pages 페이지를 이미지로 렌더링해 (0/90/180/270도) 회전마다 OCR을 돌리고,
    OCR 결과 텍스트에 marker 문자열이 포함되는 후보들을 모은다. marker가 제목처럼 짧은
    문자열이면 잘못된 회전에서도 대충 인식되는 경우가 있어(예: 표 제목만 얼추 맞고 본문
    숫자는 뒤죽박죽), 단순히 marker가 포함된 첫 후보를 쓰면 품질이 나쁠 수 있다.
    `scorer(text) -> int`를 넘기면 marker가 포함된 후보 중 점수가 가장 높은 것을 선택한다
    (예: 실제 파싱에 성공하는 데이터 행 수를 세는 함수). scorer가 없으면 첫 매치를 반환한다.

    비용이 크므로(페이지 수 x 회전 4가지 만큼 OCR 실행) 일반 텍스트 추출이 실패했을 때만
    마지막 수단으로 호출할 것. 시스템에 tesseract-ocr 바이너리가 설치되어 있어야 한다.
    """
    import pytesseract

    best_text, best_score = None, -1
    for page in pdf.pages[:max_pages]:
        for rotation in rotations:
            image = page.to_image(resolution=resolution).original
            if rotation:
                image = image.rotate(rotation, expand=True)
            text = pytesseract.image_to_string(image)
            if marker.lower() not in text.lower():
                continue
            if scorer is None:
                return text
            score = scorer(text)
            if score > best_score:
                best_text, best_score = text, score

    return best_text if best_score > 0 else None


def load_parser(country_code: str) -> ModuleType | None:
    """src/parsers/{country_code_lowercase}.py를 동적으로 로드한다.
    해당 국가 파서 모듈이 없으면 None을 반환한다."""
    module_name = f"src.parsers.{country_code.lower()}"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


def collect_via_parser(target: dict, logger) -> pd.DataFrame:
    """target에 대응하는 src/parsers 모듈을 로드해 FILE_URL/parse()를 실행한다.
    DirectExcelStrategy, InteractiveWebStrategy가 공유하는 실행 로직."""
    country_code = target["country_code"]
    url = target.get("source_url")

    module = load_parser(country_code)
    if module is None:
        logger.info("[%s] 국가별 파서 미구현, 스킵 (config/targets.json의 adapter 필드 참고)", country_code)
        return ScrapingStrategy.empty_frame()

    file_url = getattr(module, "FILE_URL", None) or url

    if file_url == "__RENDER__":
        # 다운로드 가능한 파일이 아니라 커스텀 render()가 수집 로직을 담당
        logger.info("[%s] 커스텀 render() 수행(단일 파일 다운로드 아님): %s", country_code, url)
        return module.render(target)

    if not file_url:
        logger.warning("[%s] FILE_URL/source_url이 없어 스킵", country_code)
        return ScrapingStrategy.empty_frame()

    referer = url if file_url != url else None
    logger.info("[%s] 다운로드 및 파싱 수행: %s", country_code, file_url)
    content = download(file_url, referer=referer)
    return module.parse(content, country_code)


class ScrapingStrategy(ABC):
    """모든 수집 전략이 지켜야 할 공통 인터페이스."""

    @abstractmethod
    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        """target 정보를 받아 표준 롱폼 DataFrame(LONG_FORMAT_COLUMNS)을 반환한다."""
        raise NotImplementedError

    @staticmethod
    def empty_frame() -> pd.DataFrame:
        return pd.DataFrame(columns=LONG_FORMAT_COLUMNS)
