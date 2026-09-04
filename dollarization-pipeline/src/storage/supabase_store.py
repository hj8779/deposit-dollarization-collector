"""Supabase (PostgreSQL) storage module.

1) UPSERTs the long-form DataFrame [country_code, year, period, indicator,
   value, updated_at] into the deposit_dollarization table on its composite PK.
2) UPSERTs config/targets.json country metadata into the country_metadata table.
3) Summarizes the current state of the loaded data (summarize_deposit_data).

Connection string: SUPABASE_DB_URL environment variable
  e.g. postgresql://postgres.[ref]:[password]@aws-0-...pooler.supabase.com:6543/postgres
  or   Session mode 5432 / Transaction pooler 6543
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.utils.logger import get_logger

logger = get_logger(__name__)

TABLE_NAME = "deposit_dollarization"
METADATA_TABLE = "country_metadata"
REQUIRED_COLS = ("country_code", "year", "period", "indicator", "value", "updated_at")
_BATCH_SIZE = 500

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    country_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    period TEXT NOT NULL,
    indicator TEXT NOT NULL,
    value DOUBLE PRECISION,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (country_code, year, period, indicator)
);
"""

# Defense-in-depth alongside _validate_value_range(): FCD/TD are stock levels
# (never negative), FCD_TD_RATIO is a percent in [0, 100]. Applied via a guarded
# DO block (not "ADD CONSTRAINT IF NOT EXISTS", which Postgres doesn't support)
# so re-running ensure_table() is idempotent.
ADD_VALUE_RANGE_CHECK_SQL = f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_{TABLE_NAME}_value_range'
    ) THEN
        ALTER TABLE {TABLE_NAME}
        ADD CONSTRAINT chk_{TABLE_NAME}_value_range
        CHECK (
            (indicator = 'FCD_TD_RATIO' AND value >= 0 AND value <= 100)
            OR (indicator <> 'FCD_TD_RATIO' AND value >= 0)
        );
    END IF;
END $$;
"""

CREATE_INDEX_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_country_period
    ON {TABLE_NAME} (country_code, period);
CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_indicator
    ON {TABLE_NAME} (indicator);
"""

UPSERT_SQL = f"""
INSERT INTO {TABLE_NAME} (country_code, year, period, indicator, value, updated_at)
VALUES (:country_code, :year, :period, :indicator, :value, :updated_at)
ON CONFLICT (country_code, year, period, indicator)
DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = EXCLUDED.updated_at;
"""

