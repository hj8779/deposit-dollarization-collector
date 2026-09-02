스리랑카는 **스리랑카 중앙은행(CBSL)**의 통계 부록에서 외화예금(FCD)과 총예금(TD)을 확인할 수 있습니다. 특히 2024년 연차보고서의 엑셀 통계 부록에는 `Foreign Currency Deposits`와 `Total Deposits`가 포함되어 있어, 이번 국가들 중 비교적 적합한 자료입니다. [cbsl.gov](https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/publications/aer/2024/en/monetary_and_financial_sector.xlsx)

## 권장 원자료

### CBSL 2024 통계 엑셀

[CBSL Annual Economic Review 2024 — Monetary and Financial Sector Excel](https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/publications/aer/2024/en/monetary_and_financial_sector.xlsx)

확인할 표는 다음과 같습니다.

- `Table 123`: Consolidated Monetary Survey — M2b
- `Table 130`: Assets and Liabilities of Domestic Banking Units of Commercial Banks
- `Table 137`: Savings and Fixed Deposits of Deposit Taking Institutions
- 연차보고서 본문 `Table 2.4`: Composition of Deposits of the Banking Sector

외화예금은 `Foreign Currency Deposits`를 사용하고, 총예금은 은행권의 `Total Deposits`를 사용하면 됩니다. CBSL 통계는 단위를 주로 **백만 스리랑카 루피(Rs. million)**로 표시합니다. [cbsl.gov](https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/publications/aer/2024/en/monetary_and_financial_sector.xlsx)

## 2024년 총예금

CBSL의 2024년 연차 경제보고서에 따르면 은행권 총예금은 다음과 같습니다.

| 기준시점 | TD |
|---|---:|
| 2023년 말 | Rs. 16,630.5 billion |
| 2024년 말 | Rs. 17,969.4 billion |

