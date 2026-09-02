시리아는 중앙은행 통계가 장기간 제한적으로 공개되어 최신 FCD와 TD 원자료를 모두 확보하기 어렵습니다. 다만 세계은행 자료에서 **2023년 외화예금/FCD 비율은 69.4%**로 확인되며, 이는 현재 사용 가능한 가장 유용한 공식 추정치입니다. [documents1.worldbank](https://documents1.worldbank.org/curated/en/099844407042516353/txt/IDU-6adac64c-c9b1-472e-8183-ae600f64fa78.txt)

## 최신 FCD/TD

| 기준연도 | FCD/TD | FCD | TD |
|---|---:|---:|---:|
| 2011년 | 15.8% | 약 USD 3.20 billion | USD 20.276 billion |
| 2023년 | **69.4%** | 공개 잔액 없음 | 공개 잔액 없음 |
| 2024년 | 공개 비율 없음 | 공개 잔액 없음 | 민간은행 고객예금 SYP 23.5 trillion* |

\* 2024년 수치는 시리아 민간은행 고객예금이며, 공공은행을 포함한 전체 은행권 TD와는 범위가 다릅니다.

세계은행은 시리아 은행권의 외화예금 비중이 **2011년 15.8%에서 2023년 69.4%로 상승**했다고 설명합니다. 이는 시리아 파운드 가치 하락과 미국 달러 및 튀르키예 리라 등 외화 사용 증가를 반영한 수치입니다. [documents1.worldbank](https://documents1.worldbank.org/curated/en/099844407042516353/txt/IDU-6adac64c-c9b1-472e-8183-ae600f64fa78.txt)

## 2011년 계산 가능한 수치

CEIC가 시리아 중앙은행·IMF 계열 자료로 제공하는 2011년 총예금은 **USD 20,275.678 million**입니다. [ceicdata](https://www.ceicdata.com/en/indicator/syria/total-deposits)

세계은행의 2011년 FCD/TD 비율 15.8%를 적용하면:

\[
FCD_{2011}
=
20.275678 \times 15.8\%
=
3.2036\text{ billion USD}
\]

| 항목 | 2011년 |
|---|---:|
| TD | USD 20.276 billion |
| FCD/TD | 15.8% |
| FCD 추정치 | USD 3.204 billion |

이 값은 FCD 잔액을 직접 보고한 것이 아니라, 공식 TD와 FCD/TD 비율을 이용한 역산값입니다.

## 2023년 공식 비율

2023년은 FCD/TD 비율만 확인됩니다.

\[
\boxed{FCD/TD = 69.4\%}
\]

하지만 공개된 세계은행 자료에는 같은 기준의 TD와 FCD 절대액이 함께 제시되지 않습니다. 따라서 다음과 같이 기록하는 것이 안전합니다.

```text
country,date,fcd_t​​d,fcd,td
Syria,2023-12-31,0.694,NA,NA
```

## 2024년 참고 수치

2024년 말 시리아 민간은행의 고객예금은 현지통화 및 외화 환산액 기준으로 약 **SYP 23.5 trillion**, 약 **USD 1.7 billion**으로 추정됩니다. 다만 이 자료는 민간은행 중심의 추정치이며, 공공은행과 중앙은행 기준을 포함한 전체 은행권 TD가 아닙니다. [karamshaar](https://karamshaar.com/syria-in-figures/syria-banking-crisis-2025/)

또한 시리아 파운드 환율이 크게 변했기 때문에 SYP 기준 TD는 환율 재평가만으로도 크게 증가할 수 있습니다. 따라서 2024년의 SYP 23.5 trillion을 2023년의 FCD/TD 비율과 바로 결합해서 FCD를 계산하는 것은 권장하지 않습니다.

## 과거 직접 관측자료

시리아의 과거 중앙은행·IMF 자료에는 다음과 같은 직접적인 FCD/TD 비율이 있습니다.

| 기준연도 | FCD/TD |
|---|---:|
| 2000년 | 11.1% |
| 2001년 | 10.8% |
| 2002년 | 6.6% |
| 2003년 | 9.7% |
| 2004년 | 13.3% |
| 2005년 | 13.3% |

2006년 IMF Article IV 자료는 외화예금과 총예금을 함께 제시하고 있으며, 2005년까지 FCD/TD 비율이 약 13.3%였다고 보고합니다. [imf](https://www.imf.org/external/pubs/ft/scr/2006/cr06294.pdf)

## 분석용 권장 데이터

현재 확보 가능한 데이터는 다음과 같습니다.

```text
country,date,td_usd_billion,fcd_usd_billion,fcd_td,source_type
Syria,2011-12-31,20.275678,3.2036,0.158,calculated
Syria,2023-12-31,NA,NA,0.694,reported_ratio
```

### 권장 해석

- **2011년:** TD와 FCD/TD가 모두 있어 FCD 역산 가능.
- **2023년:** FCD/TD 69.4%만 사용 가능.
- **2024년:** 민간은행 TD 추정치는 있으나 전체 은행권 및 FCD 비율과 직접 결합하지 않음.
- **최신 시계열:** 2023년 69.4%를 최신 관측치로 저장하되, 절대 FCD와 TD는 결측 처리.

시리아는 전쟁, 금융제재, 복수환율, 환율 급락, 2025년 이후 화폐개혁과 금융체계 재편까지 겹쳐 있어 일반 국가처럼 현지통화 기준 FCD/TD를 장기 비교하기 어렵습니다. 따라서 현재 데이터셋에는 **2011년 계산값과 2023년 보고 비율을 별도 출처 유형으로 보존**하는 것이 가장 안전합니다.


세이셸은 **세이셸중앙은행(Central Bank of Seychelles, CBS)**이 외화예금과 현지통화 예금을 모두 월별로 공개하고 있어 \(FCD/TD\) 계산이 가능합니다. 최신으로 확인되는 2026년 1월 Monetary Policy Report에는 외화예금과 현지통화 예금의 6개 시점 수치가 함께 제시되어 있으며, 2025년 1월 Statistical Bulletin에는 2024년 1월부터 2025년 1월까지의 월별 원자료가 있습니다. [cbs](https://www.cbs.sc/Downloads/publications/Stats%20update%20Jan%202025.pdf)

## 권장 TD 정의

CBS의 통화통계에서는 M3가 M2와 거주자 외화예금으로 구성됩니다.

\[
M3=M2+FCD
\]

따라서 총예금은 다음처럼 계산하는 것이 적절합니다.

\[
TD=
\text{Transferable deposits}
+\text{Fixed-term deposits}
+\text{Savings deposits}
+\text{Foreign currency deposits}
\]

즉, 통화유통액이나 기타부채를 포함한 `Total deposits liabilities`가 아니라, **은행 예금 항목만 합산한 TD**를 사용했습니다.

## 최신 확인 수치

단위: **SCR million, 기말 잔액**

| 기준월 | FCD | 현지통화 예금 | TD | FCD/TD |
|---|---:|---:|---:|---:|
| 2024년 1월 | 9,702 | 13,899 | 23,601 | 41.11% |
| 2024년 2월 | 9,666 | 14,121 | 23,787 | 40.64% |
| 2024년 3월 | 9,714 | 14,120 | 23,834 | 40.76% |
| 2024년 4월 | 9,842 | 14,421 | 24,263 | 40.56% |
| 2024년 5월 | 9,877 | 14,697 | 24,574 | 40.19% |
| 2024년 6월 | 9,968 | 14,707 | 24,675 | 40.40% |
| 2024년 7월 | 10,110 | 14,754 | 24,864 | 40.66% |
| 2024년 8월 | 10,019 | 14,828 | 24,847 | 40.32% |
| 2024년 9월 | 9,931 | 15,161 | 25,092 | 39.58% |
| 2024년 10월 | 10,074 | 15,269 | 25,343 | 39.75% |
| 2024년 11월 | 10,384 | 15,289 | 25,673 | 40.45% |
| 2024년 12월 | 10,154 | 15,334 | 25,488 | 39.84% |
| **2025년 1월** | **10,269** | **15,191** | **25,460** | **40.33%** |

CBS의 2025년 1월 Statistical Bulletin은 2025년 1월 FCD를 SCR 10,269 million으로, 현지통화 예금은 transferable deposits SCR 8,113 million, fixed-term deposits SCR 1,838 million, savings deposits SCR 5,240 million으로 제시합니다. [cbs](https://www.cbs.sc/Downloads/publications/Stats%20update%20Jan%202025.pdf)

2025년 1월 계산:

\[
TD
=
8,113+1,838+5,240+10,269
=
25,460
\]

\[
FCD/TD
=
\frac{10,269}{25,460}
=
40.33\%
\]

## 2026년 보고서의 최신 흐름

CBS의 2026년 1월 Monetary Policy Report에는 FCD와 현지통화 예금이 다음과 같이 제시됩니다. 보고서 표의 6개 관측치는 SCR million 기준입니다. [cbs](https://www.cbs.sc/Downloads/publications/MonetaryPolicy/Reports/Monetary%20Policy%20Report%20January%202026.pdf)

| 관측치 | FCD | 현지통화 예금 | TD | FCD/TD |
|---|---:|---:|---:|---:|
| 1 | 11,544 | 16,573 | 28,117 | 41.05% |
| 2 | 11,670 | 16,673 | 28,343 | 41.17% |
| 3 | 11,789 | 16,963 | 28,752 | 41.00% |
| 4 | 12,030 | 17,150 | 29,180 | 41.23% |
| 5 | 12,367 | 17,326 | 29,693 | 41.65% |
| 6 | **12,709** | **17,573** | **30,282** | **41.98%** |

마지막 관측치 기준:

\[
TD=12,709+17,573=30,282
\]

\[
FCD/TD
=
\frac{12,709}{30,282}
=
41.98\%
\]

따라서 가장 최근 보고서에 나타난 마지막 관측치에서는 FCD가 약 **SCR 12.709 billion**, TD가 약 **SCR 30.282 billion**, FCD/TD가 약 **41.98%**입니다. [cbs](https://www.cbs.sc/Downloads/publications/MonetaryPolicy/Reports/Monetary%20Policy%20Report%20January%202026.pdf)

## 데이터 정의별 주의점

CBS 표에는 `Total deposits liabilities`라는 더 큰 수치도 있습니다. 예를 들어 2025년 1월에는 SCR 32,418 million으로 제시됩니다. 이 항목은 예금 외의 기타 부채를 포함하므로, FCD/TD의 분모로 사용하지 않는 것이 좋습니다. [cbs](https://www.cbs.sc/Downloads/publications/Stats%20update%20Jan%202025.pdf)

| 분모 정의 | 2025년 1월 값 | 용도 |
|---|---:|---|
| 예금 항목 합계 | SCR 25,460 million | **FCD/TD 권장 분모** |
| Total deposits liabilities | SCR 32,418 million | 은행 전체 부채 분석 |

예금 달러화율 비교에는 다음 정의를 고정하는 것이 가장 적절합니다.

\[
\boxed{
FCD/TD=
\frac{\text{Residents' foreign currency deposits}}
{\text{Local-currency deposits}+\text{Residents' foreign currency deposits}}
}
\]

## 분석용 CSV

```text
country,date,fcd_scr_million,td_scr_million,fcd_td
Seychelles,2024-01,9702,23601,0.4111
Seychelles,2024-02,9666,23787,0.4064
Seychelles,2024-03,9714,23834,0.4076
Seychelles,2024-04,9842,24263,0.4056
Seychelles,2024-05,9877,24574,0.4019
Seychelles,2024-06,9968,24675,0.4040
Seychelles,2024-07,10110,24864,0.4066
Seychelles,2024-08,10019,24847,0.4032
Seychelles,2024-09,9931,25092,0.3958
Seychelles,2024-10,10074,25343,0.3975
Seychelles,2024-11,10384,25673,0.4045
Seychelles,2024-12,10154,25488,0.3984
Seychelles,2025-01,10269,25460,0.4033
```

### 핵심 결과

- **2025년 1월 FCD:** SCR 10,269 million.
- **2025년 1월 TD:** SCR 25,460 million.
- **2025년 1월 FCD/TD:** **40.33%**.
- **최신 2026년 1월 보고서의 마지막 관측치:** FCD/TD 약 **41.98%**.
- 세이셸은 중앙은행 월별 통계로 **FCD/TD 시계열을 구축할 수 있는 국가**입니다.



Sint Maarten (Dutch part)는 **CBCS(Centrale Bank van Curaçao en Sint Maarten)** 통화권에 속하며, 최신 공개자료에서 확인 가능한 가장 명확한 지표는 **2020년 예금 달러화율 58%**입니다. 이는 사실상 \(FCD/TD\), 즉 외화예금이 총예금에서 차지하는 비중으로 해석할 수 있습니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2021/187/article-A001-en.xml)

## 확인 가능한 FCD/TD

| 기준연도 | FCD/TD | FCD 잔액 | TD |
|---|---:|---:|---:|
| 2020년 | **58%** | 공개자료에서 절대액 미확인 | 공개자료에서 절대액 미확인 |

IMF는 Sint Maarten의 금융 달러화율을 다음과 같이 보고합니다.

- 예금 측면: **58%**.
- 대출 측면: 66%.
- 기준연도: 2020년.

따라서 데이터셋에는 다음과 같이 입력할 수 있습니다.

```text
country,date,fcd_td,fcd,td
Sint Maarten (Dutch part),2020-12-31,0.58,NA,NA
```

## 통화와 정의

Sint Maarten은 Curaçao와 함께 통화동맹을 구성하고 있으며, 당시 통화는 **Netherlands Antillean guilder(ANG)**였습니다. 현지통화는 미국 달러에 고정되어 있었고, 미국 달러가 자유롭게 유통되었습니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2021/187/article-A001-en.xml)

따라서 여기서 FCD는 일반적으로:

\[
FCD =
\text{USD 및 기타 외화로 표시된 예금}
\]

이며, TD는 다음과 같습니다.

\[
TD =
\text{현지통화 예금}
+
\text{외화예금}
\]

IMF가 제시한 58%는 Sint Maarten의 공식 달러화가 아니라 **사실상의 금융 달러화율**입니다.

## 최신 자료 상황

2023년 IMF Article IV 보고서에서도 Sint Maarten의 은행 예금과 현지통화·외화예금의 변동은 다루지만, 검색 가능한 본문에는 2023년 또는 2024년의 FCD와 TD 절대액이 표 형태로 제시되지 않습니다. 해당 보고서는 Sint Maarten의 금융통계 및 예금자료가 제한적이며, 통계 역량 강화가 필요하다고 지적합니다. [imf](https://www.imf.org/-/media/Files/Publications/CR/2023/English/1CUWEA2023001.ashx)

CBCS의 2024년 연차보고서에는 외화 정기예금 및 외화 CD에 관한 정보는 있으나, Sint Maarten 단독 기준의 전체 FCD와 TD 시계열을 직접 제공하는 표는 확인되지 않았습니다. [centralbank](https://www.centralbank.cw/storage/app/media/annual_report_2024/20250801_cbcs_annual_report_2024.pdf)

## 참고할 수 있는 추세

IMF의 2021년 보고서가 제공하는 가장 신뢰할 수 있는 Sint Maarten 단독 수치는 2020년 58%입니다.

| 국가·지역 | 예금 달러화율 | 기준연도 |
|---|---:|---:|
| Sint Maarten | **58%** | 2020 |
| Curaçao | 약 12% | 2020 |

Sint Maarten의 비율이 Curaçao보다 크게 높은 것은 Sint Maarten의 경제가 미국 관광객과 미국 달러 거래에 더 강하게 연결되어 있기 때문입니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2021/187/article-A001-en.xml)

## 결론

- **FCD/TD:** 2020년 **58%**.
- **FCD 절대액:** 공개자료에서 확인하지 못함.
- **TD 절대액:** 같은 기준의 공개자료에서 확인하지 못함.
- **최신 공식 단독 비율:** 2020년 58%.
- **2021년 이후:** CBCS 원자료 또는 IMF·CBCS 내부 통계에서 추가 확인 필요.

따라서 국가별 데이터셋에는 Sint Maarten을 다음처럼 저장하는 것이 안전합니다.

```text
country: Sint Maarten (Dutch part)
date: 2020-12-31
fcd_td: 0.58
fcd: NA
td: NA
source: IMF Selected Issues, 2021
definition: financial dollarization on the deposit side
```