CREATE_METADATA_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {METADATA_TABLE} (
    country_code TEXT PRIMARY KEY,
    country_name TEXT NOT NULL,
    data_type TEXT,
    source_url TEXT,
    update_frequency TEXT,
    frequency_bucket TEXT,
    requires_js BOOLEAN,
    notes TEXT,
    adapter_implemented BOOLEAN,
    adapter_status TEXT,
    adapter_strategy_class TEXT,
    adapter_notes TEXT,
    pending_parsers JSONB NOT NULL DEFAULT '[]'::jsonb,
    has_parser BOOLEAN,
    raw_target JSONB,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_METADATA_INDEX_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_{METADATA_TABLE}_data_type
    ON {METADATA_TABLE} (data_type);
CREATE INDEX IF NOT EXISTS idx_{METADATA_TABLE}_adapter_status
    ON {METADATA_TABLE} (adapter_status);
CREATE INDEX IF NOT EXISTS idx_{METADATA_TABLE}_has_parser
    ON {METADATA_TABLE} (has_parser);
CREATE INDEX IF NOT EXISTS idx_{METADATA_TABLE}_frequency_bucket
    ON {METADATA_TABLE} (frequency_bucket);
"""

# Existing deployments may predate frequency_bucket
ALTER_METADATA_SQL = f"""
ALTER TABLE {METADATA_TABLE}
    ADD COLUMN IF NOT EXISTS frequency_bucket TEXT;
"""

UPSERT_METADATA_SQL = f"""
INSERT INTO {METADATA_TABLE} (
    country_code, country_name, data_type, source_url, update_frequency,
    frequency_bucket, requires_js, notes,
    adapter_implemented, adapter_status, adapter_strategy_class, adapter_notes,
    pending_parsers, has_parser, raw_target, synced_at
) VALUES (
    :country_code, :country_name, :data_type, :source_url, :update_frequency,
    :frequency_bucket, :requires_js, :notes,
    :adapter_implemented, :adapter_status, :adapter_strategy_class, :adapter_notes,
    CAST(:pending_parsers AS jsonb), :has_parser, CAST(:raw_target AS jsonb), :synced_at
)
ON CONFLICT (country_code)
DO UPDATE SET
    country_name = EXCLUDED.country_name,
    data_type = EXCLUDED.data_type,
    source_url = EXCLUDED.source_url,
    update_frequency = EXCLUDED.update_frequency,
    frequency_bucket = EXCLUDED.frequency_bucket,
    requires_js = EXCLUDED.requires_js,
    notes = EXCLUDED.notes,
    adapter_implemented = EXCLUDED.adapter_implemented,
    adapter_status = EXCLUDED.adapter_status,
    adapter_strategy_class = EXCLUDED.adapter_strategy_class,
    adapter_notes = EXCLUDED.adapter_notes,
    pending_parsers = EXCLUDED.pending_parsers,
    has_parser = EXCLUDED.has_parser,
    raw_target = EXCLUDED.raw_target,
    synced_at = EXCLUDED.synced_at;
"""

# annual / semi_annual sources are treated as "normally sparse" even with few rows
EXPECTED_THIN_BUCKETS = frozenset({"annual", "semi_annual"})


def get_db_url() -> str:
    url = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL environment variable is not set. "
            "Set the Supabase Postgres connection string in .env. "
            "(Project Settings → Database → Connection string → URI)"
        )
    # SQLAlchemy 2 + psycopg2: postgres:// → postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def get_engine(db_url: str | None = None) -> Engine:
    url = db_url or get_db_url()
    # pool_pre_ping: guards against idle connection drops (Supabase pooler compatible)
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        connect_args={"connect_timeout": 30},
    )


def ensure_table(engine: Engine) -> None:
    """Ensure the deposit_dollarization + country_metadata tables/indexes exist."""
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
        conn.execute(text(ADD_VALUE_RANGE_CHECK_SQL))
        for stmt in CREATE_INDEX_SQL.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))
        conn.execute(text(CREATE_METADATA_TABLE_SQL))
        for stmt in ALTER_METADATA_SQL.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))
        for stmt in CREATE_METADATA_INDEX_SQL.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))
    logger.info("Tables verified/created: %s, %s", TABLE_NAME, METADATA_TABLE)


def normalize_frequency_bucket(update_frequency: str | None) -> str:
    """Map targets.json update_frequency to a canonical bucket.

    Returns one of:
      annual | semi_annual | quarterly | monthly | higher | unknown | other
    """
    s = (update_frequency or "").strip().lower()
    if not s:
        return "unknown"
    if re.search(r"semi[\s-]*annual|bi[\s-]*annual|half[\s-]*year", s):
        return "semi_annual"
    if re.search(r"annual|yearly|\byear\b", s):
        return "annual"
    if re.search(r"quarter", s):
        return "quarterly"
    if re.search(r"month", s):
        return "monthly"
    if re.search(r"week|daily|\bday\b", s):
        return "higher"
    return "other"


def periods_look_annual(min_period: str | None, max_period: str | None) -> bool:
    """True if the stored period label looks annual (e.g. 2000-Annual, 2025-Annual)."""
    for p in (min_period, max_period):
        if p and re.search(r"annual|yearly", str(p), re.I):
            return True
    return False


# Legacy → canonical indicator names (applied on write + migrate_legacy_indicators)
_INDICATOR_ALIASES = {
    "foreign_currency_deposits": "FCD",
    "fcd": "FCD",
    "td": "TD",
    "total_deposits": "TD",
    "fcd_td_ratio": "FCD_TD_RATIO",
    "ratio": "FCD_TD_RATIO",
    "dollarization_ratio": "FCD_TD_RATIO",
}


def normalize_indicator(name: str) -> str:
    """Map legacy/alias indicator labels to FCD | TD | FCD_TD_RATIO."""
    s = str(name).strip()
    if not s:
        return s
    key = s.lower().replace(" ", "_")
    return _INDICATOR_ALIASES.get(key, s)


def _validate_value_range(work: pd.DataFrame) -> pd.DataFrame:
    """FCD/TD are stock levels and can't be negative; FCD_TD_RATIO is a percent
    and must fall in [0, 100]. Rows violating this are almost always a parser
    bug (e.g. picking up a "monthly change" table instead of a levels table —
    see ARE's Table 3 "Monthly Changes" incident) rather than real data, so
    they're dropped here rather than silently upserted."""
    is_ratio = work["indicator"] == "FCD_TD_RATIO"
    bad_ratio = is_ratio & ((work["value"] < 0) | (work["value"] > 100))
    bad_level = (~is_ratio) & (work["value"] < 0)
    bad = bad_ratio | bad_level
    if bad.any():
        sample = work.loc[bad, ["country_code", "period", "indicator", "value"]].head(10)
        logger.warning(
            "Skipping %d rows that failed value-range validation (FCD/TD>=0, FCD_TD_RATIO 0-100 violated):\n%s",
            int(bad.sum()), sample.to_string(index=False),
        )
    return work.loc[~bad]


def _normalize_records(df: pd.DataFrame) -> list[dict]:
    work = df.loc[:, list(REQUIRED_COLS)].copy()
    work["country_code"] = work["country_code"].astype(str).str.upper().str.strip()
    work["year"] = work["year"].astype(int)
    work["period"] = work["period"].astype(str).str.strip()
    work["indicator"] = work["indicator"].map(normalize_indicator)
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    # drop rows without value
    work = work.dropna(subset=["value"])
    work = _validate_value_range(work)
    # updated_at → ISO string for TIMESTAMPTZ
    work["updated_at"] = work["updated_at"].astype(str)
    # de-dupe within batch (last wins)
    work = work.drop_duplicates(
        subset=["country_code", "year", "period", "indicator"], keep="last"
    )
    return work.to_dict(orient="records")


def _chunked(items: list, size: int) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def upsert_long_format(df: pd.DataFrame, engine: Engine | None = None) -> int:
    """UPSERT a long-form DataFrame into deposit_dollarization and return the affected row count."""
    if df is None or df.empty:
        logger.info("Skipping UPSERT: empty DataFrame")
        return 0

    missing = set(REQUIRED_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"Long-form DataFrame is missing required columns: {missing}")

    owns_engine = engine is None
    engine = engine or get_engine()
    try:
        ensure_table(engine)
        records = _normalize_records(df)
        if not records:
            logger.warning("Skipping UPSERT: no valid rows after normalization")
            return 0

        n = 0
        with engine.begin() as conn:
            for batch in _chunked(records, _BATCH_SIZE):
                conn.execute(text(UPSERT_SQL), batch)
                n += len(batch)

        countries = sorted({r["country_code"] for r in records})
        logger.info(
            "UPSERT complete: %d rows / %d countries (%s)",
            n,
            len(countries),
            ", ".join(countries[:12]) + ("…" if len(countries) > 12 else ""),
        )
        return n
    finally:
        if owns_engine:
            engine.dispose()


def fetch_sample(limit: int = 10, engine: Engine | None = None) -> pd.DataFrame:
    """For connectivity checks: fetch the most recently loaded rows."""
    owns = engine is None
    engine = engine or get_engine()
    try:
        q = text(
            f"""
            SELECT country_code, year, period, indicator, value, updated_at
            FROM {TABLE_NAME}
            ORDER BY updated_at DESC NULLS LAST
            LIMIT :lim
            """
        )
        with engine.connect() as conn:
            return pd.read_sql(q, conn, params={"lim": limit})
    finally:
        if owns:
            engine.dispose()


def count_rows(engine: Engine | None = None) -> int:
    owns = engine is None
    engine = engine or get_engine()
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).scalar() or 0)
    finally:
        if owns:
            engine.dispose()


