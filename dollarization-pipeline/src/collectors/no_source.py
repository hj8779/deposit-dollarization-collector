import pandas as pd

from src.collectors.base import ScrapingStrategy
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NoSourceStrategy(ScrapingStrategy):
    """수집 대상 소스가 없는 국가(No Standalone Source)를 처리한다."""

    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        logger.info("[%s] 수집 대상 없음 (스킵)", target.get("country_code"))
        return self.empty_frame()
