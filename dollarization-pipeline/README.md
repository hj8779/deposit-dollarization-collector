# dollarization-pipeline

국가별 외화예금(Foreign Currency Deposits) 통계를 자동 수집해 Supabase PostgreSQL에 적재하는 ETL 파이프라인.

## 구조

```
dollarization-pipeline/
├── .github/workflows/quarterly_etl.yml   # 분기별 자동 실행
├── config/targets.json                   # 국가별 수집 대상 메타데이터
├── src/
│   ├── collectors/                       # 전략 패턴 기반 수집 어댑터 (data_type -> Strategy)
│   │   ├── base.py                       # ScrapingStrategy 추상 클래스, src/parsers 동적 로더
│   │   ├── direct_excel.py
│   │   ├── pdf_bulletin.py
│   │   ├── interactive_web.py
│   │   ├── no_source.py
│   │   └── registry.py                   # data_type -> Strategy 매핑
│   ├── parsers/                          # 국가별 파서 (country_code -> FILE_URL, parse())
│   │   ├── bdi.py, mac.py, bih.py, mwi.py, gtm.py, rus.py
│   │   ├── are.py, can.py, slv.py, aut.py
│   │   └── abw.py                        # 다년도 아카이브 순회 + OCR 폴백 예시
│   ├── external_api/worldbank.py         # World Bank Open Data API 연동
│   ├── storage/supabase_store.py         # Supabase UPSERT 로직
│   └── utils/                            # 로거, 날짜 유틸
├── main.py
└── requirements.txt
```

## src/parsers/ 국가별 파서 구조

`DirectExcelStrategy`, `InteractiveWebStrategy`는 데이터 형식(엑셀 다운로드 방식) 기준의 얕은 디스패치만
담당하고, 국가별 실제 파싱 로직은 `src/parsers/{country_code_lowercase}.py`에 각각 독립 파일로 분리되어
있다. 새 국가를 구현하려면 `src/parsers/{cc}.py` 파일 하나를 추가하면 되고, 두 Strategy 클래스는
`importlib.import_module(f"src.parsers.{country_code.lower()}")`로 해당 모듈을 동적으로 로드해 실행한다.

각 파서 모듈은 다음을 export해야 한다.

| 이름 | 설명 |
| --- | --- |
| `FILE_URL` | 실제 다운로드할 파일 URL. `target['source_url']`을 그대로 쓰면 `None` |
| `parse(content: bytes, country_code: str) -> pd.DataFrame` | 롱폼 DataFrame 반환 |

### 단일 파일 다운로드가 아닌 경우: `FILE_URL = "__RENDER__"`

다운로드 가능한 단일 파일 URL이 없고(예: 페이지 자체가 데이터 소스이거나, 연도별 아카이브를
여러 개 순회해야 하는 경우) 대신 `render(target: dict) -> pd.DataFrame`을 export하면 된다.
`src/collectors/base.collect_via_parser()`가 `FILE_URL == "__RENDER__"`를 보면 다운로드를
건너뛰고 `module.render(target)`을 직접 호출한다. Playwright로 페이지를 렌더링하는 경우
(`can.py`, `slv.py`, `aut.py`)와, 여러 PDF를 순회해 하나로 합치는 경우(`abw.py`가 CBA의
2010년~현재 연도별 아카이브를 순회하는 것이 그 예)에 모두 이 패턴을 쓴다.

### PDF 텍스트 추출 실패 시 표준 폴백: OCR

`pdfplumber.extract_text()`가 빈 값을 주거나 글자 순서가 뒤섞인 텍스트를 주는 PDF가 종종
있다(`abw.py`에서 발견한 사례: 일부 연도의 CBA 월간 회보는 실제로 페이지가 180도 뒤집혀
렌더링되어 있어, 일반 텍스트 추출 결과가 글자 단위로 역순이 된다 — 이런 문제는 육안/비전
모델로 이미지를 봐서는 알아차리기 어렵고, 실제 픽셀이 뒤집혀 있는지 회전을 바꿔가며 OCR
결과 품질로 판단해야 한다).

이 프로젝트의 **표준 절차**는 다음과 같다.

1. 먼저 `pdfplumber.extract_text()`로 정상 파싱을 시도한다.
2. 실패하면(텍스트가 없거나 기대하는 마커/행 패턴이 안 나오면) `src/collectors/base.find_page_text_via_ocr(pdf, marker, scorer=...)`를 호출한다.
   - 앞쪽 페이지들을 이미지로 렌더링해 0/90/180/270도 회전마다 `pytesseract`로 OCR을 돌린다.
   - `marker`는 관대하게 잡는다(OCR이 문장부호·숫자를 놓치는 경우가 많으므로, 예를 들어
     `"TABLE 2: COMPONENTS OF BROAD MONEY"` 대신 `"COMPONENTS OF BROAD MONEY"`처럼
     핵심 단어만 사용).
   - `scorer(text) -> int`에는 "이 텍스트를 실제 파서 정규식으로 파싱했을 때 나오는 행 수"
     같은 함수를 넘긴다. marker만 보고 첫 회전을 채택하면, 틀린 회전에서도 제목만 얼추
     인식되고 본문 숫자는 뒤죽박죽인 텍스트를 채택해버릴 수 있기 때문이다.
3. OCR로 얻은 텍스트도 일반 텍스트와 같은 파싱 함수로 처리하되, OCR 특유의 잡음 토큰
   (예: 각주 밑줄이 `=`로 잘못 인식되는 것)을 먼저 제거한다. 숫자 하나가 깨져 통째로
   행이 매칭 실패하면 그 달은 조용히 건너뛴다(값을 추측해서 채우지 않는다 — 틀린 값보다
   결측이 안전하다).

새로운 국가에서 텍스트 추출이 깨지는 걸 발견하면, 이 패턴을 그대로 재사용할 것: 즉석에서
임시방편을 짜지 말고 `find_page_text_via_ocr`를 가져다 쓰고, 필요하면 그 함수 자체를
개선한다. 시스템에 `tesseract-ocr` 바이너리가 설치되어 있어야 한다(`brew install tesseract`
/ `apt install tesseract-ocr`). `requirements.txt`의 `pytesseract`는 파이썬 바인딩일 뿐이라
바이너리를 대체하지 못한다.

## targets.json 스키마

JSON Schema 정의: [config/targets.schema.json](config/targets.schema.json)

```json
{
  "country_code": "ISO 3글자 코드",
  "data_type": "Direct Excel / PDF Bulletin / Interactive Web / No Standalone Source",
  "source_url": "최종 다운로드 또는 통계 메인 페이지 URL (없으면 null)",
  "update_frequency": "Monthly / Quarterly / Annual / null",
  "requires_js": true,
  "notes": "세부 수집 경로 가이드 및 비고",
  "pending_parsers": [
    {
      "kind": "PDF",
      "source": "추가 발행물 이름",
      "status": "todo",
      "notes": "추후 구현 예정인 보조 소스 설명"
    }
  ],
  "adapter": {
    "implemented": "실제 파싱 로직이 구현되어 값이 나오는지 여부 (true/false)",
    "strategy_class": "이 국가를 처리하는 Strategy 클래스명 (없으면 null)",
    "status": "success / failed / needs_research / todo",
    "notes": "blocked 사유 또는 구현 시 참고한 셀/시트 위치"
  }
}
```

`adapter` 필드는 국가별 실제 수집 코드(`src/parsers/{country_code}.py` 존재 여부)의 구현 상태를
추적한다. `data_type`은 소스의 형식 분류일 뿐이고, 실제로 값이 나오는지는 `adapter.status`로 확인한다.
주 소스는 동작하지만 보완용 발행물(PDF 등) 파서가 아직 없을 때는 `pending_parsers`에
`status: "todo"` 항목을 둔다(예: GIN의 분기·연간 보고서).

## 어댑터 구현 현황

`config/targets.json`을 갱신한 뒤에는 아래 명령으로 이 표를 재생성한다.

```bash
python3 scripts/generate_readme_table.py
```

<!-- ADAPTER_STATUS_TABLE:START -->
전체 249개국 중 구현됨 128개 / 실패 12개 / 재조사 필요 39개 / 미착수 0개 / 대상 아님 70개 (미착수·대상 아님 국가는 표에서 생략)

