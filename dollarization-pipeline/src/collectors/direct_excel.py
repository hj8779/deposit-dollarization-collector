import pandas as pd

from src.collectors.base import ScrapingStrategy, collect_via_parser
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DirectExcelStrategy(ScrapingStrategy):
    """direct_download_url이 엑셀 파일을 직접 가리키는 국가를 처리한다.

    실제 파싱 로직은 src/parsers/{country_code}.py에 국가별로 분리되어 있으며,
    이 클래스는 해당 모듈을 동적으로 로드해 실행하는 역할만 한다.
    """

    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        return collect_via_parser(target, logger)