def count_rows_by_country(engine: Engine | None = None) -> dict[str, int]:
    """country_code -> long-form row count. Returns an empty dict if the table doesn't exist."""
    owns = engine is None
    engine = engine or get_engine()
    try:
        ensure_table(engine)
        q = text(
            f"""
            SELECT country_code, COUNT(*)::bigint AS n
            FROM {TABLE_NAME}
            GROUP BY country_code
            """
        )
        with engine.connect() as conn:
            rows = conn.execute(q).fetchall()
        return {str(r[0]).upper(): int(r[1]) for r in rows}
    except Exception as e:
        logger.warning("count_rows_by_country failed: %s", e)
        return {}
    finally:
        if owns:
            engine.dispose()


def list_countries_with_rows(
    *,
    max_rows: int | None = None,
    min_rows: int | None = None,
    engine: Engine | None = None,
) -> list[tuple[str, int]]:
    """List of (country_code, n), filtered by max_rows/min_rows."""
    counts = count_rows_by_country(engine=engine)
    out = []
    for code, n in sorted(counts.items()):
        if max_rows is not None and n > max_rows:
            continue
        if min_rows is not None and n < min_rows:
            continue
        out.append((code, n))
    return out


def delete_country_rows(
    country_code: str,
    engine: Engine | None = None,
) -> int:
    """Delete all deposit_dollarization rows for one ISO3 country. Returns deleted count."""
    code = str(country_code).upper().strip()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError(f"invalid country_code: {country_code!r}")
    owns = engine is None
    engine = engine or get_engine()
    try:
        ensure_table(engine)
        with engine.begin() as conn:
            r = conn.execute(
                text(f"DELETE FROM {TABLE_NAME} WHERE country_code = :cc"),
                {"cc": code},
            )
            n = int(r.rowcount or 0)
        logger.info("deleted %d rows for country_code=%s", n, code)
        return n
    finally:
        if owns:
            engine.dispose()


