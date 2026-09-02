-- Supabase / PostgreSQL schema: country-level collection metadata (targets)
-- Run in Supabase SQL Editor, or via: python main.py --init-db
-- Sync from config/targets.json: python main.py --upload-targets

CREATE TABLE IF NOT EXISTS country_metadata (
    country_code TEXT PRIMARY KEY,
    country_name TEXT NOT NULL,
    data_type TEXT,
    source_url TEXT,
    -- free-text from targets.json (Monthly / Annual / Quarterly / …)
    update_frequency TEXT,
    -- normalized: annual | quarterly | monthly | semi_annual | higher | unknown | other
    frequency_bucket TEXT,
    requires_js BOOLEAN,
    notes TEXT,
    -- adapter.* flattened for filtering/indexing
    adapter_implemented BOOLEAN,
    adapter_status TEXT,
    adapter_strategy_class TEXT,
    adapter_notes TEXT,
    -- nested list from targets.json (kind/source/status/notes)
    pending_parsers JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- convenience: whether src/parsers/{cc}.py existed at last sync
    has_parser BOOLEAN,
    -- full original target object (forward-compatible)
    raw_target JSONB,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- existing DBs created before frequency_bucket
ALTER TABLE country_metadata
    ADD COLUMN IF NOT EXISTS frequency_bucket TEXT;

CREATE INDEX IF NOT EXISTS idx_country_metadata_data_type
    ON country_metadata (data_type);

CREATE INDEX IF NOT EXISTS idx_country_metadata_adapter_status
    ON country_metadata (adapter_status);

CREATE INDEX IF NOT EXISTS idx_country_metadata_has_parser
    ON country_metadata (has_parser);

CREATE INDEX IF NOT EXISTS idx_country_metadata_frequency_bucket
    ON country_metadata (frequency_bucket);

COMMENT ON TABLE country_metadata IS
  'Per-country collection metadata synced from config/targets.json';
COMMENT ON COLUMN country_metadata.update_frequency IS
  'Raw targets.json update_frequency string (Monthly, Annual, Quarterly, …)';
COMMENT ON COLUMN country_metadata.frequency_bucket IS
  'Normalized frequency: annual | quarterly | monthly | semi_annual | higher | unknown | other';
COMMENT ON COLUMN country_metadata.pending_parsers IS
  'JSON array of {kind, source, status, notes?} auxiliary parsers still TODO';
COMMENT ON COLUMN country_metadata.raw_target IS
  'Full targets.json object at last sync (schema evolution buffer)';
