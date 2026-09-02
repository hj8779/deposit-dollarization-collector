import type { ChartPoint, DepositRow, Indicator } from "./types";
import { periodSortKey } from "./period";

/** Pivots long-form rows (one row per period+indicator) into one point per period. */
export function toChartPoints(rows: DepositRow[]): ChartPoint[] {
  const byPeriod = new Map<string, ChartPoint>();

  for (const row of rows) {
    const existing = byPeriod.get(row.period);
    const point: ChartPoint = existing ?? {
      period: row.period,
      sortKey: periodSortKey(row.period),
    };
    point[row.indicator] = row.value;
    byPeriod.set(row.period, point);
  }

  return [...byPeriod.values()].sort((a, b) => (a.sortKey < b.sortKey ? -1 : a.sortKey > b.sortKey ? 1 : 0));
}

export function availableIndicators(rows: DepositRow[]): Indicator[] {
  const set = new Set<Indicator>();
  for (const row of rows) set.add(row.indicator);
  return (["FCD", "TD", "FCD_TD_RATIO"] as const).filter((i) => set.has(i));
}