def migrate_legacy_indicators(engine: Engine | None = None) -> dict[str, int]:
    """Migrate legacy indicator names in the DB to their canonical form.

    foreign_currency_deposits -> FCD.
    If FCD already exists for the same PK, only the legacy row is deleted
    (the existing FCD row is kept).
    Returns: {"renamed": n, "deleted_dupes": m, "remaining_legacy": k}
    """
    owns = engine is None
    engine = engine or get_engine()
    try:
        ensure_table(engine)
        renamed = 0
        deleted = 0
        with engine.begin() as conn:
            # 1) drop legacy rows that would conflict with existing FCD
            r = conn.execute(
                text(
                    f"""
                    DELETE FROM {TABLE_NAME} AS legacy
                    WHERE legacy.indicator = 'foreign_currency_deposits'
                      AND EXISTS (
                        SELECT 1 FROM {TABLE_NAME} AS can
                        WHERE can.country_code = legacy.country_code
                          AND can.year = legacy.year
                          AND can.period = legacy.period
                          AND can.indicator = 'FCD'
                      )
                    """
                )
            )
            deleted = int(r.rowcount or 0)

            # 2) rename remaining legacy → FCD
            r = conn.execute(
                text(
                    f"""
                    UPDATE {TABLE_NAME}
                    SET indicator = 'FCD'
                    WHERE indicator = 'foreign_currency_deposits'
                    """
                )
            )
            renamed = int(r.rowcount or 0)

            remaining = int(
                conn.execute(
                    text(
                        f"""
                        SELECT COUNT(*) FROM {TABLE_NAME}
                        WHERE indicator = 'foreign_currency_deposits'
                        """
                    )
                ).scalar()
                or 0
            )

        logger.info(
            "Indicator migration: renamed=%d deleted_dupes=%d remaining_legacy=%d",
            renamed,
            deleted,
            remaining,
        )
        return {
            "renamed": renamed,
            "deleted_dupes": deleted,
            "remaining_legacy": remaining,
        }
    finally:
        if owns:
            engine.dispose()


# ---------------------------------------------------------------------------
# country_metadata (targets.json)
# ---------------------------------------------------------------------------


def _parser_path_for(country_code: str, parsers_dir: Path | None = None) -> Path:
    root = parsers_dir or (
        Path(__file__).resolve().parents[2] / "src" / "parsers"
    )
    return root / f"{country_code.lower()}.py"


