수단은 **수단중앙은행(Central Bank of Sudan, CBOS)**의 2018년 연차보고서에서 외화예금과 총예금을 함께 확인할 수 있습니다. 현재 공개자료에서 동일 기준으로 계산 가능한 최신 공식 수치는 **2018년 말 FCD/TD 약 39.9%**입니다. [cbos.gov](https://cbos.gov.sd/sites/default/files/CBOS%20-%2058th%20Annual%20Report%202018.pdf)

## 최신 계산 가능 수치

단위: **SDG billion, 기말 잔액**

| 기준연도 | 현지통화 예금 | 외화예금 FCD | 총예금 TD | FCD/TD |
|---|---:|---:|---:|---:|
| 2017년 | 124.9 | 27.7 | 152.6 | 18.15% |
| 2018년 | **210.5** | **139.8** | **350.3** | **39.91%** |

2018년 계산:

\[
TD
=
210.5+139.8
=
350.3\text{ billion SDG}
\]

\[
FCD/TD
=
\frac{139.8}{350.3}
=
39.91\%
\]

CBOS는 2017년 말 은행예금이 SDG 152.6 billion, 이 중 현지통화 예금이 SDG 124.9 billion, 외화예금이 SDG 27.7 billion이었다고 보고합니다. 2018년 말에는 총예금이 SDG 350.3 billion, 현지통화 예금이 SDG 210.5 billion, 외화예금이 SDG 139.8 billion으로 증가했습니다. [cbos.gov](https://cbos.gov.sd/sites/default/files/CBOS%20-%2058th%20Annual%20Report%202018.pdf)

## 데이터셋 입력값

```text
country,date,local_currency_deposits_sdg_billion,fcd_sdg_billion,td_sdg_billion,fcd_td
Sudan,2017-12-31,124.9,27.7,152.6,0.1815
Sudan,2018-12-31,210.5,139.8,350.3,0.3991
```

## 외화예금 증가

2017년에서 2018년 사이:

\[
\Delta FCD
=
139.8-27.7
=
112.1\text{ billion SDG}
\]

\[
\text{FCD 증가율}
=
\frac{139.8}{27.7}-1
=
404.7\%
\]

FCD/TD는 18.15%에서 39.91%로 약 **21.76%p 상승**했습니다. 다만 2018년의 외화예금 급증에는 환율 변화와 외화예금의 현지통화 환산액 증가가 크게 작용했을 가능성이 있으므로, 단순한 외화자금 유입으로만 해석해서는 안 됩니다.

## 범위 주의

CBOS 연차보고서에는 외화예금에 대해 서로 다른 범위의 수치가 나타납니다.

- 전체 은행예금 구성:
  - 2018년 총예금: SDG 350.3 billion.
  - 외화예금: SDG 139.8 billion.
- 운영은행의 외화예금:
  - 2018년 외화예금: 약 SDG 105,887.9 million.

따라서 `SDG 139.8 billion`은 전체 은행예금 구성표 기준, `SDG 105.8879 billion`은 별도 운영은행·예금자 범위 기준으로 보입니다. 두 값을 혼합하지 말고, 국가 간 FCD/TD에는 **동일 표의 FCD와 TD**, 즉 139.8 / 350.3을 사용하는 것이 좋습니다. [cbos.gov](https://cbos.gov.sd/sites/default/files/CBOS%20-%2058th%20Annual%20Report%202018.pdf)

## 최신자료 한계

2018년 이후 수단은 정치·경제 불안과 2023년 내전으로 인해 중앙은행 통계의 연속성이 크게 약화되었습니다. 검색 가능한 국제자료에는 2018년 이후의 최신 수단 전체 은행권 FCD와 TD를 동일 기준으로 제공하는 공식 시계열이 확인되지 않습니다.

CEIC에는 2018년 9월 외화예금이 SDG 61,492 million으로 표시되지만, 이는 CBOS 연차보고서의 전체 은행예금 구성표와 범위·시점이 다르므로 2018년 말 FCD/TD 계산에는 사용하지 않는 것이 안전합니다. [ceicdata](https://www.ceicdata.com/en/sudan/deposits-banks/banks-deposits-in-foreign-currency)

### 핵심 결과

- **2018년 말 TD:** SDG 350.3 billion.
- **2018년 말 FCD:** SDG 139.8 billion.
- **2018년 말 FCD/TD:** **39.91%**.
- **2017년 말 FCD/TD:** 18.15%.
- **최신 동일 기준 공식 수치:** 2018년.
- 2019년 이후는 FCD·TD 모두 결측 처리하고, 추가로 CBOS 원자료를 요청하는 것이 적절합니다.


르완다는 **르완다중앙은행(National Bank of Rwanda, BNR)**과 르완다 통계연감에서 외화예금과 총예금을 모두 확인할 수 있습니다. 최신으로 확인되는 **2024년 6월 말 기준 FCD/TD는 약 38.25%**이며, 총예금은 **RWF 4,850.81 billion**, 외화예금은 **RWF 1,855.597 billion**입니다. [statistics.gov](http://www.statistics.gov.rw/sites/default/files/documents/2026-01/Rwanda_Statistical_Yearbook_2025.xlsx)

## 최신 FCD/TD

단위: **RWF billion, 6월 말 잔액**

| 기준시점 | 총예금 TD | 외화예금 FCD | FCD/TD |
|---|---:|---:|---:|
| 2018년 6월 | 1,891.322 | 514.026 | 27.18% |
| 2019년 6월 | 2,177.243 | 511.563 | 23.50% |
| 2020년 6월 | 2,577.350 | 658.164 | 25.54% |
| 2021년 6월 | 3,050.015 | 841.590 | 27.59% |
| 2022년 6월 | 3,691.150 | 1,053.922 | 28.55% |
| 2023년 6월 | 4,584.580 | 1,516.609 | 33.08% |
| **2024년 6월** | **4,850.810** | **1,855.597** | **38.25%** |

르완다 통계연감의 원자료는 총예금을 `Deposits`, 외화예금을 `Foreign currency deposits`로 분리해 제공하며, 2024년 6월 값은 각각 RWF 4,850.81 billion과 RWF 1,855.597 billion입니다. [statistics.gov](http://www.statistics.gov.rw/sites/default/files/documents/2026-01/Rwanda_Statistical_Yearbook_2025.xlsx)

## 2024년 계산

\[
FCD/TD
=
\frac{1,855.597}{4,850.810}
=
38.25\%
\]

2024년 외화예금의 총예금 대비 비율은 약 **38.3%**입니다.

2023년 6월의 33.08%와 비교하면:

\[
38.25\%-33.08\%
=
5.17\text{ percentage points}
\]

즉, 2023년 6월부터 2024년 6월 사이 FCD/TD가 약 **5.2%p 상승**했습니다.

## 예금 구성

2024년 6월 기준 총예금은 다음과 같이 구성됩니다.

| 구성요소 | RWF billion |
|---|---:|
| Transferable deposits in RWF | 1,938.342 |
| Other deposits in RWF | 1,056.872 |
| Foreign currency deposits | 1,855.597 |
| **총예금** | **4,850.810** |

검산:

\[
1,938.342+1,056.872+1,855.597
=
4,850.811
\]

반올림 오차를 제외하면 총예금 4,850.810과 일치합니다. [statistics.gov](http://www.statistics.gov.rw/sites/default/files/documents/2026-01/Rwanda_Statistical_Yearbook_2025.xlsx)

## 최신 추세

BNR의 2024년 Monetary Policy Report는 2024년 6월 외화예금이 전년 대비 **43.9% 증가**했다고 설명합니다. 외화예금 증가율이 현지통화 예금보다 높아지면서 FCD/TD가 2023년 33.1%에서 2024년 38.3%로 상승한 것으로 해석할 수 있습니다. [cabri-sbo](https://www.cabri-sbo.org/uploads/bia/Rwanda_2023_Execution_External_InYearReport_Institution_EACECCASCOMESA_English_89785f.pdf)

르완다 통계연감의 외화예금 시계열은 다음과 같습니다.

```text
2018-06: 514.0263
2019-06: 511.5633
2020-06: 658.1643
2021-06: 841.5896
2022-06: 1053.922
2023-06: 1516.609
2024-06: 1855.597
```

## 데이터셋 입력

```text
country,date,fcd_rwf_billion,td_rwf_billion,fcd_td
Rwanda,2018-06-30,514.0263,1891.322,0.2718
Rwanda,2019-06-30,511.5633,2177.243,0.2350
Rwanda,2020-06-30,658.1643,2577.350,0.2554
Rwanda,2021-06-30,841.5896,3050.015,0.2759
Rwanda,2022-06-30,1053.9220,3691.150,0.2855
Rwanda,2023-06-30,1516.6090,4584.580,0.3308
Rwanda,2024-06-30,1855.5970,4850.810,0.3825
```

### 핵심 결과

- **2024년 6월 TD:** RWF 4,850.810 billion.
- **2024년 6월 FCD:** RWF 1,855.597 billion.
- **2024년 6월 FCD/TD:** **38.25%**.
- **2023년 6월 FCD/TD:** 33.08%.
- **전년 대비 상승폭:** 약 5.17%p.
- 르완다는 최근 외화예금이 빠르게 증가하여 FCD/TD 시계열을 구축하기에 적합한 국가입니다.


루마니아는 **루마니아국립은행(BNR)**이 거주자 비정부부문 예금을 현지통화와 외화로 나누어 공개합니다. 최신 확인 수치인 **2026년 6월 말 기준 FCD/TD는 32.6%**, 총예금은 **RON 680,925.4 million**이며, 외화예금은 역산하면 약 **RON 221,982 million**입니다. [bnr](https://www.bnr.ro/en/25673-2026-07-23-monetary-indicators-june-2026)

## 최신 FCD/TD

기준일: **2026년 6월 말**  
범위: **거주자 비정부 고객 예금**  
단위: **RON million**

| 항목 | 금액 |
|---|---:|
| 총예금 TD | **680,925.4** |
| 외화예금 비중 FCD/TD | **32.6%** |
| 외화예금 FCD 추정액 | **221,981.7** |
| 현지통화 예금 추정액 | 458,943.7 |

BNR은 2026년 6월 외화표시 거주자 예금이 비정부 고객 총예금의 **32.6%**라고 보고합니다. 같은 시점의 거주자 비정부 예금은 전월보다 0.4% 감소한 **RON 680,925.4 million**입니다. [bnr](https://www.bnr.ro/en/25673-2026-07-23-monetary-indicators-june-2026)

계산식:

\[
FCD
=
680,925.4\times32.6\%
=
221,981.7\text{ million RON}
\]

\[
FCD/TD
=
\frac{221,981.7}{680,925.4}
=
32.60\%
\]

## 최근 추이

| 기준시점 | TD | FCD/TD | FCD |
|---|---:|---:|---:|
| 2025년 6월 | 629,200 | 32.66% | 205,500 |
| 2025년 7월 | 약 635,100 | 32.5% | 206,400 |
| 2026년 5월 | 683,365.8 | 32.3% | 약 220,727 |
| **2026년 6월** | **680,925.4** | **32.6%** | **약 221,982** |

2025년 6월에는 현지통화 예금이 RON 423.6 billion, 외화예금이 RON 205.5 billion, 총예금이 RON 629.2 billion이었습니다. 이를 계산하면 FCD/TD는 약 32.66%입니다. [romania-insider](https://www.romania-insider.com/bank-deposits-ro-first-half-jul-2025)

2026년 5월에는 거주자 비정부 예금이 RON 683.3658 billion, 외화예금 비중은 32.3%였습니다. [seenews](https://seenews.com/news/bank-deposit-growth-in-romania-accelerates-in-may-1297101)

## 정의

BNR의 지표는 일반적인 은행권 전체 예금이 아니라 다음 범위입니다.

\[
TD=
\text{비정부 거주자 고객의 RON 예금}
+
\text{비정부 거주자 고객의 외화예금}
\]

\[
FCD/TD=
\frac{\text{거주자 비정부 고객의 외화예금}}
{\text{거주자 비정부 고객의 총예금}}
\]

외화예금은 BNR 통계에서 국내통화인 RON으로 환산되어 표시됩니다. 따라서 별도의 환율 변환 없이 FCD와 TD를 직접 나눌 수 있습니다.

## 데이터셋 입력

```text
country,date,fcd_ron_million,td_ron_million,fcd_td,scope
Romania,2025-06,205500.0,629200.0,0.3266,resident_non_government
Romania,2025-07,206400.0,635100.0,0.3250,resident_non_government
Romania,2026-05,220727.0,683365.8,0.3230,resident_non_government
Romania,2026-06,221981.7,680925.4,0.3260,resident_non_government
```

2026년 6월 FCD 절대액은 BNR이 보고한 비율과 총예금을 곱한 **역산값**입니다. BNR 원자료에서 통화별·예금자별 금액을 직접 추출할 경우 반올림 차이가 발생할 수 있습니다.

## 주의점

루마니아에는 다음과 같은 서로 다른 분모가 사용될 수 있습니다.

- 거주자 비정부 고객 예금.
- 전체 국내 은행 예금.
- 가계 예금.
- 가계·기업을 포함한 비정부 고객 예금.
- 정부 및 비거주자 예금을 포함한 전체 은행권 예금.

국가 간 FCD/TD 비교에는 BNR이 직접 비율을 제시하는 **거주자 비정부 고객 기준**을 사용하는 것이 가장 일관적입니다. 2026년 6월 기준 값은:

\[
\boxed{FCD/TD=32.6\%}
\]

### 핵심 결과

- **2026년 6월 TD:** RON 680.9254 billion.
- **2026년 6월 FCD:** 약 RON 221.982 billion.
- **2026년 6월 FCD/TD:** **32.6%**.
- **2025년 6월 FCD/TD:** 약 32.66%.
- 권장 범위: **resident non-government customer deposits**.



카타르는 **카타르중앙은행(Qatar Central Bank, QCB)**이 외화예금 비율을 통계로 제공하며, IMF 자료에서 최신으로 확인되는 **외화예금/총예금 비율은 38.8%**입니다. 2023년 은행권 고객예금은 약 **QAR 1.35 trillion**이므로, 이를 적용한 외화예금은 약 **QAR 523.8 billion**입니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2025/047/article-A001-en.xml)

## 최신 FCD/TD

기준연도: **2023년**  
단위: **QAR billion**

| 항목 | 값 |
|---|---:|
| 총예금 TD | 약 1,350 |
| FCD/TD | **38.8%** |
| FCD 추정액 | 약 523.8 |
| 현지통화 예금 추정액 | 약 826.2 |

계산식:

\[
FCD
=
1,350\times38.8\%
=
523.8\text{ billion QAR}
\]

\[
FCD/TD
=
\frac{523.8}{1,350}
=
38.8\%
\]

IMF의 카타르 Article IV 보고서는 외화예금/총예금 비율을 37.3%, 36.1%, 27.9%, 28.2%, 29.8%, 36.4%, 38.8%로 제시하며, 마지막 관측치가 최신입니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2025/047/article-A001-en.xml)

## 과거 비율 추이

| 관측값 | FCD/TD |
|---|---:|
| 1 | 37.3% |
| 2 | 36.1% |
| 3 | 27.9% |
| 4 | 28.2% |
| 5 | 29.8% |
| 6 | 36.4% |
| **7** | **38.8%** |

카타르의 FCD/TD는 2019~2021년경 28~30% 수준까지 낮아졌다가, 최근에는 36~39% 수준으로 다시 상승한 것으로 나타납니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2025/047/article-A001-en.xml)

## TD 원자료

QCB 및 관련 자료에서 확인되는 총예금 수치는 다음과 같습니다.

| 기준시점 | 총예금 TD |
|---|---:|
| 2020년 말 | QAR 905.508bn |
| 2023년 말 | 약 **QAR 1.35tn** |
| 2026년 6월 | 약 QAR 1.105tn* |

2020년 QCB 연차보고서에는 총예금이 QAR 905.508 billion으로 제시됩니다. [qcb.gov](https://www.qcb.gov.qa/PublicationFiles/2020_annual_year.pdf)

2023년 카타르 은행권 고객예금은 약 QAR 1.35 trillion으로 보고됩니다. [pwc](https://www.pwc.com/m1/en/publications/documents/2024/qatar-banking-sector-report-2024.pdf)

\* 2026년 6월 CEIC의 총예금 USD 303.589 billion에 QAR/USD 3.64를 적용한 환산값입니다.

\[
303.589\times3.64
\approx1,105.1\text{ billion QAR}
\]

이는 CEIC가 QCB 자료를 기반으로 제공하는 수치이며, 최신 QCB 원자료의 범위와 일치하는지 확인한 뒤 사용하는 것이 좋습니다. [ceicdata](https://www.ceicdata.com/en/indicator/qatar/total-deposits)

## FCD 절대액 주의

QCB 통계에서 외화예금은 다음 범위에 따라 다르게 나타날 수 있습니다.

- 정부부문 외화예금.
- 공공기관 외화예금.
- 민간부문 외화예금.
- 비거주자 예금.
- 상업은행 고객예금.
- QCB의 외화예금과 은행권 외화예금.

따라서 QCB의 외환보유액 중 `foreign bank balances`나 QCB가 보유한 외화예금을 은행 고객의 FCD로 사용하면 안 됩니다.

2023년 FCD 절대액은 IMF의 FCD/TD 비율과 은행권 고객예금을 이용한 **역산값**으로 보는 것이 안전합니다.

## 데이터셋 입력

```text
country,date,fcd_qar_billion,td_qar_billion,fcd_td,source_type
Qatar,2023-12-31,523.8,1350.0,0.388,implied_from_reported_ratio
```

과거 자료도 저장하려면:

```text
country,date,fcd_td
Qatar,2017-12-31,0.373
Qatar,2018-12-31,0.361
Qatar,2019-12-31,0.279
Qatar,2020-12-31,0.282
Qatar,2021-12-31,0.298
Qatar,2022-12-31,0.364
Qatar,2023-12-31,0.388
```

### 핵심 결과

- **2023년 TD:** 약 QAR 1.35 trillion.
- **2023년 FCD/TD:** **38.8%**.
- **2023년 FCD 추정액:** 약 QAR 523.8 billion.
- **2020년 TD:** QAR 905.508 billion.
- 최신 절대 FCD를 직접 확보하려면 QCB의 `Financial and Monetary Statistics`에서 외화예금과 총예금 원표를 같은 기준일로 추출해야 합니다.