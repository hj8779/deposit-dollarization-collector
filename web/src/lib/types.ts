export type FrequencyBucket =
  | "annual"
  | "semi_annual"
  | "quarterly"
  | "monthly"
  | "higher"
  | "unknown"
  | "other";

export type Indicator = "FCD" | "TD" | "FCD_TD_RATIO";

/** One row of the pre-aggregated `deposit_dollarization_summary` view. */
export interface CountrySummary {
  country_code: string;
  country_name: string | null;
  rows: number;
  periods: number;
  min_period: string | null;
  max_period: string | null;
  indicators: string; // comma-joined, e.g. "FCD,TD"
  last_updated: string | null;
  update_frequency: string | null;
  frequency_bucket: FrequencyBucket | null;
  source_url: string | null;
  notes: string | null;
  adapter_notes: string | null;
  adapter_status: string | null;
  data_type: string | null;
}

/** One row of the raw `deposit_dollarization` table. */
export interface DepositRow {
  country_code: string;
  year: number;
  period: string;
  indicator: Indicator;
  value: number;
  updated_at: string;
}

/** A single point ready for the chart, pivoted so each indicator is its own field. */
export interface ChartPoint {
  period: string;
  sortKey: string;
  FCD?: number;
  TD?: number;
  FCD_TD_RATIO?: number;
}