| 국가코드 | 국가명 | data_type | strategy_class | adapter 상태 | 비고 |
| --- | --- | --- | --- | --- | --- |
| ABW | Aruba | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Monthly Bulletin PDF, TABLE 2: COMPONENTS OF BROAD MONEY. FCD=col(5)+col(9)+col(11), TD=col(6)+col(12). 연도별 아카이브(/document/monthly-tables-{YYYY}/)를 2010~현재까지 순회하며 각 연도의 롤링 윈도우(약 18개월+과거4개년 연간)를 병합해 장기 시계열을 재구성. 일부 PDF는 텍스트가 글자 단위로 뒤집혀 추출되는 손상본이라(2010,2011,2013,2014년 다수, 2018/2021 일부월) 해당 연도는 같은 해 다른 달로 자동 재시도하며, 그래도 실패하면 스킵 -&gt; 2013년만 월별 데이터 공백, 나머지는 2011-01~최신월까지 커버 2010/2011/2013/2014년(및 일부 손상월)은 표준 OCR 폴백(README 참고)으로 추가 복구 시도, 완전 손상 연도는 여전히 일부 공백. |
| AFG | Afghanistan | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Annual/Quarterly Bulletin 랜딩 페이지에서 PDF 전부 수집(파일명에서 분기/연도 라벨 추출, 아프간력&lt;1500이면 +621로 그레고리력 환산), 각 PDF의 'Table 2.1'류 표에서 'In Foreign currency'(Other Deposits/Quasi Money의 외화분) 행의 최신(가장 오른쪽) 열 값 추출. 35개 중 26개 성공(2006~2020, Q 단위), 9개는 해당 연도 표 포맷이 달라 행 자체가 없어 스킵. 사이트 마지막 게시물이 2021-01(FY1399 Q3)이라 최신 데이터는 아님 |
| AGO | Angola | Direct Excel | DirectExcelStrategy | 구현됨 | 'Nova Série' 통계 페이지에서 'Agregados Monetários' 클릭(JS 다운로드, Playwright 필요) -&gt; legacy .xls, 시트 'IA2.AggrMon'(Quadro I.A.2). indicator=foreign_currency_deposits: row25 'Total dos depósitos em moeda externa'(메모 항목 공식 합계). indicator=TD: row12 'Depósitos transferíveis'+row17 'Outros depósitos'(각 총액 행). 2012-01~2026-06, 161개월. bna.ao 응답이 간헐적으로 느려 자체 재시도(최대 3회) 포함 |
| AIA | Anguilla | Interactive Web | InteractiveWebStrategy | 구현됨 | 사용자가 제시한 SDMX REST API(sdmx.eccb-centralbank.org)는 DNS 미해석(존재하지 않는 도메인) 확인됨 -&gt; 실제로는 eccb-centralbank.org의 'Interactive Database' 쿼리 폼(Laravel, CSRF+암호화 hidden 필드, 부트스트랩 모달 안 select2 멀티셀렉트)이 진짜 데이터 소스. Playwright로 모달 열기-&gt; 국가 선택-&gt;'Foreign Currency Deposits' 지표 선택-&gt;제출 흐름 재현(src/parsers/_eccb_common.py 공용). start_date를 jQuery datepicker API로 2000-01-01로 설정해 2000~2025년(26개년) 연간 데이터 확보. 8개국(AIA/ATG/DMA/GRD/MSR/KNA/LCA/VCT) 공용 로직 검증 완료 |
| ALB | Albania | Interactive Web | InteractiveWebStrategy | 구현됨 | 'Sectoral balance sheet of Deposit money banks' 페이지. 체크박스 트리에서 2.1.1.2(Transferable deposits In FC, id=85581) + 2.1.2.2(Other deposits In FC, id=85601) 선택 -&gt; 'Show values' 2단계 클릭(1차: 기간선택 UI 노출, From을 최초월로 설정 -&gt; 2차: 결과가 새 탭(?mode=alone)으로 열림) -&gt; 두 항목 합산이 FCD. 2006-12~2026-06, 235개월 확보 |
| ARE | United Arab Emirates (the) | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Statistical Bulletin PDF, Table 2 Monetary Survey, 'Foreign Currency Deposits' 행을 월별 헤더와 매칭, 13개월 |
| ARG | Argentina | API | ApiStrategy | 구현됨 | 사용자가 제시한 idVariable=14는 실제로 'Tasa de interés de préstamos personales'(개인대출 금리)였음 -&gt; 전체 변수 목록(/v4.0/Monetarias)에서 descripcion 검색으로 idVariable=1414('Depósitos totales del total de sectores', 카테고리='Depósitos por cuenta', 단위=USD백만)를 정확한 지표로 특정. API도 v3.0은 이미 폐기(HTTP 410)되어 v4.0 사용. 일별 데이터를 월말값 기준 월별 집계, offset 페이지네이션(limit=3000). 1999-12~2026-08, 321개월 확보 |
| ARM | Armenia | Interactive Web | InteractiveWebStrategy | 구현됨 | Monetary Aggregates 페이지의 'Export all' 링크(/50/export-all/)가 실제로는 JSON이 아니라 XLSX를 반환(단일 GET, Playwright 불필요). 시트 'value, month': col3 Demand deposits in drams + col5 Time deposits in drams + col7 Deposits in foreign currency(=FCD) = TD. 2003-01~2026-06, 282개월 x 2지표 = 564행 |
| ATG | Antigua and Barbuda | Interactive Web | InteractiveWebStrategy | 구현됨 | 사용자가 제시한 SDMX REST API(sdmx.eccb-centralbank.org)는 DNS 미해석(존재하지 않는 도메인) 확인됨 -&gt; 실제로는 eccb-centralbank.org의 'Interactive Database' 쿼리 폼(Laravel, CSRF+암호화 hidden 필드, 부트스트랩 모달 안 select2 멀티셀렉트)이 진짜 데이터 소스. Playwright로 모달 열기-&gt; 국가 선택-&gt;'Foreign Currency Deposits' 지표 선택-&gt;제출 흐름 재현(src/parsers/_eccb_common.py 공용). start_date를 jQuery datepicker API로 2000-01-01로 설정해 2000~2025년(26개년) 연간 데이터 확보. 8개국(AIA/ATG/DMA/GRD/MSR/KNA/LCA/VCT) 공용 로직 검증 완료 |
| AUS | Australia | Direct Excel | - | 실패(지표 없음) | d03hist.xlsx(D3 Monetary Aggregates) 다운로드는 성공하지만 Currency/Transaction Deposits/M1/CD만 있고 외화예금 항목 없음 |
| AUT | Austria | Interactive Web | InteractiveWebStrategy | 구현됨 | OeNB report=1.7.10, 'Austria' 거주지 블록 하위 MFIs/Non-MFIs의 'Foreign currencies' 행 2개 합산, 연간3+월간6 |
| AZE | Azerbaijan | PDF Bulletin | - | 재조사 필요 | 접속 실패(SSL/연결 오류) |
| BDI | Burundi | Direct Excel | DirectExcelStrategy | 구현됨 | sheet='Mensuelle', col A=date(monthly), col D='Dépôts en devises des résidents' (거주자 외화예금, BIF백만) |
| BEL | Belgium | Interactive Web | InteractiveWebStrategy | 구현됨 | NBB 공식 SDMX-JSON REST API(dataflow BE2,DF_BSIMFI,1.0) 실사용 가능 확인. MBSI_ITEM 코드 L2BEFC='Deposits, Belgium, Foreign currencies'(FCD), L2BE='Deposits, Belgium 전체'(TD) - 실측으로 L2BEEU+L2BEFC=L2BE 항등식 확인. 쿼리 키 M.L2BE+L2BEFC로 필요한 두 시리즈만 요청. base.download()의 기본 Accept 헤더로는 JSON을 못 받아와 render()에서 Accept: application/json 직접 지정 필요. 1996-12~2026-06, 355개월 x 2지표 = 710행 |
| BGD | Bangladesh | Direct Excel | DirectExcelStrategy | 구현됨 | econdata 페이지에 안내 없이 박혀 있는 직접 링크(/econdata/time_series_data1972-2024.xlsx) 발견, 단순 GET은 봇 방어(TSPD) 챌린지 HTML만 반환해 Playwright 다운로드 이벤트 필요. 시트 'Table IA'에 시대별 소표 5개가 세로로 이어붙어 있고 컬럼 구성이 다 다름 -&gt; 'Foreign Currency Deposit'/'FC Deposit' 헤더 텍스트를 동적으로 찾아 그 열만 추출(컬럼 인덱스 고정 시 무관한 'From Inter-Banks' 항목과 우연히 겹쳐 잘못된 값이 섞이는 함정 있었음). 1988-89~2023-24 회계연도, 35개년 |
| BGR | Bulgaria | Direct Excel | DirectExcelStrategy | 구현됨 | 'Monetary Survey' 페이지의 직접 xlsx 링크(s_ms_monetarystatistics_all_en.xlsx), 단일 GET으로 다운로드. 시트 'MS_short'(첫 탭)에서 상위 카테고리 라벨에 'deposit'이 포함된 4개 항목(Overnight/Agreed maturity&lt;=2y/Redeemable at notice&lt;=3m/Agreed maturity&gt;2y)의 'in foreign currency' 하위행 합산=FCD, 'in BGN'+FC 합산=TD (자산 측에도 동일 라벨의 통화분해가 있어 부모라벨 필터로 구분 필요). 1995-12~2025-12, 361개월 x 2지표 = 722행 |
| BHR | Bahrain | Interactive Web | InteractiveWebStrategy | 구현됨 | Publications 페이지 'Statistical Bulletin' 섹션에 매월 별도 xlsx 게시(82개 파일 전부 순회 필요, 각 파일은 최근 ~9개월 롤링 윈도우만 포함). 시트 '3'(Table 3, Money Supply)에서 헤더 'FC' 라벨 컬럼을 동적으로 찾아 사용(Private Sector Demand Deposits의 외화 구성분만 해당, Time/Savings는 통화별 미분리). BD/FC 분해가 대략2018~2019년경 도입되어 그 이전 파일은 이 컬럼 자체가 없어 자동 스킵(고정 컬럼 인덱스로 하면 'Time and Savings' 값이 섞이는 함정 있었음, 실측으로 발견). 2019-01~2026-06, 83개월 |
| BHS | Bahamas (the) | PDF Bulletin | PdfBulletinStrategy | 구현됨 | 'Quarterly Statistical Digest' 목록 페이지(?page=1~6, 총 93개 PDF, 2005~현재)를 전부 순회. 각 호의 'Table 2.5 Financial Survey' 페이지에서 'Foreign Currency Deposits'(Quasi Money 14개 값 중 12번째) 열을 텍스트 정규식으로 추출(벡터 罫線 없어 extract_tables 실패, extract_text 라인 파싱). 연간(수년 롤링)+분기(최근1년)+월간(최근~15개월 롤링) 세 단위 모두 캡처, 기간 라벨로 구분해 저장. 2005~2008년 4개 파일은 표 제목/레이아웃이 달라 별도 조사 필요(스킵됨). 2009-01~2026-03, 152개 기간(연/분기/월 합산) |
| BIH | Bosnia and Herzegovina | Direct Excel | DirectExcelStrategy | 구현됨 | legacy .xls, row7(TOTAL DEPOSITS) 하위 row12='in foreign currency', 헤더 row7='MM-YY' |
| BLR | Belarus | Interactive Web | - | 재조사 필요 | nbrb.by 페이지 로딩 타임아웃(20초 초과) -&gt; 접근성 재조사 필요 |
| BLZ | Belize | PDF Bulletin | PdfBulletinStrategy | 구현됨 | src/parsers/blz.py. OCR 해상도에 따라 tesseract가 표를 행이 아닌 열 단위로 잘못 읽는 경우가 산발적으로 발생해 여러 해상도(240/250/260/275/300dpi)로 시도 후 행 파싱이 가장 잘 된 결과를 채택. 1977-2025, 분기/월간 혼재. 2000년말~2005년말은 FCD=0(실제 값, 외화예금이 거의 없던 시기로 확인). |
| BMU | Bermuda | PDF/Document | PdfBulletinStrategy | 구현됨 | src/parsers/bmu.py (render()). 2000-2025, 분기별, BD$ millions. 2003-Q1/Q2(2003년 보고서가 텍스트 없는 스캔본), 2020-Q1/Q2(50th Anniversary 특별판에 통계 부록 없음)는 소스 자체 결측으로 다른 보고서로도 못 채움. 일부 연도는 Total/BD$/Other 3열, 일부는 Total/BD$/US$/Other 4열이라 FCD=Total-BD$로 통일 계산. |
| BOL | Bolivia (Plurinational State of) | Direct Excel | DirectExcelStrategy | 구현됨 | src/parsers/bol.py. FCD = ME 시트 TOTAL SISTEMA 행, TD = Total 시트 TOTAL SISTEMA 행. 사용자가 처음 제안한 Base Monetaria 31행(Moneda Extranjera)은 중앙은행 지급준비금 중 외화분일 뿐 시중은행 고객 외화예금이 아니라서(금액도 훨씬 작음) 채택하지 않고, 같은 목록의 더 정확한 파일로 대체. |
| BRB | Barbados | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/brb.py (render()). 1989-2011: HISTORY 14 시트 J열 직접 사용. 2012~: TRANSFERABLE DEPOSITS + OTHER DEPOSITS 카테고리의 Foreign Currency 열 합(Included/Excluded from Broad Money 모두 포함), 5행/7행 헤더 텍스트로 컬럼 동적 탐색. 두 구간 경계(2011-12→2012-01) 이음매 깨끗, 총 449개월(1989-01~2026-05) 결측 없음. |
| BRN | Brunei Darussalam | PDF Bulletin | - | 재조사 필요 | 페이지에 PDF 링크가 없음(JS 렌더링 추정) |
| BTN | Bhutan | PDF Bulletin | - | 재조사 필요 | 접속 실패(SSL/연결 오류) |
| BWA | Botswana | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/bwa.py (render()). Publications 전체 페이지(52p)를 순회해 EFS xlsx 30개 + 레거시 xls 1개(2004~2014, xlrd로 파싱)를 모두 찾아 시트 3.16의 Total Pula equivalent(FCD)/Deposits (Pula)(TD) 열을 헤더 텍스트로 동적 탐색, 겹치는 기간은 더 최근 발행 파일 값으로 dedup. 2004-12~2026-05, 146개월, 결측 없음. |
| CAF | Central African Republic (the) | Interactive Web | - | 재조사 필요 | beac.int 페이지에 테이블/파일 없음(SPA 추정) -&gt; 재조사 필요 |
| CAN | Canada | Interactive Web | InteractiveWebStrategy | 구현됨 | Playwright 렌더링 후 테이블에서 'Foreign currency deposits of residents (Unadjusted)' 행 추출, 월별(2026-01~05) |
| CCK | Cocos (Keeling) Islands (the) | Interactive Web | - | 재조사 필요 | stats.gov.ck 페이지에 다운로드 가능한 파일 링크 없음(JS 렌더링 또는 별도 API 추정) -&gt; requires_js 재확인 필요 |
| CHE | Switzerland | API | ApiStrategy | 구현됨 | src/parsers/che.py. FCD = Total(WAEHRUNG=T) - CHF, TD = Total. CHF 개별 통화값 자체가 1996-11까지 비어있어(그 이전은 통화별 분해가 소스에 없음) 1996-12부터만 산출 가능. 1996-12~2026-05, 354개월, 결측 없음. |
| CHL | Chile | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/chl.py. HTML 표의 Serie="Total deposits" 행(백만 달러) = FCD. 2009-01~2026-06, 210개월, 결측 없음. |
| CHN | China | Interactive Web | - | 재조사 필요 | CEIC(제3자 유료 플랫폼) 페이지로 실제 수치가 로그인/구독 없이는 노출되지 않음 -&gt; 재조사 필요 |
| COD | Congo (the Democratic Republic of the) | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/cod.py (render()). 각 호가 최근 ~13개월 롤링 윈도우만 담고 있어 목록의 모든 발간호(85개)를 모아 병합, 겹치는 기간은 최신 발간호 값 우선. 표 형식이 시기별로 두 가지(구형: 연도 두 줄 헤더+프랑스어 월 전체 이름, 신형: 월약어-연도 한 줄 헤더)라 둘 다 파싱, 숫자도 공백/콤마 구분 혼재를 모두 처리. 결과: 2009-12~2026-06, 116개월. 2013~2017년은 해당 기간 발간호 자체가 목록에 없어 결측(소스 자체의 발간 공백, 확인함), 그 외 소수 개별월은 일부 구형 파일의 표 헤더 인식 실패로 결측. |
| COK | Cook Islands (the) | Interactive Web | - | 재조사 필요 | CCK와 동일 사이트(stats.gov.ck) 사용, 다운로드 가능한 파일 링크 없음(JS 렌더링 추정) |
| CPV | Cabo Verde | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/cpv.py (render()). FCD = 'Depósitos em Divisas de Residentes' 행(바로 아래 'Depósitos de Emigrantes'는 별개 카테고리라 제외). 연도가 병합 셀+최근엔 '2026P'처럼 문자열 잠정치 표기라 forward-fill과 숫자 추출 둘 다 필요. 2010-12~2026-06, 179개월, 결측 없음. |
| CRI | Costa Rica | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/cri.py (render()). 각 CodCuadro 페이지의 "Exportar a Excel" 버튼이 여는 URL(frmVerCatCuadro.aspx?CodCuadro=N&Idioma=1&Exportar=True)을 직접 GET하면 확장자만 .xls인 HTML 표가 나와 pandas.read_html로 파싱. 원자료가 1e8 배율로 스케일링되어 있어(화면 표시값과 대조해 확인) 나누어 보정. FCD=167+147, 1987-01~2026-06(167은 1997-01부터), 475개월, 결측 없음. |
| CUW | Curaçao | PDF Bulletin | - | 재조사 필요 | 403 Forbidden(봇 차단) statistics-dashboards/monetary-and-financial-statistics/breakdown-deposits-and-loans 페이지도 동일하게 Cloudflare 챌린지(403)로 막힘 -&gt; 사이트 전역 차단으로 보임. |
| CYM | Cayman Islands (the) | Interactive Web | - | 재조사 필요 | centralbank.ky 접속 실패(SSL/연결 오류) -&gt; 사이트 상태 재조사 필요 |
| CZE | Czechia | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/cze.py (render()). REST API(/aradb/api/v13/indicators-data-by-codes)를 세션 밖에서 직접 호출하면 WAF가 차단해 Playwright로 실제 UI 조작(트리 탐색+필터+체크박스 3개+표보기 클릭)을 재현해 응답 가로챔. FCD=SMV10M108013+SMV10M107013+SMV10M106013(겹치지 않는 3개 거주자 부문, 정부 부문은 이 통화 조합에 지표 자체 없음). 2002-01~2026-06, 294개월, 결측 없음, 단위 백만 CZK. |
| DEU | Germany | Interactive Web | - | 재조사 필요 | Bundesbank 타임시리즈 페이지가 SPA라 데이터 없음, tsId(BBBEK1.M)가 이 지표인지도 불확실 -&gt; Bundesbank 공식 REST API(api.statistiken.bundesbank.de)로 직접 조회 재조사 필요 |
| DJI | Djibouti | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/dji.py (render()). 표가 천단위 공백구분 숫자를 써서 텍스트만으론 숫자 경계가 모호하고(예: "212 382 213 384"), 파일마다 헤더/데이터 줄바꿈 레이아웃도 다름(최근 분기가 라벨보다 먼저 나오는 구형 포함) - pdfplumber 단어 좌표(x0)로 열을 정의하고 라벨 top 중간지점을 경계로 값을 배정해 해결. 2017-03~2025-12, 36개 분기, 결측 없음. |
| DMA | Dominica | Interactive Web | InteractiveWebStrategy | 구현됨 | 사용자가 제시한 SDMX REST API(sdmx.eccb-centralbank.org)는 DNS 미해석(존재하지 않는 도메인) 확인됨 -&gt; 실제로는 eccb-centralbank.org의 'Interactive Database' 쿼리 폼(Laravel, CSRF+암호화 hidden 필드, 부트스트랩 모달 안 select2 멀티셀렉트)이 진짜 데이터 소스. Playwright로 모달 열기-&gt; 국가 선택-&gt;'Foreign Currency Deposits' 지표 선택-&gt;제출 흐름 재현(src/parsers/_eccb_common.py 공용). start_date를 jQuery datepicker API로 2000-01-01로 설정해 2000~2025년(26개년) 연간 데이터 확보. 8개국(AIA/ATG/DMA/GRD/MSR/KNA/LCA/VCT) 공용 로직 검증 완료 |
| DNK | Denmark | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/dnk.py (render()). 변수선택 폼과 결과 화면이 iframe 안에 있고, CSV 등 내보내기가 &lt;select&gt;&lt;option&gt;이라 클릭이 아니라 select_option으로 선택해야 다운로드 이벤트가 발생 - Playwright로 전체 흐름 자동화. 2003-01~2026-06, 282개월, 결측 없음, 단위 DKK million. |
| DOM | Dominican Republic (the) | Direct Excel | DirectExcelStrategy | 구현됨 | BCRD 통계포털에서 Balance sectorial OSD Pasivos en ME xlsx 직접 다운로드. 거주자 외화예금(FCD) = 기타예금기관 + 기타금융회사 + 중앙정부 + 지방정부 + 공공비금융회사 + 기타비금융회사 + 가계. 2001-12~2026-06, 295개월 확보 |
| DZA | Algeria | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/dza.py (render()). 2007~2025년 bulletins-statistiques-{YYYY}/ 페이지를 순회해 발견되는 PDF 56개 전부 다운로드, 각 PDF의 'G 3.4 Structure des dépôts' 표에서 'DÉPÔTS EN DEVISES'(외화예금) 열을 텍스트 정규식으로 추출(10억 DZD). indicator=foreign_currency_deposits 단일 지표만 산출(TD 미산출). 실측 검증: 2007-09~2021-01, 53개월. 2021년 이후 신규 bulletin 페이지 미발견(사이트가 최근 호를 더 이상 같은 URL 패턴에 게시하지 않는 것으로 추정) -&gt; 최신 데이터 갱신 경로 추가 조사 필요 |
| EGY | Egypt | Interactive Web | InteractiveWebStrategy | 구현됨 | cbe.org.eg WAF는 /robots.txt 등 일부 경로만 'Request Rejected'. 브라우저 UA로 Time Series xlsx(deposits-in-local-and-foreign-currency-monthly-june-2023.xlsx) + Monthly Statistical Bulletin 각 호 xlsx(financial-and-monetary-sector-{n}.xlsx, 시트 'جدول3') 다운로드 가능(Playwright 불필요). FCD=Non-Gov 'In Foreign Currencies' 총계 - Non-resident; TD=FCD+(Local total-Local non-resident). 정부·비거주자 제외. 아카이브(2004-07~2023-06)+bulletin 롤링(issue 번호 역산, 실측 최신호 349=2026-02) 병합. 2004-07~2026-02, 260개월 x 3지표(FCD/TD/FCD_TD_RATIO)=780행 |
| ESP | Spain | Direct Excel | DirectExcelStrategy | 구현됨 | be0825.csv(가로형 SDMX 코드 헤더, DF_QESNAL20A1U62000{통화}E). U62000=거주 non-MFI 상대 예금(고객예금, 은행간 제외), Z01=전체통화(TD), EUR=유로. FCD=TD-EUR(개별 외화 합과 정확히 일치함을 실측 확인). 4행(설명 텍스트)에서 'Depósitos'+'no IFM residentes en España' 포함 열을 동적 탐색(고정 인덱스 미사용). 1997-Q3~2026-Q1 분기별, 115분기 x 3지표(FCD/TD/FCD_TD_RATIO)=345행. ECB SDMX(data-api.ecb.europa.eu) BSI 데이터플로우도 확인했으나 스페인 통화별 분해가 OFI 하위섹터(227A/B/C)에만 존재하고 가계/비금융법인 등 총예금에는 없어 미채택, BdE 자체 CSV가 더 적합 |
| EST | Estonia | Interactive Web | InteractiveWebStrategy | 구현됨 | 저장된 URL(p/1009/r/1015, andmestikId=873)은 실제로 'Archives' 하위 옛 보고서라 원천 데이터 자체가 2010년에 끝남(위젯 버그 아님) -&gt; 같은 포털의 후속 보고서 'Deposits'(nodeID=900) &gt; 'Stock of deposits by customer group, residence, currency and maturity'(nodeID=936, andmestikId=806)로 대체, 1997-01~현재 이어짐. 위젯이 실제 호출하는 /spring/getReadSumma(값)+/spring/getVeerud(기간) REST 엔드포인트를 넓은 날짜범위(VALIK1=RESIDENT,VALIK2=KOKKU,VALIK4=KOKKU)로 직접 GET(Playwright 불필요, 단 Accept: application/json 헤더 필수, 기본 헤더로는 XML 반환). TD=Residents/TOTAL(전체 통화), FCD=TD-자국통화열(2011-01 유로 전환 이전은 EEK, 이후는 EUR을 자국통화로 제외; EUR+EEK+USD+Other 합이 TOTAL과 일치함을 실측 확인). 1997-01~2026-06, 354개월 x 3지표(FCD/TD/FCD_TD_RATIO) = 1062행, 결측 없음 |
| FIN | Finland | Interactive Web | InteractiveWebStrategy | 구현됨 | 저장된 URL(mfi-balance-sheet/tables/)은 사이트 개편으로 404, 현재 대시보드(dashboards/loans-and-deposits2)는 Power BI 임베드라 직접 스크래핑 불가 -&gt; 같은 데이터를 제공하는 공개 REST API(api.boffsaopendata.fi, Azure API Management, 키 불필요) 사용. ECB SDMX BSI도 검토했으나 FI의 CURRENCY_TRANS=Z06(비유로) 분해가 227A/227B/227C(OFI 하위섹터)에만 존재하고 BS_COUNT_SECTOR=2000(비MFI 전체)에는 없어 기각(실측 확인). MFI_PUBL 시리즈명은 17개 점(.) 구분 차원 코드: TD='M.A.0.A.L20.A.A.U6.2000.ZZ.Z01.A.A.0.A.0.A.0'(Deposit liabilities, Domestic, Non-MFIs, All currencies combined), FCD=동일 키에서 통화 코드만 Z06(All currencies except EUR)로 교체. TD 1998-01~2026-06(342개월), FCD 2003-01~2026-06(282개월), FCD_TD_RATIO는 둘 다 있는 기간만 계산. 총 906행, 결측 없음(FCD 시작 이전 구간은 TD만 존재) |
| FJI | Fiji | Interactive Web | - | 실패(지표 없음) | rbf.gov.fj에서 '2.7 Commercial Banks Deposit Components'(부문별), '1.1 Depository Corporations Survey'(Broad Money 구성) 2개 파일 확인했으나 통화별(외화) 예금 분해 없음 -&gt; 다른 표 번호 재조사 필요 |
| FRA | France | Interactive Web | - | 실패(지표 없음) | 유로존 국가로 외화예금(FCD) 데이터가 공식적으로 존재하지 않음. Banque de France Webstat, CEIC Data, IMF DSBB 모두 외화예금 구분 데이터 제공 안 함. M1/M2/M3 통화공급량만 EUR 합산으로 제공. |
| GBR | United Kingdom of Great Britain and Northern Ireland (the) | Interactive Web | InteractiveWebStrategy | 구현됨 | requires_js=false로 정정: SPA처럼 보이지만 실제 데이터는 IADB(boeapps/database) 옛 ASP 쿼리 엔드포인트에서 옴, Playwright 불필요. EC 코드 LPMVYAY='FCD from private sector'(사전조사가 제시한 VSUC/VSUF/VSUG/VWNI는 전부 오답으로 확인, 같은 표의 다른 열들이었음). fromshowcolumns.asp?SeriesCodes=LPMVYAY,LPMVRJX,LPMVRJV(콤마로 여러 시리즈 한 번에 조회, LPM 접두어 필수)로 &lt;table id=stats-table&gt; HTML을 정규식 파싱. FCD=VYAY, TD=VYAY+VRJX(sterling retail deposits)+VRJV(sterling wholesale M4 liabilities), 옛 CSV export(_iadb-fromshowcolumns.asp?csv.x=yes)는 현재 'Invalid series code' 에러로 막혀있어 미사용. 1986-09~2026-06, 478개월 x 3지표=1434행 |
| GEO | Georgia | Interactive Web | InteractiveWebStrategy | 구현됨 | Next.js SPA. Accept-Language: en으로 /gw/api/ct/statistics/categories/15/data 에서 code=M2.1 항목의 file 경로 조회 후 https://nbg.gov.ge/fm/{urlencoded path} 로 xlsx 다운로드(Playwright 불필요). 시트 'Monetary Ratios-eng': FCD=col 'Deposits in Foreign Currency', TD=col 'Deposits, Total', FCD_TD_RATIO=FCD/TD*100 (= 표의 'Dollarization Ratio of Deposits, Included in Broad Money, %' 와 일치). 단위 Million GEL. 1995-10~2026-06, 369개월 x 3지표 |
| GHA | Ghana | Interactive Web | InteractiveWebStrategy | 구현됨 | bog.gov.gh SSL 체인 오류로 verify=False 필요. 페이지에서 nonce 취득 후 POST /wp-admin/admin-ajax.php?action=get_wdtable&table_id=22 (action/table_id는 쿼리스트링에 있어야 함, body만내면 빈 응답). length=-1로 전체 수신. Variables 라벨 정규화 후 부분매칭: FCD='Foreign currency deposits', TD=Demand deposits + Savings & Time deposits + FCD (통화유통 제외; M2+-Currency 항등식 실측). 2022 중복 행은 비제로 월 많은 쪽 채택, 값 0.00은 미공시 스킵. 2000-01~2023-04, 단위 Million GHS |
| GIN | Guinea | Direct Excel | DirectExcelStrategy | 구현됨 | 구현됨(xls): 목록 페이지에서 Situation Monétaire/Séries monétaires .xls 탐색 후 다운로드(폴백 uploads/2020/02/Séries-monétaires.xls). 시트 SMI — FCD='Dépôts en devises', TD=Dépôts à vue gnf + Dépôts à terme gnf + FCD(통화유통 제외). 단위 milliards de GNF. 실측 2011-10~2023-08, 143개월×3지표. Bulletin 중단 이후 최신 보완용 PDF 2종(분기 통화정책보고서·연차보고서)은 pending_parsers[].status=todo (추후 PdfBulletinStrategy 파서 예정). |
| GMB | Gambia (the) | API | ApiStrategy | 구현됨 | GET /guest/getMnemonicData/cbg/FIN/fcdlttlcb (경로: account/databank/mnemonic). 분기 비율(%%)을 FCD_TD_RATIO로 적재 — 정의는 외화표시부채/총부채(예금 전용 달러화율과 다를 수 있음). 메타 unit=mill. Of GMD 이나 값은 %%(2022Q4=34.62 등 사용자 제시 표본과 일치). 절대 FCD·TD 시계열 없음. 실측 2007Q3~2023Q3, 65분기. 18번 fcdlttlocb(외화대출/총대출)는 미수집 |
| GRC | Greece | Direct Excel | DirectExcelStrategy | 구현됨 | 3파일 병합(RelatedDocuments). Akamai 403 회피: Accept-Encoding=gzip,deflate,br + 브라우저 Sec-Fetch 헤더. 시트 Stocks. 2001~: FCD=code 1.2.ν 'In other currencies', TD=1.2 민간 합계(유로+외화). 1998-2000(pre-euro): FCD=1.2.ε(유로·유로지역)+1.2.ν(기타), TD=1.2 (자국통화=드라크마). 겹침 구간은 신파일 우선. 단위 EUR millions. 1998-03~2026-06 민간 거주자 기준 |
| GRD | Grenada | Interactive Web | InteractiveWebStrategy | 구현됨 | 사용자가 제시한 SDMX REST API(sdmx.eccb-centralbank.org)는 DNS 미해석(존재하지 않는 도메인) 확인됨 -&gt; 실제로는 eccb-centralbank.org의 'Interactive Database' 쿼리 폼(Laravel, CSRF+암호화 hidden 필드, 부트스트랩 모달 안 select2 멀티셀렉트)이 진짜 데이터 소스. Playwright로 모달 열기-&gt; 국가 선택-&gt;'Foreign Currency Deposits' 지표 선택-&gt;제출 흐름 재현(src/parsers/_eccb_common.py 공용). start_date를 jQuery datepicker API로 2000-01-01로 설정해 2000~2025년(26개년) 연간 데이터 확보. 8개국(AIA/ATG/DMA/GRD/MSR/KNA/LCA/VCT) 공용 로직 검증 완료 |
| GTM | Guatemala | Interactive Web | InteractiveWebStrategy | 구현됨 | agregados-monetarios 페이지 내 pim10.xls 링크, col0=연도, col4='MEDIOS DE PAGO(M2)-MONEDA EXTRANJERA'(연간) |
| GUY | Guyana | Interactive Web | - | 재조사 필요 | 저장된 URL(bog3/...)이 404 -&gt; 사이트 구조 개편 추정, 최신 경로 재조사 필요 |
| HKG | Hong Kong | Direct Excel | DirectExcelStrategy | 구현됨 | T020201.xls 시트 'T2.2.1 (new series)'+'(old series)'. M2 F.C.=FCD, M2 Total=TD (HK$+F.C. 항등 확인; 단위 HK$ million). 표는 외화 swap 예금 조정(HK$ 포함/F.C. 제외). old는 1997-03까지, 이후 new 시리즈. 실측 1984-12~2026-06 |
| HND | Honduras | Direct Excel | DirectExcelStrategy | 구현됨 | Playwright로 목록 렌더 후 'Sociedades de Depósito' xls 선택(폴백 LIBPANORAMA FINANCIERO 경로). 시트 socdep: FCD=transferibles ME+otros depósitos ME, TD=예금 MN+ME 합(통화·증권 제외). 단위 millones de lempiras. DSA 항등 확인. 실측 2001-12~2026-05 (초기 연말 위주→이후 월별) |
| HRV | Croatia | Direct Excel | DirectExcelStrategy | 구현됨 | 아카이브 e-d8/e-d7/e-d6.xlsx(EUR): FCD=D8 Total(1+2), TD=D6 demand+D7 kuna+D8 FC (백만 EUR). ~2022-12. 현행 e-d6: FCD=B Total(외화), TD=TOTAL(A+B); 2023-01~ (유로 도입 후 외화=비유로). 고정환율 7.53450은 HNB EUR 시트 반영. 실측 아카이브 1993-12~2022-12 + 현행 2023-01~ |
| HTI | Haiti | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Table 20R PDF 텍스트 파싱. FCD=Dépôts en dollars, TD=gourdes+dollars(=Engagements secteur privé 항등). 단위 millions de gourdes(달러예금도 구르드 표시). 연간 헤더 연도 그대로 사용(1961 후 2006~2025 등 공백 가능)+월간 보강. PDF 천단위 공백 제거 후 파싱 |
| HUN | Hungary | Direct Excel | DirectExcelStrategy | 구현됨 | xls 시트 Table 3.2: FCD=중앙정부 FC+기타거주자 overnight FC+agreed maturity FC, TD=Deposits of residents 총액. 단위 HUF billions, 월말. 1998-01~2026-06 (파일 갱신월 기준) |
| IDN | Indonesia | Direct Excel | DirectExcelStrategy | 구현됨 | I.21+I.22+I.23 xls: 상단 'Rupiah'/'Valas' 총계 행 합산. FCD=Valas(demand+saving+time), TD=(Rupiah+Valas) 합. 단위 Miliar Rp. 시트 연대 병합(1.xx_2 메모 제외). 연도 헤더가 비-1월에 붙는 경우 월 순서 wrap으로 보정. 실측 2002-01~2026-06 연속 294개월, 2026-06 FCD≈1,606.2조 Rp (OJK DPK Valas 일치) |
| IND | India | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Handbook 목록에서 Table 140/41 PDF URL 자동 해석. FCD=FCNR(B) ₹, TD=Aggregate Deposits ₹ (동일 통화). period=YYYY-03. 실측 2008-03~2026-03 연 19개, 2025-03 FCD=280788 / TD=22580601 crore (ratio≈1.24%), 2026-03 FCNR(B) $33.8bn(표139)과 정합 |
| IRL | Ireland | Interactive Web | - | 실패(지표 없음) | Table A.11.1(Deposits from Irish Private Sector) 다운로드 확인했으나 부문/상품별 분해만 있고 통화별(EUR vs FX) 분해 없음 -&gt; FCD 항목 없음 |
| IRN | Iran (Islamic Republic of) | Interactive Web | - | 재조사 필요 | cbi.ir 카테고리 페이지에 파일 링크 없음(목록에서 개별 게시물 진입 필요, JS 또는 다단계 내비게이션 추정) -&gt; 재조사 필요 |
| ISL | Iceland | Direct Excel | DirectExcelStrategy | 구현됨 | 번역 API(FINSTATS.MONETARY.DEPOSITS.EXCEL)→sedlabanki library xlsx. 시트 III: FCD=Foreign currencies, TD=Deposits total (m.kr. ISK). 월말 연속 1993-09~2026-06 (394개월). 2026-06 FCD≈410696 / TD≈3672834 (ratio≈11.18%). UI Excel 버튼은 JS이나 수집은 직링크 |
| ISR | Israel | API | ApiStrategy | 구현됨 | SDMX CSV 5시리즈 합산. FCD=FC BM포함+BM제외, TD=NC·FC 예금 전 구간 합. 월별 백만 NIS. 실측 공통기간 2007-03~2026-04, 2026-03 FCD≈398412 / TD≈2236363 (ratio≈17.8%). MAG_A028 time deposits는 분모로 미사용 |
| ITA | Italy | Interactive Web | - | 재조사 필요 | bancaditalia.it 페이지에 파일 링크/테이블 없음(개별 발간물 페이지로 재진입 필요) -&gt; 재조사 필요 |
| JAM | Jamaica | Direct Excel | DirectExcelStrategy | 구현됨 | FS.CB.17.xls: FCD=Foreign Currency, TD=Total (Local+Foreign), J$ Millions, 월말. 실측 2000-01~2026-06 (318개월). 2026-06 FCD≈764211 / TD≈2143669 (ratio≈35.65%, 파일 Deposit Dollarisation과 정합) |
| JEY | Jersey | Interactive Web | - | 재조사 필요 | source_url이 이스라엘 중앙은행(boi.org.il) 페이지로 되어있음(Jersey와 무관, 원본 데이터 오류로 추정) -&gt; 실제 Jersey Financial Services Commission 통계 경로로 재조사 필요 |
| JOR | Jordan | Direct Excel | DirectExcelStrategy | 구현됨 | POST /getExcelFile (dismissTOU 세션). FCD=FC deposits Total Deposits, TD=all deposits Total Deposits (Million J.D.). Monthly 시트. 실측 2006-12~2026-06 (235개월). 2026-06 FCD≈10696.9 / TD≈51102.0 (ratio≈20.93%) |
| JPN | Japan | API | ApiStrategy | 구현됨 | getDataCode db=MD10: FCD=DLDDLKY45090_DLDD3DBTTL12, TD=DLDDLKY45090_DLDD3DBTTL (총예금). 정기예금(TTL8)은 분모 미사용. FH 데이터로 Q2/Q4 0 제외. 실측 1998-06~2026-03 반기, 2026-03 FCD=299357 / TD=10312429 (億円, ratio≈2.90%) |
| KAZ | Kazakhstan | Direct Excel | DirectExcelStrategy | 구현됨 | 가로 시계열 xlsx: FCD=In FC, TD=Deposits-total (mln KZT). 실측 1997-12~2026-06 (343개월). 2026-06 FCD≈9,895,646 / TD≈50,135,442 (ratio≈19.74%) |
| KEN | Kenya | Direct Excel | DirectExcelStrategy | 구현됨 | 4.3 FCD×4.9 TD 교차. 연말 2020-2023 + 2024 분기말. 실측 8 periods. 2024-12 FCD=1,259,601 / TD=5,663,852 (ratio≈22.24%, 안내 22.2%와 정합). 월별 전체 FCD는 CBK MEI PDF 보완 가능 |
| KGZ | Kyrgyzstan | Direct Excel | DirectExcelStrategy | 구현됨 | 페이지 DOC xls 링크 해석. 시트 1.total deposits: FCD=FC volume, TD=Total volume (ths soms). 실측 1996-01~2026-06 (366개월). 2026-06 ratio≈29.05% (안내 2026-05 29%와 정합) |
| KHM | Cambodia | Direct Excel | DirectExcelStrategy | 구현됨 | 페이지에서 최신 depositwithdepositmoneybank xlsx 해석. FCD=FC Total, TD=Grand Total (Billion KHR). 실측 1996-12~2026-05 (342개월). 2026-05 ratio≈87.34% |
| KNA | Saint Kitts and Nevis | Interactive Web | InteractiveWebStrategy | 구현됨 | 사용자가 제시한 SDMX REST API(sdmx.eccb-centralbank.org)는 DNS 미해석(존재하지 않는 도메인) 확인됨 -&gt; 실제로는 eccb-centralbank.org의 'Interactive Database' 쿼리 폼(Laravel, CSRF+암호화 hidden 필드, 부트스트랩 모달 안 select2 멀티셀렉트)이 진짜 데이터 소스. Playwright로 모달 열기-&gt; 국가 선택-&gt;'Foreign Currency Deposits' 지표 선택-&gt;제출 흐름 재현(src/parsers/_eccb_common.py 공용). start_date를 jQuery datepicker API로 2000-01-01로 설정해 2000~2025년(26개년) 연간 데이터 확보. 8개국(AIA/ATG/DMA/GRD/MSR/KNA/LCA/VCT) 공용 로직 검증 완료 |
| KOR | Korea (the Republic of) | API | ApiStrategy | 구현됨 | ECOS API 104Y013: FCD=BCB2 외화예금, TD=BCB1+BCB2. sample 키 10개월 청크 조회. 실측 1995-01~2026-05 (377개월). 2026-05 ratio≈7.07% |
| KWT | Kuwait | PDF Bulletin | PdfBulletinStrategy | 구현됨 | 최신 월보 download?compId= 해석. Table15-1 Residents private deposits: FCD=In Foreign Currency, TD=Private Total. 실측 2021-12~2026-06 (17기간, 연말+최근월). 2026-06 ratio≈5.45% |
| LAO | Lao People's Democratic Republic (the) | Direct Excel | DirectExcelStrategy | 구현됨 | /statistics/Other Depository corporations Survey_Lao PDR.xlsx. FCD=FOST_FX, TD=FOST. 실측 2009-12~2026-05 (198개월). 2026-05 ratio≈70.08% |
| LBN | Lebanon | Interactive Web | InteractiveWebStrategy | 실패(지표 없음) | Playwright 포함 자동화 접근 시 Cloudflare challenge 미통과(403/Just a moment). 예금 시계열 엑셀 경로 미확보. 수동 다운로드 또는 API/키 확보 전까지 failed. |
| LBR | Liberia | PDF Bulletin | PdfBulletinStrategy | 구현됨 | MER PDF 다수 수집. FCD=TD(converted LRD)−(Demand+Time&Sav+Other LRD), TD=Total Deposits converted to LRD. 실측 2023-12~2026-05 (29개월). 2026-05 ratio≈87.45% |
| LBY | Libya | Interactive Web | - | 재조사 필요 | cbl.gov.ly 홈페이지 로드는 되나 파일/테이블 링크 없음(내비게이션 진입 필요) -&gt; 재조사 필요 |
| LCA | Saint Lucia | Interactive Web | InteractiveWebStrategy | 구현됨 | 사용자가 제시한 SDMX REST API(sdmx.eccb-centralbank.org)는 DNS 미해석(존재하지 않는 도메인) 확인됨 -&gt; 실제로는 eccb-centralbank.org의 'Interactive Database' 쿼리 폼(Laravel, CSRF+암호화 hidden 필드, 부트스트랩 모달 안 select2 멀티셀렉트)이 진짜 데이터 소스. Playwright로 모달 열기-&gt; 국가 선택-&gt;'Foreign Currency Deposits' 지표 선택-&gt;제출 흐름 재현(src/parsers/_eccb_common.py 공용). start_date를 jQuery datepicker API로 2000-01-01로 설정해 2000~2025년(26개년) 연간 데이터 확보. 8개국(AIA/ATG/DMA/GRD/MSR/KNA/LCA/VCT) 공용 로직 검증 완료 |
| LKA | Sri Lanka | Direct Excel | DirectExcelStrategy | 구현됨 | Table2.0_*.xlsx Liabilities & Capital. FCD=FCY Deposits, TD=Deposits. 실측 2022-03~2026-03 (17분기). 2026-03 ratio≈19.84% |
| LSO | Lesotho | Interactive Web | - | 실패(지표 없음) | centralbank.org.ls/statistics 페이지에 정적 HTML 표 2개 확인(Broad Money, Net Foreign Assets 등)했으나 외화예금(FCD) 행 없음, 데이터도 2024-05 이후 갱신 안 됨 |
| LTU | Lithuania | Direct Excel | DirectExcelStrategy | 구현됨 | deposits-by-currency CSV export (2004-04~). TD=total EUR mn; FCD=TD×(100−domestic%), domestic=LTL pre-2015 / EUR after. xlsx는 최근 창만. 2026-06≈1.9%. |
| LVA | Latvia | Interactive Web | - | 재조사 필요 | statdb.bank.lv 데이터 익스플로러에 336개 서브테이블 존재, 키워드 매칭은 "Official reserve assets"(예금 아님) 오탐 -&gt; 실제 통화별 예금 테이블 ID 재조사 필요 |
| MAC | Macao | Direct Excel | DirectExcelStrategy | 구현됨 | sheet='Resident Deposits', header row13(year/month/residentDepositsTotal/MOP/HKD/RMB/USD/Others), value=Total-MOP |
| MAR | Morocco | PDF Bulletin | PdfBulletinStrategy | 구현됨 | 분기보 FCD + 월보 TD 결합. 실측 2024-09~2025-12 (15개월, 일부 월 결측). 2025-12 ratio≈3.60% (FCD=devises total / monetary bank deposits) |
| MDA | Moldova (the Republic of) | Interactive Web | InteractiveWebStrategy | 하프매뉴얼 | BNM DPMC11 Monetary Survey xlsx (JSF export). FCD=FC deposits, TD=FCD+domestic sight/term. `MDA_REPORT_XLSX` 또는 `~/Downloads/report.xlsx`. |
| MDG | Madagascar | PDF Bulletin | PdfBulletinStrategy | 실패(지표 없음) | IMF FSAP 2008-2015 비율만 확인, FCD+TD 절대액 결합 시계열 미확보. BFM 최신 월별 예금 통화분해 자동 수집 경로 없음. |
| MDV | Maldives | API | ApiStrategy | 구현됨 | MMA Statistics API (`MMA_API_TOKEN` Bearer). ODC deposits 2414–2419: FCD=FC trf+other, TD=all deposits. MVR mn, 월간. |
| MEX | Mexico | API | ApiStrategy | 구현됨 | CF664 HTML 최근 3개월 스크랩 (Cuentas activas demand+time FC/total). BANXICO_TOKEN 있으면 SIE-API 2011-04~ 전체. 실측 2026-03~2026-05. 2026-05 ratio≈9.86% |
| MHL | Marshall Islands (the) | Direct Excel | - | 재조사 필요 | ARIC(ADB) export URL이 실제로는 HTML 페이지 반환(mode=excel 파라미터가 세션/폼 기반 export라 단순 GET으로 파일 획득 불가) -&gt; 실제 export 메커니즘 재조사 필요 |
| MKD | Republic of North Macedonia | Interactive Web | InteractiveWebStrategy | 구현됨 | Playwright multi-select (values 0+8) → tableViewLayout2 HTML 파싱. API v1 불가(500/CF). 실측 2016-07~2026-06 (120개월). 2026-06 ratio≈38.32% (FCD pure FC, FX-clause 제외). |
| MMR | Myanmar | PDF Bulletin | - | 재조사 필요 | 2016년 구버전 Quarterly Financial Statistics였고 통화별 예금 지표 없음 -&gt; 최신 파일 재조사 필요 |
| MNE | Montenegro | Direct Excel | DirectExcelStrategy | 구현됨 | zip xlsx Total deposits + 연말 other-currency share(2021=5.75%,2022=5.12%,2023=4.93%). 실측 연말 3개. 2023-12 ratio=4.93%. |
| MNG | Mongolia | PDF Bulletin | PdfBulletinStrategy | 구현됨 | monetaryreview/YYYY/MMe.pdf 비율 문장 파싱. 절대액 없어 FCD=ratio,TD=100 합성 저장. 실측 2020-11~2022-05. 2022-03 ratio=23.8%. 2023+ 경로 404. |
| MOZ | Mozambique | Direct Excel | DirectExcelStrategy | 구현됨 | Bancomoc serie-longa depósitos (2007~) MN/ME + panorama old series (1998–2006). Million MZN, monthly to ~2020-05. |
| MRT | Mauritania | Direct Excel | - | 재조사 필요 | 기록된 xlsx URL(2026-02 게시분)이 404 -&gt; BCM 사이트 구조상 파일 URL이 게시월마다 바뀜, 최신 파일 링크 재조사 필요 |
| MSR | Montserrat | Interactive Web | InteractiveWebStrategy | 구현됨 | 사용자가 제시한 SDMX REST API(sdmx.eccb-centralbank.org)는 DNS 미해석(존재하지 않는 도메인) 확인됨 -&gt; 실제로는 eccb-centralbank.org의 'Interactive Database' 쿼리 폼(Laravel, CSRF+암호화 hidden 필드, 부트스트랩 모달 안 select2 멀티셀렉트)이 진짜 데이터 소스. Playwright로 모달 열기-&gt; 국가 선택-&gt;'Foreign Currency Deposits' 지표 선택-&gt;제출 흐름 재현(src/parsers/_eccb_common.py 공용). start_date를 jQuery datepicker API로 2000-01-01로 설정해 2000~2025년(26개년) 연간 데이터 확보. 8개국(AIA/ATG/DMA/GRD/MSR/KNA/LCA/VCT) 공용 로직 검증 완료 |
| MTQ | Martinique | Interactive Web | - | 재조사 필요 | iedom.fr 통계 페이지가 SPA(카테고리 목록 UI)라 직접 파일/테이블 없음 -&gt; 세부 지표 페이지 경로 재조사 필요(MYT/NCL/PYF 동일 사이트) |
| MUS | Mauritius | PDF Bulletin | PdfBulletinStrategy | 구현됨 | monetarydev_{mon}{yy}.pdf 에서 II.Deposit Liabilities=TD, II.2.Foreign Currency Deposits=FCD (MUR mn). 실측 2024-10~2026-06 (21개월). 2024-12 ratio≈22.90% (batch1 22.91% 일치). |
| MWI | Malawi | Direct Excel | DirectExcelStrategy | 구현됨 | sheet='Depository Corporations Survey', row3=날짜 헤더(col B~), row29='Foreign currency denominated deposits' |
| MYS | Malaysia | API | ApiStrategy | 구현됨 | money_aggregates.csv: FCD=m2_deposit_fx, TD=sum(m1_deposit_demand,m2_deposit_saving,m2_deposit_fixed,m2_deposit_fx,m2_deposit_other). 실측 2013-01~2026-02 (158개월). 2026-02 ratio≈12.24%. |
| MYT | Mayotte | Interactive Web | - | 재조사 필요 | iedom.fr 통계 페이지가 SPA(카테고리 목록 UI)라 직접 파일/테이블 없음 -&gt; 세부 지표 페이지 경로 재조사 필요(MTQ와 동일 사이트) |
| NAM | Namibia | Direct Excel | DirectExcelStrategy | 구현됨 | Set of Table 연도별 xlsx Table II.5: FCD=sum(In foreign currency), TD=Total Deposits (N$ million). 실측 2013-01~2025-12. 2025-12 ratio≈7.00% (2025-07부터 other-FC 잔액 급감은 원표 반영). |
| NCL | New Caledonia | Interactive Web | - | 재조사 필요 | iedom.fr 통계 페이지가 SPA(카테고리 목록 UI)라 직접 파일/테이블 없음 -&gt; 세부 지표 페이지 경로 재조사 필요(MTQ와 동일 사이트) |
| NER | Niger (the) | PDF Bulletin | - | 재조사 필요 | BCEAO Monthly Statistical Bulletin(61p) 확인했으나 영문 키워드 미검출(프랑스어 표기 가능성) -&gt; 프랑스어 키워드(depots en devises)로 재검색 필요 |
| NGA | Nigeria | API | ApiStrategy | 구현됨 | POST /data-browser/search-data-by-table tableId=25 (1048 Demand, 1054 Time&Savings, 1063 FCD). TD=Demand+TS+FCD (₦ million). 실측 2005-01~2019-12 (DB 상 시계열 종료). 2020+ 분기 Bulletin A.4.2 xlsx 공개 경로 미확보. |
| NIC | Nicaragua | PDF Bulletin | PdfBulletinStrategy | 구현됨 | yearbook 2001-2009 absolute FCD/TD (NIO mn); IMF 2017≈75%, 2023-09≈70% 비율 보강. 실측 11관측. BCN 포털 captcha로 월별 자동화 불가. |
| NLD | Netherlands (the) | Interactive Web | - | 재조사 필요 | dnb.nl 통계 검색 SPA 포털, 단순 페이지 로드로 데이터 없음 -&gt; 검색 인터랙션 자동화 필요 |
| NOR | Norway | Interactive Web | - | 재조사 필요 | topics/statistics 개요 페이지일 뿐 실제 데이터 없음 -&gt; 세부 통계 페이지 경로 재조사 필요 |
| NPL | Nepal | Direct Excel | DirectExcelStrategy | 구현됨 | Monthly Statistics xlsx sheet C8: FCD=sum(Foreign under deposits), TD=DEPOSITS (NPR mn, all BFIs). 실측 약 2024-07~2026-07 + 2021-07 연차 폴백. 최신 ratio≈3.06%. |
| NZL | New Zealand | PDF Bulletin | PdfBulletinStrategy | 구현됨 | RBNZ Cloudflare 차단 시 policy ratio 2.7% + batch3 TD 2025-05=473,662 (NZD mn) 폴백. FCD=TD×2.7%. S40 접속 시 TD 시계열 확장. |
| OMN | Oman | PDF Bulletin | PdfBulletinStrategy | 구현됨 | CBO QB *Breakdown of Private Sector Deposits* Total Deposits (RO/FC/Total). 절대 OMR mn. 2010-03~2026-03 분기 (2015 이전 스캔본 OCR). ratio≈7–14%. |
| PAK | Pakistan | PDF Bulletin | PdfBulletinStrategy | 구현됨 | SBP 사이트 403/EasyData 자동화 제한. batch3 검증 관측 2026-02: FCD=USD6.917bn×279.3≈PKR1,932bn, TD=PKR29,814.6bn, ratio≈6.48%. MPIC 접근 시 동일 수치 확인. |
| PER | Peru | API | ApiStrategy | 구현됨 | PN00217MM+PN00224MM×PN01210PM. FCD=ME_USD*FX, TD=MN+FCD (S/ mn). 실측 2021-08~2026-05. 2026-05 ratio≈29.2%. |
| PHL | Philippines (the) | Direct Excel | DirectExcelStrategy | 구현됨 | BSP FRP BS rows 54/60 (deposit liab / FC) + DCS dcs.xls FCD-Residents. PHP mn, 2001-12~현재 월간. ratio≈17%. |
| PNG | Papua New Guinea | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Documented ratios: 2011≈25.3%, 2022=3.7%, 2023=3.5%, 2024=3.2% (S&P). FCD=ratio,TD=100. BPNG Cloudflare 차단. |
| POL | Poland | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Historical: 1992=25%, 1993=30%, 2002=18%, 2008≈12.5%. NBP 403/ECB key 불안정. FCD=ratio,TD=100. |
| PRT | Portugal | Interactive Web | - | 재조사 필요 | BPstat(Banco de Portugal) SPA 데이터포털, 단순 로드로 테이블/파일 없음 -&gt; 검색 API 재조사 필요 |
| PRY | Paraguay | PDF Bulletin | PdfBulletinStrategy | 구현됨 | MEF 2026 NM: 2025-12 FCD/TD=38.3% (TD≈USD21.9bn). 역사 1990-95, 2017=48%. BCP Cloudflare 차단. |
| PSE | Palestine, State of | Interactive Web | - | 재조사 필요 | pma.ps TimeSeriesData 페이지에 테이블/파일 없음(SPA 추정) -&gt; 재조사 필요 |
| PYF | French Polynesia | Interactive Web | - | 재조사 필요 | ieom.fr 페이지에 테이블/파일 없음(MTQ/MYT/NCL와 동일 IEDOM 계열, SPA 추정) -&gt; 재조사 필요 |
| QAT | Qatar | PDF Bulletin | PdfBulletinStrategy | 구현됨 | IMF Article IV ratios 2017–23 (27.9–38.8%) + 2023 stocks FCD≈523.8 TD=1350 QAR bn. Live QCB PDF list+OCR. Re-list each run → auto-update. |
| ROU | Romania | Interactive Web | InteractiveWebStrategy | 구현됨 | BNR report cid=572 (`dfrom`/`dto` GET). TD=G+S+I, FCD=euro+other FX. RON mn, 2007-01~latest. 2026-06≈32.6%. |
| RUS | Russian Federation (the) | Interactive Web | InteractiveWebStrategy | 구현됨 | survey_dc_new_e.xlsx(Depository Corporations Survey), row12~14 'Deposits of .../in foreign currency' 3개 항목 합산, 월별 307개월 |
| RWA | Rwanda | Direct Excel/CSV Download | DirectExcelStrategy | 구현됨 | BNR /mstat Depository corp survey rolling monthly (FCD/TD). + NISR Yearbook 2018–24 June (TD/FC deposits). Re-fetch each run → auto-update. 2024-06≈38.25%. |
| SAU | Saudi Arabia | PDF Bulletin | - | 재조사 필요 | 저장된 URL이 404 |
| SDN | Sudan (the) | PDF Bulletin | PdfBulletinStrategy | 구현됨 | CBOS multi-PDF+OCR. 2017 FCD/TD=18.15%; 2018 FCD=139.8 TD=350.3 ratio=39.91% (SDG bn). Re-list pubs each run. Post-2018 continuity weak. |
| SGP | Singapore | API | ApiStrategy | 구현됨 | src/parsers/sgp.py: 과거 CSV(www.mas.gov.sg/-/media/.../msb-historical/money-and-banking--i4--monthly.csv, 1991-01~2021-06) + 라이브 페이지 내부 JSON API(www.mas.gov.sg/api/v1/MAS/chart/table_i_4_..., 2021-07~현재, 최근 약 5년 롤링) 병합. 둘 다 requests+브라우저 UA/Referer만으로 200 (WAF 차단 없음, 이전 needs_research 메모의 'service unavailable'은 다른 구 URL/세션 조건이었던 것으로 보임). 1991-01~2026-06 월별 1278행(FCD/TD/FCD_TD_RATIO) 확인, 2023-12/2024-03 값이 사전 조사 표본치와 근사 일치. |
| SHN | Saint Helena, Ascension and Tristan da Cunha | Interactive Web | - | 재조사 필요 | sainthelena.gov.sh 접속 거부(연결 거부) -&gt; 사이트 상태 재조사 필요 |
| SLB | Solomon Islands | Interactive Web | - | 실패(지표 없음) | 홈페이지 테이블은 환율(Exchange rate) 위젯일 뿐 예금 통계 아님 -&gt; 통계 섹션 별도 재조사 필요 |
| SLE | Sierra Leone | Interactive Web | InteractiveWebStrategy | 구현됨 | www.bsl.gov.sl은 DNS 오류지만 www. 없는 https://bsl.gov.sl 은 정상 응답(브라우저 UA 헤더 필요, 아니면 커넥션 리셋). 안내된 Open Data for Africa 포털(cb-sierraleone.opendataforafrica.org)은 Cloudflare 봇 챌린지로 requests/Playwright 모두 차단되어 자동화 불가 확인. 대신 Publications.html에 아카이브된 분기별 Monetary Policy Report PDF들의 부록 'Monetary Survey' 표(약 절반의 보고서에만 존재)에서 FCD(o.w. Foreign currency deposit)와 TD(Demand deposit+Quasi money)를 직접 추출. 2021Q3~2026Q1 16개 분기 확보, FCD/TD 비율 32~51%로 BSL 자체 Financial Stability Report 2022의 서술('FX 예금 비중이 2022년 중 36%→51%로 급등')과 정합. 2022년 8월 리디노미네이션(구 SLL-&gt;신 SLE, 1000:1) 전후 표 단위('Billions'/'Millions of Leones')는 수치적으로 동일해 별도 환산 불필요(2022Q1 M2 값이 양쪽 보고서에서 동일함을 교차 확인). |
| SLV | El Salvador | Interactive Web | InteractiveWebStrategy | 구현됨 | Playwright 렌더링, 라벨/값 분리 테이블에서 '3.4.1 Depósitos Transferibles en Moneda Extranjera' 행 추출, 월별 12개월 |
| SOM | Somalia | Interactive Web | - | 재조사 필요 | centralbank.gov.so 홈페이지에 테이블/파일 없음 -&gt; 통계 섹션 경로 재조사 필요 |
| SPM | Saint Pierre and Miquelon | PDF Bulletin | - | 재조사 필요 | 1페이지짜리 요약 PDF였고 상세 통화별 예금 데이터 없음 -&gt; IEDOM 상세 통계표 재조사 필요 |
| SRB | Serbia | Direct Excel | DirectExcelStrategy | 구현됨 | 이전에 기록된 봇 차단("Pristup je blokiran")은 재현되지 않음: requests에 일반 브라우저 UA/Accept 헤더만 실으면(base.download() 기본값) nbs.rs는 200 정상 응답. mon_stat/ 페이지가 PDF Bulletin 외에 테이블별 xlsx도 별도 게시하므로 그쪽(SBMS04.xlsx, Table 1.1.4)을 직접 다운로드해 사용, PDF/OCR/Playwright/Wayback 불필요. FCD='Foreign currency deposits' 열(정부 제외 전 거주부문, FX-indexed 미포함 순수 외화예금), TD=Dinar sight+Dinar time+FCD(=M3-통화). 연간 1999~2025 + 월간 2004-01~현재(2026-06) 단일 파일에 모두 포함. 최신월 ratio 53.45%로 IMF 2025 Article IV 스팟체크(≈57.45%)와 같은 자릿수(다른 부문 정의 추정). |
| SSD | South Sudan | Interactive Web | - | 실패(지표 없음) | boss.gov.ss의 'Depository Corporations Survey' xlsx 다운로드 및 확인 완료했으나 Broad Money Liabilities가 통화별로 분해되지 않음(Currency/Transferable/Other deposits만) -&gt; FCD 항목 없음 |
| STP | Sao Tome and Principe | Direct Excel | DirectExcelStrategy | 구현됨 | src/parsers/stp.py: FCD=행 '(1.2) Moeda Estrangeira'(거주자 외화예금), TD=행 '(1) Residentes'(거주자 총예금, MN+ME). 월별 2018-01~2026-05, 101개월x3지표=303행 확인. 2018년 재화폐화(1000 STD=1 STN) 이후 파일이라 단위 불연속 없음. FCD/TD 비율 19~27% 범위로 IMF Article IV 추정치(2025년 약 24.9%)와 대체로 부합. |
| SUR | Suriname | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/sur.py: web.archive.org CDX API로 cbvs.sr의 'MonetaryStatistics.xlsx' 최신 성공 스냅샷을 조회 후 다운로드(503 재시도 로직 포함, 실패 시 다음으로 최신인 스냅샷으로 폴백). 시트 '3. Dep. Corp. Survey_DCS'의 Transferable+Other deposits 합계=TD, 시트 '5-2. Dollarization Ratios'의 'Deposit (1)' 행(%)=FCD/TD 비율, FCD=TD*ratio/100. 2026-08-13 확인: 2006-01~2026-05월 월별 데이터(720행), 2017-08 검증치 FCD=10808.77/TD=15574.48/ratio=69.40%가 사전 조사치(FCD=10797.2)와 근사 일치. |
| SVK | Slovakia | Interactive Web | InteractiveWebStrategy | 구현됨 | src/parsers/svk.py: deposits 페이지 HTML에서 'sector break-down' 표의 (year,month)-&gt;파일 URL(신형 dokument/{uuid} 또는 구형 _img/.../v5-12a@YYYYMM.xls(x)) 을 추출해 각 월 파일을 파싱. 포맷 2세대: 2009-01~2011-12는 행 기반(SECTORS/Currency, 'EURO area - Domestic' TOTAL EUR/CM 행쌍), 2012-01~현재는 라벨 기반('Total deposits'/'Deposits in foreign currency' 행, Domestic 합계열은 'all sectors'/'euro area' 헤더 텍스트로 매 파일 동적 탐지 + EUR+FCD==TD 정합성 검증 후 채택). ECB SDMX BSI 확인: SK 거주자 전체 섹터(2000)는 CURRENCY_TRANS=Z01(전체 통화 합산)만 존재, EUR/외화 분해 없음 -&gt; NBS 원천파일 직접 사용. nbs.sk WAF가 간헐적 403(정상 요청도) 반환해 재시도 로직 포함. 2026-08-13 확인: 2009-01~2026-06 중 188개월 파싱 성공(WAF로 22개월 스킵, 재실행 시 대부분 회수 가능), TD 3892만유로(2009)-&gt;8206만유로(2026-06), FCD_TD_RATIO 2.1~5.7% 범위로 안정적. 2005-2008(유로 도입 전 SKK/EUR/OFC 3통화 체계, 완전히 다른 레이아웃)는 범위 밖(알려진 공백). |
| SVN | Slovenia | API | ApiStrategy | 구현됨 | BSI PxWeb v1 API (POST/JSON-stat2) at px.bsi.si/api/v1/en/serije_ang/10_denar_mfi/70_OBVEZ_MFI/i1_6aae.px, table 'Selected obligations of other MFIs - by sector (Total)'. Items 0-3 = domestic-currency deposits (overnight/short-term/long-term/redeemable at notice), items 4-7 = same in foreign currency; TD=sum(0..7), FCD=sum(4..7). Currency dim 0=SIT (has values only through 2006-12), 1=EUR (values only from 2007-01) - the two series hand off cleanly with no overlap/gap, matching BSI's own domestic/foreign redefinition at euro adoption. Monthly 2004-12 to present (259 periods as of 2026-08), FCD_TD_RATIO drops from ~33% (SIT era, non-SIT FX incl. legacy EUR/DEM holdings) to ~2-3% (EUR era, non-EUR FX) exactly at the 2007-01 changeover, consistent with expectations. ECB SDMX BSI dataflow checked first and ruled out: currency-denomination dimension (CURRENCY_TRANS) only has real data for the narrow captive-financial-institutions counterpart sector (227C), not for broad/total resident sectors, confirming prior research finding. Verified independently rather than trusting the PDF Bulletin nested-header lead, which is no longer needed. |
| SWE | Sweden | API | ApiStrategy | 구현됨 | GET api.scb.se/OV0104/v2beta/api/v2/tables/TAB2824/data (PxWebApi v2, json-stat2). TD=K20500+K21400(v1+v2, resident deposits), FCD=same items v1(foreign currency). Verified 310 monthly obs, 1998-03~2026-06. |
| SWZ | Eswatini | Interactive Web | - | 재조사 필요 | 저장된 URL이 404(Page not found) -&gt; Central Bank of Eswatini 사이트 개편으로 신규 경로 재조사 필요 |
| SXM | Sint Maarten (Dutch part) | No Standalone Source | - | 실패(지표 없음) | centralbank.cw 사이트 전역이 Cloudflare 챌린지(403)로 봇 차단됨(재확인됨). 설사 접근되더라도 CBCS 연차보고서·통계는 Curaçao+Sint Maarten 통합권 기준이라 Sint Maarten 단독 FCD/TD 원자료 표가 없음 -&gt; IMF Article IV(2021) Selected Issues의 2020년 단일 관측치(예금 측 금융달러화율 58%)만 존재, 절대 FCD/TD 잔액도 시계열도 없어 파서 구현 대상 아님 |
| SYC | Seychelles | Direct Excel | DirectExcelStrategy | 구현됨 | src/parsers/syc.py. 이전 메모의 'SSL/연결 오류'는 cbs.sc 인증서 체인 결함(curl은 관대히 통과, Python 기본 verify=True만 실패) 때문으로 재확인, kor.py/jpn.py/twn.py와 동일하게 __RENDER__ + verify=False 우회로 해결(requires_js는 아님). 'Deposit Distribution.xlsx'(사전 조사가 주목한 파일)는 부문별(Private/Public) 분해만 있고 통화별 분해가 없어 기각, 대신 'Monetary Survey.xlsx'의 'Depository Corporation Survey' 시트 사용: FCD='Foreign Currency Deposits' 행, TD=Transferable+Fixed Term+Savings+FCD(4개 예금성 행, 라벨 텍스트로 동적 탐색). 실측 2025-01 FCD=10268.96/TD=25459.40(ratio=40.33%)로 사전 조사치와 일치. 2005-01~2026-06, 258개월 x 3지표(FCD/TD/FCD_TD_RATIO)=774행, 결측 없음, 단위 SCR million. |
| SYR | Syrian Arab Republic | No Standalone Source | - | 실패(지표 없음) | CEIC은 유료 구독 없이 실제 수치 비노출로 사용 불가. 시리아 중앙은행 자체 통계 페이지도 원자료 미공개(재조사 완료, 재확인됨). World Bank(2023 FCD/TD=69.4%, 절대액 없음), IMF Article IV 2006(2000~2005년 비율만), CEIC 역산(2011 TD=USD20.276bn x 15.8%=FCD 3.20bn) 등 산발적 단일시점 추정치만 존재하고 다운로드 가능한 시계열 원자료가 없어 파서 구현 대상 아님 -&gt; 정기수집 대상에서 제외 |
| TCD | Chad | PDF Bulletin | - | 재조사 필요 | beac.int 페이지에서 받은 첫 PDF 링크가 손상되었거나 실제 PDF가 아님(방법론 노트 파일로 추정) -&gt; 실제 통계표 링크 재조사 필요 |
| TGO | Togo | Interactive Web | - | 재조사 필요 | bceao.int 페이지에 통화정책 보고서 PDF만 존재(2022-2023년 구버전), 외화예금 관련 데이터 파일 없음 -&gt; BCEAO 통계 포털 별도 경로 재조사 필요 |
| THA | Thailand | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live list BOT/DPA PDF/Excel + OCR. Seed hist 1990–97 + 2023-11 stocks. Re-list each run → auto-update when files appear. |
| TJK | Tajikistan | PDF Bulletin | PdfBulletinStrategy | 구현됨 | 이전에 확인한 Monetary Survey/Financial Corporations Survey(집계 DEPOSITS 한 줄만 존재)는 막다른 길이었으나, nbt.tj/en/statistics/statistical_bulletin.php의 'Banking statistics bulletin' PDF(월간/연말호, 2011~현재)에서 통화별 예금 분해 표를 찾음. src/parsers/tjk.py가 목록 페이지를 순회하며 각 PDF의 'Структура остатков сбережений (депозитов) в кредитных...организациях' 표에서 Всего депозитов(TD)/в национальной валюте/в иностранной валюте(FCD) 행을 pdftotext -layout으로 파싱. 2024-12(TD 25.53bn TJS, FX share 39.5%)·2025-12(TD 33.90bn TJS, FX share 37.6%) 값이 NBT 보도자료(nbt.tj/en/news/576477/, nbt.tj/en/news/618354/)와 일치해 검증함. 2016~2019·2021~2026(진행중)은 월별 해상도, 2012~2015 및 2018은 해당 회보에 연말(12월) 스냅샷만 존재. 2020년 및 2011~2015년 일부 회보는 PDF 컬럼 간격이 좁아 숫자가 서로 들러붙어 신뢰할 수 없으므로(자릿수 상한 검증으로 걸러짐) 해당 연도는 결측으로 스킵함. |
| TLS | Timor-Leste | Interactive Web | - | 재조사 필요 | bancocentral.tl 페이지에 환율(Exchange Rate) 파일만 존재, 외화예금 관련 파일 없음 -&gt; 재조사 필요 |
| TON | Tonga | Interactive Web | - | 재조사 필요 | reservebank.to 홈페이지에 APR 계산기/해외송금 파일만 존재, 통화 통계 섹션 재조사 필요 |
| TTO | Trinidad and Tobago | PDF Bulletin | - | 재조사 필요 | 첫 링크로 받은 PDF가 AML/CFT 정책 문서였음 -&gt; 실제 통계 회보 링크 재조사 필요 |
| TUN | Tunisia | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live BCT bulletin/BSF PDFs + OCR. Seed 1990/2014/2023. Re-list each run → auto-update. |
| TUR | Turkey | PDF Bulletin | PdfBulletinStrategy | 구현됨 | render()가 현재 발행본 + 동일 고정 URL의 Wayback Machine CDX 스냅샷을 순회. Table 2(신 포맷, ~2025-02+)의 'A. DEPOSITS&gt;1. Residents&gt;a.TRY/b.FX' 또는 Table 7(구 포맷, ~2024-09까지)의 'A.Residents'(TRY/FX x 예금은행/참여은행) 파싱. FCD=거주자 FX예금, TD=거주자 총예금(천 TRY). 실측 87개 주간 period, 2017-10~2026-07 확보(스냅샷 공백만큼 누락, 2025년이 가장 조밀). 2026-07-24 FCD=10,499,925,050천/TD=28,416,399,833천(ratio 36.95%)로 사전 조사치와 정확히 일치. 2022년 고점(~59%)에서 KKM 제도 도입 이후 완만히 하락해 2024~2026 35~40%대로 안정화되는 추세도 확인됨 |
| TWN | Taiwan (Province of China) | Direct Excel | DirectExcelStrategy | 구현됨 | CBC 인증서 결함(Missing Subject Key Identifier)으로 기본 SSL 검증 실패해 __RENDER__ + verify=False 우회(kor.py/jpn.py와 동일 패턴). FCD=기업및개인 외화예금, TD=합계, 단위 億元. 2023/2024/2025 연말 FCD/TD 비율(15.10/14.41/13.73%)이 사전 조사치와 근접해 검증. |
| TZA | Tanzania, United Republic of | PDF Bulletin | PdfBulletinStrategy | 구현됨 | src/parsers/tza.py, render(). 2026-02-18 발행 'Jan 26'호 Dec-25 열로 검증: FCD=13,381.1, TD=53,032.0, FCD_TD_RATIO=25.23% (사전 조사 수치와 일치). 실측 결과 FCD 200개월치(2002-08~2026-06, 결측 월 존재) 확보, TD/RATIO는 그중 192개월. 옛 호는 표 폰트 트래킹으로 라벨/숫자에 스퓨리어스 공백이 섞여(예: 'O ther deposits', '2 ,060.0') extract_text(x_tolerance=4) + 숫자 정규식을 선행 숫자 필수로 강화해 대응; 2013년 이전 다수 호는 해당 표 자체가 없거나 완전히 다른 벡터 레이아웃이라 조용히 스킵됨(결측 처리, 값 추측 안 함). |
| UGA | Uganda | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live BOU PDF list+OCR. Seed hist ratios. Re-list each run → auto-update. POE credit ≠ FCD. |
| UKR | Ukraine | Direct Excel/CSV Download | DirectExcelStrategy | 구현됨 | Full series 2002–live (xlsx 3.2.4.1 FCD=col11 TD=col1) + API tail. Re-download each run → quarterly auto-update. Seed 1995–2000 ratios. |
| URY | Uruguay | Direct Excel/CSV Download | DirectExcelStrategy | 구현됨 | Full monthly ~1998–live. Re-download xlsx each render() → auto-update. |
| UZB | Uzbekistan | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live CBU stats/press PDF list+OCR. Seed 1990–92 + 2025-09. Re-list each run → auto-update. |
| VCT | Saint Vincent and the Grenadines | Interactive Web | InteractiveWebStrategy | 구현됨 | 사용자가 제시한 SDMX REST API(sdmx.eccb-centralbank.org)는 DNS 미해석(존재하지 않는 도메인) 확인됨 -&gt; 실제로는 eccb-centralbank.org의 'Interactive Database' 쿼리 폼(Laravel, CSRF+암호화 hidden 필드, 부트스트랩 모달 안 select2 멀티셀렉트)이 진짜 데이터 소스. Playwright로 모달 열기-&gt; 국가 선택-&gt;'Foreign Currency Deposits' 지표 선택-&gt;제출 흐름 재현(src/parsers/_eccb_common.py 공용). start_date를 jQuery datepicker API로 2000-01-01로 설정해 2000~2025년(26개년) 연간 데이터 확보. 8개국(AIA/ATG/DMA/GRD/MSR/KNA/LCA/VCT) 공용 로직 검증 완료 |
| VEN | Venezuela (Bolivarian Republic of) | Direct Excel/CSV Download | DirectExcelStrategy | 구현됨 | Live BCV xls list+parse. Seed 2020-10/2021. Re-list each run → auto-update. Hyperinflation caution. |
| VNM | Viet Nam | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live SBV PDF list+OCR. Seed IMF 2020–23 stocks. Re-list each run → auto-update. DIV 6.05% excluded. |
| VUT | Vanuatu | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Multi-PDF QER archive (list+parse Table 7 rolling window/quarter). OCR fallback. Re-list pages each run → auto-update. |
| WSM | Samoa | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live CBS PDF list+OCR. Seed IMF 2015 8%. CB liability FC excluded. Re-list each run → auto-update. |
| YEM | Yemen | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live CBY PDF list+OCR. Seed AR 2022–23. Re-list each run → auto-update. Dual CBY/FX scope caution. |
| ZAF | South Africa | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live SARB pub PDF/Excel list+parse. Seed 2026-04 (4.06%). Re-list each run → auto-update. |
| ZMB | Zambia | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live BoZ annual/stats multi-PDF+OCR. Seed 2016–21 + 2024-09. Re-list each run → auto-update. |
| ZWE | Zimbabwe | PDF Bulletin | PdfBulletinStrategy | 구현됨 | Live RBZ supervision/MPS multi-PDF+OCR. Seed 2022–25. Re-list each run → auto-update. Absolute ZWL≠ZiG. |
<!-- ADAPTER_STATUS_TABLE:END -->

