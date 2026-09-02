# Dollarization Ratio — DB Dashboard

React + TypeScript + [Effect](https://effect.website) + Recharts dashboard that reads
directly from Supabase (no custom backend). Shows:

- **DB Summary table** — one row per country (rows, distinct periods, min/max period,
  declared update frequency, indicators present), sortable/filterable, with a ⚠ badge
  for countries whose *source* blocks or lacks automatable data (see
  `src/lib/manualUpdateCountries.ts` — keep this list in sync with the collector's
  parser docstrings).
- **Chart form** — pick a country and any of FCD / TD / FCD_TD_RATIO; the x-axis
  label format (year / "YYYY Qn" / month name / date) adapts automatically per period
  string shape (`src/lib/period.ts`), since a country's declared frequency in
  `country_metadata` can drift from what's actually stored.

## Setup

```bash
npm install
cp .env.example .env   # already done in this checkout; just fill in the key below
```

Fill in `VITE_SUPABASE_ANON_KEY` in `.env` — Supabase dashboard → Project Settings →
API → `anon` `public` key. `VITE_SUPABASE_URL` is already set.

```bash
npm run dev
```

## Data access

The frontend queries Supabase directly via `@supabase/supabase-js` with the public
anon key — no separate REST API. This requires:

1. RLS enabled + a public read-only `SELECT` policy on `deposit_dollarization` and
   `country_metadata` (already applied to the project's Supabase instance).
2. A pre-aggregated view, `deposit_dollarization_summary`, that does the
   country-level GROUP BY server-side instead of shipping 50k+ raw rows to the
   browser (also already applied). Recreate it with:

   ```sql
   -- Starts FROM country_metadata (not deposit_dollarization) so a country with
   -- zero collected rows (e.g. a source that's currently fully blocked) still
   -- shows up as a 0-row entry instead of silently disappearing from the summary.
   CREATE OR REPLACE VIEW deposit_dollarization_summary
   WITH (security_invoker = true) AS
   SELECT
       m.country_code,
       COALESCE(COUNT(d.*), 0)::bigint AS rows,
       COUNT(DISTINCT d.period)::bigint AS periods,
       MIN(d.period) AS min_period,
       MAX(d.period) AS max_period,
       STRING_AGG(DISTINCT d.indicator, ',' ORDER BY d.indicator) AS indicators,
       MAX(d.updated_at) AS last_updated,
       m.update_frequency,
       m.frequency_bucket,
       m.country_name,
       m.source_url,
       m.notes,
       m.adapter_notes,
       m.adapter_status,
       m.data_type
   FROM country_metadata m
   LEFT JOIN deposit_dollarization d ON d.country_code = m.country_code
   GROUP BY m.country_code, m.update_frequency, m.frequency_bucket, m.country_name,
            m.source_url, m.notes, m.adapter_notes, m.adapter_status, m.data_type
   ORDER BY m.country_code;

   GRANT SELECT ON deposit_dollarization_summary TO anon, authenticated;
   ```
3. A second lightweight view, `deposit_dollarization_periods`, giving the frontend
   just the distinct (country_code, period) pairs — enough to classify each
   country's coverage into annual/quarterly/monthly for the header coverage counts
   (`src/lib/frequencyCoverage.ts`) without shipping every FCD/TD/ratio row:

   ```sql
   CREATE OR REPLACE VIEW deposit_dollarization_periods
   WITH (security_invoker = true) AS
   SELECT DISTINCT country_code, period
   FROM deposit_dollarization;

   GRANT SELECT ON deposit_dollarization_periods TO anon, authenticated;
   ```
4. Write access (INSERT/UPDATE/DELETE) for the manual-entry table, scoped to
   *only* the countries in `src/lib/manualUpdateCountries.ts` — the anon key
   otherwise has no write access at all, so a bug in one manual-entry form
   can't corrupt the 240+ auto-collected countries. **Whenever you add or
   remove a country from `MANUAL_UPDATE_COUNTRIES`, re-run this with the
   updated list** (forgetting this step is exactly what causes a fresh manual
   country to fail with `new row violates row-level security policy`):

   ```sql
   DROP POLICY IF EXISTS manual_write_deposit_dollarization ON deposit_dollarization;
   CREATE POLICY manual_write_deposit_dollarization
   ON deposit_dollarization FOR INSERT
   TO anon, authenticated
   WITH CHECK (country_code IN ('COD','LBN','MDG','BTN','MDA','IRQ','RWA','TUR','LVA','AGO'));

   DROP POLICY IF EXISTS manual_update_deposit_dollarization ON deposit_dollarization;
   CREATE POLICY manual_update_deposit_dollarization
   ON deposit_dollarization FOR UPDATE
   TO anon, authenticated
   USING (country_code IN ('COD','LBN','MDG','BTN','MDA','IRQ','RWA','TUR','LVA','AGO'))
   WITH CHECK (country_code IN ('COD','LBN','MDG','BTN','MDA','IRQ','RWA','TUR','LVA','AGO'));

   DROP POLICY IF EXISTS manual_delete_deposit_dollarization ON deposit_dollarization;
   CREATE POLICY manual_delete_deposit_dollarization
   ON deposit_dollarization FOR DELETE
   TO anon, authenticated
   USING (country_code IN ('COD','LBN','MDG','BTN','MDA','IRQ','RWA','TUR','LVA','AGO'));
   ```

   Half-manual countries (`kind: "half_manual"`, badge **◐ 하프**) still use the same
   write whitelist so the dashboard form can patch gaps; primary refresh is usually
   a local `report.xlsx` + collector `render()` (see MDA).

## Structure

```
src/lib/
  supabase.ts        Supabase client (throws at startup if env vars are missing)
  types.ts            Domain types (CountrySummary, DepositRow, ChartPoint)
  db.ts                Effect-returning queries (fetchCountrySummaries, fetchDepositRows)
  useEffectQuery.ts   React hook: runs an Effect as a fiber tied to the component
                       lifecycle (interrupts stale requests on unmount/dep change)
  period.ts            Period-string parsing/formatting/sorting (annual/quarterly/monthly/daily)
  chartData.ts         Pivots long-form rows into per-period chart points
  manualUpdateCountries.ts   Manual / half-manual country flags (kind + reason + sourceUrl)
src/components/
  DbSummaryTable.tsx
  ChartForm.tsx
  DepositChart.tsx
```
