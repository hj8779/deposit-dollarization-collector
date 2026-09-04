from src.collectors.api import ApiStrategy
from src.collectors.base import ScrapingStrategy
from src.collectors.direct_excel import DirectExcelStrategy
from src.collectors.interactive_web import InteractiveWebStrategy
from src.collectors.no_source import NoSourceStrategy
from src.collectors.pdf_bulletin import PdfBulletinStrategy

# data_type -> Strategy mapping. Any data_type not in this list falls back to NoSourceStrategy.
STRATEGIES: dict[str, ScrapingStrategy] = {
    "Direct Excel": DirectExcelStrategy(),
    "Direct Excel/CSV Download": DirectExcelStrategy(),
    "PDF Bulletin": PdfBulletinStrategy(),
    "PDF/Document": PdfBulletinStrategy(),
    "Interactive Web": InteractiveWebStrategy(),
    "API": ApiStrategy(),
    "No Standalone Source": NoSourceStrategy(),
}

_DEFAULT_STRATEGY = NoSourceStrategy()


def get_strategy(data_type: str | None) -> ScrapingStrategy:
    return STRATEGIES.get(data_type, _DEFAULT_STRATEGY)
