# Deposit Dollarization Collector

[한국어](#한국어) · [English](#english) · [日本語](#日本語) · [Français](#français)

A monorepo that collects foreign-currency-deposit (FCD) statistics for ~130 countries and territories, stores them in Supabase, and visualizes them on a bilingual web dashboard.

**🔗 Live dashboard: [deposit-dollarization-collector.macrolab.workers.dev](https://deposit-dollarization-collector.macrolab.workers.dev)**

- [`dollarization-pipeline/`](dollarization-pipeline) — the Python ETL collector (see its [README](dollarization-pipeline/README.md) / [README.en.md](dollarization-pipeline/README.en.md) and [OPERATIONS.ko.md](dollarization-pipeline/OPERATIONS.ko.md) / [OPERATIONS.en.md](dollarization-pipeline/OPERATIONS.en.md))
- [`web/`](web) — the React + TypeScript dashboard (see its [README](web/README.md))

---

## 한국어

국가별 외화예금(Foreign Currency Deposits, FCD) 통계를 자동으로 수집해 Supabase PostgreSQL에 적재하고, 웹 대시보드로 시각화하는 프로젝트입니다.

**🔗 대시보드 바로가기: [deposit-dollarization-collector.macrolab.workers.dev](https://deposit-dollarization-collector.macrolab.workers.dev)**

### 구성

| 디렉터리 | 설명 |
| --- | --- |
| [`dollarization-pipeline/`](dollarization-pipeline) | 약 250개국의 외화예금 통계를 수집하는 Python ETL 파이프라인. 국가별로 독립된 파서를 두고 있으며, PDF·Excel·웹페이지·API 등 다양한 소스 형식을 지원합니다. |
| [`web/`](web) | Supabase에서 직접 데이터를 읽어오는 React + TypeScript 대시보드. 한국어/영어를 지원하며, 국가별 시계열 차트와 데이터 현황 요약 표를 제공합니다. |

### 데이터 모델

모든 지표는 `(국가코드, 연도, 기간, 지표명)`을 기본키로 하는 롱포맷으로 저장됩니다.

- `FCD` — 외화예금
- `TD` — 총예금
- `FCD_TD_RATIO` — 예금 달러화율 (0–100 백분율, `(FCD/TD)×100`)

기간은 국가마다 수집 가능한 최고 해상도(월별/분기별/연간)로 저장되며, 더 세밀한 데이터가 있는 경우 연간·분기 시점(12월/Q4 등)을 자동으로 복제해 더 굵은 단위로도 조회할 수 있게 되어 있습니다.

### 시작하기

- 수집기 실행 방법은 [OPERATIONS.ko.md](dollarization-pipeline/OPERATIONS.ko.md)를 참고해 주십시오.
- 대시보드 실행 방법은 [web/README.md](web/README.md)를 참고해 주십시오.

### 코드로 데이터 가져오기

대시보드에서 국가별로 CSV/Excel을 내려받을 수 있고(선택한 국가의 차트 위에 다운로드 버튼), 코드로 바로 가져오고 싶다면 저장소를 내려받을 필요 없이 아래 값 그대로 복사해서 실행하면 됩니다. Supabase의 REST API(PostgREST)를 직접 호출하는 방식이며, 아래 키는 읽기 전용 공개 키(anon key)라 코드에 그대로 넣어도 안전합니다(이미 대시보드 웹 번들에도 그대로 포함되어 있습니다).

```bash
# curl 예시: 한 국가(KOR)의 전체 지표
curl "https://xyspwvpcfrxpnjqrofkp.supabase.co/rest/v1/deposit_dollarization?country_code=eq.KOR&select=*&order=period" \
  -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"
```

```python
# Python 예시: pandas DataFrame으로 바로 받기
import requests
import pandas as pd

SUPABASE_URL = "https://xyspwvpcfrxpnjqrofkp.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"

def fetch_country(country_code: str) -> pd.DataFrame:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/deposit_dollarization",
        params={"country_code": f"eq.{country_code}", "select": "*", "order": "period"},
        headers={"apikey": SUPABASE_ANON_KEY},
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())

df = fetch_country("KOR")
print(df.head())
```

```r
# R 예시: httr2로 바로 data.frame 받기
library(httr2)

SUPABASE_URL <- "https://xyspwvpcfrxpnjqrofkp.supabase.co"
SUPABASE_ANON_KEY <- "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"

df <- request(paste0(SUPABASE_URL, "/rest/v1/deposit_dollarization")) |>
  req_url_query(country_code = "eq.KOR", select = "*", order = "period") |>
  req_headers(apikey = SUPABASE_ANON_KEY) |>
  req_perform() |>
  resp_body_json(simplifyVector = TRUE)

head(df)
```

전체 테이블(약 10만 행 이상)을 한 번에 받고 싶다면 PostgREST 기본 페이지 크기(1,000행) 제한 때문에 `Range` 헤더나 `.range()`(supabase-py 사용 시)로 페이지네이션이 필요합니다. 국가별 요약 정보만 필요하다면 `deposit_dollarization_summary` 뷰를 사용하십시오. 위 키/URL은 `web/.env.example`에서도 확인할 수 있습니다.

### 라이선스 및 기여

별도 명시된 라이선스가 없으며, 이슈/PR을 통한 기여를 환영합니다.

---

## English

A project that automatically collects foreign-currency-deposit (FCD) statistics for roughly 250 countries, loads them into Supabase PostgreSQL, and visualizes them on a web dashboard.

**🔗 Live dashboard: [deposit-dollarization-collector.macrolab.workers.dev](https://deposit-dollarization-collector.macrolab.workers.dev)**

### Structure

| Directory | Description |
| --- | --- |
| [`dollarization-pipeline/`](dollarization-pipeline) | A Python ETL pipeline that collects FCD statistics for ~250 countries. Each country has its own independent parser, supporting a range of source formats — PDF, Excel, web pages, and APIs. |
| [`web/`](web) | A React + TypeScript dashboard that reads directly from Supabase. Supports Korean and English, and provides per-country time-series charts and a data-coverage summary table. |

### Data model

Every indicator is stored in long format, keyed on `(country_code, year, period, indicator)`.

- `FCD` — foreign currency deposits
- `TD` — total deposits
- `FCD_TD_RATIO` — deposit dollarization ratio (0–100 percent, `(FCD/TD)×100`)

Periods are stored at whichever resolution (monthly/quarterly/annual) is actually collectible for a given country. Where finer-grained data exists, the year-end/quarter-end observation (December, Q4, etc.) is automatically duplicated into the coarser period label too, so a country's data remains queryable at every coarser resolution.

### Getting started

- See [OPERATIONS.en.md](dollarization-pipeline/OPERATIONS.en.md) for how to run the collector.
- See [web/README.md](web/README.md) for how to run the dashboard.

### Fetching the data programmatically

The dashboard has CSV/Excel download buttons above the chart for whichever country is selected. To pull data straight into code without cloning the repo, just copy the values below and run them as-is — this calls Supabase's REST API (PostgREST) directly, and the key below is a read-only public anon key, safe to paste into your own code (it's already shipped in the dashboard's browser bundle).

```bash
# curl: every indicator for one country (KOR)
curl "https://xyspwvpcfrxpnjqrofkp.supabase.co/rest/v1/deposit_dollarization?country_code=eq.KOR&select=*&order=period" \
  -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"
```

```python
# Python: straight into a pandas DataFrame
import requests
import pandas as pd

SUPABASE_URL = "https://xyspwvpcfrxpnjqrofkp.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"

def fetch_country(country_code: str) -> pd.DataFrame:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/deposit_dollarization",
        params={"country_code": f"eq.{country_code}", "select": "*", "order": "period"},
        headers={"apikey": SUPABASE_ANON_KEY},
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())

df = fetch_country("KOR")
print(df.head())
```

```r
# R: straight into a data.frame with httr2
library(httr2)

SUPABASE_URL <- "https://xyspwvpcfrxpnjqrofkp.supabase.co"
SUPABASE_ANON_KEY <- "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"

df <- request(paste0(SUPABASE_URL, "/rest/v1/deposit_dollarization")) |>
  req_url_query(country_code = "eq.KOR", select = "*", order = "period") |>
  req_headers(apikey = SUPABASE_ANON_KEY) |>
  req_perform() |>
  resp_body_json(simplifyVector = TRUE)

head(df)
```

To pull the whole table (100k+ rows) in one go, paginate with the `Range` header (or `.range()` if you use `supabase-py`) since PostgREST caps a single response at 1,000 rows by default. If you only need per-country summaries, query the `deposit_dollarization_summary` view instead. The same URL/key are also in `web/.env.example`.

### License & contributing

No license has been declared. Issues and pull requests are welcome.

---

## 日本語

約250か国・地域の外貨預金(Foreign Currency Deposits, FCD)統計を自動的に収集し、Supabase PostgreSQLに格納した上で、Webダッシュボードで可視化するプロジェクトです。

**🔗 ダッシュボードはこちら: [deposit-dollarization-collector.macrolab.workers.dev](https://deposit-dollarization-collector.macrolab.workers.dev)**

### 構成

| ディレクトリ | 説明 |
| --- | --- |
| [`dollarization-pipeline/`](dollarization-pipeline) | 約250か国の外貨預金統計を収集するPython製ETLパイプラインです。国ごとに独立したパーサーを備えており、PDF・Excel・Webページ・APIなど多様なソース形式に対応しています。 |
| [`web/`](web) | Supabaseから直接データを読み込むReact + TypeScript製ダッシュボードです。韓国語・英語に対応しており、国別の時系列チャートとデータ収集状況の要約表を提供します。 |

### データモデル

すべての指標は `(国コード, 年, 期間, 指標名)` を主キーとするロング形式で保存されます。

- `FCD` — 外貨預金
- `TD` — 総預金
- `FCD_TD_RATIO` — 預金ドル化率(0〜100のパーセンテージ、`(FCD/TD)×100`)

期間は、各国について実際に収集可能な最高解像度(月次・四半期・年次)で保存されます。より細かい粒度のデータが存在する場合は、年末・四半期末の観測値(12月分・Q4など)を自動的に複製し、より粗い単位でも参照できるようになっています。

### はじめに

- 収集パイプラインの実行方法については [OPERATIONS.en.md](dollarization-pipeline/OPERATIONS.en.md) をご参照ください(日本語版は未整備です)。
- ダッシュボードの実行方法については [web/README.md](web/README.md) をご参照ください。

### プログラムからデータを取得する

ダッシュボードでは、選択した国のチャート上部にあるボタンからCSV/Excelをダウンロードできます。リポジトリをクローンせずコードから直接取得したい場合は、以下の値をそのままコピーして実行してください。SupabaseのREST API(PostgREST)を直接呼び出す方式で、以下のキーは読み取り専用の公開キー(anonキー)のため、そのままコードに貼り付けても問題ありません(ダッシュボードのブラウザバンドルにも同じ値が含まれています)。

```bash
# curlの例: 1か国(KOR)の全指標を取得
curl "https://xyspwvpcfrxpnjqrofkp.supabase.co/rest/v1/deposit_dollarization?country_code=eq.KOR&select=*&order=period" \
  -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"
```

```python
# Pythonの例: そのままpandas DataFrameとして取得
import requests
import pandas as pd

SUPABASE_URL = "https://xyspwvpcfrxpnjqrofkp.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"

def fetch_country(country_code: str) -> pd.DataFrame:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/deposit_dollarization",
        params={"country_code": f"eq.{country_code}", "select": "*", "order": "period"},
        headers={"apikey": SUPABASE_ANON_KEY},
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())

df = fetch_country("KOR")
print(df.head())
```

```r
# Rの例: httr2でそのままdata.frameとして取得
library(httr2)

SUPABASE_URL <- "https://xyspwvpcfrxpnjqrofkp.supabase.co"
SUPABASE_ANON_KEY <- "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"

df <- request(paste0(SUPABASE_URL, "/rest/v1/deposit_dollarization")) |>
  req_url_query(country_code = "eq.KOR", select = "*", order = "period") |>
  req_headers(apikey = SUPABASE_ANON_KEY) |>
  req_perform() |>
  resp_body_json(simplifyVector = TRUE)

head(df)
```

テーブル全体(10万行以上)を一度に取得したい場合は、PostgRESTの既定のページサイズ(1,000行)の制限があるため、`Range` ヘッダー(`supabase-py` をお使いの場合は `.range()`)によるページネーションが必要です。国別の要約情報のみで良い場合は、`deposit_dollarization_summary` ビューをご利用ください。同じURL/キーは `web/.env.example` にも記載されています。

### ライセンスと貢献について

ライセンスは明示されておりません。Issue・Pull Requestによる貢献を歓迎いたします。

---

## Français

Un projet qui collecte automatiquement les statistiques de dépôts en devises étrangères (Foreign Currency Deposits, FCD) pour environ 250 pays, les charge dans Supabase PostgreSQL, et les visualise sur un tableau de bord web.

**🔗 Tableau de bord en ligne : [deposit-dollarization-collector.macrolab.workers.dev](https://deposit-dollarization-collector.macrolab.workers.dev)**

### Structure

| Répertoire | Description |
| --- | --- |
| [`dollarization-pipeline/`](dollarization-pipeline) | Un pipeline ETL en Python qui collecte les statistiques de FCD pour environ 250 pays. Chaque pays dispose de son propre analyseur indépendant, prenant en charge divers formats de source — PDF, Excel, pages web et API. |
| [`web/`](web) | Un tableau de bord React + TypeScript qui lit directement depuis Supabase. Prend en charge le coréen et l'anglais, et propose des graphiques chronologiques par pays ainsi qu'un tableau récapitulatif de la couverture des données. |

### Modèle de données

Chaque indicateur est stocké au format long, avec pour clé `(country_code, year, period, indicator)`.

- `FCD` — dépôts en devises étrangères
- `TD` — dépôts totaux
- `FCD_TD_RATIO` — taux de dollarisation des dépôts (pourcentage de 0 à 100, `(FCD/TD)×100`)

Les périodes sont stockées à la résolution (mensuelle/trimestrielle/annuelle) réellement collectible pour chaque pays. Lorsque des données plus fines existent, l'observation de fin d'année/de trimestre (décembre, T4, etc.) est automatiquement dupliquée dans l'étiquette de période plus grossière, afin que les données d'un pays restent consultables à chaque résolution plus large.

### Pour commencer

- Consultez [OPERATIONS.en.md](dollarization-pipeline/OPERATIONS.en.md) pour savoir comment exécuter le collecteur (une version française n'est pas encore disponible).
- Consultez [web/README.md](web/README.md) pour savoir comment exécuter le tableau de bord.

### Récupérer les données par programmation

Le tableau de bord propose des boutons de téléchargement CSV/Excel au-dessus du graphique, pour le pays sélectionné. Pour récupérer les données directement en code sans cloner le dépôt, copiez simplement les valeurs ci-dessous et exécutez-les telles quelles — cela appelle directement l'API REST de Supabase (PostgREST), et la clé ci-dessous est une clé publique en lecture seule (anon key), sans risque à coller dans votre propre code (elle est déjà présente dans le bundle du navigateur du tableau de bord).

```bash
# curl : tous les indicateurs pour un pays (KOR)
curl "https://xyspwvpcfrxpnjqrofkp.supabase.co/rest/v1/deposit_dollarization?country_code=eq.KOR&select=*&order=period" \
  -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"
```

```python
# Python : directement dans un DataFrame pandas
import requests
import pandas as pd

SUPABASE_URL = "https://xyspwvpcfrxpnjqrofkp.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"

def fetch_country(country_code: str) -> pd.DataFrame:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/deposit_dollarization",
        params={"country_code": f"eq.{country_code}", "select": "*", "order": "period"},
        headers={"apikey": SUPABASE_ANON_KEY},
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())

df = fetch_country("KOR")
print(df.head())
```

```r
# R : directement dans un data.frame avec httr2
library(httr2)

SUPABASE_URL <- "https://xyspwvpcfrxpnjqrofkp.supabase.co"
SUPABASE_ANON_KEY <- "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5c3B3dnBjZnJ4cG5qcXJvZmtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY2MjQzNzksImV4cCI6MjEwMjIwMDM3OX0.K19YtvsK0VbE4piZzPuhEBhz_vcJgbB0FZAnsv3le-Q"

df <- request(paste0(SUPABASE_URL, "/rest/v1/deposit_dollarization")) |>
  req_url_query(country_code = "eq.KOR", select = "*", order = "period") |>
  req_headers(apikey = SUPABASE_ANON_KEY) |>
  req_perform() |>
  resp_body_json(simplifyVector = TRUE)

head(df)
```

Pour récupérer la table entière (plus de 100 000 lignes) en une fois, paginez avec l'en-tête `Range` (ou `.range()` avec `supabase-py`), car PostgREST limite une réponse à 1 000 lignes par défaut. Si seuls les résumés par pays vous intéressent, interrogez plutôt la vue `deposit_dollarization_summary`. La même URL/clé figure aussi dans `web/.env.example`.

### Licence et contributions

Aucune licence n'a été déclarée. Les issues et pull requests sont les bienvenues.
