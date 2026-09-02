말레이시아의 외화예금(FCD)과 총예금(TD)은 **Bank Negara Malaysia(BNM)** 통계에서 직접 구할 수 있습니다. FCD/TD 비율을 만들 목적이라면, 서로 다른 민간 데이터베이스보다 BNM의 월별 시계열을 사용하는 것이 가장 적절합니다.

## 권장 데이터 조합

| 목적 | BNM 통계표 | 설명 |
|---|---|---|
| FCD | **1.25.5 Banking System: Foreign Currency and Other Deposits by Holder** | 은행시스템의 외화예금 및 기타예금. FCD를 직접 추출할 때 가장 적합 |
| TD | **1.25 Banking System: Total Deposits by Holder** | 동일한 은행시스템 기준의 총예금 |
| 보조 FCD | **Monetary Aggregates: M1, M2 and M3** | M2 구성요소 중 Foreign Currency Deposits. 2013년 이후 월별 CSV 제공 |

BNM의 최신 월별 통계 목록에도 위 두 표가 각각 **1.25**와 **1.25.5**로 계속 제공되고 있습니다. [bnm.gov](https://www.bnm.gov.my/-/monthly-highlights-statistics-in-march-2026)

## 바로 사용할 수 있는 FCD 데이터

말레이시아 정부의 공개 데이터 포털에는 M2 구성요소별 월별 데이터가 CSV와 Parquet으로 공개되어 있습니다.

- [Monetary Aggregates 데이터 설명](https://data.gov.my/data-catalogue/monetary_aggregates)
- [FCD 포함 전체 CSV](https://storage.data.gov.my/finsector/money_aggregates.csv)
- [FCD 포함 전체 Parquet](https://storage.data.gov.my/finsector/money_aggregates.parquet)

이 데이터의 단위는 **RM million**이며, 월말 잔액입니다. FCD는 M2의 구성요소로 포함되어 있습니다. 데이터는 2013년 1월부터 시작하며, 2014년부터 새로운 분류체계가 적용되어 이전 시계열과 연결할 때 주의해야 합니다. [data.gov](https://data.gov.my/data-catalogue/monetary_aggregates)

공개된 최신 대시보드 검색 결과에서 FCD는 **2026년 1월 RM294.9 billion**으로 표시됩니다.  다만 대시보드와 BNM 원자료의 업데이트 시점이 다를 수 있으므로, 실제 분석에는 CSV/XLS 원자료의 기준월을 확인하는 것이 좋습니다. [data.gov](https://data.gov.my/dashboard/money-supply)

## TD 데이터

TD는 BNM의 다음 통계표를 사용하면 됩니다.

- [BNM Monthly Highlights & Statistics](https://www.bnm.gov.my/publications/mhs)
- 해당 월의 **1.25 Banking System: Total Deposits by Holder**
- FCD 세부표: **1.25.5 Banking System: Foreign Currency and Other Deposits by Holder**

BNM 표에는 1.25 외에도 수요예금, 저축·고정예금, 환매조건부채권, NID, 외화 및 기타예금 표가 별도로 제공됩니다.  과거 데이터는 말레이시아 정부의 데이터 아카이브에서도 확인할 수 있습니다. [bnm.gov](https://www.bnm.gov.my/-/monthly-highlights-statistics-in-march-2026)

참고로 CEIC가 BNM의 TD를 재가공한 자료에 따르면, 말레이시아 총예금은 **2026년 6월 USD672.473 billion**으로 표시됩니다. 다만 CEIC 수치는 BNM의 링깃 자료를 환율로 환산한 값이므로, FCD/TD 계산에는 CEIC의 USD 값보다 BNM 원자료의 **RM million 값**을 쓰는 편이 낫습니다. [ceicdata](https://www.ceicdata.com/en/indicator/malaysia/total-deposits)

## FCD/TD 계산 방법

가장 일관적인 계산은 다음과 같습니다.

\[
\text{FCD/TD}_t
=
\frac{\text{Foreign Currency Deposits}_t}
{\text{Total Deposits}_t}
\times 100
\]

Python으로는 다음처럼 처리할 수 있습니다.

```python
import pandas as pd

fcd_url = "https://storage.data.gov.my/finsector/money_aggregates.csv"

money = pd.read_csv(fcd_url)
money["date"] = pd.to_datetime(money["date"])

fcd = (
    money[money["measure"].str.contains(
        "foreign currency", case=False, na=False
    )][["date", "value"]]
    .rename(columns={"value": "fcd_rm_million"})
)

# BNM 1.25 Total Deposits by Holder XLSX를 별도로 읽은 뒤
# date, td_rm_million 컬럼으로 정리했다고 가정
td = pd.read_excel(
    "bnm_1_25_total_deposits_by_holder.xlsx"
)

td["date"] = pd.to_datetime(td["date"])

result = fcd.merge(td[["date", "td_rm_million"]], on="date", how="inner")
result["fcd_td_percent"] = (
    result["fcd_rm_million"] / result["td_rm_million"] * 100
)
```

## 주의할 점

- **FCD/TD의 분모 정의를 통일**해야 합니다. FCD는 M2의 민간부문 외화예금이고 TD는 은행시스템 총예금이므로, 가장 엄밀하게 하려면 1.25.5와 1.25를 같은 BNM 월별 통계 묶음에서 추출하는 것이 좋습니다.
- 1.25.5의 표 제목은 “Foreign Currency and Other Deposits”이므로, 파일 안에서 **Foreign Currency Deposits 행만 사용**하고 Other Deposits를 합치면 안 됩니다.
- BNM 자료의 단위는 대체로 **RM million**입니다. USD로 변환할 필요가 없다면 원 단위를 그대로 유지하는 것이 좋습니다.
- 공개 M2 CSV와 BNM XLS의 기준월·개정 시점이 다를 수 있으므로, FCD/TD 비율 산출 시에는 가능하면 **두 값을 동일한 BNM 발표월의 XLS에서 추출**하는 것을 권장합니다.
- 검색 결과상 FCD는 2026년 1월 이후에도 증가하여 2026년 5월 약 **RM316.0 billion** 수준까지 올라간 것으로 보도됐지만, 이는 BNM 표 원자료가 아니라 2차 자료에서 인용된 수치이므로 최종 시계열에는 직접 사용하지 않는 편이 안전합니다. [bixmalaysia](https://www.bixmalaysia.com/CMSPages/GetFile.aspx?guid=ab559d93-7786-4474-8052-09ee76e81574)

가장 좋은 원자료 구성은 **BNM 1.25.5의 FCD 행 + BNM 1.25의 Total Deposits 행**입니다. 이를 월별로 정리하면 사용 목적에 맞는 `date, fcd_rm_million, td_rm_million, fcd_td_percent` 시계열을 만들 수 있습니다.



나미비아는 **Bank of Namibia(BoN)**가 외화예금(FCD)과 총예금(TD)을 모두 제공하고 있습니다. 말레이시아와 달리 공개 형식은 주로 월별·분기별 통계표 PDF/XLSX이며, FCD/TD 계산에는 BoN의 **Monetary and Financial Statistics**를 사용하는 것이 가장 적절합니다.

## 권장 원자료

| 필요한 값 | BoN 통계 항목 | 비고 |
|---|---|---|
| FCD | **Foreign currency deposits** | 은행권 비은행부문 예금 중 외화예금 |
| TD | **Deposits** 또는 예금 세부항목 합계 | 같은 표의 총예금 |
| 보조 TD | Monetary survey 또는 Banking survey의 **Total deposits** | 통화·은행 통계상의 총예금 |

공식 통계 페이지는 나미비아 은행부문의 자산·부채와 예금 거래를 집계해 제공하며, 2026년판부터 2002년판까지 연도별 통계표를 다운로드할 수 있습니다. [bon.com](https://www.bon.com.na/Economic-information/Statistical-information/Monetary-and-fincancial-statistics.aspx)

- [Bank of Namibia Monetary and Financial Statistics](https://www.bon.com.na/Economic-information/Statistical-information/Monetary-and-fincancial-statistics.aspx)
- [Bank of Namibia Statistical Information](https://www.bon.com.na/Economic-information/Statistical-information.aspx)

## FCD 자료

BoN의 은행권 통계표에는 다음과 같은 항목이 있습니다.

```text
Non-Bank Funding
  Deposits
    Current accounts
    Call deposits
    Savings deposits
    Fixed and notice deposits
    Negotiable Certificates of Deposits
    Foreign currency deposits
```

따라서 FCD는 `Foreign currency deposits` 행을 그대로 사용하면 됩니다. BoN 자료의 단위는 최신 표에서 대체로 **N$ ’000**이며, 과거 표에는 **N$ million**이 사용되기도 하므로 단위를 반드시 확인해야 합니다.

검색 가능한 BoN 자료에서 FCD는 과거 월별·분기별 시계열로도 제공됩니다. 예를 들어 2018년 은행권 자료에는 `Foreign currency deposits`가 N$ ’000 단위로 별도 표시되어 있습니다.  2014년 자료도 월별 FCD 값을 별도 항목으로 제공하고 있습니다. [bon.com](https://www.bon.com.na/CMSTemplates/Bon/Files/bon.com.na/ea/ea50bcd2-c8c2-4724-9c29-b101e7f5c68a.pdf)

## TD 산출

FCD/TD 비율의 분모는 다음 우선순위로 선택하는 것이 좋습니다.

1. 같은 BoN 통계표의 `Deposits` 총액.
2. `Current accounts + Call deposits + Savings deposits + Fixed and notice deposits + NCDs + Foreign currency deposits`의 합계.
3. Monetary survey 또는 Banking survey의 `Total deposits`.

가장 일관된 방식은 다음처럼 **동일한 통계표에서 FCD와 TD를 동시에 추출**하는 것입니다.

\[
\text{FCD/TD}_t
=
\frac{\text{Foreign currency deposits}_t}
{\text{Total deposits}_t}
\times 100
\]

다만 `Deposits`가 이미 외화예금을 포함하는지, 혹은 외화예금이 별도 부문으로 분류되어 총액에 포함되지 않는지는 해당 연도의 BoN 표 주석을 확인해야 합니다. 예금 세부항목을 직접 합산할 경우 중복계상이 발생하지 않는지 확인해야 합니다.

## 확인된 수치와 범위

BoN의 공개 자료에는 외화예금의 장기 시계열이 존재합니다. CEIC가 IMF/BoN 계열 자료를 재가공한 과거 연간 시계열은 1990~2008년 외화예금을 제공하지만, FCD/TD 비율을 계산할 때는 CEIC보다 BoN 원자료를 사용하는 것이 낫습니다. [ceicdata](https://www.ceicdata.com/en/namibia/financial-system-deposit-money-banks-annual/na-deposit-money-banks-time-savings-and-foreign-currency-deposits)

최근 자료의 경우 BoN 통계 페이지에서 **Set of Table 2026**, **Set of Table 2025**, **Set of Table 2024** 등을 다운로드할 수 있습니다.  검색 결과상 2025년 BoN XLSX 파일도 존재하지만, 해당 파일은 특정 은행감독 통계표인 BIR 610이므로 전체 은행권 TD 자료와 혼동하면 안 됩니다. [bon.com](https://www.bon.com.na/Economic-information/Statistical-information/Monetary-and-fincancial-statistics.aspx)

## 분석용 데이터 구조

최종적으로는 다음 형식으로 정리하면 됩니다.

```text
date,fcd_nad_thousand,td_nad_thousand,fcd_td_percent
2024-01,.........,.........,.........
2024-02,.........,.........,.........
2024-03,.........,.........,.........
```

Python 처리 예시는 다음과 같습니다.

```python
import pandas as pd

df = pd.read_excel(
    "bank_of_namibia_monetary_statistics.xlsx",
    sheet_name=0
)

# 실제 파일의 열 이름에 맞게 수정
df["fcd_td_percent"] = (
    df["foreign_currency_deposits"]
    / df["total_deposits"]
    * 100
)
```

## 결론

나미비아의 경우 사용할 원자료는 다음 조합이 가장 좋습니다.

- **FCD:** BoN `Foreign currency deposits`
- **TD:** 같은 BoN 표의 `Deposits` 또는 `Total deposits`
- **단위:** 보통 N$ ’000
- **빈도:** 월별 또는 분기별
- **공식 출처:** [BoN Monetary and Financial Statistics](https://www.bon.com.na/Economic-information/Statistical-information/Monetary-and-fincancial-statistics.aspx) [bon.com](https://www.bon.com.na/Economic-information/Statistical-information/Monetary-and-fincancial-statistics.aspx)

특히 FCD/TD 비율을 장기간 계산하려면 **2026년 통계표와 2025년 이전 통계표의 항목명·단위·은행권 범위가 동일한지 먼저 맞춰야 합니다.**



나이지리아는 **Central Bank of Nigeria(CBN)**의 통계 데이터베이스와 Statistical Bulletin에서 외화예금(FCD) 및 총예금(TD)을 찾을 수 있습니다. FCD/TD 비율을 계산하려면 CBN의 **Financial Statistics** 중 `Depository Corporations Survey` 또는 `Commercial & Merchant Banks’ Accounts – Liabilities`를 사용하는 것이 가장 적절합니다.

## 권장 데이터

| 필요한 값 | CBN 통계표 | 설명 |
|---|---|---|
| FCD | **Foreign Currency Deposits** | 예금취급기관의 외화표시 예금 |
| TD | **Deposits / Total Deposits** | 예금취급기관의 총예금 |
| 보조 FCD | **Time, Savings & Foreign Currency Deposits** | 구형 CBN 통계표에서 FCD가 별도 열로 제공됨 |
| 보조 TD | **Depository Corporations Survey** | 중앙은행과 예금취급기관을 통합한 통화통계 |

공식 CBN 데이터 페이지에는 `Money and Credit Statistics`, `Financial Data`, `Statistics Database`, `Statistical Bulletins`가 별도 항목으로 제공됩니다. [cbn.gov](https://www.cbn.gov.ng/rates/)

- [CBN Data & Statistics](https://www.cbn.gov.ng/rates/)
- [CBN Statistics Database](https://www.cbn.gov.ng/rates/)
- [CBN Statistical Bulletins](https://www.cbn.gov.ng/Out/2026/STD/)

## 가장 유용한 공식 표

CBN의 최신 분기 통계 Bulletin인 **2025년 3분기판**에는 다음 금융통계표가 포함되어 있습니다.

- **Table A.1: Depository Corporations Survey**
- **Table A.2: Depository Corporations Survey – Growth Rates**
- **Table A.4.1: Commercial & Merchant Banks’ Accounts – Assets**
- **Table A.4.2: Commercial & Merchant Banks’ Accounts – Liabilities**
- **Table A.4.3: Commercial & Merchant Banks’ Survey**
- **Table A.5.1~A.5.3: Non-Interest Banks**
- **Table A.8.1~A.8.3: Other Depository Corporations**

2025년 3분기 Bulletin의 금융통계 단위는 **₦ million**입니다. [cbnwincenbankwebprod-dnfwb6hwduemgbf7.westeurope-01.azurewebsites](https://cbnwincenbankwebprod-dnfwb6hwduemgbf7.westeurope-01.azurewebsites.net/Out/2026/STD/2025Q3%20Statistical%20Bulletin_Contents%20and%20Narratives_Final.pdf)

특히 FCD/TD 목적에는 다음 순서가 좋습니다.

1. **A.4.2 Commercial & Merchant Banks’ Accounts – Liabilities**
2. **A.4.3 Commercial & Merchant Banks’ Survey**
3. **A.1 Depository Corporations Survey**

나이지리아의 예금 대부분을 차지하는 상업은행·상인은행 기준을 원하면 A.4 계열을 쓰고, 통화당국과 기타 예금취급기관까지 포함한 광의의 은행시스템 기준을 원하면 A.1을 사용하면 됩니다.

## FCD/TD 계산

기본 계산은 다음과 같습니다.

\[
\text{FCD/TD}_t
=
\frac{\text{Foreign Currency Deposits}_t}
{\text{Total Deposits}_t}
\times 100
\]

구형 CBN 표에서는 `Time, Savings & Foreign Currency Deposits`가 예금 구성요소로 제공되며, CBN 설명상 quasi-money에는 **time deposits, savings deposits, foreign currency deposits**가 포함됩니다. [cbn.gov](https://www.cbn.gov.ng/OUT/PUBLICATIONS/REPORTS/RSD/2008/ECONOMIC%20REPORT%20FOR%20THE%20MONTH%20OF%20AUGUST%202008.PDF)

따라서 표가 다음과 같은 구조라면:

```text
Demand deposits
Time deposits
Savings deposits
Foreign currency deposits
Total deposits
```

다음처럼 계산하면 됩니다.

```python
df["fcd_td_percent"] = (
    df["foreign_currency_deposits"]
    / df["total_deposits"]
    * 100
)
```

만약 `Total deposits` 행이 없으면, 표의 정의에 따라 다음을 합산합니다.

```python
df["total_deposits"] = (
    df["demand_deposits"]
    + df["time_deposits"]
    + df["savings_deposits"]
    + df["foreign_currency_deposits"]
)
```

다만 최신 SRF(Standardized Report Forms) 체계에서는 예금이 경제부문·통화·금융상품별로 더 세분화되어 있으므로, 단순히 모든 예금행을 합산하기 전에 표의 합계행을 우선 사용하는 것이 안전합니다. CBN은 2019년 12월부터 IMF의 SRF 체계를 전면 도입했다고 설명하고 있습니다. [cbnwincenbankwebprod-dnfwb6hwduemgbf7.westeurope-01.azurewebsites](https://cbnwincenbankwebprod-dnfwb6hwduemgbf7.westeurope-01.azurewebsites.net/Out/2026/STD/2025Q3%20Statistical%20Bulletin_Contents%20and%20Narratives_Final.pdf)

## 데이터 해석상의 주의점

- `Foreign currency deposits`가 **거주자 외화예금만 포함하는지**, 비거주자까지 포함하는지 확인해야 합니다.
- `Total deposits`는 표에 따라 상업은행만 포함할 수도 있고, 중앙은행·비은행 예금취급기관까지 포함할 수도 있습니다.
- 최신 자료는 **₦ million**, 과거 자료는 일부 **₦ billion** 또는 별도 단위일 수 있습니다.
- 나이라 가치 기준 FCD는 환율 변동의 영향을 받습니다. 달러화예금 잔액 자체가 변하지 않아도 나이라 환산액은 움직일 수 있습니다.
- FCD/TD 비율을 장기 비교할 때는 2019년 SRF 도입 전후로 정의가 바뀌었는지 확인해야 합니다.

## 추천 최종 시계열

나이지리아에 대해서는 다음 구조로 수집하는 것을 권합니다.

```text
date,fcd_ngn_million,td_ngn_million,fcd_td_percent,source_table
2019Q1,..........,..........,..........,A.4.2
2019Q2,..........,..........,..........,A.4.2
...
2025Q3,..........,..........,..........,A.4.2
```

**가장 일관적인 기준은 CBN A.4.2의 `Foreign Currency Deposits`와 같은 표의 `Total Deposits`를 사용하는 방식**입니다. 전체 금융시스템 기준이 필요하면 A.1의 FCD와 TD를 사용하면 됩니다. CBN은 2025년 3분기 Bulletin에서 A.1을 `Depository Corporations Survey (₦ million)`, A.4.2를 `Commercial & Merchant Banks’ Accounts – Liabilities (₦ million)`으로 제공하고 있습니다. [cbnwincenbankwebprod-dnfwb6hwduemgbf7.westeurope-01.azurewebsites](https://cbnwincenbankwebprod-dnfwb6hwduemgbf7.westeurope-01.azurewebsites.net/Out/2026/STD/2025Q3%20Statistical%20Bulletin_Contents%20and%20Narratives_Final.pdf)


나이지리아의 FCD/TD 자료는 **Central Bank of Nigeria(CBN)** 통계에서 찾는 것이 맞습니다. 다만 CBN의 공개 웹페이지에는 최신 FCD가 단순 지표로 바로 표시되기보다는, **Statistical Bulletin의 은행권 대차대조표 표**에서 추출해야 합니다.

## 권장 원자료

| 값 | CBN 표 | 사용 방법 |
|---|---|---|
| FCD | **Commercial & Merchant Banks’ Accounts – Liabilities** | `Foreign Currency Deposits` 행 |
| TD | 같은 표 | `Total Deposits` 또는 표의 예금 합계행 |
| 대체 TD | **Depository Corporations Survey** | 중앙은행·예금취급기관을 포함하는 광의의 총예금 |
| 보조 FCD | Money and Credit Statistics의 `Quasi Money` | FCD 단독값이 아니므로 보조자료로만 사용 |

CBN은 `Money and Credit Statistics`, `Financial Data`, `Statistics Database`, `Statistical Bulletins`를 공식 데이터 메뉴로 제공합니다. [cbn.gov](https://www.cbn.gov.ng/rates/)

- [CBN Data & Statistics](https://www.cbn.gov.ng/rates/)
- [CBN Money and Credit Statistics](https://www.cbn.gov.ng/rates/mnycredit.html)
- [CBN Statistical Bulletins](https://www.cbn.gov.ng/Out/2026/STD/)

## 최신 공식 통계표

현재 확인되는 최신 공식 분기 자료는 **2025년 3분기 Statistical Bulletin**입니다. 이 자료에는 다음 표가 포함되어 있습니다.

- **A.1 Depository Corporations Survey**
- **A.4.1 Commercial & Merchant Banks’ Accounts – Assets**
- **A.4.2 Commercial & Merchant Banks’ Accounts – Liabilities**
- **A.4.3 Commercial & Merchant Banks’ Survey**

FCD/TD 계산에는 우선 **A.4.2**를 사용하는 것이 좋습니다. 이 표는 상업은행·상인은행의 부채를 다루며, `Foreign Currency Deposits`가 별도 항목으로 제공됩니다. 자료의 단위는 **million naira**입니다. [cbnwincenbankwebprod-dnfwb6hwduemgbf7.westeurope-01.azurewebsites](https://cbnwincenbankwebprod-dnfwb6hwduemgbf7.westeurope-01.azurewebsites.net/Out/2026/STD/2025Q3%20Statistical%20Bulletin_Contents%20and%20Narratives_Final.pdf)

## 계산 방식

가장 적절한 비율은 다음과 같습니다.

\[
\text{FCD/TD}_t
=
\frac{\text{Foreign Currency Deposits}_t}
{\text{Total Deposits}_t}
\times 100
\]

추출 결과는 다음과 같은 형태로 구성하면 됩니다.

```text
date,fcd_ngn_million,td_ngn_million,fcd_td_percent
2019Q1,...,...,...
2019Q2,...,...,...
...
2025Q3,...,...,...
```

표에 `Total Deposits` 행이 없다면 예금 구성항목을 합산할 수 있습니다.

```python
df["total_deposits"] = (
    df["demand_deposits"]
    + df["time_deposits"]
    + df["savings_deposits"]
    + df["foreign_currency_deposits"]
)

df["fcd_td_percent"] = (
    df["foreign_currency_deposits"]
    / df["total_deposits"]
    * 100
)
```

단, 최신 CBN 표에서 예금 항목이 세분화되어 있으면 표에 표시된 합계행을 우선 사용해야 합니다.

## 해석상 주의점

- CBN의 `Foreign Currency Deposits`는 일반적으로 **예금은행의 외화표시 고객예금**을 의미합니다.
- `Quasi Money`는 보통 정기예금·저축예금·외화예금을 포함하는 광의 항목이므로, FCD의 대체값으로 사용하면 안 됩니다. CBN의 과거 설명에서도 quasi-money는 time, savings, foreign-currency deposits의 합성 개념으로 정의됩니다. [cbn.gov](https://www.cbn.gov.ng/OUT/PUBLICATIONS/REPORTS/RSD/2008/ECONOMIC%20REPORT%20FOR%20THE%20MONTH%20OF%20AUGUST%202008.PDF)
- A.4.2의 TD는 상업은행·상인은행 기준이고, A.1의 TD는 더 넓은 예금취급기관 기준일 수 있습니다. FCD와 TD는 반드시 **같은 표와 같은 기관 범위**에서 추출해야 합니다.
- 단위는 최신 Bulletin에서 **₦ million**입니다. 과거 자료와 연결할 때 billion/미만 단위 변환을 확인해야 합니다.
- 2019년 전후로 CBN의 IMF 표준보고양식(SRF) 적용 및 분류 변경이 있었을 수 있으므로 장기 시계열에는 구조변경 표시를 추가하는 것이 좋습니다.

## 참고 가능한 TD 자료

민간 데이터베이스 CEIC에는 나이지리아 총예금 시계열이 있지만, 검색 결과에서는 2019년 12월 총예금이 **USD84,213.801 million**으로 표시됩니다. 이는 CBN의 나이라 원자료를 환율로 변환한 값이므로 FCD/TD 계산에는 적합성이 낮습니다. [ceicdata](https://www.ceicdata.com/ko/indicator/nigeria/total-deposits)

따라서 나이지리아의 최종 산출에는 다음 조합을 권장합니다.

```text
FCD = CBN A.4.2 Foreign Currency Deposits
TD  = CBN A.4.2 Total Deposits
비율 = FCD / TD × 100
단위 = million naira
빈도 = 분기별 또는 CBN 원자료가 제공하는 월별
```

현재 공개 검색으로 확인된 범위에서는 CBN이 FCD와 TD의 최신 수치를 별도 HTML 표로 제공하지 않고, Bulletin 내부 표로 제공하는 구조입니다. 따라서 실제 수치 시계열은 **A.4.2 원본 XLS/PDF를 내려받아 행·열을 추출하는 방식**이 가장 신뢰할 만합니다.