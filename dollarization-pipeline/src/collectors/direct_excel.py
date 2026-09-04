import pandas as pd

from src.collectors.base import ScrapingStrategy, collect_via_parser
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DirectExcelStrategy(ScrapingStrategy):
    """Handles countries whose direct_download_url points straight at an Excel file.

    The actual parsing logic lives per-country in src/parsers/{country_code}.py;
    this class only dynamically loads and runs that module.
    """

    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        return collect_via_parser(target, logger)
