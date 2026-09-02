몰디브는 **몰디브통화청(MMA)**이 `In foreign currency`와 `Dollarization ratio`를 공식 통계 데이터베이스에서 직접 제공합니다. IMF 자료에서도 몰디브의 예금 달러화율을 FCD/총예금으로 정의해 제시하므로, FCD/TD 목적에는 적합한 국가입니다. [database.mma.gov](https://database.mma.gov.mv/viya/explore/2219)

## 공식 원자료

### MMA Statistics Database

[MMA Financial Sector Statistics Database](https://database.mma.gov.mv/viya/explore/2276)

여기서 다음 항목을 사용하면 됩니다.

- `Depository Corporations Survey`
- `Other Depository Corporation Survey`
- `Broad money`
- `Quasi money`
- `In foreign currency`
- `Dollarization ratio`

MMA 데이터베이스는 중앙은행과 상업은행을 합친 **Depository Corporations Survey**를 제공하며, `In national currency`, `In foreign currency`, `Dollarization ratio`를 별도 항목으로 포함합니다. [database.mma.gov](https://database.mma.gov.mv/viya/explore/2276)

## 변수 정의

몰디브의 경우 다음 정의가 가장 적합합니다.

| 변수 | MMA 항목 |
|---|---|
| `fcd` | Quasi money — In foreign currency |
| `td` | Total deposits 또는 FCD + domestic-currency deposits |
| `fcd_td` | Dollarization ratio |

직접 계산할 경우:

\[
\text{FCD/TD}
=
\frac{\text{Foreign-currency deposits}}
{\text{Foreign-currency deposits}+\text{Domestic-currency deposits}}
\times 100
\]

MMA의 금융통계에서 상업은행 부채도 `Transferable deposits`와 `Other deposits`로 나뉘며, 각각 `Local currency`와 `Foreign currency` 세부항목을 제공합니다. 따라서 더 엄밀하게 계산하려면 다음을 합산하면 됩니다. [database.mma.gov](https://database.mma.gov.mv/viya/explore/2219)

\[
FCD =
FC\ transferable\ deposits
+
FC\ other\ deposits
\]

\[
TD =
LC\ transferable\ deposits
+
LC\ other\ deposits
+
FCD
\]

## 확인된 예금 달러화율

IMF 금융부문 평가 자료에서 확인되는 몰디브의 FCD/TD는 다음과 같습니다.

| 기준시점 | FCD/TD |
|---|---:|
| 2023년경 | 53% |
| 2024년경 | 49% |

IMF는 2023년 몰디브 은행권에서 총예금의 **53%**가 외화로 표시되어 있다고 평가했습니다.  2024년 IMF 자료에서는 예금 달러화율을 **49% of total deposits**로 제시했습니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2024/020/article-A001-en.xml)

따라서 현재 공개된 공식·국제기구 자료 기준으로는 몰디브의 예금 달러화율이 대략 **50% 전후**라고 볼 수 있습니다.

## TD 수치

MMA 데이터베이스에는 FCD와 국내통화 예금의 절대액을 함께 제공하는 `Depository Corporations Survey`가 있으므로, TD도 직접 구성할 수 있습니다. [database.mma.gov](https://database.mma.gov.mv/viya/explore/2276)

다만 검색 결과 본문에서는 최신 시점의 숫자 열이 표시되지 않아, 현재 확인된 자료만으로 특정 월의 정확한 TD 금액을 확정하기는 어렵습니다. TD는 다음과 같이 추출해야 합니다.

```text
td =
local-currency transferable deposits
+ local-currency other deposits
+ foreign-currency transferable deposits
+ foreign-currency other deposits
```

또는 MMA 데이터베이스에 `Total deposits`가 별도 제공되는 경우 해당 항목을 사용하면 됩니다.

## 데이터 구성 예시

```csv
date,fcd_mvr_million,td_mvr_million,fcd_td_pct
2023-12,,,53.00
2024-12,,,49.00
```

정확한 금액 시계열을 구축하려면 MMA 데이터베이스에서 다음 행을 내려받으면 됩니다.

```text
Other Depository Corporation Survey
  Liabilities
    Deposits
      Transferable deposits
        Local currency
        Foreign currency
      Other deposits
        Local currency
        Foreign currency
```

## 해석상 주의점

- 몰디브에서는 외화예금이 주로 **미국 달러 예금**이므로 FCD/TD가 매우 높습니다.
- IMF가 말하는 53%와 49%는 단순히 `foreign currency / broad money`가 아니라 은행권 **총예금 중 외화표시 예금 비중**입니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2024/020/article-A001-en.xml)
- `Foreign currency loans`는 FCD가 아니므로 예금 달러화율 계산에서 제외해야 합니다.
- MMA의 `Broad money`에는 현금통화가 포함될 수 있으므로, FCD/TD 계산에서는 Broad money 전체를 TD로 사용하지 말고 예금부채 항목을 사용하는 것이 좋습니다. [database.mma.gov](https://database.mma.gov.mv/viya/explore/2276)
- 2025년 이후 외화예금 규제가 변경되었고, 외화예금 지급준비율도 2025년 7월 24일부터 5.0%로 낮아졌으므로, 시계열 분석에서는 정책 변경 시점을 별도 표시하는 것이 좋습니다. [documents1.worldbank](https://documents1.worldbank.org/curated/en/099846210302541970/pdf/IDU-f29ea907-6c13-451b-a6a3-f951f927b5a8.pdf)

현재 확인 결과를 요약하면 다음과 같습니다.

```text
공식 데이터베이스:
  MMA Depository Corporations Survey

FCD:
  Quasi money / In foreign currency
  또는 FC transferable deposits + FC other deposits

TD:
  domestic-currency deposits + foreign-currency deposits

FCD/TD:
  2023년경 약 53%
  2024년경 약 49%
```

몰디브는 **FCD와 TD를 모두 MMA 원자료에서 재구성할 수 있고, IMF가 FCD/TD 비율도 직접 제공하는 국가**로 분류하면 됩니다.


멕시코는 **멕시코은행(Banco de México, Banxico)**의 SIE(Economic Information System)에서 상업은행 예금을 통화별·상품별로 제공하므로 FCD/TD를 직접 계산할 수 있습니다. 가장 적합한 표는 `CF664: Saldos de los instrumentos de captación de la banca comercial por moneda`입니다. [banxico.org](https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=19&idCuadro=CF664&accion=consultarCuadro&locale=es)

## 공식 원자료

### Banxico SIE — CF664

[CF664: Commercial-bank deposit instruments by currency](https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=19&idCuadro=CF664&accion=consultarCuadro&locale=es)

이 표는 다음 예금상품을 통화별로 분해합니다.

- `Depósitos de exigibilidad inmediata`
- `Captación a plazo`
- `En moneda nacional`
- `En moneda extranjera`

자료는 월별이며, 2011년 4월 이후 시계열을 제공합니다. [banxico.org](https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=19&idCuadro=CF664&accion=consultarCuadro&locale=es)

## 변수 정의

멕시코의 경우 다음처럼 계산하는 것이 적절합니다.

| 변수 | Banxico 항목 |
|---|---|
| `fcd` | Foreign-currency demand deposits + foreign-currency time deposits |
| `td` | Total demand deposits + total time deposits |
| `fcd_td` | `fcd / td × 100` |

계산식:

\[
\text{FCD}
=
\text{FC demand deposits}
+
\text{FC time deposits}
\]

\[
\text{TD}
=
\text{Total demand deposits}
+
\text{Total time deposits}
\]

\[
\text{FCD/TD}
=
\frac{\text{FCD}}{\text{TD}}
\times 100
\]

Banxico의 통계 표는 금액을 **십억 멕시코 페소(MXN billion)** 단위로 요약하거나, SIE 원자료에서는 더 세부 단위로 제공합니다.

## 확인 가능한 예시

Banxico 요약표의 2025년 4월 자료에서:

| 항목 | 전체 | 외화 |
|---|---:|---:|
| Demand deposits | MXN 5,061.8 billion | MXN 200.5 billion |
| Time deposits | MXN 3,089.8 billion | MXN 216.8 billion |
| 합계 | MXN 8,151.6 billion | MXN 417.3 billion |

따라서:

\[
\text{FCD/TD}
=
\frac{200.5+216.8}
{5{,}061.8+3{,}089.8}
\times 100
=
5.12\%
\]

| 기준시점 | FCD | TD | FCD/TD |
|---|---:|---:|---:|
| 2025-04 | MXN 417.3 bn | MXN 8,151.6 bn | 5.12% |

Banxico의 통화별 예금 요약에서도 외화 수치는 요구불예금 약 MXN 200.5 billion, 정기예금 약 MXN 216.8 billion으로 제시됩니다. [banxico.org](https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=3&idCuadro=CA452&accion=consultarCuadroAnalitico&locale=en)

## 더 넓은 TD 정의

멕시코 통계에는 `Dépósitos bancarios` 또는 `Captación bancaria` 범위가 표마다 다를 수 있습니다. 따라서 국제비교용으로는 다음 두 가지 중 하나를 고정하는 것이 좋습니다.

### 상품기준 TD

```text
TD =
demand deposits
+ time deposits
```

이 정의는 FCD를 같은 두 상품의 외화분으로 계산할 때 가장 일관적입니다.

### 전체 은행수신 기준 TD

Banxico SIE의 `Captación de la banca comercial` 표에는 요구불·정기예금 외에 일부 기타 수신상품이 포함될 수 있습니다. 이 경우에는 전체 `Total`과 전체 `En moneda extranjera` 열을 같은 표에서 사용해야 합니다. [banxico.org](https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=3&accion=consultarCuadroAnalitico&idCuadro=CA452&locale=es)

```text
fcd = Total foreign-currency bank funding/deposits
td  = Total commercial-bank deposit funding
```

다만 채권성 수신이나 은행 간 자금까지 포함될 수 있으므로, 사용 목적이 예금 달러화율이면 첫 번째 **demand + time deposits 기준**을 권장합니다.

## 장기·월별 데이터 형식

```csv
date,fc_demand_mxn_billion,fc_time_mxn_billion,fcd_mxn_billion,td_mxn_billion,fcd_td_pct
2025-04,200.5,216.8,417.3,8151.6,5.12
```

실제 다운로드 시에는 CF664에서 다음 열을 추출하면 됩니다.

```text
date
demand_deposits_total
demand_deposits_foreign_currency
time_deposits_total
time_deposits_foreign_currency
```

그리고 Python이나 SQL에서:

```text
fcd = demand_fc + time_fc
td = demand_total + time_total
fcd_td_pct = fcd / td * 100
```

## 주의점

- Banxico의 `En moneda extranjera`는 외화로 표시된 은행 예금의 **페소 환산 잔액**입니다.
- 외환보유액, 은행의 해외예금, 외화대출은 FCD에 포함하면 안 됩니다.
- 멕시코에는 상업은행과 개발은행이 모두 존재하므로, 상업은행만 볼지 전체 예금취급기관을 볼지 범위를 고정해야 합니다. Banxico의 요약표에서는 은행 예금과 개발은행 포함 여부가 각주로 구분됩니다. [banxico.org](https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=3&accion=consultarCuadroAnalitico&idCuadro=CA452&locale=es)
- 기업과 가계의 예금만 필요한 경우에는 Banxico의 부문별 수신표를 사용하고, 전체 은행권 달러화율에는 CF664 또는 monetary aggregates 표를 사용하는 것이 적절합니다.

현재 확인 결과의 핵심값은 다음과 같습니다.

```text
Source: Banco de México SIE, CF664
Frequency: monthly
FCD: foreign-currency demand + time deposits
TD: total demand + time deposits
Example: 2025-04 FCD/TD ≈ 5.12%
```



북마케도니아는 **북마케도니아공화국 국립은행(NBRNM)**이 월별 예금 통계를 통화별로 제공하며, IMF Article IV 보고서에는 `Foreign currency deposits / total deposits` 비율도 직접 수록되어 있습니다. 따라서 FCD/TD를 구하기에 적합한 국가입니다. [nbrm](https://www.nbrm.mk/monetarna_statistika_i_statistika_na_kamatni_stapki-en.nspx)

## 공식 원자료

### NBRNM 월별 통화·금리 통계

[NBRNM Monetary and Interest Rates Statistics](https://www.nbrm.mk/monetarna_statistika_i_statistika_na_kamatni_stapki-en.nspx)

NBRNM은 비금융기업과 가계의 예금을 다음과 같이 분류합니다.

- Denar deposits
- Foreign-currency deposits
- Denar deposits with foreign-exchange clause
- Demand deposits
- Time deposits
- Savings deposits
- Restricted deposits

NBRNM 자료에서 외화예금은 외화 표시 예금과 일부 외환연동 예금을 구분해 제공할 수 있으므로, 순수 FCD만 사용할지 FX-clause 예금까지 포함할지 명확히 해야 합니다. [nbrm](https://www.nbrm.mk/monetarna_statistika_i_statistika_na_kamatni_stapki-en.nspx)

### PXWeb 월별 예금 데이터

[Deposits with other depository corporations](https://nbstat.nbrm.mk/pxweb/en/MS%20i%20KS/MS%20i%20KS__MS__Monetarni%20i%20kreditni%20agregati/1_DepozitiOstanatiInstiMesecniEN.px/)

이 표에는 다음 항목이 포함됩니다.

> **TOTAL DEPOSITS — Deposits included in broad money M4**

통화별·부문별 예금이 제공되므로, 월별 FCD와 TD를 직접 추출할 수 있습니다. [nbstat.nbrm](https://nbstat.nbrm.mk/pxweb/en/MS%20i%20KS/MS%20i%20KS__MS__Monetarni%20i%20kreditni%20agregati/1_DepozitiOstanatiInstiMesecniEN.px/)

## 2024년 최신 연간 수치

IMF의 2025년 Article IV 표에 따르면 2024년 북마케도니아 은행권 총예금은 **MKD 799.0 billion**이며, 외화예금 비중은 **44.4%**입니다. [imf](https://www.imf.org/-/media/Files/Publications/CR/2025/English/1mkdea2025001-print-pdf.ashx)

| 기준시점 | TD | FCD/TD | FCD 추정액 |
|---|---:|---:|---:|
| 2024년 말 | MKD 799.0 bn | 44.4% | 약 MKD 354.8 bn |

계산:

\[
\text{FCD}
=
799.0 \times 44.4\%
=
354.76
\]

따라서 2024년 말 외화예금은 약 **MKD 354.8 billion**입니다.

```text
date = 2024-12
td = 799.0 billion MKD
fcd_td = 44.4%
fcd ≈ 354.8 billion MKD
```

## 최근 추이

IMF 표에서 확인되는 총예금과 외화예금 비중은 다음과 같습니다.

| 연도 | TD, MKD bn | FCD/TD |
|---|---:|---:|
| 2016 | 392.5 | 43.0% |
| 2017 | 430.3 | 42.7% |
| 2018 | 452.3 | 42.3% |
| 2019 | 479.3 | 40.7% |
| 2020 | 526.5 | 41.8% |
| 2021 | 572.9 | 44.8% |
| 2022 | 615.5 | 44.8% |
| 2023 | 656.9 | 46.3% |
| 2024 | 700.1 또는 748.3 | 44.4% |
| 최신 표 말미 | 799.0 | 44.4% |

원문 표에는 392.5부터 799.0까지의 연도별 값이 연속적으로 제시되어 있습니다. 표의 2024년 관측치와 보고기간 표기는 IMF 원문 각주를 기준으로 확인하는 것이 좋습니다. [elibrary.imf](https://www.elibrary.imf.org/view/journals/002/2025/101/article-A001-en.xml)

## 2024년 FCD/TD 시계열

표의 총예금과 비율을 결합하면 다음처럼 정리할 수 있습니다.

```csv
date,td_mkd_billion,fcd_td_pct,fcd_mkd_billion
2016,392.5,43.0,168.8
2017,430.3,42.7,183.7
2018,452.3,42.3,191.3
2019,479.3,40.7,195.1
2020,526.5,41.8,220.1
2021,572.9,44.8,256.3
2022,615.5,44.8,275.7
2023,656.9,46.3,304.2
2024,799.0,44.4,354.8
```

단, 위 표의 FCD 금액은 IMF가 제공한 총예금과 비율을 곱한 **계산값**입니다. 정확한 FCD 잔액은 NBRNM PXWeb의 통화별 예금 원자료에서 직접 추출하는 것이 좋습니다.

## 계산 시 주의점

NBRNM의 방법론에서는 외화예금과 외환연동형 데나르 예금을 별도 분류합니다. 따라서 다음 두 가지 비율을 구분할 수 있습니다. [nbrm](https://www.nbrm.mk/content/statistika/Monetarna%20statistika/metodologija/Metodologija%20_monetarna_07_2021_eng.pdf)

### 순수 FCD/TD

```text
fcd =
  deposits in foreign currency

td =
  deposits in denars
+ deposits in foreign currency
```

### 외환위험 포함 비율

```text
fcd_fx_linked =
  deposits in foreign currency
+ denar deposits with FX clause

ratio =
  fcd_fx_linked / td
```

IMF 표에도 `Foreign currency deposits/total deposits`와 `Including foreign exchange-indexed`가 별도 행으로 제시됩니다. 2024년 기준 표준 FCD/TD는 **44.4%**, 외환연동 예금까지 포함하면 약 **44.5%**입니다. [imf](https://www.imf.org/-/media/Files/Publications/CR/2025/English/1mkdea2025001-print-pdf.ashx)

## 최종 권장 정의

국제비교용 데이터셋에는 다음 정의를 권장합니다.

```text
country = Republic of North Macedonia
source = NBRNM
fcd = pure foreign-currency deposits
td = total deposits included in broad money M4
ratio = fcd / td * 100
```

현재 확인 가능한 핵심값은 다음과 같습니다.

```text
2024 TD       = MKD 799.0 billion
2024 FCD/TD   = 44.4%
2024 FCD      ≈ MKD 354.8 billion
```

북마케도니아는 **FCD와 TD의 공식 월별 원자료가 모두 존재하고, IMF가 검증된 FCD/TD 비율까지 제공하는 국가**로 분류하면 됩니다.


몬테네그로는 유로화를 일방적으로 사용하는 **유로화 경제**이므로, FCD는 유로 이외 통화로 표시된 예금입니다. 중앙은행(CBCG)은 `deposits in other currencies`와 `total deposits`를 별도로 제공하므로 FCD/TD 계산이 가능합니다. [cbcg](https://www.cbcg.me/slike_i_fajlovi/eng/fajlovi/fajlovi_publikacije/god_izv_o_radu/cbcg_annual_report_2023.pdf)

## 공식 원자료

### Central Bank of Montenegro

[CBCG Statistics](https://www.cbcg.me/en/about-us/legislation/regulations/statistics)

주요 자료:

- [CBCG Annual Report 2023](https://www.cbcg.me/slike_i_fajlovi/eng/fajlovi/fajlovi_publikacije/god_izv_o_radu/cbcg_annual_report_2023.pdf)
- [CBCG Financial Stability Report 2024](https://www.cbcg.me/slike_i_fajlovi/eng/fajlovi/fajlovi_publikacije/fin_stabilnost/financial_stability_report_2024.pdf)
- [CBCG Q1 2024 Macroeconomic Report](https://www.cbcg.me/slike_i_fajlovi/eng/fajlovi/fajlovi_publikacije/makroekonomski/macro_q1_2024.pdf)
- [CBCG Reserve Requirement Statistics](https://www.cbcg.me/en/core-functions/financial-and-banking-operations/reserve-requirement)

## 변수 정의

몬테네그로에서는 다음과 같이 계산합니다.

| 변수 | CBCG 항목 |
|---|---|
| `fcd` | Deposits in other currencies |
| `td` | Total deposits |
| `fcd_td` | `Deposits in other currencies / Total deposits × 100` |

계산식:

\[
\text{FCD/TD}
=
\frac{\text{Deposits in other currencies}}
{\text{Total deposits}}
\times 100
\]

유로화가 사실상 국내통화이므로:

\[
TD = EUR\ deposits + other\ currency\ deposits
\]

여기서 `other currencies`에는 주로 USD, CHF, GBP 등의 예금이 포함됩니다.

## 2023년 말 수치

CBCG 연차보고서에 따르면 2023년 말 총예금은 **EUR 5,473.183 million**이며, 기타 통화 예금 비중은 **4.93%**였습니다. [cbcg](https://www.cbcg.me/slike_i_fajlovi/eng/fajlovi/fajlovi_publikacije/god_izv_o_radu/cbcg_annual_report_2023.pdf)

| 기준시점 | TD | FCD/TD | FCD 계산값 |
|---|---:|---:|---:|
| 2023년 말 | EUR 5,473.183 million | 4.93% | 약 EUR 269.8 million |

계산:

\[
5{,}473.183 \times 4.93\%
=
269.83
\]

따라서 2023년 말 외화예금은 약 **EUR 269.8 million**입니다.

```text
date = 2023-12
td = 5,473.183 million EUR
fcd_td = 4.93%
fcd ≈ 269.8 million EUR
```

CBCG는 2023년 말 예금 중 유로예금이 압도적인 비중을 차지했고, 기타 통화 예금이 전체의 4.93%였다고 명시합니다. [cbcg](https://www.cbcg.me/slike_i_fajlovi/eng/fajlovi/fajlovi_publikacije/god_izv_o_radu/cbcg_annual_report_2023.pdf)

## 2024년 TD

CBCG의 2024년 금융안정보고서에 따르면 2024년 말 총예금은 약 **EUR 5.8 billion**으로 사상 최고치를 기록했습니다. 예금은 연중 365.7 million EUR, 6.7% 증가했습니다. [cbcg](https://www.cbcg.me/slike_i_fajlovi/eng/fajlovi/fajlovi_publikacije/fin_stabilnost/financial_stability_report_2024.pdf)

보다 상세한 2024년 분기 자료에서:

| 기준시점 | TD |
|---|---:|
| 2024-03 | EUR 5,333.29 million |
| 2024-06 | EUR 5,383.36 million |
| 2024-12 | 약 EUR 5,839 million |

2024년 3월 총예금은 EUR 5,333.29 million, 6월은 EUR 5,383.36 million으로 보고되었습니다. [cbcg](https://www.cbcg.me/slike_i_fajlovi/eng/fajlovi/fajlovi_publikacije/makroekonomski/macro_q1_2024.pdf)

2024년 말 FCD 비율은 검색 결과에서 정확한 통화구성 수치가 확인되지 않지만, CBCG의 상세 월·분기 통계에서 `deposits in other currencies`를 추출하면 다음과 같이 계산할 수 있습니다.

```text
fcd = deposits in USD
    + deposits in CHF
    + deposits in GBP
    + deposits in other currencies

td = total deposits
fcd_td = fcd / td * 100
```

## 과거 추이

CBCG 보고서에서 확인되는 FCD/TD는 다음과 같습니다.

| 기준시점 | FCD/TD |
|---|---:|
| 2021년 말 | 약 5.75% |
| 2022년 말 | 5.12% |
| 2023년 말 | 4.93% |

2022년 말에는 기타 통화 예금이 총예금의 5.12%였고, 전년보다 0.63%p 하락했습니다.  2023년에는 다시 4.93%로 하락했습니다. [cbcg](https://www.cbcg.me/slike_i_fajlovi/eng/fajlovi/fajlovi_publikacije/god_izv_o_radu/cbcg_annual_report_2023.pdf)

## 최신 TD 참고

CBCG의 2026년 6월 지급준비금 통계에 따르면 지급준비금 산정 대상 총예금의 평균은 **EUR 5,883.50 million**이었습니다. 이 기간의 요구불예금 비중은 84.28%, 정기예금 비중은 15.72%입니다. [cbcg](https://www.cbcg.me/en/core-functions/financial-and-banking-operations/reserve-requirement)

다만 이 수치는 월말 잔액이 아닌 지급준비금 산정기간의 **평균 총예금**이므로, 월말 FCD/TD의 분모로 사용할 때는 CBCG 월말 `Total deposits`를 우선 사용해야 합니다.

## 분석용 데이터 형식

```csv
date,fcd_eur_million,td_eur_million,fcd_td_pct
2021-12,,,
2022-12,,,
2023-12,269.8,5473.183,4.93
2024-03,,5333.29,
2024-06,,5383.36,
2024-12,,5839.0,
```

몬테네그로는 다음처럼 처리하면 됩니다.

```text
source = Central Bank of Montenegro
fcd = deposits in other currencies
td = total deposits
currency = EUR
domestic_currency = EUR
```

중요한 점은 **유로예금을 FCD로 포함하지 않는 것**입니다. 몬테네그로는 유로화를 사용하므로, FCD는 `foreign currency deposits`라는 이름보다 CBCG의 **`deposits in other currencies`** 항목을 사용하는 것이 정확합니다.


몽골은 **몽골은행(Bank of Mongolia)**이 외화예금 비중을 직접 발표하고, 월별 총예금 시계열도 제공합니다. 공식 월간 통화리뷰에서 `foreign currency deposits accounted for X% of total deposits`를 직접 확인할 수 있어 FCD/TD 계산에 적합합니다. [mongolbank](https://www.mongolbank.mn/documents/statistic/monetaryreview/2021/05e.pdf)

## 공식 원자료

### Bank of Mongolia — Monetary Review

[Bank of Mongolia Monetary Review — May 2021](https://www.mongolbank.mn/documents/statistic/monetaryreview/2021/05e.pdf)

[Bank of Mongolia Monetary Review — March 2022](https://www.mongolbank.mn/documents/statistic/monetaryreview/2022/03e.pdf)

월간 리뷰에는 다음 항목이 있습니다.

- Deposits in domestic currency
- Deposits in foreign currency
- Current accounts in domestic currency
- Current accounts in foreign currency
- Total deposits
- Foreign-currency deposits as a percentage of total deposits

## 확인 가능한 FCD/TD 수치

몽골은행 공식 자료에서 확인되는 예금 달러화율은 다음과 같습니다.

| 기준시점 | FCD/TD |
|---|---:|
| 2021년 5월 | 22.1% |
| 2022년 2월 | 23.8% |

2021년 5월에는 외화예금이 총예금의 **22.1%**였고, 개인예금의 19.7%, 기업예금의 38.2%가 외화로 표시되어 있었습니다. [mongolbank](https://www.mongolbank.mn/documents/statistic/monetaryreview/2021/05e.pdf)

2022년 2월에는 외화예금이 총예금의 **23.8%**로 상승했으며, 개인예금의 22.0%, 기업예금의 37.7%가 외화예금이었습니다. [mongolbank](https://www.mongolbank.mn/documents/statistic/monetaryreview/2022/03e.pdf)

## 2022년 2월 수치

몽골은행은 2022년 2월 총예금의 외화 비중을 직접 제시합니다.

| 기준시점 | TD | FCD/TD | FCD |
|---|---:|---:|---:|
| 2022-02 | 원자료 기준 총예금 | 23.8% | `TD × 23.8%` |

공식 리뷰에는 예금 증가 요인으로 국내통화 예금과 외화예금을 분리해 설명하고, 총예금 중 외화예금 비율을 23.8%로 표시합니다. [mongolbank](https://www.mongolbank.mn/documents/statistic/monetaryreview/2022/03e.pdf)

## 총예금(TD) 자료

장기·월별 TD는 몽골은행 자료를 기반으로 한 CEIC 시계열에서 확인됩니다.

| 기준시점 | TD |
|---|---:|
| 2024-12 | 약 USD 7.864 billion |
| 2025-01 | 약 USD 7.685 billion |
| 2026-04 | 약 USD 9.228 billion |
| 2026-05 | 약 USD 9.312 billion |

CEIC는 원자료가 몽골은행의 현지통화 기준 총예금이며, 달러 수치는 기간 말 환율로 환산했다고 설명합니다. 따라서 분석에는 USD 환산값보다 몽골은행 원자료의 **MNT 기준 금액**을 사용하는 것이 좋습니다. [ceicdata](https://www.ceicdata.com/en/indicator/mongolia/total-deposits)

## 몽골은행 통계에서 직접 계산하는 방법

몽골은행의 월별 통화통계에서 다음 항목을 가져오면 됩니다.

```text
fcd =
  deposits in foreign currency
+ current accounts in foreign currency

td =
  deposits in domestic currency
+ current accounts in domestic currency
+ deposits in foreign currency
+ current accounts in foreign currency
```

또는 예금 표에서 `Total deposits`를 직접 사용합니다.

\[
\text{FCD/TD}
=
\frac{\text{FC deposits}+\text{FC current accounts}}
{\text{Total deposits}}
\times 100
\]

몽골의 경우 외화예금과 외화 당좌·요구불계정이 별도로 표시되므로, FCD를 순수하게 계산할 때는 두 항목을 모두 포함하는 것이 좋습니다. 몽골은행의 통화리뷰도 `deposits in FC`와 `current accounts in FC`를 따로 표시합니다. [mongolbank](https://www.mongolbank.mn/documents/statistic/monetaryreview/2021/05e.pdf)

## 데이터 구조

```csv
date,fcd_mnt_billion,td_mnt_billion,fcd_td_pct
2021-05,,,22.10
2022-02,,,23.80
2024-12,,,
2025-01,,,
2026-05,,,
```

비율만 공식적으로 확인되는 과거 자료는 다음처럼 저장할 수 있습니다.

```text
2021-05: 22.1%
2022-02: 23.8%
```

## 주의점

- 몽골의 FCD는 외화예금과 외화 당좌·요구불계정을 구분해 표시할 수 있습니다.
- 단순히 `Deposits in FC`만 사용하는지, `Current accounts in FC`까지 포함하는지 정의를 고정해야 합니다.
- 총예금은 예금과 외화 당좌계정까지 포함한 예금부채 기준으로 맞추는 것이 좋습니다.
- CEIC의 USD 금액은 환산값이므로, FCD/TD 계산에서는 FCD와 TD를 모두 MNT로 통일해야 합니다.
- 외화대출, 외환보유액, 상업은행의 해외예금은 FCD에 포함하면 안 됩니다.
- 2026년 1월부터 몽골은행은 MNT와 외화 예금에 서로 다른 지급준비율을 적용하고 있으므로, 최근 시계열 분석에서는 정책 변경 시점을 표시하는 것이 좋습니다. [mongolbank](https://www.mongolbank.mn/en/p/1220)

현재 확인 결과를 요약하면 다음과 같습니다.

```text
Source:
  Bank of Mongolia Monetary Review

FCD/TD:
  2021-05 = 22.1%
  2022-02 = 23.8%

TD:
  Bank of Mongolia monthly data
  2026-05 converted value ≈ USD 9.312 billion

Recommended:
  fcd = FC deposits + FC current accounts
  td = total deposits
  ratio = fcd / td × 100
```


모잠비크는 **모잠비크은행(Banco de Moçambique)**이 총예금과 통화별 예금을 직접 제공하므로 FCD/TD 계산에 적합합니다. 최신으로 확인되는 중앙은행 금융안정보고서 기준 2024년 예금 총액은 MZN 708.67 billion, 외화예금은 MZN 152.06 billion입니다. [bancomoc](https://www.bancomoc.mz/media/rs3dkkii/financial-stability-report-2024_v02.pdf)

## 공식 원자료

### Banco de Moçambique — Financial Stability Report 2024

[Financial Stability Report 2024](https://www.bancomoc.mz/media/rs3dkkii/financial-stability-report-2024_v02.pdf)

이 보고서의 `Weight of Deposits by Currency`에서 다음을 제공합니다.

- Total deposits
- Deposits in national currency
- Deposits in foreign currency
- 외화예금 비중

보고서의 기준은 모잠비크 상업은행 시스템이며, 금액 단위는 **십억 메티칼(MZN billion)**입니다. [bancomoc](https://www.bancomoc.mz/media/rs3dkkii/financial-stability-report-2024_v02.pdf)

## 2024년 수치

| 기준시점 | TD | FCD | FCD/TD |
|---|---:|---:|---:|
| 2024년 말 | MZN 708.67 bn | MZN 152.06 bn | 21.46% |

계산:

\[
\frac{152.06}{708.67}
\times 100
=
21.46\%
\]

국내통화 예금은 MZN 556.60 billion으로 총예금의 78.54%, 외화예금은 MZN 152.06 billion으로 21.46%였습니다. [bancomoc](https://www.bancomoc.mz/media/rs3dkkii/financial-stability-report-2024_v02.pdf)

```text
date = 2024-12
td = 708.67 billion MZN
fcd = 152.06 billion MZN
fcd_td = 21.46%
```

## 과거 비교

모잠비크 중앙은행 금융안정보고서에서 확인되는 비교값은 다음과 같습니다.

| 기준시점 | TD | FCD | FCD/TD |
|---|---:|---:|---:|
| 2022년 상반기 | MZN 573.7 bn | MZN 148.3 bn | 25.84% |
| 2024년 말 | MZN 708.67 bn | MZN 152.06 bn | 21.46% |

2022년 상반기에는 외화예금 비중이 25.84%였고, 148.3 billion MZN이었습니다. 이후 외화예금 잔액 자체는 비슷한 수준이었지만 총예금이 증가하면서 비중은 2024년 말 21.46%로 낮아졌습니다. [bancomoc](https://www.bancomoc.mz/media/rs3dkkii/financial-stability-report-2024_v02.pdf)

## 2024년 상반기 자료

모잠비크은행의 2024년 금융안정성 bulletin은 2024년 상반기 총예금을 **MZN 642.61 billion**으로 보고합니다. 이는 2023년 같은 기간보다 10.64%, 직전 반기보다 5.99% 증가한 수치입니다. [bancomoc](https://www.bancomoc.mz/media/ltlmilc0/financial-stability-bulletin-2024_-v0.pdf)

같은 보고서는 2024년 상반기 국내통화 예금이 MZN 496.99 billion이라고 제시합니다. 따라서 외화예금은 대략 다음과 같이 계산할 수 있습니다.

\[
FCD
\approx 642.61 - 496.99
=
145.62
\]

| 기준시점 | TD | NCD | FCD 계산값 | FCD/TD |
|---|---:|---:|---:|---:|
| 2024년 상반기 | 642.61 | 496.99 | 약 145.62 | 약 22.66% |

다만 이 값은 서로 다른 표의 반올림 수치를 이용한 계산값이므로, 정식 시계열에는 중앙은행 보고서의 통화별 총액을 우선 사용해야 합니다. [bancomoc](https://www.bancomoc.mz/media/ltlmilc0/financial-stability-bulletin-2024_-v0.pdf)

## 데이터 형식

```csv
date,fcd_mzn_billion,td_mzn_billion,fcd_td_pct
2022-H1,148.30,573.70,25.84
2024-H1,145.62,642.61,22.66
2024-12,152.06,708.67,21.46
```

## 추가 자료

Banco de Moçambique의 금융안정성 자료는 `foreign currency deposits to total deposits` 비율을 금융안정성 지표로 사용합니다. [bancomoc](https://www.bancomoc.mz/media/ltlmilc0/financial-stability-bulletin-2024_-v0.pdf)

IMF 자료도 모잠비크 은행 예금의 통화구성을 제공합니다. IMF 보고서의 통화표에서는 외화예금과 국내통화 예금을 별도 계열로 제시하며, 2024년 보고서의 과거 시계열에는 외화예금이 256.2 billion MZN까지 증가한 관측치도 포함되어 있습니다. [imf](https://www.imf.org/-/media/files/publications/cr/2024/english/1mozea2024001.pdf)

다만 IMF 표의 FCD 수치는 시점과 금융기관 범위가 중앙은행 금융안정보고서와 다를 수 있으므로, 국제비교용 기준값으로는 다음을 우선 권장합니다.

```text
source = Banco de Moçambique Financial Stability Report
fcd = Deposits in foreign currency
td = Total deposits
ratio = fcd / td × 100
```

현재 확인된 모잠비크의 핵심값은 다음과 같습니다.

```text
2024 TD       = MZN 708.67 billion
2024 FCD      = MZN 152.06 billion
2024 FCD/TD   = 21.46%
```


모리셔스는 **모리셔스은행(Bank of Mauritius, BoM)**이 월별로 루피 예금과 외화예금을 분리해 제공하므로, FCD/TD 계산에 매우 적합합니다. BoM의 `Monetary Developments`와 `Monthly Statistical Bulletin`에서 FCD와 총예금(TD)을 같은 기준월로 구성할 수 있습니다. [bom](https://www.bom.mu/economic-and-financial-data-mauritius)

## 공식 원자료

### Bank of Mauritius Monetary and Financial Statistics

[BoM Economic and Financial Data](https://www.bom.mu/economic-and-financial-data-mauritius)

주요 자료:

- `Depository Corporation Survey`
- `Sectoral Balance Sheet of Banks`
- `Monthly Statistical Bulletin`
- `Maturity Pattern of Banks' Foreign Currency Deposits`

BoM는 외화예금의 만기·통화별 세부 통계도 별도로 제공합니다. [bom](https://www.bom.mu/economic-and-financial-data-mauritius)

## 변수 정의

BoM의 `Deposit Liabilities` 표를 사용하면 됩니다.

| 변수 | BoM 항목 |
|---|---|
| `ncd` | Rupee Deposits |
| `fcd` | Foreign Currency Deposits |
| `td` | Deposit Liabilities = Rupee Deposits + Foreign Currency Deposits |
| `fcd_td` | `FCD / TD × 100` |

계산식:

\[
TD = NCD + FCD
\]

\[
\text{FCD/TD}
=
\frac{FCD}{TD}
\times 100
\]

금액 단위는 **백만 모리셔스 루피(MUR million)**입니다.

## 확인 가능한 수치

### 2024년 12월

BoM의 2024년 12월 통화개발 자료는 다음과 같습니다.

| 기준시점 | 루피 예금 | FCD | TD | FCD/TD |
|---|---:|---:|---:|---:|
| 2024-12 | 704,088 | 209,165 | 913,253 | 22.91% |

계산:

\[
TD = 704{,}088 + 209{,}165 = 913{,}253
\]

\[
\frac{209{,}165}{913{,}253}
\times 100
=
22.91\%
\]

BoM 자료에서 2024년 12월 FCD는 MUR 209,165 million, 루피 예금은 MUR 704,088 million으로 확인됩니다. [bom](https://www.bom.mu/sites/default/files/monetarydev_dec24.pdf)

### 2025년 1월

2025년 1월에는 다음과 같습니다.

| 기준시점 | 루피 예금 | FCD | TD | FCD/TD |
|---|---:|---:|---:|---:|
| 2025-01 | 708,500 | 218,417 | 926,917 | 23.56% |

계산:

\[
TD = 708{,}500 + 218{,}417 = 926{,}917
\]

\[
\frac{218{,}417}{926{,}917}
\times 100
=
23.56\%
\]

BoM의 2025년 1월 자료는 총 예금부채를 MUR 926,917 million으로 보고하며, 루피 예금은 MUR 708,500 million, 외화예금은 MUR 218,417 million입니다. [bom](https://www.bom.mu/sites/default/files/monetarydev_jan25.pdf)

## 정리된 데이터

```csv
date,ncd_mur_million,fcd_mur_million,td_mur_million,fcd_td_pct
2024-12,704088,209165,913253,22.91
2025-01,708500,218417,926917,23.56
```

## 월별 시계열

BoM의 월간 bulletin에는 다음과 같은 월별 FCD 시계열이 제공됩니다.

| 기준시점 | FCD, MUR million |
|---|---:|
| 2024-03 | 187,518 |
| 2024-04 | 190,378 |
| 2024-05 | 195,213 |
| 2024-06 | 196,894 |
| 2024-07 | 207,197 |
| 2024-08 | 206,682 |
| 2024-09 | 206,364 |
| 2024-10 | 202,361 |
| 2024-11 | 206,913 |
| 2024-12 | 209,165 |
| 2025-01 | 218,417 |
| 2025-02 | 218,670 |
| 2025-03 | 211,522 |
| 2025-04 | 218,647 |
| 2025-05 | 220,752 |

BoM의 월별 통계 bulletin은 2024년 3월부터 2025년 3월 이후까지 외화예금 잔액을 통화·상품별로 제공합니다. [bom](https://www.bom.mu/sites/default/files/pdf/Research_and_Publications/Monthly_Statistical_Bulletin/msb_apr-25_0.pdf)

## TD의 범위

BoM 자료에는 몇 가지 범위가 있으므로 다음을 구분해야 합니다.

### 은행권 예금부채

`Sectoral Balance Sheet of Banks`의 `Deposits`를 사용합니다.

예를 들어 2025년 3월 은행권 예금부채는 MUR 2,028,901.5 million으로 표시됩니다. [bom](https://www.bom.mu/sites/default/files/pdf/Research_and_Publications/Monthly_Statistical_Bulletin/msb_apr-25_0.pdf)

### 통화·예금 기반 TD

`Monetary Developments`의 `Rupee Deposits + Foreign Currency Deposits`를 사용합니다.

2025년 1월 예시:

```text
Rupee deposits = 708,500
Foreign-currency deposits = 218,417
TD = 926,917
FCD/TD = 23.56%
```

국제 비교용 FCD/TD에는 두 항목이 같은 표에서 제공되는 두 번째 정의를 권장합니다.

## 주의점

- 모리셔스에는 글로벌 비즈니스 기업(GBC)과 국제금융업 관련 예금이 포함될 수 있으므로, 국내은행권만 사용할지 전체 예금취급기관을 사용할지 고정해야 합니다.
- BoM의 `Foreign Currency Deposits`는 MUR로 환산된 외화예금 잔액입니다.
- 외환보유액, 은행의 해외자산, 중앙은행의 외화예치금은 FCD에 포함하지 않아야 합니다.
- BoM의 `Maturity Pattern of Banks' Foreign Currency Deposits`는 FCD의 통화·만기별 세부구조를 확인하는 데 사용하고, FCD/TD의 분모는 `Deposit Liabilities` 표에서 가져오는 것이 좋습니다. [bom](https://www.bom.mu/publications-and-statistics/statistics/monetary-and-financial-statistics/maturity-pattern-of-banks'-foreign-currency-deposits)

현재 확인된 핵심값은 다음과 같습니다.

```text
2024-12:
  FCD = MUR 209,165 million
  TD  = MUR 913,253 million
  FCD/TD = 22.91%

2025-01:
  FCD = MUR 218,417 million
  TD  = MUR 926,917 million
  FCD/TD = 23.56%
```