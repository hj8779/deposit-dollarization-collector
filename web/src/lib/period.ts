/**
 * Period-label helpers. We deliberately parse the *period string itself*
 * (e.g. "2020-Annual", "2020-Q1", "2020-01", "2020-01-15") rather than
 * trusting `country_metadata.frequency_bucket` alone: that field records
 * what the *source* claims to publish, which can drift from what the
 * collector actually stores (see e.g. ARG: source is "Daily" but the
 * pipeline persists monthly-aggregated periods).
 */

const ANNUAL_RE = /^(\d{4})-Annual$/;
const QUARTER_RE = /^(\d{4})-Q([1-4])$/;
const MONTH_RE = /^(\d{4})-(\d{2})$/;
const DAY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Lexically-sortable key so mixed period shapes for the same country order sensibly. */
export function periodSortKey(period: string): string {
  const annual = ANNUAL_RE.exec(period);
  if (annual) return `${annual[1]}-13`; // after Dec (12) of the same year

  const quarter = QUARTER_RE.exec(period);
  if (quarter) {
    const q = Number(quarter[2]);
    return `${quarter[1]}-${String(q * 3).padStart(2, "0")}`; // Q1->03, Q2->06 (end-of-quarter month)
  }

  return period; // "YYYY-MM" and "YYYY-MM-DD" already sort correctly as strings
}

/** Short axis-tick label, adapted to whichever shape this particular period is in. */
export function formatPeriodLabel(period: string): string {
  const annual = ANNUAL_RE.exec(period);
  if (annual) return annual[1];

  const quarter = QUARTER_RE.exec(period);
  if (quarter) return `${quarter[1]} Q${quarter[2]}`;

  const month = MONTH_RE.exec(period);
  if (month) {
    const idx = Number(month[2]) - 1;
    const name = MONTH_NAMES[idx] ?? month[2];
    return `${name} ${month[1]}`;
  }

  const day = DAY_RE.exec(period);
  if (day) return `${day[1]}-${day[2]}-${day[3]}`;

  return period;
}

export type PeriodShape = "annual" | "quarterly" | "monthly" | "daily" | "other";

export function periodShape(period: string): PeriodShape {
  if (ANNUAL_RE.test(period)) return "annual";
  if (QUARTER_RE.test(period)) return "quarterly";
  if (MONTH_RE.test(period)) return "monthly";
  if (DAY_RE.test(period)) return "daily";
  return "other";
}
