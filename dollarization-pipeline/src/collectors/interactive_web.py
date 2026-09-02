import pandas as pd

from src.collectors.base import ScrapingStrategy, collect_via_parser
from src.utils.logger import get_logger

logger = get_logger(__name__)


class InteractiveWebStrategy(ScrapingStrategy):
    """JS 렌더링이 필요한 통계 웹페이지, 혹은 정적 페이지 내부 파일 링크를 처리한다.

    실제 파싱 로직은 src/parsers/{country_code}.py에 국가별로 분리되어 있으며,
    이 클래스는 해당 모듈을 동적으로 로드해 실행하는 역할만 한다.
    requires_js=true인 국가 중 파서가 없는 경우는 아직 미구현(Playwright 필요, TODO)이다.
    """

    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        return collect_via_parser(target, logger)
