남수단은 **남수단중앙은행(Bank of South Sudan, BoSS)**과 IMF 자료에서 총예금 및 외화예금 관련 지표를 일부 확인할 수 있습니다. 다만 최신 공개자료는 매우 제한적이며, **FCD와 TD의 절대액을 같은 기준으로 제공하는 최신 월별 시계열은 확인하기 어렵습니다.**

## 확인 가능한 FCD/TD

IMF의 남수단 Article IV 자료는 다음과 같은 `Share of foreign currency deposits to total deposits` 지표를 제공합니다.

| 기준연도·전망 | FCD/TD |
|---|---:|
| 2016년 | 0.6% |
| 2017년 | 0.7% |
| 2018년 | 0.7% |
| 2019년 | 0.6% |
| 2020년 | 0.7% |
| 2021년 | 0.7% |
| 2022년 전망 | 0.5% |
| 2023년 전망 | 0.3% |
| 2024년 전망 | 0.7% |

IMF 자료의 표기 단위는 퍼센트입니다. 따라서 가장 최근 확인 가능한 수치는 **2021년 0.7%**이며, 2022~2024년 값은 당시 IMF 전망치입니다. [imf](https://www.imf.org/-/media/files/publications/cr/2022/english/1ssdea2022001.pdf)

다만 이 수치는 최신 실측 월별 통계가 아니라 IMF 프로그램 자료와 전망치라는 점을 표시해야 합니다.

## 확인 가능한 TD

남수단의 은행권 총예금은 2018년 자료에서 비교적 명확하게 확인됩니다.

| 기준일 | 총예금 TD |
|---|---:|
| 2018년 12월 31일 | **SSP 92.3 billion** |
| 2018년 12월 31일 달러 환산 | 약 **USD 599.2 million** |

2018년 말 남수단 상업은행의 총예금은 SSP 92.3 billion, 당시 환율 기준 약 USD 599.2 million이었습니다. [mfw4a](https://www.mfw4a.org/country/south-sudan)

## FCD 절대액

동일한 2018년 기준의 FCD 절대액은 공개자료에서 직접 확인하지 못했습니다. 따라서 FCD는 다음처럼 저장하는 것이 안전합니다.

| 기준연도 | FCD | TD | FCD/TD |
|---|---:|---:|---:|
| 2018년 | 공개 잔액 없음 | SSP 92.3bn | 약 0.7%* |
| 2021년 | 공개 잔액 없음 | 공개 잔액 확인 필요 | 0.7% |
| 2023년 | 공개 잔액 없음 | 공개 잔액 확인 필요 | 0.3% 전망 |
| 2024년 | 공개 잔액 없음 | 공개 잔액 확인 필요 | 0.7% 전망 |

\* 2018년 TD에 IMF의 2018년 FCD/TD 보고값 0.7%를 적용한 경우의 참고값입니다. FCD 절대액을 직접 보고한 수치가 아닙니다.

2018년 FCD를 비율로 역산하면:

\[
FCD_{2018}
=
92.3\times0.7\%
=
0.6461\text{ billion SSP}
\]

즉, 참고용 역산값은 약 **SSP 646 million**입니다.

## 주의: 외화부채와 FCD는 다름

IMF의 2024년 남수단 보고서는 상업은행 부채의 **70% 이상이 외화표시**라고 설명합니다. 하지만 이 수치는 은행 전체 부채의 통화구성이고, 고객예금의 FCD/TD와 동일하지 않습니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2024/327/article-A001-en.xml)

따라서 다음 항목을 FCD로 사용하면 안 됩니다.

- 외화표시 은행부채.
- 은행의 외화자산.
- 중앙은행 외환보유액.
- 외화대출.
- 은행의 달러 결제계정.

남수단은 공식환율과 평행시장환율 간 격차가 크고, 2024년에는 공식환율도 급격히 조정되었습니다. SSP 기준 예금 잔액을 장기 비교할 때는 환율 효과도 별도로 관리해야 합니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2024/327/article-A001-en.xml)

## 데이터셋 입력 권장값

```text
country,date,fcd_ssp_billion,td_ssp_billion,fcd_td,source_type
South Sudan,2018-12-31,NA,92.3,0.007,reported_ratio_and_td
South Sudan,2021-12-31,NA,NA,0.007,imf_reported
South Sudan,2022-12-31,NA,NA,0.005,imf_projection
South Sudan,2023-12-31,NA,NA,0.003,imf_projection
South Sudan,2024-12-31,NA,NA,0.007,imf_projection
```

