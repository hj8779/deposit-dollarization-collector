# Deposit Dollarization Collector

[한국어](#한국어) · [English](#english) · [日本語](#日本語) · [Français](#français)

A monorepo that collects foreign-currency-deposit (FCD) statistics for ~250 countries and territories, stores them in Supabase, and visualizes them on a bilingual web dashboard.

- [`dollarization-pipeline/`](dollarization-pipeline) — the Python ETL collector (see its [README](dollarization-pipeline/README.md) / [README.en.md](dollarization-pipeline/README.en.md) and [OPERATIONS.ko.md](dollarization-pipeline/OPERATIONS.ko.md) / [OPERATIONS.en.md](dollarization-pipeline/OPERATIONS.en.md))
- [`web/`](web) — the React + TypeScript dashboard (see its [README](web/README.md))

---

## 한국어

국가별 외화예금(Foreign Currency Deposits, FCD) 통계를 자동으로 수집해 Supabase PostgreSQL에 적재하고, 웹 대시보드로 시각화하는 프로젝트입니다.

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

### 라이선스 및 기여

별도 명시된 라이선스가 없으며, 이슈/PR을 통한 기여를 환영합니다.

---

## English

A project that automatically collects foreign-currency-deposit (FCD) statistics for roughly 250 countries, loads them into Supabase PostgreSQL, and visualizes them on a web dashboard.

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

### License & contributing

No license has been declared. Issues and pull requests are welcome.

---

## 日本語

約250か国・地域の外貨預金(Foreign Currency Deposits, FCD)統計を自動的に収集し、Supabase PostgreSQLに格納した上で、Webダッシュボードで可視化するプロジェクトです。

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

### ライセンスと貢献について

ライセンスは明示されておりません。Issue・Pull Requestによる貢献を歓迎いたします。

---

## Français

Un projet qui collecte automatiquement les statistiques de dépôts en devises étrangères (Foreign Currency Deposits, FCD) pour environ 250 pays, les charge dans Supabase PostgreSQL, et les visualise sur un tableau de bord web.

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

### Licence et contributions

Aucune licence n'a été déclarée. Les issues et pull requests sont les bienvenues.
