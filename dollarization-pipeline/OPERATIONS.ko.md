# 조작법 (Operations Guide)

`dollarization-pipeline`을 설치하고, 실행하고, 새 국가를 추가하는 방법을 다룬다. 아키텍처 전체 설명은 [README.md](README.md) 참고.

[English version](OPERATIONS.en.md)

## 1. 준비물

- Python 3.10+
- Supabase 프로젝트 (PostgreSQL 연결 문자열)
- (Interactive Web 전략을 쓰는 국가를 수집할 경우) Playwright용 Chromium
- (일부 PDF 파서의 OCR 폴백용) `tesseract-ocr` 바이너리 — `brew install tesseract` / `apt install tesseract-ocr`

## 2. 설치

```bash
cd dollarization-pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 3. 환경 변수 설정

```bash
cp .env.example .env
```

`.env`에 Supabase 연결 문자열을 채운다:

```
SUPABASE_DB_URL=postgresql://postgres.[ref]:[password]@...pooler.supabase.com:6543/postgres
```

- Supabase Dashboard → **Project Settings → Database → Connection string → URI**에서 확인
- CI/서버리스 환경에서는 **Transaction pooler (포트 6543)** 사용 권장
- GitHub Actions에서 자동 실행하려면 저장소 secret 이름을 `SUPABASE_DB_URL`로 등록

## 4. DB 테이블 생성 (최초 1회)

```bash
python main.py --init-db
```

또는 Supabase Dashboard → **SQL Editor**에서 `sql/deposit_dollarization.sql`, `sql/country_metadata.sql`을 직접 실행해도 된다.

## 5. 기본 실행

```bash
# 무엇이 수집되는지만 확인 (DB 저장 안 함)
python main.py --dry-run --status success --only-with-parser

# 구현된 국가 전체 수집 → Supabase 적재
python main.py --status success --only-with-parser

# 특정 국가만
python main.py --countries UKR,URY,RWA
```

### 자주 쓰는 CLI 옵션

| 옵션 | 설명 |
| --- | --- |
| `--dry-run` | 수집만 하고 DB에 저장하지 않음 |
| `--countries UKR,URY` | ISO3 코드로 필터 |
| `--status success` | `adapter.status` 값으로 필터 |
| `--only-with-parser` | `src/parsers/{cc}.py`가 있는 국가만 |
| `--init-db` | 테이블/인덱스 생성 (`deposit_dollarization` + `country_metadata`) |
| `--migrate-indicators` | 레거시 `foreign_currency_deposits` 지표명을 `FCD`로 일괄 이전 |
| `--list-db-stats` | Supabase에 적재된 국가별 행 수 출력 |
| `--db-summary` | 적재 데이터 요약(기간·지표·저행수). `--summary-json PATH`로 JSON 저장 가능 |
| `--upload-targets` | `targets.json` 내용을 `country_metadata` 테이블에 UPSERT |
| `--thin-threshold N` | `--db-summary`의 저행수 판정 기준 (기본 30) |
| `--include-annual-thin` | 저행수 목록에 annual/semi_annual 지표도 포함 (기본은 제외) |
| `--workers N` | 동시 수집 워커 수 (기본 4). 한 국가가 끝나면 바로 다음 국가 시작 |
| `--timeout-sec N` | 국가당 하드 타임아웃(초과 시 프로세스 강제 종료). 0=무제한 |
| `--upsert-batch-size N` | 성공한 국가 N개가 모이면 UPSERT (기본 5) |
| `--skip-existing` | DB에 이미 1행이라도 있으면 해당 국가 스킵 |
| `--skip-if-rows-gte N` | DB 행 수가 N 이상이면 스킵 |
| `--max-db-rows N` | DB 행 수가 N 이하이거나 아예 없는 국가만 대상 (저행수 파서 점검용) |
| `--min-db-rows N` | DB 행 수가 N 이상인 국가만 대상 |

### 운영 예시

```bash
# 권장 운영 실행: 워커 8개 + 120초 타임아웃 + 5국마다 UPSERT + 이미 있는 국가는 스킵
python main.py --status success --only-with-parser \
  --workers 8 --timeout-sec 120 --upsert-batch-size 5 --skip-existing

# 저행수(≤30행)이거나 미수집인 국가만 다시 수집 (파서 개선 후 재작업용)
python main.py --status success --only-with-parser \
  --workers 6 --timeout-sec 180 --max-db-rows 30

# 현황 확인 / 요약 저장 / 메타데이터 업로드
python main.py --list-db-stats
python main.py --list-db-stats --max-db-rows 30
python main.py --db-summary
python main.py --db-summary --summary-json runs/db-summary.json
python main.py --upload-targets
```

## 6. 새 국가 파서 추가하기

1. `config/targets.json`에 국가 항목이 있는지 확인하고 `source_url`, `data_type` 등을 채운다. 스키마는 [config/targets.schema.json](config/targets.schema.json) 참고.
2. `src/parsers/{country_code_lowercase}.py` 파일 하나를 새로 만든다. 이 파일은 다음을 export해야 한다.
   - `FILE_URL`: 다운로드할 파일의 URL. `target['source_url']`을 그대로 쓸 경우 `None`
   - `parse(content: bytes, country_code: str) -> pd.DataFrame`: 롱폼 DataFrame 반환
3. 다운로드 가능한 단일 파일 URL이 없는 경우(페이지 자체가 데이터이거나, 여러 연도 아카이브를 순회해야 하는 경우) `FILE_URL = "__RENDER__"`로 설정하고 대신 `render(target: dict) -> pd.DataFrame`을 export한다. Playwright로 페이지를 조작해야 하는 경우, 또는 여러 파일을 모아 하나로 합쳐야 하는 경우 이 패턴을 쓴다.
4. PDF 텍스트 추출이 실패하거나(빈 결과, 글자 순서가 뒤섞임) 하면 `src/collectors/base.find_page_text_via_ocr(pdf, marker, scorer=...)`를 표준 폴백으로 사용한다. 즉석 임시방편을 짜지 말고 이 함수를 재사용하거나, 필요하면 함수 자체를 개선한다.
5. 값을 추측해서 채우지 않는다 — 매칭에 실패한 달은 조용히 스킵하는 것이 틀린 값보다 안전하다.
6. 완료 후 `config/targets.json`의 `adapter.implemented`/`adapter.status`/`adapter.strategy_class`/`adapter.notes`를 갱신한다.

## 7. README 어댑터 현황 표 갱신

`config/targets.json`을 수정한 뒤에는 아래 명령으로 README의 국가별 구현 현황 표를 재생성한다.

```bash
python3 scripts/generate_readme_table.py
```

## 8. 정기 자동 실행

분기별(1·4·7·10월 1일 UTC) 자동 실행은 [`.github/workflows/quarterly_etl.yml`](.github/workflows/quarterly_etl.yml)에 설정되어 있다. GitHub Actions의 `workflow_dispatch`로 수동 실행하거나 국가를 필터링해 실행할 수도 있다.

## 9. 문제 해결

- **DB 연결 실패**: `.env`의 `SUPABASE_DB_URL`이 올바른지, 포트가 6543(Transaction pooler)인지 확인
- **Playwright 관련 오류**: `playwright install chromium`을 다시 실행
- **PDF에서 OCR이 필요한데 실패**: 시스템에 `tesseract-ocr` 바이너리가 설치되어 있는지 확인 (`requirements.txt`의 `pytesseract`는 파이썬 바인딩일 뿐 바이너리를 대체하지 못한다)
- **특정 국가만 재시도하고 싶을 때**: `--countries CC1,CC2 --dry-run`으로 먼저 확인 후 실제 적재
