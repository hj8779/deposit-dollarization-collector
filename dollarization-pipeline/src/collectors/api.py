import pandas as pd

from src.collectors.base import ScrapingStrategy, collect_via_parser
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ApiStrategy(ScrapingStrategy):
    """Handles countries collected by calling an official REST API (e.g. SIE-API) directly.

    The actual parsing logic lives per-country in src/parsers/{country_code}.py;
    this class only dynamically loads and runs that module.
    """

    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        return collect_via_parser(target, logger)
