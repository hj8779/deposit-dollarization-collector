/**
 * Classifies each country's *actual stored* periods (not the declared
 * `country_metadata.frequency_bucket`, which can drift — see `period.ts`) into
 * effective annual/quarterly/monthly coverage, then counts how many countries
 * have at least one observation in each bucket. Used for the header coverage
 * summary.
 *
 * Rule: finer-grained data cascades DOWN into coarser buckets, never up.
 *   - A full calendar quarter of monthly data (all 3 months present) counts as
 *     one quarterly observation for that quarter.
 *   - A quarterly Q4 observation, or a December (YYYY-12) monthly observation,
 *     counts as one annual observation for that year.
 *   - Native "YYYY-Annual" periods count as annual directly.
 * A country whose only data is annual contributes 0 to quarterly/monthly (no
 * cascading upward) — e.g. 10 years of annual-only data does NOT count as 10
 * quarterly or 10 monthly observations, it's simply absent from those buckets.
 */

const ANNUAL_RE = /^(\d{4})-Annual$/;
const QUARTER_RE = /^(\d{4})-Q([1-4])$/;
const MONTH_RE = /^(\d{4})-(\d{2})$/;
const DAY_RE = /^(\d{4})-(\d{2})-\d{2}$/;

export interface FrequencyCoverage {
  annual: number;
  quarterly: number;
  monthly: number;
}

interface CountryPeriods {
  annualYears: Set<number>;
  quarterKeys: Set<string>; // "year-q"
  monthsByYear: Map<number, Set<number>>;
}

function emptyCountryPeriods(): CountryPeriods {
  return { annualYears: new Set(), quarterKeys: new Set(), monthsByYear: new Map() };
}

function addMonth(cp: CountryPeriods, year: number, month: number) {
  let months = cp.monthsByYear.get(year);
  if (!months) {
    months = new Set();
    cp.monthsByYear.set(year, months);
  }
  months.add(month);
}

/** Per-country effective annual/quarterly/monthly observation counts (after cascade). */
export interface CountryFrequencyCounts {
  country_code: string;
  annual: number;
  quarterly: number;
  monthly: number;
}

export function computeCountryFrequencyCounts(
  rows: { country_code: string; period: string }[],
): CountryFrequencyCounts[] {
  const byCountry = new Map<string, CountryPeriods>();

  for (const { country_code, period } of rows) {
    let cp = byCountry.get(country_code);
    if (!cp) {
      cp = emptyCountryPeriods();
      byCountry.set(country_code, cp);
    }

    const annual = ANNUAL_RE.exec(period);
    if (annual) {
      cp.annualYears.add(Number(annual[1]));
      continue;
    }
    const quarter = QUARTER_RE.exec(period);
    if (quarter) {
      cp.quarterKeys.add(`${quarter[1]}-${quarter[2]}`);
      continue;
    }
    const month = MONTH_RE.exec(period);
    if (month) {
      addMonth(cp, Number(month[1]), Number(month[2]));
      continue;
    }
    const day = DAY_RE.exec(period);
    if (day) {
      addMonth(cp, Number(day[1]), Number(day[2]));
      continue;
    }
    // Unrecognized shape ("other"): not counted in any bucket.
  }

  const out: CountryFrequencyCounts[] = [];
  for (const [country_code, cp] of byCountry) {
    // Cascade monthly -> quarterly: a calendar quarter counts if all 3 of its
    // months are present.
    const effQuarterKeys = new Set(cp.quarterKeys);
    for (const [year, months] of cp.monthsByYear) {
      for (let q = 1; q <= 4; q++) {
        const m1 = q * 3 - 2;
        const m2 = q * 3 - 1;
        const m3 = q * 3;
        if (months.has(m1) && months.has(m2) && months.has(m3)) {
          effQuarterKeys.add(`${year}-${q}`);
        }
      }
    }

    // Cascade quarterly (Q4) / monthly (December) -> annual.
    const effAnnualYears = new Set(cp.annualYears);
    for (const key of effQuarterKeys) {
      const [yearStr, qStr] = key.split("-");
      if (qStr === "4") effAnnualYears.add(Number(yearStr));
    }
    for (const [year, months] of cp.monthsByYear) {
      if (months.has(12)) effAnnualYears.add(year);
    }

    const monthlyCount = [...cp.monthsByYear.values()].reduce((sum, months) => sum + months.size, 0);

    out.push({
      country_code,
      annual: effAnnualYears.size,
      quarterly: effQuarterKeys.size,
      monthly: monthlyCount,
    });
  }

  return out;
}

/** Number of countries with at least one effective observation in each bucket. */
export function computeFrequencyCoverage(
  rows: { country_code: string; period: string }[],
): FrequencyCoverage {
  const perCountry = computeCountryFrequencyCounts(rows);
  return {
    annual: perCountry.filter((c) => c.annual > 0).length,
    quarterly: perCountry.filter((c) => c.quarterly > 0).length,
    monthly: perCountry.filter((c) => c.monthly > 0).length,
  };
}

/** Total effective observation count in each bucket, summed across all countries
 * (same cascade rule — e.g. a full year of monthly data contributes 12 to the
 * monthly total, 4 to the quarterly total, and 1 to the annual total). */
export function computeFrequencyTotals(
  rows: { country_code: string; period: string }[],
): FrequencyCoverage {
  const perCountry = computeCountryFrequencyCounts(rows);
  return perCountry.reduce(
    (acc, c) => ({
      annual: acc.annual + c.annual,
      quarterly: acc.quarterly + c.quarterly,
      monthly: acc.monthly + c.monthly,
    }),
    { annual: 0, quarterly: 0, monthly: 0 },
  );
}