def target_to_metadata_record(
    target: dict,
    *,
    parsers_dir: Path | None = None,
    synced_at: str | None = None,
) -> dict[str, Any]:
    """Convert one targets.json entry into a country_metadata UPSERT record."""
    code = str(target.get("country_code", "")).upper().strip()
    adapter = target.get("adapter") or {}
    pending = target.get("pending_parsers") or []
    if not isinstance(pending, list):
        pending = []
    ts = synced_at or datetime.now(timezone.utc).isoformat()
    has_parser = _parser_path_for(code, parsers_dir).exists() if code else False
    raw_freq = target.get("update_frequency")
    return {
        "country_code": code,
        "country_name": str(target.get("country_name") or code),
        "data_type": target.get("data_type"),
        "source_url": target.get("source_url"),
        "update_frequency": raw_freq,
        "frequency_bucket": normalize_frequency_bucket(
            str(raw_freq) if raw_freq is not None else None
        ),
        "requires_js": target.get("requires_js"),
        "notes": target.get("notes"),
        "adapter_implemented": bool(adapter.get("implemented"))
        if adapter.get("implemented") is not None
        else None,
        "adapter_status": adapter.get("status"),
        "adapter_strategy_class": adapter.get("strategy_class"),
        "adapter_notes": adapter.get("notes"),
        "pending_parsers": json.dumps(pending, ensure_ascii=False),
        "has_parser": has_parser,
        "raw_target": json.dumps(target, ensure_ascii=False),
        "synced_at": ts,
    }


def upsert_country_metadata(
    targets: list[dict],
    engine: Engine | None = None,
    *,
    parsers_dir: Path | None = None,
) -> int:
    """UPSERT the targets.json list into country_metadata. Returns the affected row count."""
    if not targets:
        logger.info("Skipping metadata UPSERT: empty list")
        return 0

    owns_engine = engine is None
    engine = engine or get_engine()
    try:
        ensure_table(engine)
        ts = datetime.now(timezone.utc).isoformat()
        records = [
            target_to_metadata_record(t, parsers_dir=parsers_dir, synced_at=ts)
            for t in targets
            if t.get("country_code")
        ]
        if not records:
            return 0

        n = 0
        with engine.begin() as conn:
            for batch in _chunked(records, _BATCH_SIZE):
                conn.execute(text(UPSERT_METADATA_SQL), batch)
                n += len(batch)

        logger.info(
            "country_metadata UPSERT complete: %d countries (has_parser=%d)",
            n,
            sum(1 for r in records if r.get("has_parser")),
        )
        return n
    finally:
        if owns_engine:
            engine.dispose()


def count_metadata_rows(engine: Engine | None = None) -> int:
    owns = engine is None
    engine = engine or get_engine()
    try:
        with engine.connect() as conn:
            return int(
                conn.execute(text(f"SELECT COUNT(*) FROM {METADATA_TABLE}")).scalar()
                or 0
            )
    except Exception as e:
        logger.warning("count_metadata_rows failed: %s", e)
        return 0
    finally:
        if owns:
            engine.dispose()


def fetch_country_metadata(
    codes: list[str] | None = None,
    engine: Engine | None = None,
) -> pd.DataFrame:
    """Fetch country_metadata (optional ISO3 filter)."""
    owns = engine is None
    engine = engine or get_engine()
    try:
        ensure_table(engine)
        q = text(
            f"""
            SELECT country_code, country_name, data_type, source_url,
                   update_frequency, frequency_bucket, requires_js, notes,
                   adapter_implemented, adapter_status, adapter_strategy_class,
                   has_parser, synced_at
            FROM {METADATA_TABLE}
            ORDER BY country_code
            """
        )
        with engine.connect() as conn:
            df = pd.read_sql(q, conn)
        if codes and not df.empty:
            want = {c.upper().strip() for c in codes if c and str(c).strip()}
            df = df[df["country_code"].astype(str).str.upper().isin(want)]
        return df
    finally:
        if owns:
            engine.dispose()


# ---------------------------------------------------------------------------
# deposit data summary
# ---------------------------------------------------------------------------


