"""Backfill derived annual/quarterly observations from finer-grained data.

For each (country_code, indicator) pair in `deposit_dollarization`, derives
missing coarser-frequency observations by copying the corresponding
fine-grained value, so the "Annual" / "Quarterly" filter views on the
dashboard include the maximum number of countries and the longest possible
series:

  - monthly (YYYY-MM) -> quarterly (YYYY-QN): copies March/June/Sept/Dec
    values into Q1-Q4 respectively.
  - monthly (YYYY-MM) -> annual (YYYY-Annual): copies the December value.
  - quarterly (YYYY-QN) -> annual (YYYY-Annual): copies the Q4 value, for
    years not already covered by a monthly-derived annual value.
  - semi_annual (JPN only, stored as YYYY-MM with ~2 populated months/year)
    -> annual (YYYY-Annual): copies the later-month observation each year.

A derived row is only ever INSERTed where the (country_code, year, period,
indicator) primary key does not already exist -- an existing row (real or
previously derived) is never overwritten or duplicated.

Every derived row is also recorded in a JSON manifest file under
`runs/` (source period/value -> derived period, and which rule produced it)
so the provenance of every backfilled observation stays auditable without
changing the `deposit_dollarization` schema.

Usage:
    python3 scripts/backfill_frequency.py            # dry run (no DB writes)
    python3 scripts/backfill_frequency.py --apply     # actually insert rows
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

MONTHLY_RE = re.compile(r"^(\d{4})-(\d{2})$")
QUARTERLY_RE = re.compile(r"^(\d{4})-Q([1-4])$")
ANNUAL_RE = re.compile(r"^(\d{4})-Annual$")

MONTH_TO_QUARTER = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}

# Countries whose YYYY-MM-formatted periods are semi-annual cadence, not
# true monthly (confirmed by inspecting actual populated months in the DB).
SEMI_ANNUAL_MONTHLY_FORMAT_COUNTRIES = {"JPN"}


def load_rows(conn):
    rows = conn.execute(
        text("SELECT country_code, year, period, indicator, value FROM deposit_dollarization")
    ).fetchall()
    by_key = defaultdict(dict)  # (country_code, indicator) -> {period: value}
    for country_code, year, period, indicator, value in rows:
        by_key[(country_code, indicator)][period] = value
    return by_key


def classify_periods(periods: dict[str, float]) -> dict[str, dict]:
    monthly = {}   # (year, month) -> value
    quarterly = {}  # (year, quarter) -> value
    annual = set()  # years already having a real/derived annual row
    for period in periods:
        m = MONTHLY_RE.match(period)
        if m:
            monthly[(m.group(1), m.group(2))] = periods[period]
            continue
        q = QUARTERLY_RE.match(period)
        if q:
            quarterly[(q.group(1), q.group(2))] = periods[period]
            continue
        a = ANNUAL_RE.match(period)
        if a:
            annual.add(a.group(1))
    return {"monthly": monthly, "quarterly": quarterly, "annual": annual}


def derive_for_series(country_code: str, indicator: str, periods: dict[str, float]):
    """Returns a list of (derived_period, value, rule, source_period) to insert."""
    existing = set(periods.keys())
    c = classify_periods(periods)
    monthly, quarterly, annual_years = c["monthly"], c["quarterly"], c["annual"]
    out = []

    is_semi_annual_country = country_code in SEMI_ANNUAL_MONTHLY_FORMAT_COUNTRIES

    if monthly and not is_semi_annual_country:
        # monthly -> quarterly
        for (year, month), value in monthly.items():
            q = MONTH_TO_QUARTER.get(month)
            if not q:
                continue
            target = f"{year}-{q}"
            if target not in existing:
                out.append((target, value, "monthly_to_quarterly", f"{year}-{month}"))
                existing.add(target)  # avoid double-deriving within this run

        # monthly -> annual (December)
        for (year, month), value in monthly.items():
            if month != "12":
                continue
            target = f"{year}-Annual"
            if target not in existing:
                out.append((target, value, "monthly_dec_to_annual", f"{year}-12"))
                existing.add(target)
                annual_years.add(year)

    if quarterly:
        # quarterly -> annual (Q4), only for years not already given an annual value
        for (year, q), value in quarterly.items():
            if q != "4":
                continue
            if year in annual_years:
                continue
            target = f"{year}-Annual"
            if target not in existing:
                out.append((target, value, "quarterly_q4_to_annual", f"{year}-Q4"))
                existing.add(target)
                annual_years.add(year)

    if is_semi_annual_country and monthly:
        # semi_annual -> annual: use the later-in-year populated month each year
        by_year = defaultdict(list)
        for (year, month), value in monthly.items():
            by_year[year].append((month, value))
        for year, obs in by_year.items():
            if year in annual_years:
                continue
            month, value = max(obs, key=lambda t: t[0])
            target = f"{year}-Annual"
            if target not in existing:
                out.append((target, value, "semiannual_to_annual", f"{year}-{month}"))
                existing.add(target)
                annual_years.add(year)

    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write to the DB (default is dry-run)")
    parser.add_argument("--countries", help="Comma-separated ISO3 filter, for testing on a subset")
    args = parser.parse_args()

    load_dotenv()
    engine = create_engine(os.environ["SUPABASE_DB_URL"])

    country_filter = None
    if args.countries:
        country_filter = {c.strip().upper() for c in args.countries.split(",")}

    with engine.connect() as conn:
        by_key = load_rows(conn)

    all_derived = []  # (country_code, indicator, derived_period, value, rule, source_period)
    for (country_code, indicator), periods in by_key.items():
        if country_filter and country_code not in country_filter:
            continue
        for derived_period, value, rule, source_period in derive_for_series(country_code, indicator, periods):
            all_derived.append((country_code, indicator, derived_period, value, rule, source_period))

    # --- summary ---
    by_rule = defaultdict(int)
    countries_by_rule = defaultdict(set)
    for country_code, indicator, derived_period, value, rule, source_period in all_derived:
        by_rule[rule] += 1
        countries_by_rule[rule].add(country_code)

    print(f"Total derived rows: {len(all_derived)}")
    for rule in sorted(by_rule):
        print(f"  {rule}: {by_rule[rule]} rows across {len(countries_by_rule[rule])} countries")

    countries_gaining_annual = {
        c for c, ind, p, v, rule, sp in all_derived if p.endswith("-Annual")
    }
    countries_gaining_quarterly = {
        c for c, ind, p, v, rule, sp in all_derived if re.search(r"-Q[1-4]$", p)
    }
    print(f"Countries gaining >=1 derived annual row: {len(countries_gaining_annual)}")
    print(f"Countries gaining >=1 derived quarterly row: {len(countries_gaining_quarterly)}")

    # --- manifest ---
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    mode = "apply" if args.apply else "dryrun"
    manifest_path = Path(__file__).resolve().parent.parent / "runs" / f"backfill-freq-{mode}-{ts}.json"
    manifest_path.parent.mkdir(exist_ok=True)
    manifest = [
        {
            "country_code": c,
            "indicator": ind,
            "derived_period": p,
            "value": v,
            "rule": rule,
            "source_period": sp,
        }
        for c, ind, p, v, rule, sp in all_derived
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"Manifest written: {manifest_path} ({len(manifest)} entries)")

    if not args.apply:
        print("\nDry run only -- no DB changes made. Re-run with --apply to write these rows.")
        return

    now = datetime.now(timezone.utc)
    inserted = 0
    with engine.begin() as conn:
        for country_code, indicator, derived_period, value, rule, source_period in all_derived:
            year = int(derived_period[:4])
            result = conn.execute(
                text(
                    """
                    INSERT INTO deposit_dollarization (country_code, year, period, indicator, value, updated_at)
                    VALUES (:country_code, :year, :period, :indicator, :value, :updated_at)
                    ON CONFLICT (country_code, year, period, indicator) DO NOTHING
                    """
                ),
                {
                    "country_code": country_code,
                    "year": year,
                    "period": derived_period,
                    "indicator": indicator,
                    "value": value,
                    "updated_at": now,
                },
            )
            inserted += result.rowcount
    print(f"Inserted {inserted} rows into deposit_dollarization.")


if __name__ == "__main__":
    main()
