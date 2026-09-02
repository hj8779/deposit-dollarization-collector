import {
  CartesianGrid,
  Legend,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartPoint, Indicator } from "../lib/types";
import { formatPeriodLabel } from "../lib/period";

const SERIES: Record<Indicator, { color: string; axis: "left" | "right"; label: string }> = {
  FCD: { color: "#2563eb", axis: "left", label: "FCD" },
  TD: { color: "#059669", axis: "left", label: "TD" },
  FCD_TD_RATIO: { color: "#d97706", axis: "right", label: "FCD/TD (%)" },
};

interface Props {
  points: ChartPoint[];
  visibleIndicators: Indicator[];
}

export function DepositChart({ points, visibleIndicators }: Props) {
  const showLeft = visibleIndicators.some((i) => SERIES[i].axis === "left");
  const showRight = visibleIndicators.some((i) => SERIES[i].axis === "right");

  if (points.length === 0) {
    return <div className="chart-empty">이 국가에는 표시할 데이터가 없습니다.</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={420}>
      <ComposedChart data={points} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis
          dataKey="period"
          tickFormatter={formatPeriodLabel}
          tick={{ fontSize: 12 }}
          minTickGap={24}
        />
        {showLeft && (
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 12 }}
            width={80}
            tickFormatter={(v: number) => v.toLocaleString()}
            label={{ value: "FCD / TD", angle: -90, position: "insideLeft", fontSize: 12 }}
          />
        )}
        {showRight && (
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={[0, 100]}
            tick={{ fontSize: 12 }}
            width={60}
            tickFormatter={(v: number) => `${v}%`}
            label={{ value: "FCD/TD ratio", angle: 90, position: "insideRight", fontSize: 12 }}
          />
        )}
        <Tooltip
          labelFormatter={(label) => (typeof label === "string" ? formatPeriodLabel(label) : label)}
          formatter={(value, name) => [typeof value === "number" ? value.toLocaleString() : value, name]}
        />
        <Legend />
        {visibleIndicators.map((indicator) => {
          const s = SERIES[indicator];
          return (
            <Line
              key={indicator}
              yAxisId={s.axis}
              type="monotone"
              dataKey={indicator}
              name={s.label}
              stroke={s.color}
              dot={false}
              connectNulls
              strokeWidth={2}
            />
          );
        })}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