def load_frequency_map(engine: Engine | None = None) -> dict[str, dict[str, str | None]]:
    """country_code -> {update_frequency, frequency_bucket}."""
    owns = engine is None
    engine = engine or get_engine()
    try:
        ensure_table(engine)
        q = text(
            f"""
            SELECT country_code, update_frequency, frequency_bucket
            FROM {METADATA_TABLE}
            """
        )
        with engine.connect() as conn:
            rows = conn.execute(q).fetchall()
        return {
            str(r[0]).upper(): {
                "update_frequency": r[1],
                "frequency_bucket": r[2] or normalize_frequency_bucket(r[1]),
            }
            for r in rows
        }
    except Exception as e:
        logger.warning("load_frequency_map failed: %s", e)
        return {}
    finally:
        if owns:
            engine.dispose()


def is_expected_thin(
    *,
    frequency_bucket: str | None,
    min_period: str | None = None,
    max_period: str | None = None,
) -> bool:
    """Exempt annual (or semi-annual) sources from thin-row review even with few rows."""
    bucket = (frequency_bucket or "").lower()
    if bucket in EXPECTED_THIN_BUCKETS:
        return True
    if periods_look_annual(min_period, max_period):
        return True
    return False


def summarize_deposit_data(
    engine: Engine | None = None,
    *,
    thin_threshold: int = 30,
    exclude_annual_from_thin: bool = True,
) -> dict[str, Any]:
    """Summarize the deposit_dollarization data currently loaded in the DB.

    thin_countries: parser review candidates (default: annual/semi_annual excluded)
    thin_expected: countries where a thin row count is expected (e.g. annual)
    """
    owns = engine is None
    engine = engine or get_engine()
    try:
        ensure_table(engine)
        with engine.connect() as conn:
            total_rows = int(
                conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).scalar() or 0
            )
            ind_rows = conn.execute(
                text(
                    f"""
                    SELECT indicator, COUNT(*)::bigint AS n
                    FROM {TABLE_NAME}
                    GROUP BY indicator
                    ORDER BY indicator
                    """
                )
            ).fetchall()
            by_indicator = {str(r[0]): int(r[1]) for r in ind_rows}

            country_q = text(
                f"""
                SELECT
                    country_code,
                    COUNT(*)::bigint AS rows,
                    COUNT(DISTINCT period)::bigint AS periods,
                    MIN(period) AS min_period,
                    MAX(period) AS max_period,
                    STRING_AGG(DISTINCT indicator, ',') AS indicators,
                    MAX(updated_at) AS last_updated
                FROM {TABLE_NAME}
                GROUP BY country_code
                ORDER BY country_code
                """
            )
            country_rows = conn.execute(country_q).fetchall()

            meta_n = 0
            freq_map: dict[str, dict[str, str | None]] = {}
            try:
                meta_n = int(
                    conn.execute(
                        text(f"SELECT COUNT(*) FROM {METADATA_TABLE}")
                    ).scalar()
                    or 0
                )
                freq_rows = conn.execute(
                    text(
                        f"""
                        SELECT country_code, update_frequency, frequency_bucket
                        FROM {METADATA_TABLE}
                        """
                    )
                ).fetchall()
                for fr in freq_rows:
                    code = str(fr[0]).upper()
                    freq_map[code] = {
                        "update_frequency": fr[1],
                        "frequency_bucket": fr[2]
                        or normalize_frequency_bucket(fr[1]),
                    }
            except Exception:
                meta_n = 0

            # frequency_bucket distribution
            bucket_counts: dict[str, int] = {}
            for m in freq_map.values():
                b = str(m.get("frequency_bucket") or "unknown")
                bucket_counts[b] = bucket_counts.get(b, 0) + 1

        countries: list[dict[str, Any]] = []
        for r in country_rows:
            code = str(r[0]).upper()
            meta = freq_map.get(code) or {}
            bucket = meta.get("frequency_bucket") or "unknown"
            countries.append(
                {
                    "country_code": code,
                    "rows": int(r[1]),
                    "periods": int(r[2]),
                    "min_period": r[3],
                    "max_period": r[4],
                    "indicators": (r[5] or "").split(",") if r[5] else [],
                    "last_updated": r[6].isoformat() if r[6] is not None else None,
                    "update_frequency": meta.get("update_frequency"),
                    "frequency_bucket": bucket,
                }
            )

        thin_all = [c for c in countries if c["rows"] <= thin_threshold]
        thin_expected: list[dict[str, Any]] = []
        thin_review: list[dict[str, Any]] = []
        for c in thin_all:
            if exclude_annual_from_thin and is_expected_thin(
                frequency_bucket=c.get("frequency_bucket"),
                min_period=c.get("min_period"),
                max_period=c.get("max_period"),
            ):
                thin_expected.append(c)
            else:
                thin_review.append(c)

        thin_review.sort(key=lambda x: (x["rows"], x["country_code"]))
        thin_expected.sort(key=lambda x: (x["rows"], x["country_code"]))

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "totals": {
                "rows": total_rows,
                "countries": len(countries),
                "indicators": sorted(by_indicator.keys()),
            },
            "by_indicator": by_indicator,
            "countries": countries,
            # backward compat: thin_countries = review candidates (annual excluded)
            "thin_countries": thin_review,
            "thin_expected": thin_expected,
            "thin_threshold": thin_threshold,
            "exclude_annual_from_thin": exclude_annual_from_thin,
            "metadata": {
                "rows": meta_n,
                "frequency_buckets": bucket_counts,
            },
        }
    finally:
        if owns:
            engine.dispose()


