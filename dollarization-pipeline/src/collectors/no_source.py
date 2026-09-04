import pandas as pd

from src.collectors.base import ScrapingStrategy
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NoSourceStrategy(ScrapingStrategy):
    """Handles countries with no source to collect from (No Standalone Source)."""

    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        logger.info("[%s] No source to collect (skipping)", target.get("country_code"))
        return self.empty_frame()
