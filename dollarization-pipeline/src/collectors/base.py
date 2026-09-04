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

# Some sites block requests with default UA/Accept headers (403/406), so we
# use headers that resemble a real browser.
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
    """Render a page with Playwright (Chromium) and return the Page object.
    The caller is responsible for calling browser.close() (wrap in a with-block)."""
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
    """Standard OCR fallback for PDFs where pdfplumber.extract_text() can't read the
    text (e.g. broken character encoding, or pages that render upside down).

    Renders the first max_pages pages as images, runs OCR at each rotation
    (0/90/180/270 degrees), and collects candidates whose OCR text contains the
    marker string. If marker is a short string like a title, it can sometimes
    match loosely under the wrong rotation (e.g. the table title roughly matches
    but the body numbers are scrambled), so simply taking the first candidate
    that contains marker can yield poor quality. Pass `scorer(text) -> int` to
    pick the highest-scoring candidate among those containing marker (e.g. a
    function that counts how many data rows actually parse successfully). If no
    scorer is given, the first match is returned.

    This is expensive (OCR runs once per page x 4 rotations), so only call it as
    a last resort when plain text extraction has failed. Requires the
    tesseract-ocr binary to be installed on the system.
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
    """Dynamically load src/parsers/{country_code_lowercase}.py.
    Returns None if no parser module exists for that country."""
    module_name = f"src.parsers.{country_code.lower()}"
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


def collect_via_parser(target: dict, logger) -> pd.DataFrame:
    """Load the src/parsers module matching target and run FILE_URL/parse().
    Execution logic shared by DirectExcelStrategy and InteractiveWebStrategy."""
    country_code = target["country_code"]
    url = target.get("source_url")

    module = load_parser(country_code)
    if module is None:
        logger.info("[%s] No country-specific parser implemented, skipping (see the adapter field in config/targets.json)", country_code)
        return ScrapingStrategy.empty_frame()

    file_url = getattr(module, "FILE_URL", None) or url

    if file_url == "__RENDER__":
        # Not a downloadable file — a custom render() handles the collection logic
        logger.info("[%s] Running custom render() (not a single file download): %s", country_code, url)
        return module.render(target)

    if not file_url:
        logger.warning("[%s] No FILE_URL/source_url, skipping", country_code)
        return ScrapingStrategy.empty_frame()

    referer = url if file_url != url else None
    logger.info("[%s] Downloading and parsing: %s", country_code, file_url)
    content = download(file_url, referer=referer)
    return module.parse(content, country_code)


class ScrapingStrategy(ABC):
    """Common interface that every collection strategy must implement."""

    @abstractmethod
    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        """Given target info, return the standard long-form DataFrame (LONG_FORMAT_COLUMNS)."""
        raise NotImplementedError

    @staticmethod
    def empty_frame() -> pd.DataFrame:
        return pd.DataFrame(columns=LONG_FORMAT_COLUMNS)
