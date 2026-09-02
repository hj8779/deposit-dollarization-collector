니카라과는 **니카라과 중앙은행(BCN)**과 IMF 자료에서 외화예금 비율을 확인할 수 있습니다. 최신으로 확인되는 공식 수치는 **2023년 9월 기준 예금 달러화율 약 70%**이며, 이는 사용자가 원하는 \(FCD/TD\)와 동일한 개념입니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2024/018/article-A001-en.xml)

## 최신 FCD/TD

| 기준시점 | FCD/TD | FCD | TD |
|---|---:|---:|---:|
| 2017년 | 약 75% | 공개자료에서 일부 확인 | 공개자료에서 일부 확인 |
| 2023년 9월 | **약 70%** | 원자료 확인 필요 | 원자료 확인 필요 |

IMF는 니카라과의 예금 달러화율이 2017년 약 75%에서 2023년 9월 약 **70%**로 하락했다고 설명합니다. 외화대출 비율은 여전히 약 90%로, 예금보다 높은 수준입니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2024/018/article-A001-en.xml)

계산식은 다음과 같습니다.

\[
FCD/TD
=
\frac{\text{Foreign-currency deposits}}
{\text{Total deposits}}
\]

따라서 2023년 9월 데이터셋에는 다음처럼 입력할 수 있습니다.

```text
country,date,fcd_td,fcd,td
Nicaragua,2023-09-30,0.70,NA,NA
```

## BCN 원자료

BCN의 통계연보는 다음 항목을 별도 제공하는 통화·금융통계 체계를 갖고 있습니다.

- Total deposits.
- Deposits in domestic currency.
- Deposits in foreign currency.
- Foreign currency deposits / total deposits.
- M3A.
- Deposits subject to foreign-currency reserve requirements.
- Financial-sector balance sheet.