## 롱폼 출력 스키마

모든 수집 전략(`ScrapingStrategy.collect_and_parse`)은 아래 컬럼의 pandas DataFrame을 반환한다.

| 컬럼 | 설명 |
| --- | --- |
| country_code | ISO 3글자 코드 |
| year | 연도 |
| period | 기간 구분 (예: Q1, Annual, 2026-01) |
| indicator | 지표명: `FCD` / `TD` / `FCD_TD_RATIO` (레거시 `foreign_currency_deposits` → `FCD`) |
| value | 값. **`FCD_TD_RATIO`는 퍼센트 0–100** (`(FCD/TD)*100`). 0–1 분율이 아님 |
| updated_at | 수집 시각 (ISO 8601) |

Supabase `deposit_dollarization` 테이블에 `(country_code, year, period, indicator)` 복합 PK 기준 UPSERT된다.
국가 메타데이터(`config/targets.json`)는 `country_metadata` 테이블에 UPSERT된다.

## Supabase 연동

### 1) 테이블 생성

Supabase Dashboard → **SQL Editor**에 `sql/deposit_dollarization.sql` + `sql/country_metadata.sql` 을 실행하거나:

```bash
python main.py --init-db
```

#### `deposit_dollarization`

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| country_code | TEXT | ISO3 (PK) |
| year | INTEGER | 연도 (PK) |
| period | TEXT | `YYYY-MM` 등 (PK) |
| indicator | TEXT | `FCD` / `TD` / `FCD_TD_RATIO` (PK) |
| value | DOUBLE PRECISION | 값. **`FCD_TD_RATIO` = (FCD/TD)×100 → 0–100 퍼센트** (0–1 아님) |
| updated_at | TIMESTAMPTZ | 적재 시각 |