def format_deposit_summary(
    summary: dict[str, Any],
    *,
    show_all_countries: bool = True,
    max_list: int = 40,
) -> str:
    """Render the summarize_deposit_data result as console text."""
    lines: list[str] = []
    t = summary.get("totals") or {}
    lines.append("=== deposit_dollarization summary ===")
    lines.append(
        f"Total rows: {t.get('rows', 0):,}  |  Countries: {t.get('countries', 0)}  |  "
        f"Indicators: {', '.join(t.get('indicators') or []) or '-'}"
    )
    by_ind = summary.get("by_indicator") or {}
    if by_ind:
        lines.append(
            "Rows by indicator: "
            + ", ".join(f"{k}={v:,}" for k, v in sorted(by_ind.items()))
        )
    meta = summary.get("metadata") or {}
    lines.append(f"country_metadata rows: {meta.get('rows', 0)}")
    buckets = meta.get("frequency_buckets") or {}
    if buckets:
        lines.append(
            "Metadata frequency (frequency_bucket): "
            + ", ".join(f"{k}={v}" for k, v in sorted(buckets.items()))
        )

    thr = summary.get("thin_threshold", 30)
    thin = summary.get("thin_countries") or []
    thin_exp = summary.get("thin_expected") or []
    if thin:
        sample = ", ".join(
            f"{c['country_code']}({c['rows']}"
            f"/{c.get('frequency_bucket') or '?'})"
            for c in thin[:max_list]
        )
        more = f" …+{len(thin) - max_list}" if len(thin) > max_list else ""
        lines.append(
            f"Thin-row review candidates (<={thr}, annual excluded) {len(thin)} countries: {sample}{more}"
        )
    else:
        lines.append(f"Thin-row review candidates (<={thr}, annual excluded): none")

    if thin_exp:
        sample = ", ".join(
            f"{c['country_code']}({c['rows']}"
            f"/{c.get('frequency_bucket') or 'annual-period'})"
            for c in thin_exp[:max_list]
        )
        more = f" …+{len(thin_exp) - max_list}" if len(thin_exp) > max_list else ""
        lines.append(
            f"Thin-row exemptions (annual/semi_annual, etc.) {len(thin_exp)} countries: {sample}{more}"
        )

    countries = summary.get("countries") or []
    if show_all_countries and countries:
        lines.append("")
        lines.append(
            f"{'CC':4} {'rows':>6} {'per':>5} {'freq':10}  "
            f"{'min':12} {'max':12}  indicators"
        )
        lines.append("-" * 80)
        for c in sorted(countries, key=lambda x: x["country_code"]):
            inds = ",".join(c.get("indicators") or [])
            lines.append(
                f"{c['country_code']:4} {c['rows']:6d} {c['periods']:5d} "
                f"{str(c.get('frequency_bucket') or '-'):10}  "
                f"{str(c.get('min_period') or '-'):12} "
                f"{str(c.get('max_period') or '-'):12}  {inds}"
            )
    return "\n".join(lines)