2018년 FCD를 역산해서 저장하려면:

```text
country,date,fcd_ssp_billion,td_ssp_billion,fcd_td,source_type
South Sudan,2018-12-31,0.6461,92.3,0.007,calculated
```

## 결론

- **2018년 TD:** SSP 92.3 billion.
- **2018년 FCD/TD 참고값:** 약 0.7%.
- **2021년 IMF 보고 FCD/TD:** 0.7%.
- **2022~2024년 IMF 전망:** 0.5%, 0.3%, 0.7%.
- **최신 실측 FCD 및 TD 월별 시계열:** 공개자료에서 확인하기 어려움.
- **주의:** 은행 부채의 70% 이상이 외화표시라는 수치를 FCD/TD로 사용하면 안 됨.

현재 국가별 데이터셋에는 **2018년 TD와 IMF FCD/TD 비율을 별도 출처 유형으로 저장**하고, 2022년 이후는 실측값과 전망값을 구분하는 것이 가장 안전합니다.


세르비아는 **세르비아 국립은행(National Bank of Serbia, NBS)**이 외화예금과 총예금을 모두 공개합니다. 세르비아는 유로화·외화예금 비중이 높은 국가이며, 최신 IMF 자료를 이용하면 FCD/TD는 대략 **57.5%** 수준으로 계산됩니다. [imf](https://www.imf.org/-/media/files/publications/cr/2025/english/1srbea2025003-source-pdf.pdf)

## 최신 FCD/TD 추정

IMF의 2025년 세르비아 보고서에 제시된 최근 예금 구성은 다음과 같습니다. 단위는 보고서 표의 **EUR million 기준**입니다.

| 항목 | 금액 |
|---|---:|
| Demand deposits | 1,340 |
| Time and saving deposits | 1,153 |
| Foreign currency deposits | 3,366 |
| **TD 계산값** | **5,859** |
| **FCD/TD** | **57.45%** |

계산식:

\[
TD
=
1,340+1,153+3,366
=
5,859
\]

\[
FCD/TD
=
\frac{3,366}{5,859}
=
57.45\%
\]

따라서 현재 확인 가능한 최신 IMF 표 기준으로:

\[
\boxed{FCD/TD \approx 57.5\%}
\]

IMF 표에는 외화예금이 2,264에서 3,366으로, 요구불예금이 1,340, 정기·저축성 예금이 1,153까지 증가하는 시계열이 제시됩니다. [imf](https://www.imf.org/-/media/files/publications/cr/2025/english/1srbea2025003-source-pdf.pdf)

## 장기 추이

| 관측값 | Demand deposits | Time/saving deposits | FCD | FCD/TD |
|---|---:|---:|---:|---:|
| 1 | 1,340 | 516 | 2,264 | 54.97% |
| 2 | — | 636 | 2,475 | — |
| 3 | — | 636 | 2,475 | — |
| 4 | — | 697 | 2,619 | — |
| 5 | — | 697 | 2,649 | — |
| 6 | — | 766 | 2,776 | — |
| 7 | — | 765 | 2,799 | — |
| 8 | — | 848 | 2,957 | — |
| 9 | — | 856 | 2,975 | — |
| 10 | — | 943 | 3,105 | — |
| 11 | — | 1,042 | 3,238 | — |
| 12 | — | **1,153** | **3,366** | **약 57.5%** |

첫 번째 행의 demand deposits와 마지막 행의 demand deposits가 동일한 시계열 표에 들어 있는지, 그리고 중간 열이 동일한 기준의 local-currency deposits인지에 대해서는 IMF 원문 표의 날짜 열을 함께 확인해야 합니다. 따라서 중간 관측치의 FCD/TD를 임의로 계산하지 않고, 마지막 행만 최신 참고치로 사용하는 것이 안전합니다. [imf](https://www.imf.org/-/media/files/publications/cr/2025/english/1srbea2025003-source-pdf.pdf)

## NBS 원자료

NBS의 Statistical Bulletin은 다음 항목을 제공합니다.

- Dinar deposits.
- Foreign currency deposits.
- FX-indexed savings and time deposits.
- Foreign currency deposits and FX-indexed savings and term deposits.
- Total short-term deposits.
- Total long-term deposits.
- Total deposits.
- Foreign currency bank deposits.

NBS는 외화금융상품에 **실제 외화표시 상품뿐 아니라 외화연동 예금·정기예금**도 포함할 수 있다고 설명합니다. 따라서 분석에서 순수 FCD만 사용할지, FX-indexed deposits까지 포함한 넓은 외화예금 정의를 사용할지 구분해야 합니다. [nbs](https://nbs.rs/export/sites/NBS_site/documents/publikacije/metodologija/I1-MS-e.pdf)

2025년 11월 NBS Statistical Bulletin은 다음 표를 제공합니다.

- Foreign currency bank deposits.
- Foreign currency deposits and FX-indexed savings and term deposits.
- Total deposits.
- Dinar deposits.
- Short-term·long-term deposits.

따라서 최신 월별 시계열은 해당 NBS Bulletin의 표에서 같은 월의 `Foreign currency deposits`와 `TOTAL DEPOSITS`를 직접 추출하는 방식이 가장 좋습니다. [nbs](https://www.nbs.rs/export/sites/NBS_site/documents-eng/publikacije/sb/sb_11_25.pdf)

## 데이터셋 권장값

최신 IMF 표 기준으로 우선 기록할 값:

```text
country,date,fcd,td,fcd_td,source_type
Serbia,latest_imf_observation,3366,5859,0.5745,calculated_from_imf_components
```

NBS 원자료를 내려받아 순수 외화예금 기준으로 구축할 경우:

```text
country,date,fcd_rsd_million,td_rsd_million,fcd_td
Serbia,2025-11,[NBS foreign currency deposits],[NBS total deposits],calculated
```

## 주의할 점

세르비아에서는 다음 세 가지 지표가 서로 다를 수 있습니다.

1. 순수 외화표시 예금.
2. 외화표시 예금 + 외화연동 정기·저축예금.
3. 가계·비금융기업의 외화예금만 포함한 euroization ratio.

국가 간 FCD/TD 비교에는 다음 정의를 고정하는 것이 좋습니다.

\[
FCD/TD
=
\frac{\text{Foreign-currency-denominated deposits}}
{\text{Dinar deposits}+\text{Foreign-currency-denominated deposits}}
\]

FX-indexed deposits를 포함하려면 변수명을 별도로 두는 것이 좋습니다.

```text
fcd_narrow = foreign-currency-denominated deposits
fcd_broad = foreign-currency-denominated + FX-indexed deposits
td = dinar deposits + fcd_broad
```

### 핵심 결과

- **세르비아 최신 FCD/TD 참고값:** 약 **57.5%**.
- **FCD:** 약 3,366.
- **TD 계산값:** 약 5,859.
- **권장 공식 원자료:** NBS Statistical Bulletin.
- **주의:** 순수 FCD와 FX-indexed deposits를 혼합하면 비율이 달라질 수 있음.


시에라리온은 **시에라리온은행(Bank of Sierra Leone, BSL)** 자료를 이용한 세계은행 경제보고서에서 외화예금 비중과 총예금을 함께 확인할 수 있습니다. 최신으로 확인되는 2022년 기준 **FCD/TD는 38.1%**, 총예금은 **SLE 16,935 billion**입니다. [documents1.worldbank](https://documents1.worldbank.org/curated/en/099129110242318576/pdf/IDU06c24816805aaa04d28098bc015c2cdf495af.pdf)

## 최신 FCD/TD

단위: **SLE billion**, 기말 잔액

| 기준연도 | 총예금 TD | 외화예금 비중 | FCD 추정액 | FCD/TD |
|---|---:|---:|---:|---:|
| 2018년 | 5,275 | 37.1% | 1,957.0 | 37.1% |
| 2019년 | 6,111 | 38.3% | 2,340.6 | 38.3% |
| 2020년 | 6,759 | 37.0% | 2,500.8 | 37.0% |
| 2021년 | 9,407 | 37.5% | 3,527.6 | 37.5% |
| 2022년 | **16,935** | **38.1%** | **6,452.2** | **38.1%** |

FCD는 다음과 같이 역산했습니다.

\[
FCD=TD\times(FCD/TD)
\]

2022년:

\[
FCD
=
16,935\times38.1\%
=
6,452.2\text{ billion SLE}
\]

세계은행 보고서의 총예금 및 외화예금 비중은 BSL 자료를 기반으로 하며, 2022년 총예금은 SLE 16,935 billion, 외화예금 비중은 38.1%입니다. [documents1.worldbank](https://documents1.worldbank.org/curated/en/099129110242318576/pdf/IDU06c24816805aaa04d28098bc015c2cdf495af.pdf)

## 해석

시에라리온의 외화예금 비중은 2018~2022년 동안 대체로 **37~38%** 수준에서 안정적이었습니다.

- 2018년: 37.1%.
- 2019년: 38.3%.
- 2020년: 37.0%.
- 2021년: 37.5%.
- 2022년: 38.1%.

2022년 외화예금 비중은 전년보다 0.6%p 상승했습니다. 총예금은 SLE 9,407 billion에서 16,935 billion으로 증가했는데, 시에라리온은 2022년 8월 화폐단위를 1,000대 1로 변경했으므로 전년과의 절대액 비교에는 화폐개혁 기준을 반드시 확인해야 합니다. [documents1.worldbank](https://documents1.worldbank.org/curated/en/099129110242318576/pdf/IDU06c24816805aaa04d28098bc015c2cdf495af.pdf)

## 데이터셋 입력

```text
country,date,fcd_sle_billion,td_sle_billion,fcd_td
Sierra Leone,2018-12-31,1957.025,5275,0.371
Sierra Leone,2019-12-31,2340.513,6111,0.383
Sierra Leone,2020-12-31,2500.830,6759,0.370
Sierra Leone,2021-12-31,3527.625,9407,0.375
Sierra Leone,2022-12-31,6452.235,16935,0.381
```

## 참고사항

- 위 FCD 금액은 보고서의 외화예금 비중과 TD를 곱한 **역산값**입니다.
- 보고서가 직접 제공하는 것은 `share of foreign currency in total deposits`와 `total deposits`입니다.
- 2022년 화폐개혁으로 구(구 SLL)와 신 SLE 단위가 혼동될 수 있습니다. 2022년 이후에는 보고서의 단위를 그대로 사용해야 합니다.
- 2023년 이후 최신 BSL 원자료의 FCD·TD 월별 시계열은 검색 결과에서 확인하지 못했습니다.

### 핵심 결과

- **2022년 TD:** SLE 16,935 billion.
- **2022년 FCD/TD:** **38.1%**.
- **2022년 FCD 추정액:** SLE 6,452.2 billion.
- **2018~2022년 FCD/TD 범위:** 37.0~38.3%.
- **권장 출처:** BSL 자료를 인용한 World Bank Sierra Leone Economic Update.


싱가포르는 **싱가포르 통화청(MAS)**이 외화예금과 총예금을 모두 공개합니다. 가장 명확하게 확인되는 수치는 2023년 12월 기준으로 **외화예금 S$936 billion**, 전체 예금 대비 **55%**입니다. [businesstimes.com](https://www.businesstimes.com.sg/companies-markets/banking-finance/singaporeans-flock-foreign-currency-lock-top-interest-rates)

## 최신 확인 수치

| 기준시점 | 외화예금 FCD | 총예금 TD | FCD/TD |
|---|---:|---:|---:|
| 2023년 12월 | **S$936bn** | 약 S$1,702bn | **55%** |
| 2024년 3월 | **S$1,008.2bn** | 최신 동일 표 확인 필요 | 약 55~58% 추정 |
| 2024년 4분기 | — | — | 주요 국내은행 약 61%* |

\* 2024년 4분기 수치는 전체 은행권이 아니라 싱가포르 국내 시스템적으로 중요한 은행(local D-SIBs)의 외화표시 예금 비중입니다.

2023년 12월 MAS 자료를 인용한 보도에 따르면 외화예금은 **S$936 billion**으로 전체 예금의 **55%**를 차지했습니다. 따라서 역산한 총예금은:

\[
TD
=
\frac{936}{0.55}
=
1,701.8\text{ billion SGD}
\]

 [businesstimes.com](https://www.businesstimes.com.sg/companies-markets/banking-finance/singaporeans-flock-foreign-currency-lock-top-interest-rates)

## 2024년 증가

2024년 3월에는 외화예금이 **S$1.0082 trillion**까지 증가했습니다. 이는 2021년 7월 S$783.2 billion에서 28.7% 증가한 수치입니다. [cresceream](https://www.cresceream.com/post/surging-travel-and-fixed-deposit-demand-singapore-s-foreign-currency-deposits-break-the-sgd-1-tril)

이 수치는 정부·비은행금융기관·기업·개인의 외화예금을 포함하는 MAS 은행권 통계입니다.

| 기준시점 | FCD |
|---|---:|
| 2021년 7월 | S$783.2bn |
| 2023년 12월 | S$936.0bn |
| 2024년 3월 | **S$1,008.2bn** |

## 2024년 4분기 참고

IMF는 2024년 4분기 싱가포르 국내 시스템적으로 중요한 은행의 대출·예금 중 약 **61%가 외화표시**였다고 설명합니다. 이 중 미국 달러 예금만 전체 예금의 약 **34%**를 차지했습니다. [imfsti](https://www.imfsti.org/content/dam/STI/Home/STI_News/IMF%20Country%20Report%20No%2025193.pdf)

이는 다음과 구분해야 합니다.

| 지표 | 범위 | 비율 |
|---|---|---:|
| FCD/TD | 전체 은행권의 외화예금/총예금 | 2023년 말 약 55% |
| 외화표시 예금 비중 | 싱가포르 국내 D-SIBs | 2024년 4분기 약 61% |
| USD 예금/TD | 싱가포르 국내 D-SIBs | 2024년 4분기 약 34% |

싱가포르는 국제금융센터이므로 비거주자·금융기관·기업의 외화예금이 매우 많습니다. 따라서 가계 예금만을 대상으로 한 달러화율과 전체 은행권 FCD/TD는 큰 차이가 날 수 있습니다.

## TD 참고자료

CEIC가 MAS 자료를 바탕으로 제공하는 싱가포르 총예금은 2026년 1월 기준 **USD 1,598.278 billion**입니다. MAS 원자료의 총예금은 싱가포르 달러로 제공되며, CEIC는 환율을 이용해 USD로 환산합니다. [ceicdata](https://www.ceicdata.com/en/indicator/singapore/total-deposits)

다만 FCD와 TD의 범위를 정확히 맞추려면 다음 MAS 표를 사용하는 것이 좋습니다.

- `I.4 Commercial Banks: Deposits and Balances`.
- `Deposits and Balances – Foreign Currencies`.
- `Deposits and Balances – Singapore Dollars`.
- `Deposits and Balances – Total`.

MAS의 I.4 표에는 외화 예금·잔액이 별도 행으로 표시됩니다. 검색 결과에서 확인되는 외화예금 잔액은 약 S$1.13 trillion 수준입니다. [mas.gov](https://www.mas.gov.sg/statistics/monthly-statistical-bulletin/i-4-commercial-banks-deposits-and-balances-excluding-s$ncds)

## 권장 계산 방식

싱가포르의 경우 다음 정의를 사용하는 것이 좋습니다.

\[
TD=
\text{SGD deposits}
+
\text{Foreign-currency deposits}
\]

\[
FCD/TD
=
\frac{\text{Foreign-currency deposits}}
{\text{SGD deposits}+\text{Foreign-currency deposits}}
\]

2023년 12월 기준:

```text
country,date,fcd_sgd_billion,td_sgd_billion,fcd_td
Singapore,2023-12,936.0,1701.8,0.55
```

2024년 3월 외화예금까지 반영하면:

```text
country,date,fcd_sgd_billion,td_sgd_billion,fcd_td
Singapore,2024-03,1008.2,NA,NA
```

## 핵심 결과

- **2023년 12월 FCD:** S$936 billion.
- **2023년 12월 TD 역산값:** 약 S$1,701.8 billion.
- **2023년 12월 FCD/TD:** **55%**.
- **2024년 3월 FCD:** S$1,008.2 billion.
- **2024년 4분기 국내 D-SIBs 외화표시 예금 비중:** 약 61%.
- 싱가포르는 국제금융센터이므로 비거주자·기업·금융기관 예금이 포함된 전체 은행권 기준을 사용할지, 거주자 예금만 사용할지 반드시 구분해야 합니다.