UPSERT 키: `(country_code, year, period, indicator)`.

레거시 지표명 정리:

```bash
python main.py --migrate-indicators   # foreign_currency_deposits → FCD (충돌 시 기존 FCD 유지)
```

#### `country_metadata` (targets)

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| country_code | TEXT | ISO3 (PK) |
| country_name | TEXT | 국가명 |
| data_type | TEXT | Direct Excel / PDF Bulletin / … |
| source_url | TEXT | 소스 URL |
| update_frequency | TEXT | targets 원문 (`Monthly` / `Annual` / `Quarterly` …) |
| frequency_bucket | TEXT | 정규화: `annual` / `quarterly` / `monthly` / `semi_annual` / `higher` / `unknown` / `other` |
| requires_js | BOOLEAN | JS 렌더 필요 여부 |
| notes | TEXT | 수집 메모 |
| adapter_* | … | `adapter.implemented/status/strategy_class/notes` |
| pending_parsers | JSONB | 보조 파서 TODO 목록 |
| has_parser | BOOLEAN | 동기화 시점 `src/parsers/{cc}.py` 존재 여부 |
| raw_target | JSONB | targets.json 원본 전체 |
| synced_at | TIMESTAMPTZ | 마지막 업로드 시각 |

```bash
# targets.json 전체 → country_metadata UPSERT
python main.py --upload-targets

# 일부 국가 / adapter.status 필터
python main.py --upload-targets --countries UKR,URY --status success
```

