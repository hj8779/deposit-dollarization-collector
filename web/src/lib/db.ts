import { Data, Effect } from "effect";
import { supabase } from "./supabase";
import type { CountrySummary, DepositRow } from "./types";

export class DbError extends Data.TaggedError("DbError")<{
  readonly operation: string;
  readonly message: string;
}> {}

/** Supabase/PostgREST errors are plain objects (`{ message, code, ... }`), so
 * `String(cause)` on them collapses to the useless "[object Object]" instead
 * of the actual message. Prefer `.message` when present. */
function causeMessage(cause: unknown): string {
  if (cause instanceof Error) return cause.message;
  if (typeof cause === "object" && cause !== null && "message" in cause) {
    return String((cause as { message: unknown }).message);
  }
  return String(cause);
}

/** All rows of the pre-aggregated summary view, one per country. */
export const fetchCountrySummaries: Effect.Effect<CountrySummary[], DbError> =
  Effect.tryPromise({
    try: async () => {
      const { data, error } = await supabase
        .from("deposit_dollarization_summary")
        .select("*")
        .order("country_code");
      if (error) throw error;
      return data as CountrySummary[];
    },
    catch: (cause) =>
      new DbError({ operation: "fetchCountrySummaries", message: causeMessage(cause) }),
  });

/** Distinct (country_code, period) pairs across every country, from the lightweight
 * `deposit_dollarization_periods` view — used to classify each country's coverage
 * into annual/quarterly/monthly (see `frequencyCoverage.ts`). Paginated since the
 * table comfortably exceeds PostgREST's default page size. */
const PERIODS_PAGE_SIZE = 1000;

export const fetchAllPeriods: Effect.Effect<
  { country_code: string; period: string }[],
  DbError
> = Effect.tryPromise({
  try: async () => {
    const out: { country_code: string; period: string }[] = [];
    for (let from = 0; ; from += PERIODS_PAGE_SIZE) {
      const { data, error } = await supabase
        .from("deposit_dollarization_periods")
        .select("country_code, period")
        .range(from, from + PERIODS_PAGE_SIZE - 1);
      if (error) throw error;
      out.push(...(data as { country_code: string; period: string }[]));
      if (!data || data.length < PERIODS_PAGE_SIZE) break;
    }
    return out;
  },
  catch: (cause) => new DbError({ operation: "fetchAllPeriods", message: causeMessage(cause) }),
});

/** Raw FCD/TD/FCD_TD_RATIO rows for one country, sorted by period. */
export const fetchDepositRows = (
  countryCode: string,
): Effect.Effect<DepositRow[], DbError> =>
  Effect.tryPromise({
    try: async () => {
      const { data, error } = await supabase
        .from("deposit_dollarization")
        .select("country_code, year, period, indicator, value, updated_at")
        .eq("country_code", countryCode)
        .order("period", { ascending: true });
      if (error) throw error;
      return data as DepositRow[];
    },
    catch: (cause) =>
      new DbError({ operation: "fetchDepositRows", message: causeMessage(cause) }),
  });

/** Upserts one (country_code, year, period, indicator) row — the table's primary
 * key — for manual data entry. RLS on the DB side additionally restricts which
 * country codes this is allowed for (see MANUAL_UPDATE_COUNTRIES). */
export const upsertDepositRow = (row: DepositRow): Effect.Effect<void, DbError> =>
  Effect.tryPromise({
    try: async () => {
      const { error } = await supabase
        .from("deposit_dollarization")
        .upsert(row, { onConflict: "country_code,year,period,indicator" });
      if (error) throw error;
    },
    catch: (cause) => new DbError({ operation: "upsertDepositRow", message: causeMessage(cause) }),
  });

/** Upserts many rows in one round trip (e.g. a parsed EVDS export). Same
 * conflict target/RLS scoping as `upsertDepositRow`. */
export const upsertDepositRows = (rows: DepositRow[]): Effect.Effect<void, DbError> =>
  Effect.tryPromise({
    try: async () => {
      if (rows.length === 0) return;
      const { error } = await supabase
        .from("deposit_dollarization")
        .upsert(rows, { onConflict: "country_code,year,period,indicator" });
      if (error) throw error;
    },
    catch: (cause) => new DbError({ operation: "upsertDepositRows", message: causeMessage(cause) }),
  });

export const deleteDepositRow = (
  row: Pick<DepositRow, "country_code" | "period" | "indicator">,
): Effect.Effect<void, DbError> =>
  Effect.tryPromise({
    try: async () => {
      const { error } = await supabase
        .from("deposit_dollarization")
        .delete()
        .eq("country_code", row.country_code)
        .eq("period", row.period)
        .eq("indicator", row.indicator);
      if (error) throw error;
    },
    catch: (cause) => new DbError({ operation: "deleteDepositRow", message: causeMessage(cause) }),
  });
