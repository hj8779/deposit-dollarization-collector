

📁 Root
 ├── 📂 1. dollarization-pipeline  (백엔드: ETL + API 통합 + 분석 모델링)
 └── 📂 2. dollarization-portfolio (프론트엔드: Streamlit 앱 + GitHub Pages)

dollarization-pipeline/
├── .github/
│   └── workflows/
│       └── quarterly_etl.yml       # 분기별 자동 실행 GitHub Actions
├── config/
│   └── targets.json               # 질문자님이 올려주신 129개국 수집 정보 데이터
├── src/
│   ├── __init__.py
│   ├── collectors/                # 전략 패턴 적용 수집 및 파싱 모듈
│   │   ├── __init__.py
│   │   ├── base.py                # ScrapingStrategy (추상 클래스)
│   │   ├── direct_excel.py        # Direct Excel 수집기
│   │   ├── pdf_bulletin.py        # PDF Bulletin 파서 (pdfplumber)
│   │   ├── interactive_web.py     # Interactive Web 수집기 (Playwright)
│   │   └── registry.py            # data_type -> Strategy 매핑 레지스트리
│   ├── external_api/              # World Bank API 연동 모듈
│   │   ├── __init__.py
│   │   └── worldbank.py
│   ├── storage/                   # DB 저장 모듈
│   │   ├── __init__.py
│   │   └── supabase_store.py      # Supabase PostgreSQL UPSERT 로직
│   └── utils/                     # 공통 유틸리티 (로거, 날짜 계산 등)
│       ├── __init__.py
│       └── logger.py
├── .env.example                   # Supabase DB URL 환경변수 템플릿
├── .gitignore
├── main.py                        # 전체 수집 파이프라인 실행 엔트리포인트
├── README.md
└── requirements.txt               # pandas, sqlalchemy, psycopg2, playwright, pdfplumber 등

**메타데이터 스키마**
{
  "country_code": "ISO 3글자 코드",
  "data_type": "Direct Excel / PDF Bulletin / Interactive Web / No Standalone Source 중 하나",
  "source_url": "최종 다운로드 또는 통계 메인 페이지 URL (없으면 null)",
  "update_frequency": "Monthly / Quarterly / Annual / null",
  "requires_js": true 또는 false,
  "notes": "세부 수집 경로 가이드 및 비고"
}

**개발패턴**

from abc import ABC, abstractmethod
import pandas as pd

# 1. 공통 인터페이스 (모든 전략이 지켜야 할 규칙)
class ScrapingStrategy(ABC):
    @abstractmethod
    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        """모든 수집 전략은 target 정보를 받아 표준 롱폼 DataFrame을 반환해야 함"""
        pass

# 2. 구체적인 전략 클래스들 구현
class DirectExcelStrategy(ScrapingStrategy):
    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        print(f"[{target['country_code']}] 엑셀 직접 다운로드 수행")
        # 엑셀 다운로드 및 롱폼 파싱 로직...
        return pd.DataFrame()

class PdfBulletinStrategy(ScrapingStrategy):
    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        print(f"[{target['country_code']}] PDF 표 파싱 수행")
        # pdfplumber 로직...
        return pd.DataFrame()

class NoSourceStrategy(ScrapingStrategy):
    def collect_and_parse(self, target: dict) -> pd.DataFrame:
        print(f"[{target['country_code']}] 수집 대상 없음 (스킵)")
        return pd.DataFrame()


# 3. 전략을 실행하는 '컨텍스트(Context)' / 매핑 딕셔너리
STRATEGIES = {
    "Direct Excel": DirectExcelStrategy(),
    "PDF Bulletin": PdfBulletinStrategy(),
    "No Standalone Source": NoSourceStrategy(),
}

# 4. 실행부 (if-else 문이 완전히 사라짐)
def execute_collector(target: dict):
    # targets.json의 data_type에 맞춰 알맞은 전략 객체를 꺼냄
    data_type = target.get("data_type", "No Standalone Source")
    
    # 전략 객체 가져오기 (없으면 기본값으로 NoSourceStrategy)
    strategy = STRATEGIES.get(data_type, NoSourceStrategy())
    
    # 전략 실행! (어떤 전략이든 똑같이 .collect_and_parse() 호출)
    return strategy.collect_and_parse(target)



[클로드 코드 요청 지시문]

"우리가 구축한 config/targets.json 파일 기반으로 **외화예금 데이터 자동 수집 파이프라인(dollarization-pipeline)**의 초기 프로젝트 구조와 기본 코드를 작성해 줘.

[요구사항]

디렉토리 구조 생성: 아래에 정의된 파이썬 프로젝트 폴더 구조를 자동으로 만들어 줄 것.

전략 패턴(Strategy Pattern) 기반 어댑터 구현:

data_type이 Direct Excel, PDF Bulletin, Interactive Web, null (또는 No Standalone Source)인 경우를 구분하여 각각을 처리할 수 있는 ScrapingStrategy Abstract Class 및 구현체(Subclass)들을 만들 것.

if-else문 분기 대신, data_type을 Key로 사용하는 Strategy Registry(매핑 테이블) 방식으로 디스패치되도록 구현할 것.

표준 롱폼(Long Format) 정규화:

모든 파서/어댑터의 출력값은 [country_code, year, period, indicator, value, updated_at] 컬럼을 가진 Pandas DataFrame으로 반환되도록 인터페이스를 통합할 것.

Supabase PostgreSQL 연동 저장소 구현:

src/storage/supabase_store.py 모듈을 작성하여, 파싱된 롱폼 데이터를 Supabase PostgreSQL 테이블(deposit_dollarization)에 Composite Primary Key (country_code, year, period, indicator) 기준 UPSERT 방식으로 저장하는 로직을 작성할 것.

GitHub Actions 설정:

매 분기(1월, 4월, 7월, 10월 1일) 실행되는 .github/workflows/quarterly_etl.yml 워크플로우를 작성할 것."




**배치루프**

# scripts/batch_runner.py 개념 예시
import json
from src.collectors.direct_excel import DirectExcelCollector

def run_next_batch(batch_size=5):
    with open('config/targets.json', 'r') as f:
        targets = json.load(f)
    
    # 아직 구현 안 된 Direct Excel 국가 5개 추출
    todo_list = [t for t in targets if t.get('target', {}).get('data_type') == 'Direct Excel' 
                  and t.get('adapter', {}).get('status') == 'todo'][:batch_size]
    
    print(f"=== 다음 배치 대상 ({len(todo_list)}개국) ===")
    for t in todo_list:
        print(f"- {t['country_name']} ({t['alpha3_code']}): {t['target']['direct_download_url']}")
        
    # 각 국가별 자동 수집 테스트 및 롱폼 변환 결과 행(Row) 수 출력
    # ...