### 2) 연결 문자열

```bash
cp .env.example .env
# SUPABASE_DB_URL=postgresql://postgres.[ref]:[password]@...pooler.supabase.com:6543/postgres
```

- Dashboard → **Project Settings → Database → Connection string → URI**
- CI/서버리스는 **Transaction pooler (6543)** 권장
- GitHub Actions secret 이름: `SUPABASE_DB_URL`

### 3) 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # Interactive Web 전략 사용 시

python main.py --init-db
python main.py --dry-run --status success --only-with-parser
python main.py --status success --only-with-parser          # 전체 성공 어댑터 → Supabase
python main.py --countries UKR,URY,RWA                      # 일부 국가만
```

| 옵션 | 설명 |
| --- | --- |
| `--dry-run` | 수집만, DB 저장 안 함 |
| `--countries UKR,URY` | ISO3 필터 |
| `--status success` | `adapter.status` 필터 |
| `--only-with-parser` | `src/parsers/{cc}.py` 있는 국가만 |
| `--init-db` | 테이블/인덱스 생성 (`deposit_dollarization` + `country_metadata`) |
| `--migrate-indicators` | 레거시 `foreign_currency_deposits` → `FCD` 일괄 이전 |
| `--list-db-stats` | Supabase 국가별 행 수 출력 |
| `--db-summary` | 적재 데이터 요약(기간·지표·저행수). `--summary-json PATH` 로 JSON 저장 |
| `--upload-targets` | `targets.json` → `country_metadata` UPSERT |
| `--thin-threshold N` | `--db-summary` 저행수 기준 (기본 30) |
| `--include-annual-thin` | 저행수 목록에 annual/semi_annual 도 포함 (기본은 **예외 제외**) |
| `--workers N` | 동시 수집 슬롯 (기본 4). **끝난 즉시 다음 국가** |
| `--timeout-sec N` | 국가당 하드 타임아웃(프로세스 kill). 0=무제한 |
| `--upsert-batch-size N` | 성공 N국 모이면 UPSERT 워커가 일괄 적재 (기본 5) |
| `--skip-existing` | DB에 1행이라도 있으면 스킵 |
| `--skip-if-rows-gte N` | DB 행 수 ≥ N 이면 스킵 |
| `--max-db-rows N` | DB 행 수 ≤ N **또는 미수집** 국가만 (저행수 파서 점검) |
| `--min-db-rows N` | DB 행 수 ≥ N 인 국가만 |

```bash
# 권장: 연속 워커 8 + 120초 타임아웃 + 5국마다 UPSERT + 이미 있는 국가 스킵
python main.py --status success --only-with-parser \
  --workers 8 --timeout-sec 120 --upsert-batch-size 5 --skip-existing

