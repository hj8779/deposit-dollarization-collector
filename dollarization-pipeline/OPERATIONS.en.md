# Operations Guide

How to install, run, and extend `dollarization-pipeline`. For the full architecture overview, see [README.en.md](README.en.md).

[한국어 버전](OPERATIONS.ko.md)

## 1. Prerequisites

- Python 3.10+
- A Supabase project (PostgreSQL connection string)
- Chromium for Playwright (needed for countries using the Interactive Web strategy)
- The `tesseract-ocr` binary, for the OCR fallback used by some PDF parsers — `brew install tesseract` / `apt install tesseract-ocr`

## 2. Install

```bash
cd dollarization-pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 3. Configure environment variables

```bash
cp .env.example .env
```

Fill in your Supabase connection string in `.env`:

```
SUPABASE_DB_URL=postgresql://postgres.[ref]:[password]@...pooler.supabase.com:6543/postgres
```

- Find it under Supabase Dashboard → **Project Settings → Database → Connection string → URI**
- For CI/serverless environments, use the **Transaction pooler (port 6543)**
- To run automatically on GitHub Actions, register a repository secret named `SUPABASE_DB_URL`

## 4. Create the database tables (one-time)

```bash
python main.py --init-db
```

Alternatively, run `sql/deposit_dollarization.sql` and `sql/country_metadata.sql` directly from the Supabase Dashboard **SQL Editor**.

## 5. Basic usage

```bash
# Preview what would be collected, without writing to the DB
python main.py --dry-run --status success --only-with-parser

# Collect every implemented country and upsert into Supabase
python main.py --status success --only-with-parser

# Collect specific countries only
python main.py --countries UKR,URY,RWA
```

### Common CLI options

| Option | Description |
| --- | --- |
| `--dry-run` | Collect only, don't write to the DB |
| `--countries UKR,URY` | Filter by ISO3 code |
| `--status success` | Filter by `adapter.status` |
| `--only-with-parser` | Only countries with an `src/parsers/{cc}.py` module |
| `--init-db` | Create tables/indexes (`deposit_dollarization` + `country_metadata`) |
| `--migrate-indicators` | Bulk-migrate the legacy `foreign_currency_deposits` indicator name to `FCD` |
| `--list-db-stats` | Print row counts per country currently in Supabase |
| `--db-summary` | Summarize loaded data (coverage, indicators, thin rows). Save as JSON with `--summary-json PATH` |
| `--upload-targets` | Upsert `targets.json` contents into the `country_metadata` table |
| `--thin-threshold N` | Row-count threshold used by `--db-summary` to flag thin countries (default 30) |
| `--include-annual-thin` | Include annual/semi_annual indicators in the thin-row list (excluded by default) |
| `--workers N` | Number of concurrent collection workers (default 4). Each worker starts the next country as soon as it finishes |
| `--timeout-sec N` | Hard per-country timeout in seconds (the process is killed if exceeded). 0 = no limit |
| `--upsert-batch-size N` | Flush an UPSERT once N countries have succeeded (default 5) |
| `--skip-existing` | Skip a country if it already has at least 1 row in the DB |
| `--skip-if-rows-gte N` | Skip a country if its DB row count is ≥ N |
| `--max-db-rows N` | Only target countries with DB row count ≤ N, or not yet collected (useful for reworking thin parsers) |
| `--min-db-rows N` | Only target countries with DB row count ≥ N |

### Example workflows

```bash
# Recommended production run: 8 workers, 120s timeout, upsert every 5 countries, skip ones already loaded
python main.py --status success --only-with-parser \
  --workers 8 --timeout-sec 120 --upsert-batch-size 5 --skip-existing

# Re-run only thin (<=30 rows) or not-yet-collected countries after improving a parser
python main.py --status success --only-with-parser \
  --workers 6 --timeout-sec 180 --max-db-rows 30

# Inspect status / save a summary / upload metadata
python main.py --list-db-stats
python main.py --list-db-stats --max-db-rows 30
python main.py --db-summary
python main.py --db-summary --summary-json runs/db-summary.json
python main.py --upload-targets
```

## 6. Adding a new country parser

1. Make sure `config/targets.json` has an entry for the country, with `source_url`, `data_type`, etc. filled in. See [config/targets.schema.json](config/targets.schema.json) for the schema.
2. Create a new `src/parsers/{country_code_lowercase}.py` module. It must export:
   - `FILE_URL`: the URL of the file to download. Use `None` to fall back to `target['source_url']`
   - `parse(content: bytes, country_code: str) -> pd.DataFrame`: returns a long-form DataFrame
3. If there's no single downloadable file URL (the page itself is the data source, or you need to walk multiple yearly archives), set `FILE_URL = "__RENDER__"` and export `render(target: dict) -> pd.DataFrame"` instead. Use this pattern whenever you need to drive a page with Playwright, or need to merge several files into one series.
4. If PDF text extraction fails (empty result, or characters come out scrambled), use `src/collectors/base.find_page_text_via_ocr(pdf, marker, scorer=...)` as the standard fallback. Reuse this helper (improving it if needed) rather than writing an ad-hoc workaround.
5. Never fabricate values — silently skip a month that fails to match rather than guessing; a missing value is safer than a wrong one.
6. Once done, update `adapter.implemented` / `adapter.status` / `adapter.strategy_class` / `adapter.notes` in `config/targets.json`.

## 7. Regenerating the README adapter status table

After editing `config/targets.json`, regenerate the per-country implementation table in the README:

```bash
python3 scripts/generate_readme_table.py
```

## 8. Scheduled runs

A quarterly scheduled run (1st of Jan/Apr/Jul/Oct, UTC) is configured in [`.github/workflows/quarterly_etl.yml`](.github/workflows/quarterly_etl.yml). It can also be triggered manually, with optional country filters, via GitHub Actions `workflow_dispatch`.

## 9. Troubleshooting

- **DB connection fails**: verify `SUPABASE_DB_URL` in `.env`, and that the port is 6543 (Transaction pooler)
- **Playwright errors**: re-run `playwright install chromium`
- **A PDF needs OCR but it's failing**: confirm the `tesseract-ocr` binary is installed on the system (the `pytesseract` package in `requirements.txt` is only Python bindings — it doesn't include the binary)
- **Retrying a single country**: run `--countries CC1,CC2 --dry-run` first to preview before writing to the DB