BCN의 경제통계연보에는 `Foreign currency deposits / total deposits`라는 직접적인 지표가 포함되어 있으며, 과거 자료의 예금 총액과 외화예금 잔액도 함께 제공됩니다. [bcn.gob](https://www.bcn.gob.ni/sites/default/files/documentos/macroeconomic_yearbook_2009.pdf)

## 과거 직접 관측자료

BCN의 장기 통계연보에서 확인되는 외화예금 달러화율은 다음과 같습니다.

| 기준연도 | FCD/TD |
|---|---:|
| 2001년 | 71.0% |
| 2002년 | 72.5% |
| 2003년 | 69.7% |
| 2004년 | 68.9% |
| 2005년 | 68.1% |
| 2006년 | 65.6% |
| 2007년 | 약 70%대 |
| 2008년 | 약 70%대 |
| 2009년 | 약 70%대 |

BCN 자료는 니카라과의 외화예금 비중이 장기간 높은 수준에 있었음을 보여줍니다. [bcn.gob](https://www.bcn.gob.ni/sites/default/files/documentos/macroeconomic_yearbook_2009.pdf)

## TD 자료

BCN의 2009년 통계연보에서 확인되는 총예금은 다음과 같습니다.

| 기준연도 | 총예금 TD |
|---|---:|
| 2001년 | NIO 20,694.2 million |
| 2002년 | NIO 23,471.3 million |
| 2003년 | NIO 27,253.6 million |
| 2004년 | NIO 31,701.5 million |
| 2005년 | NIO 35,692.6 million |
| 2006년 | NIO 39,277.2 million |
| 2007년 | NIO 46,057.9 million |
| 2008년 | NIO 49,621.3 million |
| 2009년 | NIO 57,148.5 million |

이 자료의 `Total deposits`는 BCN의 금융시스템 통계상 예금 총액이며, 중앙은행과 민간 금융시스템의 범위가 표에 따라 다를 수 있으므로 최신 BCN 월별 원자료와 결합할 때 정의를 확인해야 합니다. [bcn.gob](https://www.bcn.gob.ni/sites/default/files/documentos/macroeconomic_yearbook_2009.pdf)

## 2023년 절대액 사용 시 주의

IMF의 2023년 보고서는 2023년 9월 FCD/TD 비율 약 70%를 명확히 제시하지만, 검색 가능한 본문에서 같은 기준일의 FCD와 TD 절대액을 표 형태로 함께 제공하지는 않습니다. 따라서 다음처럼 분리해 저장하는 것이 좋습니다.

```text
country: Nicaragua
date: 2023-09-30
fcd_td: 0.70
fcd: NA
td: NA
source: IMF 2023 Article IV
source_type: reported_ratio
```

BCN 월별 원자료에서 FCD와 TD 절대액을 확보하면 다음과 같이 계산할 수 있습니다.

\[
FCD/TD
=
\frac{FCD_{\text{NIO million}}}
{TD_{\text{NIO million}}}
\]

외화예금을 USD로 보유한 뒤 NIO 기준 TD와 비교할 경우에는 반드시 BCN의 해당 월말 환율로 환산해야 합니다.

## 해석

니카라과는 부분적 달러화 국가 중에서도 예금 달러화율이 매우 높은 편입니다. IMF는 2023년 9월 기준 예금의 약 70%가 외화예금이라고 평가하며, 이는 높은 송금 유입과 금융기관의 외화 취급 관행, 그리고 코르도바에 대한 달러 선호를 반영합니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2024/018/article-A001-en.xml)

### 핵심 결과

- **2023년 9월 FCD/TD:** 약 **70%**.
- **2017년 FCD/TD:** 약 75%.
- **BCN 장기 통계:** 2000년대에도 대체로 65~73% 수준.
- **최신 절대 FCD·TD:** BCN 월별 원자료에서 추가 추출 필요.
- **데이터셋 권장값:** 2023-09 `fcd_td = 0.70`, FCD·TD 절대액은 우선 결측 처리.

네팔은 **네팔 중앙은행(Nepal Rastra Bank, NRB)**이 총예금과 외화예금을 모두 통계로 관리합니다. 다만 최신 월별 경제보고서에는 TD가 공개되지만, FCD 잔액은 검색 가능한 요약표에 매번 함께 표시되지 않아 **같은 기준일의 최신 FCD/TD를 바로 계산하기는 어렵습니다.**

## 확인 가능한 최신 TD

단위: **NPR billion**

| 기준시점 | 예금 범위 | TD |
|---|---|---:|
| 2025년 7월 중순 | 은행 및 금융기관(BFIs) | **7,264** |
| 2026년 1월 중순 | 은행 및 금융기관(BFIs) | **7,681.35** |
| 2026년 2월 중순 | 은행 및 금융기관(BFIs) | **7,697.59** |
| 2026년 4월 중순 | 은행 및 금융기관(BFIs) | **7,879.54** |
| 2026년 5월 중순 | 은행 및 금융기관(BFIs) | **7,949.28** |
| 2026년 8월 10일 전후 | 전체 금융기관 | **약 8,244** |

NRB는 2025년 7월 중순 BFIs 예금을 **NPR 7,264 billion**, 2026년 4월 중순을 **NPR 7,879.54 billion**, 2026년 5월 중순을 **NPR 7,949.28 billion**으로 보고합니다. [nrb.org](https://www.nrb.org.np/red/current-macroeconomic-and-financial-situation-english-based-on-ten-months-data-of-2025-26/)

NRB 홈페이지의 최신 지표는 2026년 8월 기준 전체 금융기관 예금 약 **NPR 8,244 billion**, 상업은행 예금 약 **NPR 7,441 billion**으로 표시합니다. [nrb.org](https://www.nrb.org.np/)

## 확인 가능한 FCD

NRB의 Banking and Financial Statistics 및 연차보고서에는 다음 항목이 있습니다.

- Foreign Currency Deposits.
- Deposits in domestic currency.
- Deposits in foreign currency.
- Deposits at banks and financial institutions.
- Commercial-bank deposits.
- Development-bank 및 finance-company deposits.

2020/21 연차보고서에서 확인되는 외화예금은 **NPR 117,674.8 million**입니다. 같은 보고서의 총예금은 **NPR 4,662,729.3 million**으로 제시됩니다. [nrb.org](https://www.nrb.org.np/contents/uploads/2022/05/Annual-Report-2020-21-English.pdf)

## 계산 가능한 과거 FCD/TD

단위: **NPR million**

| 기준연도 | FCD | TD | FCD/TD |
|---|---:|---:|---:|
| 2020/21 | 117,674.8 | 4,662,729.3 | **2.52%** |

계산식:

\[
FCD/TD
=
\frac{117,674.8}{4,662,729.3}
=
2.5237\%
\]

따라서 약 **2.52%**입니다.

다만 이 값은 NRB 연차보고서의 FCD와 TD 표를 이용한 계산이며, FCD가 상업은행 중심이고 TD가 전체 BFIs 기준일 가능성이 있으므로, 국가 간 비교에서는 **표의 적용 범위가 완전히 같은지 확인한 뒤 사용**하는 것이 좋습니다.

## 최신 FCD/TD

현재 확인 가능한 최신 공식자료는 TD가 더 최신입니다.

| 기준시점 | FCD | TD | FCD/TD |
|---|---:|---:|---:|
| 2020/21 | NPR 117.675bn | NPR 4,662.729bn | **2.52%** |
| 2025년 7월 중순 | 최신 동일 기준 FCD 미확인 | NPR 7,264bn | N/A |
| 2026년 5월 중순 | 최신 동일 기준 FCD 미확인 | NPR 7,949.28bn | N/A |

NRB의 2024/25 Financial Stability Report는 2025년 7월 중순 예금 구성에서 요구불예금 7.23%, 저축예금 36.60%, 정기예금 48.02%, call deposits 7.49%, 기타예금 0.66%를 제시하지만, 이 표는 통화별 FCD를 분리하지 않습니다. [nrb.org](https://www.nrb.org.np/contents/uploads/2026/07/Financial-Stability-Report-Issue-17-1-1.pdf)

## 데이터셋 입력 권장값

```text
country,date,fcd_npr_million,td_npr_million,fcd_td,scope
Nepal,2021-07,117674.8,4662729.3,0.025237,annual_report
Nepal,2025-07,NA,7264000,NA,BFIs
Nepal,2026-01,NA,7681350,NA,BFIs
Nepal,2026-02,NA,7697590,NA,BFIs
Nepal,2026-04,NA,7879540,NA,BFIs
Nepal,2026-05,NA,7949280,NA,BFIs
```

### 결론

- **가장 명확한 계산값:** 2020/21 FCD/TD 약 **2.52%**.
- **최신 TD:** 2026년 5월 중순 BFIs 기준 **NPR 7,949.28 billion**.
- **최신 FCD:** NRB의 세부 Banking and Financial Statistics 원표에서 추출 필요.
- **2026년 전체 금융기관 TD:** 약 **NPR 8,244 billion**.
- 최신 FCD를 확보하면 반드시 동일한 범위, 즉 `commercial banks only` 또는 `all BFIs` 기준으로 TD를 맞춰 계산해야 합니다.


뉴질랜드는 **뉴질랜드중앙은행(RBNZ)**이 은행권 총예금과 외화예금을 관리합니다. RBNZ 자료에 따르면 외화예금은 전체 예금의 약 **2.7%**로, FCD/TD가 낮은 국가에 해당합니다. [rbnz.govt](https://www.rbnz.govt.nz/-/media/project/sites/rbnz/files/proactive-releases/13-explanatory-note-for-introduction-of-the-deposit-takers-bill.pdf)

## 확인 가능한 FCD/TD

| 기준 | FCD/TD | FCD | TD |
|---|---:|---:|---:|
| RBNZ 정책자료 기준 | **약 2.7%** | 동일 기준 절대액 미제시 | 전체 예금의 2.7% |
| 2025년 5월 은행권 | 약 2.7% 적용 시 약 NZD 12.79bn | 추정 | **NZD 473.662bn** |

RBNZ는 외화예금이 뉴질랜드 등록은행 전체 예금의 약 **2.7%**라고 설명합니다. 이 수치는 예금보호제도(DCS) 설계 과정에서 사용된 공식 정책자료의 수치입니다. [rbnz.govt](https://www.rbnz.govt.nz/-/media/project/sites/rbnz/files/proactive-releases/13-explanatory-note-for-introduction-of-the-deposit-takers-bill.pdf)

## 최신 TD

RBNZ의 `S40 Banks: Liabilities – Deposits by sector`에서 2025년 5월 기준 전체 예금은 다음과 같습니다.

단위: **NZD million**

| 구분 | 2025년 5월 |
|---|---:|
| 거주자 예금 | 438,600 |
| 비거주자 예금 | 35,062 |
| **전체 예금 TD** | **473,662** |
| 거래성 예금 | 129,905 |
| 저축성 예금 | 114,830 |
| 정기예금 | 228,927 |

RBNZ의 S40 표는 2025년 5월 은행권 전체 예금을 **NZD 473,662 million**, 즉 약 **NZD 473.662 billion**으로 보고합니다. 이 TD는 거주자와 비거주자 예금을 모두 포함하며, 외화 잔액은 NZD로 환산되어 포함됩니다. [rbnz.govt](https://www.rbnz.govt.nz/statistics/series/registered-banks/banks-liabilities-deposits-by-sector)

## FCD 추정액

RBNZ가 제시한 외화예금 비중 2.7%를 2025년 5월 TD에 적용하면:

\[
FCD
=
473.662 \times 2.7\%
=
12.789\text{ billion NZD}
\]

따라서 정책자료의 2.7%를 적용한 추정값은 다음과 같습니다.

| 기준월 | TD | FCD 추정치 | FCD/TD |
|---|---:|---:|---:|
| 2025년 5월 | NZD 473.662bn | 약 NZD 12.789bn | **약 2.70%** |

다만 FCD 절대액은 RBNZ가 해당 정책자료에서 직접 제시한 값이 아니라, 공식 비율과 TD를 이용한 역산값입니다.

## RBNZ 원자료의 장점

RBNZ의 은행 대차대조표 통계는 국내통화와 외화로 표시된 자산·부채를 모두 다룹니다. 외화 잔액은 해당 월말 환율을 이용해 NZD로 환산됩니다. [rbnz.govt](https://www.rbnz.govt.nz/statistics/series/registered-banks/banks-liabilities-deposits-by-sector)

관련 표는 다음과 같습니다.

- `S40 Banks: Liabilities – Deposits by sector`
- `S45 Banks: Liabilities – Deposits by size (value)`
- `S10 Banks: Balance sheet`
- `F5 Banks: Foreign currency assets and liabilities`

특히 S40은 예금 총액과 예금자 부문을 제공하고, RBNZ의 정의상 외화예금도 포함하는 구조입니다. [rbnz.govt](https://www.rbnz.govt.nz/statistics/series/registered-banks/banks-liabilities-deposits-by-sector)

## 분모 정의 주의

RBNZ의 S45 예금 규모별 통계는 **NZD 예금만 포함하고 외화예금은 포함하지 않습니다.** 따라서 FCD/TD 계산에는 S45를 사용하면 안 됩니다. [rbnz.govt](https://www.rbnz.govt.nz/statistics/series/registered-banks/banks-liabilities-deposits-by-size-value)

FCD/TD의 분모는 다음 중 S40의 `All deposits – Total (Gross)`를 사용하는 것이 적절합니다.

\[
TD =
\text{Resident deposits}
+
\text{Non-resident deposits}
\]

2025년 5월:

\[
TD
=
438,600+35,062
=
473,662\text{ million NZD}
\]

## 데이터셋 입력 권장값

```text
country,date,fcd_nzd_million,td_nzd_million,fcd_td,source_type
New Zealand,2025-05,12789.0,473662.0,0.027,policy_estimate
```

또는 절대 FCD 추정치를 공식값과 구분하려면:

```text
country,date,fcd_nzd_million,td_nzd_million,fcd_td
New Zealand,2025-05,NA,473662.0,0.027
```

### 핵심 결과

- **2025년 5월 TD:** NZD 473.662 billion.
- **공식 정책자료상 FCD/TD:** 약 **2.7%**.
- **FCD 역산 추정치:** 약 NZD 12.789 billion.
- **권장 원자료:** RBNZ S40.
- **주의:** S45는 NZD 예금만 포함하므로 FCD/TD 분모로 사용하지 않음.


오만은 **오만중앙은행(Central Bank of Oman, CBO)**이 외화예금과 총예금을 직접 공개하며, 통계표에 **“Foreign Currency Deposits to Total Deposits”**라는 FCD/TD 지표를 별도로 제공합니다. 따라서 오만은 FCD/TD 시계열 구축이 가능한 국가입니다. [cbo.gov](https://cbo.gov.om/sites/assets/Documents/English/Publications/MonthlyBulletins/MonthlyStatisticalBulletinJuly%202025%20En.pdf)

## 최신 TD

단위: **OMR billion**

| 기준시점 | 총예금 TD |
|---|---:|
| 2023년 4월 | 27.1 |
| 2024년 2월 | 30.0 |
| 2024년 5월 | 약 30.0 |
| 2024년 말 | **31.7** |

오만 재무부는 2024년 말 은행권 총예금이 전년보다 9.1% 증가하여 **OMR 31.7 billion**에 도달했다고 발표했습니다. [fm.gov](https://www.fm.gov.om/en/31278/)

## FCD/TD 공식 지표

CBO 월간·분기별 통계에는 다음 항목이 있습니다.

- Total Rial Omani Deposits.
- Total Foreign Currency Deposits.
- Total Deposits.
- Foreign Currency Deposits to Total Deposits.
- Foreign Currency Credit to Total Credit.

CBO의 2024년 4월 Monthly Statistical Bulletin은 FCD/TD 지표를 월별로 제공하며, 검색 가능한 표에는 다음과 같은 값이 표시됩니다.

| 관측값 | FCD/TD |
|---|---:|
| 2023년 초 전후 | 12.5~13.1% |
| 2023년 중반 | 13.5~15.4% |
| 2023년 말 | 15.6~18.2% |
| 2024년 초 | 약 18%대 |

CBO의 표에는 FCD/TD가 12.5%, 13.1%, 12.8%, 13.5%, 14.5%, 15.3%, 15.4%, 15.6%, 17.6%, 18.2%, 18.1%, 17.2% 등의 월별 값으로 나타납니다. [cbo.gov](https://cbo.gov.om/sites/assets/Documents/English/Publications/MonthlyBulletins/MonthlyStatisticalBulletinApril2024En.pdf)

## 확인 가능한 외화예금 금액

CBO의 통계표는 예금을 현지통화와 외화로 분리합니다. 예를 들어 2024년 3월 분기통계에는 다음과 같은 구조가 포함됩니다.

```text
Total Rial Omani Deposits
Total Foreign Currency Deposits
Total Deposits
```

또한 2018년 이후 표에서 요구불·저축·정기·상업선불예금을 각각 현지통화와 외화로 나누고, 마지막에 총예금을 제시합니다. [cbo.gov](https://cbo.gov.om/sites/assets/Documents/English/Publications/QuarterlyBulletins/2024/QBMarch2024En.pdf)

2024년 7월 보도자료 기준으로는 민간부문 예금 중 외화예금이 **OMR 1,980.5 million**, 현지통화 예금이 **OMR 14,058.3 million**으로 제시되며, 해당 보도자료는 외화예금의 총예금 대비 비중을 **16.7%**로 보고합니다. 다만 이 수치는 전체 은행권이 아니라 **민간부문 예금 기준**일 가능성이 있으므로, 국가 전체 FCD/TD 시계열에는 CBO의 월간 통계표를 우선 사용해야 합니다. [omanobserver](https://www.omanobserver.om/article/1156545/business/banking/private-bank-deposits-in-oman-increase-by-88)

## 계산식

CBO 표의 총액을 직접 사용하면:

\[
TD =
\text{Total Rial Omani Deposits}
+
\text{Total Foreign Currency Deposits}
\]

\[
FCD/TD
=
\frac{\text{Total Foreign Currency Deposits}}
{\text{Total Deposits}}
\]

예를 들어 민간부문 수치만 이용하면:

\[
TD_{\text{private}}
=
14,058.3+1,980.5
=
16,038.8\text{ million OMR}
\]

\[
FCD/TD_{\text{private}}
=
\frac{1,980.5}{16,038.8}
=
12.35\%
\]

하지만 보도자료가 별도로 16.7%를 제시하므로, 해당 두 금액과 비율은 서로 다른 분모 또는 통계 범위를 사용했을 가능성이 있습니다. 따라서 이 계산값을 공식 FCD/TD로 사용하지 말고, CBO 표의 직접 보고 비율을 우선 사용해야 합니다.

## 데이터셋 입력 권장값

가장 안전한 입력은 CBO가 직접 보고한 FCD/TD를 사용하는 것입니다.

```text
country,date,fcd_td,fcd_omr_million,td_omr_million,scope
Oman,2024-04,NA,NA,NA,banking_sector
Oman,2024-12,NA,NA,31700,banking_sector
```

CBO 월간 PDF에서 월별 `Foreign Currency Deposits to Total Deposits` 행의 날짜와 값을 추출하면 다음 구조로 만들 수 있습니다.

```text
country,date,fcd_omr_million,td_omr_million,fcd_td
Oman,2023-01,[CBO],[CBO],[CBO]
Oman,2023-02,[CBO],[CBO],[CBO]
...
Oman,2024-12,[CBO],[CBO],[CBO]
```

## 결론

- **2024년 말 TD:** OMR 31.7 billion.
- **CBO 공식 FCD/TD 지표:** 월별로 제공.
- **확인 가능한 FCD/TD 범위:** 2023년 약 12.5~18.2% 구간, 2024년 초 약 18%대.
- **민간부문 2024년 외화예금:** OMR 1.981 billion.
- **권장 원자료:** CBO Monthly Statistical Bulletin 및 Data.gov.om의 `Foreign currency Total Deposits` 시계열.
- **주의:** 민간부문 비율과 전체 은행권 비율을 혼합하지 않아야 함.


파키스탄은 **파키스탄 국립은행(State Bank of Pakistan, SBP)**이 외화예금(FCD)과 예정은행(scheduled banks)의 총예금(TD)을 각각 월별·주별로 공개합니다. 최신으로 확인되는 2026년 2월 기준으로 FCD는 **USD 6.917 billion**, 총예금은 **PKR 29,814.6 billion**이며, 환산 기준 FCD/TD는 약 **6.5%**입니다. [easydata.sbp.org](https://easydata.sbp.org.pk/apex/f?p=10:211:23807261003320::NO::P211_DATASET_TYPE_CODE,P211_PAGE_ID:TS_GP_BOP_FCD_M,210&cs=182687764F001F36E3F81764FB786D94E)

## 최신 FCD/TD

기준시점: **2026년 2월**  
단위: FCD는 USD billion, TD는 PKR billion

| 항목 | 값 |
|---|---:|
| 외화예금 FCD | USD 6.917bn |
| 총예금 TD | PKR 29,814.6bn |
| 적용 환율 | 약 PKR 279.3/USD |
| FCD 환산액 | 약 PKR 1,932bn |
| **FCD/TD** | **약 6.48%** |

계산식:

\[
FCD_{\text{PKR}}
=
6.917\times279.3
=
1,932.0\text{ billion PKR}
\]

\[
FCD/TD
=
\frac{1,932.0}{29,814.6}
=
6.48\%
\]

FCD는 SBP EasyData의 `Total Foreign Currency Deposits (FE-25)` 월별 시계열이며, TD는 SBP의 `Total Deposits with Banks` 통계입니다. [sbp.org](https://www.sbp.org.pk/assets/document/publications/MPIC_March_2026.pdf)

## 최근 추이

SBP 자료를 인용한 보도에 따르면 외화예금은 2025년 중 다음과 같이 움직였습니다.

| 기준월 | FCD, USD billion |
|---|---:|
| 2025년 6월 | 6.9878 |
| 2025년 7월 | 6.9214 |
| 2025년 8월 | 7.0044 |
| 2025년 9월 | 7.0557 |
| 2025년 10월 | 7.0184 |
| 2025년 11월 | 6.8773 |
| 2026년 2월 | **6.9170** |

2025년 6월 FCD는 USD 6,987.82 million이었고, 2025년 11월에는 USD 6,877.33 million으로 감소했습니다. [inp.net](https://www.inp.net.pk/article-detail/inp-wealthpk/sbp-reports-steady-growth-in-foreign-currency-deposits-and-borrowings)

## TD 원자료

SBP의 공식 Economic Data 페이지는 다음 총예금 자료를 제공합니다.

- `Total Deposits of Scheduled Banks – Stock`.
- `Total Deposits with Banks` 주별 통계.
- `Deposits Distributed by Category of Deposit Holders`.
- `Depository Corporations Survey`.
- `Other Depository Corporations Survey`.

SBP의 2026년 3월 Monetary Policy Information Compendium은 2026년 2월 총예금을 **PKR 29,814.6 billion**으로 표시합니다. [sbp.org](https://www.sbp.org.pk/assets/document/publications/MPIC_March_2026.pdf)

참고로 SBP의 주별 broad-money 자료는 2026년 7월까지 예정은행 총예금을 제공하므로, 월별 FCD와 주별 TD를 결합할 때는 동일한 기준일을 맞추는 것이 좋습니다. [easydata.sbp.org](https://easydata.sbp.org.pk/apex/f?p=10:220:::NO:RP:P220_SERIES_KEY,P220_ACTION,P220_PAGE_ID:TS_GP_BAM_M2_W.M000030,New,211&cs=17BF0052E2560ABD8082B932EDDAB1803)

## 데이터셋 입력

```text
country,date,fcd_usd_billion,td_pkr_billion,fx_rate_pkr_per_usd,fcd_pkr_billion,fcd_td
Pakistan,2026-02,6.917,29814.6,279.3,1932.0,0.0648
```

또는 환율 변환으로 인한 추정임을 분명히 하려면:

```text
country,date,fcd,td,fcd_td,source_type
Pakistan,2026-02,6.917,29814.6,0.0648,converted_from_usd
```

## 정의상 주의점

파키스탄의 FCD와 TD는 SBP에서 서로 다른 통화 단위로 공개될 수 있습니다.

\[
FCD =
\text{외화예금의 USD 표시액}
\]

\[
TD =
\text{예정은행 총예금의 PKR 표시액}
\]

따라서 FCD/TD를 계산할 때는 반드시 FCD를 월말 환율로 PKR로 환산해야 합니다. 외화예금에 외국환은행의 해외차입금이나 파키스탄의 외환보유액을 포함하면 안 됩니다.

또한 `Total Foreign Currency Deposits`에는 거주자 및 비거주자 외화예금, 외화계좌 유형별 잔액 등이 포함될 수 있으므로, 한국·태국처럼 **거주자 FCD만** 사용하는 국가와 비교할 때는 범위 차이를 별도 메모해야 합니다.

### 핵심 결과

- **2026년 2월 FCD:** USD 6.917 billion.
- **2026년 2월 TD:** PKR 29,814.6 billion.
- **FCD 환산액:** 약 PKR 1,932 billion.
- **FCD/TD:** 약 **6.48%**.
- **권장 원자료:** SBP EasyData `FCD00` 및 SBP `Total Deposits with Banks`.