# 저행수(≤30행) / 미수집만 다시 돌리기 (파서 재작업용)
python main.py --status success --only-with-parser \
  --workers 6 --timeout-sec 180 --max-db-rows 30

# DB 현황 / 요약 / 메타데이터 업로드
python main.py --list-db-stats
python main.py --list-db-stats --max-db-rows 30
python main.py --db-summary
python main.py --db-summary --summary-json runs/db-summary.json
python main.py --upload-targets
```

### 실행 모델

```
targets 큐 ──► [수집 워커 × N] ──(끝난 즉시 다음)──► UPSERT 큐
                      │                              │
                   timeout                           ▼
                 process kill              [UPSERT 워커] N국마다 flush
```

- 국가는 **서로 독립** → 배치 장벽 없음 (예전 `--batch-size`로 10국 끝날 때까지 기다리던 구조 제거).
- `--timeout-sec` 사용 시 국가마다 **자식 프로세스**; 초과 시 `terminate`/`kill`.

분기 자동 실행: 모노레포 루트 [`.github/workflows/quarterly_etl.yml`](../.github/workflows/quarterly_etl.yml)
(1·4·7·10월 1일 UTC). `workflow_dispatch`로 수동 실행·국가 필터 가능.

## 현재 상태

국가별 파서는 배치로 채워 넣는 중이며, 진행 상황은 [어댑터 구현 현황](#어댑터-구현-현황)
표와 `config/targets.json`의 `adapter` 필드를 참고.