2024년에는 총예금이 전년 대비 약 8.1% 증가했으며, 예금 구성은 정기예금 67.6%, 저축예금 25.1%, 요구불예금 6.2%, 기타예금 1.1%였습니다. [parliament](https://www.parliament.lk/uploads/documents/paperspresented/1758694503074434.pdf)

## FCD/TD 확인값

스리랑카 은행권의 외화예금 비중은 2024년 말 기준 약 **22%**로 보고됩니다. [economy](https://economy.lk/foreign-currency-srr-a-missing-piece-in-sri-lankas-monetary-policy/)

따라서 2024년 말 FCD를 역산하면:

\[
\text{FCD}
\approx 17{,}969.4 \times 22.0\%
= 3{,}953.3
\]

| 기준시점 | FCD 추정치 | TD | FCD/TD |
|---|---:|---:|---:|
| 2024년 말 | 약 Rs. 3,953.3 billion | Rs. 17,969.4 billion | 약 22.0% |

다만 위 FCD 금액은 공개된 22% 비율을 이용한 역산값입니다. 정확한 원자료 수치가 필요한 경우에는 CBSL 엑셀의 `Foreign Currency Deposits` 행을 직접 추출해야 합니다.

## 월별 데이터

CBSL의 `Monthly Economic Indicators`도 월별 금융통계에 `Total Deposits`를 포함합니다. 예를 들어 2024년 9월 자료는 통화·금융 부문과 총예금 관련 월별 수치를 제공합니다. [cbsl.gov](https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/statistics/mei/MEI_202409_e.pdf)

월별 분석에는 다음 방식이 적합합니다.

```text
date = 기준월 말
fcd = Foreign Currency Deposits
td  = Total Deposits of the banking sector
fcd_td = fcd / td * 100
```

최종 데이터 구조는 다음과 같이 만들 수 있습니다.

```csv
date,fcd_lkr_million,td_lkr_million,fcd_td_pct
2024-12,3953300,17969400,22.00
```

## 주의할 점

- CBSL의 `M2b`는 일반적인 총예금과 동일하지 않습니다. M2b에는 루피화 표시 통화 및 예금 중심의 통화량이 포함되므로, FCD/TD 계산의 분모로 직접 사용하지 않는 편이 좋습니다. [cbsl.gov](https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/publications/aer/2024/en/monetary_and_financial_sector.xlsx)
- `Total Deposits`는 은행권의 예금 총액을 사용해야 합니다.
- 외화예금의 국내부채·외국부채 분류에는 NRFC, RNNFC 등 계좌 유형별 처리 규칙이 적용됩니다. CBSL은 NRFC 예금의 일부를 국내 예금부채로 처리하고, RNNFC 잔액은 외국부채로 처리하는 등 통계 편제상 주의사항을 명시합니다. [cbsl.gov](https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/publications/aer/2024/en/monetary_and_financial_sector.xlsx)
- 따라서 국제 비교용으로는 `Foreign Currency Deposits / Total Deposits`를 사용하되, 원자료 각주와 금융기관 범위를 함께 저장하는 것이 좋습니다.

현재 확인 결과를 요약하면 다음과 같습니다.

```text
TD, 2024-12 = Rs. 17,969.4 billion
FCD/TD       ≈ 22.0%
FCD          ≈ Rs. 3,953.3 billion
```

정확한 월별 FCD/TD 시계열을 만들 때는 CBSL 통계 엑셀의 `Foreign Currency Deposits` 행과 연차보고서 또는 월간지표의 `Total Deposits` 행을 같은 기준월에 결합하면 됩니다.


리투아니아는 **리투아니아은행(Bank of Lithuania)**이 예금을 통화별로 직접 제공하므로, 지금까지 살펴본 국가 중 FCD/TD를 가장 깔끔하게 계산할 수 있는 편입니다. 공식 표에 `Deposits of Lithuanian residents non-MFIs`의 총액과 EUR·USD·JPY·CHF·GBP·기타 통화별 잔액이 함께 있습니다. [lb](https://www.lb.lt/en/deposits-by-currency)

## 권장 원자료

### Bank of Lithuania — Deposits by currency

[Deposits by currency](https://www.lb.lt/en/deposits-by-currency)

이 표의 핵심 대상은 다음입니다.

> **Deposits of Lithuanian residents non-MFIs with other Lithuanian MFIs by currency**

단위는 **EUR million**이며, 데이터는 기간 말 잔액입니다. [lb](https://www.lb.lt/en/deposits-by-currency)

사용할 변수는 다음처럼 정의하면 됩니다.

| 변수 | 공식 항목 |
|---|---|
| `td` | Deposits of Lithuanian resident non-MFIs — Total |
| `fcd` | USD + JPY + CHF + GBP + Remaining currencies |
| `fcd_td` | `fcd / td × 100` |

리투아니아는 현재 유로화를 사용하므로, 여기서 FCD는 **EUR 이외의 통화로 표시된 예금**입니다.

## 2024년 말

2024년 12월 리투아니아 거주자 비금융부문 예금은 다음과 같습니다.

| 항목 | 금액 |
|---|---:|
| TD | EUR 43,286.3 million |
| EUR 예금 | 약 97.8% |
| 외화예금 비중 | 약 2.2% |
| FCD 추정액 | 약 EUR 952.3 million |
| FCD/TD | 약 2.2% |

외화예금 추정액은 다음과 같이 계산했습니다.

\[
43{,}286.3 \times 2.2\%
\approx 952.3
\]

공식 표에서 2024년 12월의 통화별 비중은 EUR 97.8%, USD 1.6%, JPY 0.0%, CHF 0.0%, GBP 0.2%, 기타 0.3%로 표시됩니다. 반올림 때문에 세부 통화별 금액을 합산한 값과 2.2% 역산값 사이에 소폭 차이가 날 수 있습니다. [lb](https://www.lb.lt/en/deposits-by-currency)

## 월별 FCD/TD

공식 표에 표시된 통화별 비중을 이용해 계산한 근사 시계열은 다음과 같습니다.

| 월 | TD, EUR million | 외화예금 비중 | FCD 추정액, EUR million |
|---|---:|---:|---:|
| 2024-05 | 39,331.4 | 2.3% | 904.6 |
| 2024-06 | 38,947.6 | 2.4% | 934.7 |
| 2024-07 | 39,880.4 | 2.3% | 917.2 |
| 2024-08 | 40,123.9 | 2.4% | 963.0 |
| 2024-09 | 40,404.5 | 2.3% | 929.3 |
| 2024-10 | 41,136.4 | 2.3% | 946.1 |
| 2024-11 | 42,378.0 | 2.2% | 932.3 |
| 2024-12 | 43,286.3 | 2.2% | 952.3 |
| 2025-01 | 43,020.3 | 2.2% | 946.4 |
| 2025-02 | 43,096.8 | 2.2% | 948.1 |
| 2025-03 | 43,490.8 | 2.1% | 913.3 |
| 2025-04 | 43,483.9 | 2.1% | 913.2 |
| 2025-05 | 43,618.6 | 2.0% | 872.4 |

2025년 5월까지의 원자료 표에서는 거주자 예금의 EUR 비중이 98.0%, 비유로 통화 비중이 약 2.0%로 나타납니다. [lb](https://www.lb.lt/en/deposits-by-currency)

## 더 엄밀한 FCD 계산

표의 비중은 반올림되어 있으므로, 가능하면 다운로드 가능한 원자료에서 통화별 **금액**을 추출하는 것이 좋습니다.

```text
fcd =
  deposits_usd
+ deposits_jpy
+ deposits_chf
+ deposits_gbp
+ deposits_remaining_currencies

td = deposits_total

fcd_td = fcd / td * 100
```

월별 데이터셋은 다음 형태로 정리할 수 있습니다.

```csv
date,td_eur_million,fcd_eur_million,fcd_td_pct
2024-12,43286.3,952.3,2.20
2025-01,43020.3,946.4,2.20
2025-02,43096.8,948.1,2.20
2025-03,43490.8,913.3,2.10
2025-04,43483.9,913.2,2.10
2025-05,43618.6,872.4,2.00
```

## 범위 선택 시 주의점

Bank of Lithuania에는 비거주자 및 다른 유로지역 거주자의 예금도 별도 그룹으로 제공됩니다. 예를 들어 `Deposits of other euro area residents non-MFIs`와 `Deposits of non-euro area residents non-MFIs`가 따로 표시됩니다. [lb](https://www.lb.lt/en/deposits-by-currency)

국가의 **예금 달러화율**을 계산하려는 목적이라면 다음 정의를 권장합니다.

```text
분자:
  리투아니아 거주자 비금융부문의 EUR 이외 통화 예금

분모:
  리투아니아 거주자 비금융부문의 전체 예금

FCD/TD:
  resident non-MFI foreign-currency deposits
  / resident non-MFI total deposits
```

비거주자 예금까지 포함하면 외화예금 비중이 크게 높아질 수 있으므로, 다른 국가의 거주자 기준 FCD/TD와 비교할 때는 **첫 번째 그룹인 Lithuanian residents non-MFIs만 사용하는 것**이 일관적입니다. 통화량 통계에서도 리투아니아은행은 예금을 EUR와 외화로 분리해 제공하며, 통화별 예금 잔액은 기간 말 기준으로 집계됩니다. [lb](https://www.lb.lt/en/contribution-of-lithuania-to-monetary-aggregate-components)



모로코는 **Bank Al-Maghrib(BAM, 모로코 중앙은행)**의 월간 통화통계에서 외화예금과 총예금을 모두 확인할 수 있습니다. FCD는 BAM이 정의한 **은행의 외화 요구불예금 및 정기예금**이며, 총예금은 은행 예금의 총잔액을 사용하면 됩니다. [bkam](https://www.bkam.ma/content/download/838570/9102478/DSGD%20SM%20d%C3%A9cembre%202025.pdf)

## 공식 원자료

### BAM 월간 통화통계

[Bank Al-Maghrib — Key indicators of monetary statistics](https://www.bkam.ma/en/Statistics/Monetary-statistics/Key-indicators-of-monetary-statistics)

해당 페이지에서 다음 자료를 받을 수 있습니다.

- `Key monetary statistics`
- `Statistiques monétaires`
- `Bulletin trimestriel`
- `Flash crédits dépôts`

2026년 월간 자료와 2025년 연간 자료가 제공되며, 최신 연간 통계는 2026년 2월 2일 공개되었습니다. [bkam](https://www.bkam.ma/en/Statistics/Monetary-statistics/Key-indicators-of-monetary-statistics)

## 변수 정의

| 변수 | BAM 항목 |
|---|---|
| `fcd` | `Dépôts en devises` |
| `td` | `Dépôts bancaires à caractère monétaire` 또는 `Total des dépôts` |
| `fcd_td` | `fcd / td × 100` |

BAM의 FCD 정의는 다음과 같습니다.

> **Dépôts à vue et à terme en devises auprès des banques**

즉, 은행에 예치된 외화 요구불예금과 외화 정기예금입니다. 외화보유액, 은행의 해외자산, 외화대출은 FCD에 포함하면 안 됩니다. [bkam](https://www.bkam.ma/content/download/834764/9076962/Bulletin%20trimestriel%20T3%202025%2019112025.pdf)

## 2025년 12월 수치

BAM의 2025년 12월 통화통계에서 확인되는 수치는 다음과 같습니다.

| 기준시점 | FCD | TD | FCD/TD |
|---|---:|---:|---:|
| 2025-12 | MAD 17,728 million | MAD 1,367,653 million | 1.30% |

계산:

\[
\frac{17{,}728}{1{,}367{,}653}
\times 100
=
1.296\%
\]

따라서 2025년 12월 기준 모로코의 예금 달러화율에 해당하는 FCD/TD는 약 **1.30%**입니다.

BAM은 같은 시점의 `Dépôts bancaires à caractère monétaire`를 MAD 1,367,653 million으로 보고했습니다.  외화예금은 BAM의 분기 통계 표에 MAD 17,728 million으로 표시됩니다. [bkam](https://www.bkam.ma/content/download/838570/9102478/DSGD%20SM%20d%C3%A9cembre%202025.pdf)

## 최근 시계열

BAM 분기 통계에서 확인되는 외화예금은 다음과 같습니다.

| 기준시점 | FCD, MAD million |
|---|---:|
| 2024년 4분기 | 17,478 |
| 2025년 1분기 | 17,003 |
| 2025년 2분기 | 16,833 |
| 2025년 3분기 | 17,003 |
| 2025년 4분기 | 17,728 |

2025년 3분기 보고서의 FCD 표는 외화예금을 월별·분기별로 제시하며, 각 수치는 은행의 외화 요구불예금과 정기예금 잔액입니다.  2025년 4분기 자료에서도 외화예금은 17,728 million MAD로 제시됩니다. [bkam](https://www.bkam.ma/content/download/839758/9110367/BT%20T4%202025.pdf)

## TD 자료

BAM의 `Flash crédits dépôts` 자료에서 은행 예금 총액을 확인할 수 있습니다.

| 기준시점 | TD |
|---|---:|
| 2024년 12월 | 약 MAD 1,165.3 billion |
| 2025년 1월 | MAD 1,241.0 billion |
| 2025년 4월 | MAD 1,250.2 billion |
| 2025년 5월 | MAD 1,268.7 billion |
| 2025년 6월 | MAD 1,309.0 billion |
| 2025년 7월 | MAD 1,303.1 billion |
| 2025년 12월 | 약 MAD 1,367.7 billion |

2025년 6월 말 예금은 MAD 1,309 billion, 7월 말 예금은 MAD 1,303.1 billion으로 보고되었습니다.  2025년 12월 통화통계에서는 `Dépôts bancaires à caractère monétaire`가 MAD 1,367.653 billion으로 확인됩니다. [bkam](https://www.bkam.ma/content/download/838570/9102478/DSGD%20SM%20d%C3%A9cembre%202025.pdf)

## 분석용 형식

```csv
date,fcd_mad_million,td_mad_million,fcd_td_pct
2025-12,17728,1367653,1.30
```

다만 BAM 자료에서는 `Total des dépôts`와 `Dépôts bancaires à caractère monétaire`가 표에 따라 다르게 표시될 수 있습니다. 국제비교용으로는 다음처럼 고정하는 것이 좋습니다.

```text
fcd = BAM Dépôts en devises
td  = BAM Dépôts bancaires à caractère monétaire
ratio = fcd / td * 100
```

모로코는 외화예금 비중이 약 1%대에 불과해, 유로화 사용국인 리투아니아와 비슷하게 **은행 예금의 대부분이 국내통화인 디르함으로 구성된 국가**로 분류할 수 있습니다.


몰도바는 **몰도바 국립은행(NBM)**이 외화예금 잔액과 총예금 잔액을 모두 제공합니다. NBM의 `Evolution of monetary indicators`에서 **은행예금 잔액(balance of bank deposits)**을 국내통화와 외화로 나누어 제시하므로, FCD/TD 계산에 적합합니다. [bnm](http://www.bnm.md/en/content/evolution-monetary-indicators-june-2026)

## 공식 원자료

### NBM monetary indicators

[National Bank of Moldova — Monetary indicators](https://www.bnm.md/en)

사용할 항목은 다음입니다.

| 변수 | NBM 항목 |
|---|---|
| `td` | Balance of bank deposits |
| `fcd` | Balance of deposits in foreign currency, recalculated in MDL |
| `ncd` | Balance of deposits in domestic currency |
| `fcd_td` | `fcd / td × 100` |

계산식은 다음과 같습니다.

\[
\text{FCD/TD}
=
\frac{\text{Foreign-currency deposit balance}}
{\text{Total bank-deposit balance}}
\times 100
\]

NBM은 외화예금을 모두 **MDL로 환산한 잔액**으로 발표하므로 FCD와 TD의 통화 단위가 일치합니다.

## 최신 총예금

2026년 6월 말 NBM 자료에서 은행예금 잔액은 다음과 같습니다.

| 기준시점 | TD |
|---|---:|
| 2026-06 | MDL 147,709 million |

NBM은 2026년 6월 은행예금 잔액이 전월 대비 1.4% 증가했으며, 국내통화 예금은 1.1%, 외화예금은 1.9% 증가했다고 보고했습니다. [bnm](http://www.bnm.md/en/content/evolution-monetary-indicators-june-2026)

## 2025년 8월 검증 가능한 수치

2025년 8월에는 NBM이 국내통화와 외화예금 잔액을 모두 금액으로 공개했습니다.

| 기준시점 | 국내통화 예금 | FCD | TD | FCD/TD |
|---|---:|---:|---:|---:|
| 2025-08 | 87,549.3 | 44,683.9 | 132,233.2 | 33.79% |

계산:

\[
TD = 87{,}549.3 + 44{,}683.9
= 132{,}233.2
\]

\[
\text{FCD/TD}
=
\frac{44{,}683.9}{132{,}233.2}
\times 100
=
33.79\%
\]

NBM은 2025년 8월 외화예금 잔액을 **MDL 44,683.9 million**, 국내통화 예금을 **MDL 87,549.3 million**으로 발표했습니다. [bnm](https://bnm.md/en/content/evolution-monetary-indicators-august-2025)

## 최근 추이

NBM 발표에서 확인되는 수치는 다음과 같습니다.

| 기준시점 | NCD | FCD | TD | FCD/TD |
|---|---:|---:|---:|---:|
| 2024-03 | 74,529.6 | 39,858.8 | 114,388.4 | 34.85% |
| 2025-02 | 84,383.1 | 43,268.4 | 127,651.5 | 33.88% |
| 2025-04 | 85,361.3 | 42,531.6 | 127,892.9 | 33.26% |
| 2025-07 | 87,480.5 | 43,234.9 | 130,715.4 | 33.07% |
| 2025-08 | 87,549.3 | 44,683.9 | 132,233.2 | 33.79% |

각 수치는 NBM의 월별 통화지표 발표에서 확인됩니다. [bnm](https://bnm.md/en/content/evolution-monetary-indicators-august-2025)

## 2026년 6월 추정값

2026년 6월 NBM 발표에서는 TD와 전월 대비 증가율은 공개되어 있지만, 검색 가능한 본문에는 FCD 절대액이 표시되지 않고 차트로 제공됩니다. [bnm](http://www.bnm.md/en/content/evolution-monetary-indicators-june-2026)

외부 시계열에 표시된 2026년 5월 FCD는 약 **MDL 47,760 million**입니다. 6월 외화예금이 전월 대비 1.9% 증가했다는 NBM 발표를 적용하면:

\[
FCD_{2026-06}
\approx 47{,}760 \times 1.019
\approx 48{,}668
\]

따라서 2026년 6월은 대략 다음 수준으로 추정됩니다.

| 기준시점 | FCD 추정치 | TD | FCD/TD 추정치 |
|---|---:|---:|---:|
| 2026-06 | 약 48,668 | 147,709 | 약 32.95% |

이 값은 2026년 5월 FCD와 NBM의 증가율을 이용한 추정치이므로, 정식 데이터셋에는 `estimated = true`로 표시하는 것이 좋습니다. 정확한 2026년 6월 FCD는 NBM 발표문에 첨부된 차트 또는 원자료에서 직접 추출해야 합니다.

## 데이터 정리 형식

```csv
date,ncd_mdl_million,fcd_mdl_million,td_mdl_million,fcd_td_pct
2024-03,74529.6,39858.8,114388.4,34.85
2025-02,84383.1,43268.4,127651.5,33.88
2025-04,85361.3,42531.6,127892.9,33.26
2025-07,87480.5,43234.9,130715.4,33.07
2025-08,87549.3,44683.9,132233.2,33.79
2026-06,,48668,147709,32.95
```

NBM에는 `Deposits attracted in foreign currency`라는 별도 지표도 있지만, 이는 해당 월에 새로 유치된 예금의 **유량(flow)**입니다. FCD/TD에는 반드시 `balance of deposits in foreign currency`, 즉 기간 말 외화예금 **잔액(stock)**을 사용해야 합니다. [bnm](http://www.bnm.md/en/content/evolution-monetary-indicators-june-2026)




마다가스카르는 **외화예금(FCD)** 자료는 확인되지만, 최신 공개자료에서 FCD와 총예금(TD)을 항상 같은 표에 제공하지는 않습니다. 가장 직접적으로 `FCD/TD`를 확인할 수 있는 자료는 IMF의 마다가스카르 금융안정성평가(FSAP)이며, 최신 FCD 잔액은 IMF 프로그램 보고서와 마다가스카르 중앙은행(BFM) 자료에서 확인할 수 있습니다.

## 공식 원자료

### IMF 금융안정성 지표

[IMF — Madagascar Financial System Stability Assessment](https://www.imf.org/external/pubs/ft/scr/2016/cr16377.pdf)

IMF의 `Bank FSIs` 표에는 다음 지표가 직접 포함되어 있습니다.

> **Foreign currency deposits / total deposits**

단위는 비율(%)이며, 2008~2015년 은행권 자료입니다. 자료 출처는 마다가스카르 중앙은행(당시 BCM)입니다. [imf](https://www.imf.org/external/pubs/ft/scr/2016/cr16377.pdf)

### 마다가스카르 중앙은행(BFM)

[Banky Foiben’i Madagasikara — Annual Report 2019](https://www.banky-foibe.mg/admin/wp-content/uploads/2020/06/Rapport-annuel-2019.pdf)

BFM 연차보고서에는 다음 항목이 포함됩니다.

- `Dépôts en devises des résidents`
- `Dépôts à vue des résidents`
- `Dépôts à terme des résidents`
- `Dépôts des banques`
- `Masse monétaire et ses composantes`

외화예금은 주로 거주자 예금 기준으로 집계됩니다. [banky-foibe](https://www.banky-foibe.mg/admin/wp-content/uploads/2020/06/Rapport-annuel-2019.pdf)

## FCD/TD 역사 시계열

IMF FSAP의 공식 금융안정성 표에서 확인되는 FCD/TD는 다음과 같습니다.

| 연도 | FCD/TD |
|---|---:|
| 2008 | 21.0% |
| 2009 | 19.4% |
| 2010 | 21.5% |
| 2011 | 19.5% |
| 2012 | 19.2% |
| 2013 | 16.6% |
| 2014 | 18.1% |
| 2015 | 17.7% |

2015년 은행권 예금의 약 **17.7%**가 외화예금이었습니다. IMF 표의 해당 지표는 은행권의 외화예금을 총예금으로 나눈 비율이며, 다른 금융안정성 지표와 함께 제시됩니다. [imf](https://www.imf.org/external/pubs/ft/scr/2016/cr16377.pdf)

## 최근 FCD 잔액

IMF의 2023년 마다가스카르 프로그램 보고서에는 외화예금 잔액이 다음과 같이 제시됩니다.

| 연도 또는 기준시점 | FCD |
|---|---:|
| 2019 | 1,111 billion MGA |
| 2020 | 1,472 billion MGA |
| 2021 | 1,519 billion MGA |
| 2022 | 1,548 billion MGA |
| 이후 관측치 | 1,640 → 1,959 → 1,604 → 1,719 → 1,996 → 2,112 → 2,197 → 2,289 → 2,346 → 2,372 billion MGA |

다만 이 표의 FCD 시계열은 월별 또는 분기별 관측치가 혼합되어 있고, 같은 표에 TD가 별도로 제공되지 않으므로 그대로 FCD/TD를 계산하면 안 됩니다. [imf](https://www.imf.org/-/media/files/publications/cr/2023/english/1mdgea2023004.pdf)

2022년 IMF 보고서에도 외화예금 잔액이 1,202 billion MGA에서 2,361 billion MGA까지 증가한 시계열이 제시되지만, 역시 분모인 TD는 별도로 확인해야 합니다. [imf](https://www.imf.org/-/media/Files/Publications/CR/2022/English/1MDGEA2022001.ashx)

## 사용할 수 있는 데이터 구조

공식적으로 직접 확인 가능한 FCD/TD 역사 시계열은 다음과 같이 정리할 수 있습니다.

```csv
date,fcd_td_pct
2008,21.0
2009,19.4
2010,21.5
2011,19.5
2012,19.2
2013,16.6
2014,18.1
2015,17.7
```

최신 FCD 잔액은 다음처럼 별도 관리하는 것이 안전합니다.

```csv
date,fcd_mga_billion,td_mga_billion,fcd_td_pct
2019,,,
2020,,,
2021,,,
2022,,,
```

## TD 확보 방법

FCD/TD의 최신 시계열을 만들려면 BFM의 `Situation des banques de dépôts` 또는 IMF IFS에서 다음 두 계열을 함께 받아야 합니다.

```text
fcd = Foreign currency deposits of residents
td  = Total deposits of residents or total customer deposits
fcd_td = fcd / td * 100
```

BFM 연차보고서의 2019년 자료에는 `Dépôts en devises des résidents`와 거주자 예금의 요구불·정기예금 항목이 포함되어 있어, 연말 기준 FCD와 TD를 재구성할 수 있습니다. [banky-foibe](https://www.banky-foibe.mg/admin/wp-content/uploads/2020/06/Rapport-annuel-2019.pdf)

다만 **FCD + 현지통화 예금**으로 TD를 만들 때는 정부예금, 은행 간 예금, 비거주자 예금의 포함 여부를 확인해야 합니다. IMF의 FCD/TD 지표는 은행권 총예금 기준이므로, BFM의 특정 고객예금 표와 결합할 경우 금융기관 범위를 동일하게 맞춰야 합니다.

## 결론

현재 확인 가능한 가장 신뢰성 높은 결과는 다음입니다.

```text
자료:
  IMF Financial System Stability Assessment / BFM

FCD/TD:
  2008 = 21.0%
  2009 = 19.4%
  2010 = 21.5%
  2011 = 19.5%
  2012 = 19.2%
  2013 = 16.6%
  2014 = 18.1%
  2015 = 17.7%

최신 FCD:
  2022년 이후 약 2.0~2.4 trillion MGA 수준의 관측치 존재

최신 TD:
  같은 표에서 직접 확인되지 않음
```

따라서 마다가스카르는 **과거 FCD/TD 비율은 IMF FSI로 사용 가능하지만, 최신 월별 FCD/TD에는 BFM 또는 IMF IFS의 TD 원자료를 추가로 결합해야 하는 국가**입니다.