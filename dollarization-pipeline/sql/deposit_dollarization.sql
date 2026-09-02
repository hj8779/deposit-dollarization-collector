-- Supabase / PostgreSQL schema for dollarization-pipeline
-- Run in Supabase SQL Editor, or via: python main.py --init-db
-- Related: sql/country_metadata.sql (targets / country collection metadata)

CREATE TABLE IF NOT EXISTS deposit_dollarization (
    country_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    period TEXT NOT NULL,
    indicator TEXT NOT NULL,
    value DOUBLE PRECISION,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (country_code, year, period, indicator)
);

CREATE INDEX IF NOT EXISTS idx_deposit_dollarization_country_period
    ON deposit_dollarization (country_code, period);

CREATE INDEX IF NOT EXISTS idx_deposit_dollarization_indicator
    ON deposit_dollarization (indicator);

-- Optional: enable read access for anon key (frontend)
-- ALTER TABLE deposit_dollarization ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow public read" ON deposit_dollarization
--   FOR SELECT USING (true);

COMMENT ON TABLE deposit_dollarization IS
  'Long-format FCD/TD/FCD_TD_RATIO by country and period';
COMMENT ON COLUMN deposit_dollarization.indicator IS
  'FCD | TD | FCD_TD_RATIO (ratio in percent 0-100)';
COMMENT ON COLUMN deposit_dollarization.period IS
  'YYYY-MM (preferred) or other period labels';
