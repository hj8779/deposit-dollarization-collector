import pandas as pd

from src.collectors.base import ScrapingStrategy, collect_via_parser
from src.utils.logger import get_logger

logger = get_logger(__name__)


class InteractiveWebStrategy(ScrapingStrategy):
    """Handles statistics web pages that require JS rendering, or file links embedded in static pages.

    The actual parsing logic lives per-country in src/parsers/{country_code}.py;
    this class only dynamically loads and runs that module.
    Countries with requires_js=true that lack a parser are not yet implemented
    (needs Playwright, TODO).
    """

    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        return collect_via_parser(target, logger)
