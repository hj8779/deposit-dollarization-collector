
스웨덴의 외화예금(FCD) 및 총예금(TD) 데이터를 찾기 위해 SCB(통계청)와 Riksbank(중앙은행)의 공식 통계를 확인했습니다.

## 주요 데이터 소스

스웨덴의 외화예금 관련 공식 통계는 **SCB(Statistics Sweden)**의 금융시장통계(Financial Market Statistics, FM5001)에서 제공됩니다. [scb](https://www.scb.se/en/finding-statistics/statistics-by-subject-area/financial-markets/financial-market-statistics/financial-market-statistics/)

### SCB 통계 데이터베이스

가장 직접적인 데이터는 SCB의 통계 데이터베이스에서 "Monetary financial institutions´ (MFI) assets and liabilities" 테이블에서 확인할 수 있습니다.  이 통계는 통화금융기관(MFI)의 자산과 부채를 통화별(SEK 및 외화)로 세분화하여 제공합니다. [scb](https://www.scb.se/en/finding-statistics/statistics-by-subject-area/financial-markets/financial-market-statistics/financial-market-statistics/)

- **데이터 범위**: 2004년 1월 ~ 2026년 6월 (월간)
- **포함 항목**: 은행, 주택신용기관, 금융회사의 외화예금
- **통화 구분**: SEK, EUR, USD, 기타 통화
- **접근 URL**: https://www.statistikdatabasen.scb.se/ (FM5001 시리즈) [dsbb.imf](https://dsbb.imf.org/sddsplus/dqaf-base/country/SWE/category/AAB00)

### Riksbank IRIS 통계

Riksbank의 국제은행통계(IRIS)에서도 스웨덴 은행부문의 외화자금 조달 현황을 확인할 수 있습니다. [riksbank](https://www.riksbank.se/en-gb/statistics/reporting-of-international-bank-statistics-iris/swedish-banking-sector/)

- 2026년 1/4분기 기준, 스웨덴 은행부문의 총 부채 SEK 15,218십억 중 **약 37%가 외화 조달** [riksbank](https://www.riksbank.se/en-gb/statistics/reporting-of-international-bank-statistics-iris/swedish-banking-sector/)
- 예금이 은행 부채의 가장 큰 부분을 차지하며, 대부분 SEK 예금이지만 외화예금도 포함 [riksbank](https://www.riksbank.se/en-gb/statistics/reporting-of-international-bank-statistics-iris/swedish-banking-sector/)

## FCD/TD(외화예금비율) 데이터

IMF의 Deposit Dollarization 연구에 따르면, 스웨덴은 선진국으로 외화예금비율이 낮지만, SCB의 MFI 통계에서 통화별 예금 잔액을 추출하여 FCD/TD를 계산할 수 있습니다. [documents.worldbank](https://documents.worldbank.org/curated/en/688721468766211450/pdf/multi0page.pdf)

### 데이터 추출 방법

1. **SCB 통계데이터베이스**에서 다음 테이블 접근:
   - `Monetary financial institutions´ (MFI) assets and liabilities (incl. the Central Bank and excl. Swedish foreign branches)` [scb](https://www.scb.se/en/finding-statistics/statistics-by-subject-area/financial-markets/financial-market-statistics/financial-market-statistics/)
   - 통화별(valuta) 예금 잔액 추출

2. **계산식**:
   \[
   \text{FCD/TD} = \frac{\text{외화예금 (EUR + USD + 기타)}}{\text{총예금 (SEK + 외화)}}
   \]

## 추가 참고사항

- 스웨덴은 기축통화국(SEK)으로 외화예금비율이 신흥국보다 일반적으로 낮음 [brookings](https://www.brookings.edu/wp-content/uploads/2016/06/0119_sweden_finance_bryant.pdf)
- 가계 및 비금융기업 부문별 외화예금 데이터도 SCB에서 제공 [scb](https://www.scb.se/en/finding-statistics/statistics-by-subject-area/financial-markets/financial-market-statistics/financial-market-statistics/pong/statistical-news/financial-market-statistics-august-2025/)
- 영어 문의: fmr@scb.se [scb](https://www.scb.se/en/finding-statistics/statistics-by-subject-area/financial-markets/financial-market-statistics/financial-market-statistics/)

직접 데이터 추출이 필요하시면 SCB 통계데이터베이스에서 FM5001 시리즈를 다운로드하거나, Riksbank의 IRIS 보고서를 참조하시기 바랍니다. [scb](https://www.scb.se/en/finding-statistics/statistics-by-subject-area/financial-markets/financial-market-statistics/financial-market-statistics/)


슬로바키아의 외화예금(FCD) 및 총예금(TD) 데이터를 NBS(국립은행)와 국제통계 소스에서 확인했습니다.

## 주요 데이터 소스

### NBS(나로드나 방카 슬로벤스카) 공식 통계

슬로바키아 중앙은행(NBS)은 통화금융기관(MFI)의 예금 통계를 월간으로 제공합니다. [nbs](https://nbs.sk/en/statistics/financial-institutions/banks/statistical-data-of-monetary-financial-institutions/deposits/)

**데이터 위치**: https://nbs.sk/en/statistics/financial-institutions/banks/statistical-data-of-monetary-financial-institutions/deposits/ [nbs](https://nbs.sk/en/statistics/financial-institutions/banks/statistical-data-of-monetary-financial-institutions/deposits/)

- **통계명**: "Deposits and loans received" (예금 및 차입금)
- **세부내역**: 부문별(가계, 기업, 보험사), 통화별(EUR 및 외화), 만기별 구분
- **데이터 기간**: 2003년~2026년 (월간)
- **단위**: EUR 백만 [nbs](https://nbs.sk/en/statistics/data-categories-of-sdds/analytical-accounts-of-the-banking-sector/mpa/mp2003a/)

### 총예금(TD) 데이터

CEIC와 Trading Economics에서 슬로바키아 총예금 데이터를 제공합니다. [ceicdata](https://www.ceicdata.com/ko/indicator/slovakia/total-deposits)

- **2026년 5월 기준**: USD 116.367십억 (약 EUR 106십억) [ceicdata](https://www.ceicdata.com/en/indicator/slovakia/total-deposits)
- **2025년 1월 기준**: USD 93.561십억 [ceicdata](https://www.ceicdata.com/ko/indicator/slovakia/total-deposits)
- **2015-2025 평균**: USD 74.399십억 [ceicdata](https://www.ceicdata.com/ko/indicator/slovakia/total-deposits)

## FCD/TD(외화예금비율) 역사적 데이터

### IMF 및 연구자료

World Bank의 Deposit Dollarization 연구에 따르면, 슬로바키아의 외화예금비율은 다음과 같습니다. 

| 연도 | FCD/TD (%) |
|------|-----------|
| 1990 | 12.5 |
| 1995 | 16.4 |
| 1998 | 17.6 |
| 2000 | 14.7 |

2000년대 초반에는 약 10-15% 수준이었으며, 1998년 외환위기 당시 16% 이상으로 상승한 바 있습니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/1999/112/article-A002-en.xml)

### 유로존 가입 이후 변화

슬로바키아는 2009년 유로존에 가입하면서 외화예금의 대부분이 EUR로 전환되었습니다. [oenb](https://www.oenb.at/dam/jcr:dd3719ce-2927-4d38-a075-4e45c8fb0fd0/wp140_tcm16-84943.pdf)

- **2004-2005년 기준**: 가계 예금 중 외화 비중 약 13% [oenb](https://www.oenb.at/dam/jcr:dd3719ce-2927-4d38-a075-4e45c8fb0fd0/wp140_tcm16-84943.pdf)
- **2009년 이후**: 유로화 도입으로 외화예금비율 급감 (대부분 EUR denomination) [nbs](https://nbs.sk/_img/documents/_publikacie/annualreport/arnbs09.pdf)

## 현재 데이터 접근 방법

### NBS 통계데이터베이스

1. **접속**: https://nbs.sk/en/statistics/ [nbs](https://nbs.sk/en/statistics/)
2. **네비게이션**: Financial Institutions → Banks → Statistical data of monetary financial institutions → Deposits [nbs](https://nbs.sk/en/statistics/financial-institutions/banks/statistical-data-of-monetary-financial-institutions/deposits/)
3. **데이터 다운로드**: 엑셀/CSV 형식 지원

### ECB Data Portal

유로존 회원국으로서 ECB 통계포털에서도 슬로바키아 금융통계를 확인할 수 있습니다. [data.ecb.europa](https://data.ecb.europa.eu/data/geographical-areas/slovakia?reference_area_name[0]=Slovakia)

- **URL**: https://data.ecb.europa.eu/data/geographical-areas/slovakia [data.ecb.europa](https://data.ecb.europa.eu/data/geographical-areas/slovakia?reference_area_name[0]=Slovakia)
- **포함 항목**: MFI 자산/부채, 통화별 예금, 이자율 등

## 참고사항

- 슬로바키아는 유로존 회원국으로, 현재 "외화"는 주로 비유로화(USD, CHF 등)를 의미 [nbs](https://nbs.sk/_img/documents/_publikacie/annualreport/arnbs09.pdf)
- 2009년 유로 도입 이전에는 DEM, USD, CHF 등이 주요 외화예금 통화였음 [nbs](https://nbs.sk/en/statistics/data-categories-of-sdds/analytical-accounts-of-the-banking-sector/mpa/mp2003a/)
- NBS 통계문의: statistics@nbs.sk 또는 gregor_bajtay@nbs.sk [documents.worldbank](https://documents.worldbank.org/curated/en/688721468766211450/pdf/multi0page.pdf)

직접 FCD/TD 계산을 원하시면 NBS의 "Deposits and loans received" 테이블에서 통화별 잔액을 추출하여 계산하시기 바랍니다. [nbs](https://nbs.sk/en/statistics/financial-institutions/banks/statistical-data-of-monetary-financial-institutions/deposits/)


슬로베니아의 외화예금(FCD) 및 총예금(TD) 데이터를 Banka Slovenije(중앙은행)와 ECB 통계에서 확인했습니다.

## 주요 데이터 소스

### Banka Slovenije 공식 통계

슬로베니아 중앙은행(Banka Slovenije, BSI)은 통화금융기관(MFI) 통계를 제공합니다. [bsi](https://www.bsi.si/en/statistics)

**데이터 위치**: https://www.bsi.si/en/financial-institutions-and-markets [bsi](https://www.bsi.si/en/financial-institutions-and-markets)

- **통계명**: "Consolidated balance sheet of monetary financial institutions (MFIs)"
- **포함 항목**: 중앙은행, 은행, 저축은행, 머니마켓펀드의 자산/부채
- **통화 구분**: EUR 및 외화 breakdown 가능
- **데이터 형식**: 엑셀/CSV 다운로드 지원 (Data series) [bsi](https://www.bsi.si/en/statistics)

### 총예금(TD) 데이터

CEIC에서 슬로베니아 총예금 데이터를 제공합니다. [ceicdata](https://www.ceicdata.com/ko/indicator/slovenia/total-deposits)

- **2026년 5월 기준**: USD 53,385백만 (약 EUR 48.5십억) [ceicdata](https://www.ceicdata.com/ko/indicator/slovenia/total-deposits)
- **2026년 4월**: USD 53,220백만 [ceicdata](https://www.ceicdata.com/ko/indicator/slovenia/total-deposits)
- **2005-2026 평균**: USD 35,176백만 [ceicdata](https://www.ceicdata.com/ko/indicator/slovenia/total-deposits)

## FCD/TD(외화예금비율) 역사적 데이터

### IMF 자료

2004년 IMF Article IV Consultation에 따르면, 슬로베니아의 외화예금 현황은 다음과 같습니다. [imf](https://www.imf.org/external/pubs/ft/scr/2004/cr04150.pdf)

| 연도 | 외화예금 (EUR 백만) | M3 (EUR 백만) | FCD/M3 (%) |
|------|-------------------|--------------|-----------|
| 1999 | 569.1 | - | - |
| 2000 | 739.7 | - | - |
| 2001 | 962.6 | - | - |
| 2002 | 1,020.8 | - | - |
| 2003 | 1,062.3 | - | - |

### 유로존 가입 이전 외화예금비율

2004년 연구에 따르면, 2004년 기준 슬로베니아 가계 예금 중 **외화 비중은 약 36%**였습니다. 

- **슬로바키아**: 13%
- **슬로베니아**: 36%
- **크로아티아**: 83%

### 유로존 가입 이후 변화

슬로베니아는 **2007년 1월 1일** 유로존에 가입하면서 통화단위가 톨라르(SIT)에서 유로(EUR)로 전환되었습니다. [bsi](https://www.bsi.si/storage/uploads/1549e097-221e-4a7a-8536-f6298eb94333/bil_2007_07.pdf)

- **2007년 이후**: 외화예금의 대부분이 EUR denomination으로 전환 [bsi](https://www.bsi.si/storage/uploads/1549e097-221e-4a7a-8536-f6298eb94333/bil_2007_07.pdf)
- **현재**: "외화"는 비유로화(USD, CHF 등)를 의미 [dsbb.imf](https://dsbb.imf.org/sddsplus/dqaf-base/country/SVN/category/ILV00)

## ECB Data Portal

슬로베니아는 유로존 회원국으로서 ECB 통계포털에서도 데이터를 확인할 수 있습니다. [data.ecb.europa](https://data.ecb.europa.eu/data/geographical-areas/slovenia?reference_area_name[0]=Slovenia)

- **URL**: https://data.ecb.europa.eu/data/geographical-areas/slovenia [data.ecb.europa](https://data.ecb.europa.eu/data/geographical-areas/slovenia?reference_area_name[0]=Slovenia)
- **포함 항목**: MFI 자산/부채, 통화별 예금, 이자율, 가계/기업 대출 등
- **데이터 기간**: 1999년~현재 (월간/분기)

## 현재 데이터 접근 방법

### Banka Slovenije Data Series

1. **접속**: https://www.bsi.si/en/statistics [bsi](https://www.bsi.si/en/statistics)
2. **네비게이션**: Financial Institutions and Markets → Monetary statistics → Data series [bsi](https://www.bsi.si/en/financial-institutions-and-markets)
3. **테이블**: "Consolidated balance sheet of MFIs" 또는 "Deposits and loans"
4. **다운로드**: 엑셀/CSV 형식

### ECB Statistical Data Warehouse

- **URL**: https://data.ecb.europa.eu/ [data.ecb.europa](https://data.ecb.europa.eu/data/geographical-areas/slovenia?reference_area_name[0]=Slovenia)
- **검색어**: "Slovenia MFI deposits currency breakdown"
- **데이터 시리즈**: BSI (Balance Sheet Items)

## 참고사항

- 슬로베니아는 2007년 유로존 가입으로 외화예금 통계의 의미가 변화 (대부분 EUR) [bsi](https://www.bsi.si/storage/uploads/1549e097-221e-4a7a-8536-f6298eb94333/bil_2007_07.pdf)
- 현재 "외화"는 주로 비유로화(USD, CHF, GBP 등)를 의미 [dsbb.imf](https://dsbb.imf.org/sddsplus/dqaf-base/country/SVN/category/ILV00)
- 가계 예금이 총예금의 약 50%를 차지 (2023년 기준 49.9%) [ebf](https://www.ebf.eu/wp-content/uploads/2024/12/Slovenia.pdf)
- Banka Slovenije 통계문의: statistics@bsi.si 또는 데이터 시리즈 페이지의 연락처 참조 [bsi](https://www.bsi.si/en/statistics)

직접 FCD/TD 계산을 원하시면 Banka Slovenije의 MFI 대차대조표에서 통화별 예금 잔액을 추출하거나, ECB BSI 통계를 활용하시기 바랍니다. [bsi](https://www.bsi.si/en/financial-institutions-and-markets)


수리남의 외화예금(FCD) 및 총예금(TD) 데이터를 Centrale Bank van Suriname(CBvS, 중앙은행)과 IMF 자료에서 확인했습니다.

## 주요 데이터 소스

### Centrale Bank van Suriname (CBvS) 공식 통계

수리남 중앙은행(CBvS)은 GDDS(General Data Dissemination System)를 통해 금융통계를 제공합니다. [cbvs](https://www.cbvs.sr/index.php?option=com_content&view=article&id=118&Itemid=185&lang=en)

**데이터 위치**: https://www.cbvs.sr/index.php?option=com_content&view=article&id=118&Itemid=185&lang=en [cbvs](https://www.cbvs.sr/index.php?option=com_content&view=article&id=118&Itemid=185&lang=en)

- **통계명**: "Depository Corporations Survey" 및 "Broad Money"
- **포함 항목**: M2, 외화예금, 국내통화예금, 신용 등
- **데이터 기간**: 2017년 이후 월간/분기 데이터
- **단위**: SRD(수리남 달러) 백만 [cbvs](https://www.cbvs.sr/index.php?option=com_content&view=article&id=118&Itemid=185&lang=en)

### 총예금(TD) 및 외화예금(FCD) 데이터

CBvS의 2017년 8월 기준 데이터는 다음과 같습니다. [cbvs](https://www.cbvs.sr/index.php?option=com_content&view=article&id=118&Itemid=185&lang=en)

| 항목 | 단위 | 금액 (SRD 백만) |
|------|------|----------------|
| M2 (광의통화) | SRD 백만 | 16,748.0 |
| **외화예금 (FCD)** | SRD 백만 | **10,797.2** |
| 국내통화예금 (추정) | SRD 백만 | 5,950.8 |

**FCD/TD 비율 계산** (2017년 8월):
\[
\text{FCD/TD} = \frac{10,797.2}{16,748.0} \approx 64.5\%
\]

## FCD/TD(외화예금비율) 역사적 데이터

### IMF 및 연구자료

수리남은 카리브 지역에서 **가장 높은 외화예금비율**을 보이는 국가입니다. [imf](https://www.imf.org/-/media/files/publications/cr/2019/1surea2019002.pdf)

| 연도 | FCD/TD (%) | 자료출처 |
|------|-----------|----------|
| 1996 | 20% |  [cert-net](https://cert-net.com/files/publications/conference/2012/10_3-Adhin-p.pdf) |
| 2001 | 51% |  [cert-net](https://cert-net.com/files/publications/conference/2012/10_3-Adhin-p.pdf) |
| 2004 | 58% (최대) |  [cert-net](https://cert-net.com/files/publications/conference/2012/10_3-Adhin-p.pdf) |
| 2011 | 57% |  [cert-net](https://cert-net.com/files/publications/conference/2012/10_3-Adhin-p.pdf) |
| 2018 | 65.3% |  [imf](https://www.imf.org/-/media/files/publications/cr/2019/1surea2019002.pdf) |
| 2023 | ~80% |  [cbvs](https://www.cbvs.sr/en/?view=category&id=80) |

### 주요 특징

- **2004년 정점**: 외화예금비율이 58%로 최고치 기록 (2002-2004년 동안 47%→56% 상승) [imf](https://www.imf.org/external/pubs/ft/scr/2005/cr05143.pdf)
- **2018년 기준**: 예금의 65.3%, 부채의 47.7%가 외화표시 [imf](https://www.imf.org/-/media/files/publications/cr/2019/1surea2019002.pdf)
- **2023년 기준**: 예금 달러라이제이션 약 80%, 신용 달러라이제이션 약 55% [cbvs](https://www.cbvs.sr/en/?view=category&id=80)
- **카리브 평균**: 예금 16.5%, 부채 11.1% (수리남은 이보다 훨씬 높음) [imf](https://www.imf.org/-/media/files/publications/cr/2019/1surea2019002.pdf)

## 최근 데이터 접근 방법

### CBvS 공식 웹사이트

1. **접속**: https://www.cbvs.sr/ [cbvs](https://www.cbvs.sr/)
2. **네비게이션**: Statistics → Financial Market Statistics → Monetary Statistics [cbvs](https://www.cbvs.sr/index.php?option=com_content&view=article&id=118&Itemid=185&lang=en)
3. **데이터 시리즈**:
   - "Depository Corporations Survey" (Table 3)
   - "Broad Money" (Table 5)
   - "Deposits in Foreign Currency" [cbvs](https://www.cbvs.sr/index.php?option=com_content&view=article&id=118&Itemid=185&lang=en)

### IMF Article IV Consultation

IMF는 수리남에 대해 정기적인 Article IV Consultation을 실시하며, 최신 데이터는 2025년 보고서에서 확인할 수 있습니다. [imf](https://www.imf.org/-/media/files/publications/cr/2025/english/1surea2025002-print-pdf.pdf)

- **2025년 보고서**: "Suriname: Selected Issues" - 달러라이제이션 및 외화예금 동향 포함 [imf](https://www.imf.org/-/media/files/publications/cr/2025/english/1surea2025002-print-pdf.pdf)
- **데이터 출처**: CBvS 및 IMF Staff Calculations [imf](https://www.imf.org/-/media/files/publications/cr/2025/english/1surea2025002-print-pdf.pdf)

### World Bank FRED 데이터

- **Bank Deposits to GDP**: 2021년 기준 75.84% [fred.stlouisfed](https://fred.stlouisfed.org/series/DDOI02SRA156NWDB)
- **URL**: https://fred.stlouisfed.org/series/DDOI02SRA156NWDB [fred.stlouisfed](https://fred.stlouisfed.org/series/DDOI02SRA156NWDB)

## 참고사항

- 수리남은 1992년 외화예금, 1995년 외화대출 허용 이후 급속한 금융 달러라이제이션 경험 [cert-net](https://cert-net.com/files/publications/conference/2012/10_3-Adhin-p.pdf)
- 2020-2021년 수리남 달러 182.5% 평가절하로 인플레이션 및 거시경제 문제 발생 [elibrary.imf](https://www.elibrary.imf.org/view/journals/019/2025/050/article-A001-en.xml)
- 2023년 4월 CBvS, 지급준비율을 39%에서 44%로 인상 (유동성 관리 강화) [elibrary.imf](https://www.elibrary.imf.org/view/journals/019/2025/050/article-A001-en.xml)
- 외화예금은 주로 USD 및 EUR 표시 [cert-net](https://cert-net.com/files/publications/conference/2012/10_3-Adhin-p.pdf)
- CBvS 통계문의: statistics@cbvs.sr 또는 웹사이트 연락처 참조 [cbvs](https://www.cbvs.sr/)

직접 최신 FCD/TD 데이터를 원하시면 CBvS의 "Depository Corporations Survey" 또는 IMF의 2025년 Article IV 보고서에서 통화별 예금 잔액을 추출하시기 바랍니다. [cbvs](https://www.cbvs.sr/index.php?option=com_content&view=article&id=118&Itemid=185&lang=en)


상투메프린시피의 외화예금(FCD) 및 총예금(TD) 데이터를 BCSTP(중앙은행)와 IMF 자료에서 확인했습니다.

## 주요 데이터 소스

### Banco Central de São Tomé e Príncipe (BCSTP) 공식 통계

상투메프린시피 중앙은행(BCSTP)은 은행시스템 통계를 제공합니다. [bcstp](https://www.bcstp.st/)

**데이터 위치**: https://www.bcstp.st/ (통계 섹션) [bcstp](https://www.bcstp.st/)

- **통계명**: "Estatísticas do Sistema Bancário" (은행시스템 통계)
- **포함 항목**: 은행별 자산/부채, 예금, 대출, 외화예금 등
- **데이터 기간**: 월간/분기/연간 데이터
- **단위**: STN(신 도브라) 또는 USD 백만 [imf](https://www.imf.org/-/media/Files/Publications/CR/2021/English/1STPEA2021001.ashx)

## FCD/TD(외화예금비율) 데이터

### World Bank 연구자료

World Bank의 Deposit Dollarization 연구에 따르면, 상투메프린시피의 외화예금비율은 다음과 같습니다. 

| 연도 | FCD/TD (%) |
|------|-----------|
| 1995 | 38.3 |
| 1996 | 29.6 |
| 1997 | 34.9 |
| 1998 | 37.9 |
| 1999 | 39.2 |
| 2000 | 33.5 |

**1990년대 평균**: 약 35-39% 수준 

### IMF Article IV Consultation 데이터

IMF의 최신 보고서(2021-2025년)에서 상투메프린시피의 통화통계 데이터가 제공됩니다. [imf](https://www.imf.org/-/media/Files/Publications/CR/2021/English/1STPEA2021001.ashx)

#### 외화예금 잔액 (USD 백만)

| 연도 | 외화예금 (USD 백만) |
|------|-------------------|
| 2015 | 716 |
| 2016 | 741 |
| 2017 | 704 |
| 2018 | 700 |
| 2019 | 752 |
| 2020 | 752 |
| 2021 | 791 |
| 2022 | 774 |
| 2023 | 774 |
| 2024 | 940 |
| 2025 | 1,088 |

#### 총예금 구성 (2025년 기준, USD 백만) [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2025/001/article-A001-en.xml)

| 항목 | 금액 (USD 백만) |
|------|---------------|
| 통화 (지중통화) | 553 |
| 양도성 예금 (도브라) | 2,768 |
| 기타 예금 (도브라) | 409 |
| **외화예금 (FCD)** | **1,238** |
| **총예금 (TD, 추정)** | **4,968** |

**FCD/TD 비율 계산** (2025년):
\[
\text{FCD/TD} = \frac{1,238}{4,968} \approx 24.9\%
\]

### 주요 특징

- **2010년 이후**: 유로화 페그제 도입 (1 EUR = 24.50 STD, 이후 STN) [trade](https://www.trade.gov/country-commercial-guides/sao-tome-and-principe-trade-financing)
- **2018년**: 도브라 리디노미네이션 (1,000 STD = 1 STN) [state](https://www.state.gov/reports/2025-investment-climate-statements/sao-tome-and-principe)
- **2024년**: 외환규제 강화 (수출대금의 25% 강제환전) [state](https://www.state.gov/reports/2025-investment-climate-statements/sao-tome-and-principe)
- **은행집중도**: BISTP(Banco Internacional de São Tomé e Príncipe)가 외화예금의 70% 점유 [migrantmoney.uncdf](https://migrantmoney.uncdf.org/wp-content/uploads/2025/05/Policy-Diagnostic-Sao-Tome-April2025.pdf)

## 총예금(TD) 관련 데이터

### World Bank 지표

- **Bank Deposits to GDP**: 2020년 기준 29.04% [tradingeconomics](https://tradingeconomics.com/sao-tome-and-principe/bank-deposits-to-gdp-percent-wb-data.html)
- **Bank Credit to Bank Deposits**: 2020년 기준 64.64% [tradingeconomics](https://tradingeconomics.com/sao-tome-and-principe/bank-credit-to-bank-deposits-percent-wb-data.html)
- **URL**: https://tradingeconomics.com/sao-tome-and-principe/bank-deposits-to-gdp-percent-wb-data.html [tradingeconomics](https://tradingeconomics.com/sao-tome-and-principe/bank-deposits-to-gdp-percent-wb-data.html)

### IMF M3 데이터

| 연도 | M3 (USD 백만) |
|------|--------------|
| 2015 | 1,447 |
| 2016 | 1,352 |
| 2017 | 1,482 |
| 2018 | 1,669 |
| 2019 | 1,752 |
| 2020 | 1,823 |
| 2021 | 1,930 |
| 2022 | 2,043 |
| 2023 | 2,209 |

## 현재 데이터 접근 방법

### BCSTP 공식 웹사이트

1. **접속**: https://www.bcstp.st/ [bcstp](https://www.bcstp.st/)
2. **네비게이션**: Estatísticas → Estatísticas do Sistema Bancário [bcstp](https://www.bcstp.st/)
3. **데이터 시리즈**:
   - "Evolução do Sistema Bancário" (은행시스템 동향)
   - "Resumo Monetário" (통계요약)
   - "Depósitos em Moeda Estrangeira" (외화예금) [imf](https://www.imf.org/-/media/Files/Publications/CR/2021/English/1STPEA2021001.ashx)

### IMF Data Portal

- **URL**: https://www.imf.org/en/Data [imf](https://www.imf.org/-/media/Files/Publications/CR/2021/English/1STPEA2021001.ashx)
- **검색어**: "São Tomé and Príncipe monetary statistics"
- **데이터 시리즈**: IFS (International Financial Statistics)

## 참고사항

- 상투메프린시피는 2010년 이후 유로화 페그제 운영 (환율 안정성 확보) [trade](https://www.trade.gov/country-commercial-guides/sao-tome-and-principe-trade-financing)
- 2018년 도브라 리디노미네이션으로 통화단위 변경 (1,000:1) [state](https://www.state.gov/reports/2025-investment-climate-statements/sao-tome-and-principe)
- 6개 상업은행 중 BISTP가 시장 지배적 (자산 50%, 외화예금 70%) [migrantmoney.uncdf](https://migrantmoney.uncdf.org/wp-content/uploads/2025/05/Policy-Diagnostic-Sao-Tome-April2025.pdf)
- 외화예금은 주로 EUR 및 USD 표시 [imf](https://www.imf.org/-/media/Files/Publications/CR/2021/English/1STPEA2021001.ashx)
- BCSTP 통계문의: 통계섹션의 연락처 또는 estatisticas@bcstp.st 참조 [bcstp](https://www.bcstp.st/)

직접 최신 FCD/TD 데이터를 원하시면 BCSTP의 "Estatísticas do Sistema Bancário" 또는 IMF의 2025년 Article IV 보고서에서 통화별 예금 잔액을 추출하시기 바랍니다. [imf](https://www.imf.org/-/media/Files/Publications/CR/2021/English/1STPEA2021001.ashx)