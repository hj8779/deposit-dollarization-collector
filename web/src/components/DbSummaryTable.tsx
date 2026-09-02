import { useMemo, useState } from "react";
import { fetchCountrySummaries } from "../lib/db";
import { useEffectQuery } from "../lib/useEffectQuery";
import {
  getManualInfo,
  isHalfManual,
  needsManualUpdate,
} from "../lib/manualUpdateCountries";
import type { CountrySummary, FrequencyBucket } from "../lib/types";

interface Props {
  selectedCountry: string | null;
  onSelectCountry: (countryCode: string) => void;
}

const FREQUENCY_ORDER: FrequencyBucket[] = [
  "monthly",
  "quarterly",
  "semi_annual",
  "annual",
  "higher",
  "other",
  "unknown",
];

type SortKey =
  | "country_code"
  | "rows"
  | "periods"
  | "min_period"
  | "max_period"
  | "frequency_bucket"
  | "manual";

export function DbSummaryTable({ selectedCountry, onSelectCountry }: Props) {
  const { loading, data, error } = useEffectQuery(fetchCountrySummaries, []);
  // Default to the flag column, flagged countries on top, so the list opens
  // with exactly what needs manual attention front and center.
  const [sortKey, setSortKey] = useState<SortKey>("manual");
  const [sortDir, setSortDir] = useState<1 | -1>(1);
  const [filter, setFilter] = useState("");
  const [selectedFreqs, setSelectedFreqs] = useState<Set<FrequencyBucket>>(
    () => new Set(),
  );

  const availableFreqs = useMemo(() => {
    const present = new Set((data ?? []).map((c) => c.frequency_bucket ?? "unknown"));
    return FREQUENCY_ORDER.filter((f) => present.has(f));
  }, [data]);

  function toggleFreq(freq: FrequencyBucket) {
    setSelectedFreqs((prev) => {
      const next = new Set(prev);
      if (next.has(freq)) next.delete(freq);
      else next.add(freq);
      return next;
    });
  }

  const rows = useMemo(() => {
    if (!data) return [];
    let filtered = filter
      ? data.filter(
          (c) =>
            c.country_code.toLowerCase().includes(filter.toLowerCase()) ||
            (c.country_name ?? "").toLowerCase().includes(filter.toLowerCase()),
        )
      : data;
    if (selectedFreqs.size > 0) {
      filtered = filtered.filter((c) =>
        selectedFreqs.has((c.frequency_bucket ?? "unknown") as FrequencyBucket),
      );
    }
    return [...filtered].sort((a, b) => {
      if (sortKey === "manual") {
        // Flagged countries first on the "ascending" click (dir=1), matching
        // how a user reads "sort by flag" — not literal false<true ordering.
        const av = needsManualUpdate(a.country_code) ? 0 : 1;
        const bv = needsManualUpdate(b.country_code) ? 0 : 1;
        if (av !== bv) return (av - bv) * sortDir;
        return a.country_code < b.country_code ? -1 : a.country_code > b.country_code ? 1 : 0;
      }
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    });
  }, [data, filter, selectedFreqs, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 1 ? -1 : 1));
    } else {
      setSortKey(key);
      setSortDir(1);
    }
  }

  if (loading) return <div className="panel">DB 요약 불러오는 중…</div>;
  if (error) {
    return (
      <div className="panel error">
        DB 요약을 불러오지 못했습니다: {error.message}
      </div>
    );
  }

  const manualCount = (data ?? []).filter((c) => needsManualUpdate(c.country_code)).length;
  const halfManualCount = (data ?? []).filter((c) => isHalfManual(c.country_code)).length;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>DB Summary</h2>
        <span className="muted">
          {data?.length ?? 0}개국 · 수동 {manualCount - halfManualCount} · 하프매뉴얼{" "}
          {halfManualCount}
        </span>
      </div>

      <input
        className="filter-input"
        placeholder="국가 코드/이름 검색…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      <div className="freq-tags">
        {availableFreqs.map((freq) => (
          <button
            key={freq}
            type="button"
            className={`freq-tag freq-${freq}${selectedFreqs.has(freq) ? " active" : ""}`}
            onClick={() => toggleFreq(freq)}
          >
            {freq}
          </button>
        ))}
        {selectedFreqs.size > 0 ? (
          <button
            type="button"
            className="freq-tag freq-clear"
            onClick={() => setSelectedFreqs(new Set())}
          >
            초기화
          </button>
        ) : null}
      </div>

      <div className="table-scroll">
        <table className="summary-table">
          <thead>
            <tr>
              <Th label="CC" onClick={() => toggleSort("country_code")} active={sortKey === "country_code"} dir={sortDir} />
              <th>Country</th>
              <Th label="Rows" onClick={() => toggleSort("rows")} active={sortKey === "rows"} dir={sortDir} />
              <Th label="Periods" onClick={() => toggleSort("periods")} active={sortKey === "periods"} dir={sortDir} />
              <Th label="Min" onClick={() => toggleSort("min_period")} active={sortKey === "min_period"} dir={sortDir} />
              <Th label="Max" onClick={() => toggleSort("max_period")} active={sortKey === "max_period"} dir={sortDir} />
              <Th label="Freq" onClick={() => toggleSort("frequency_bucket")} active={sortKey === "frequency_bucket"} dir={sortDir} />
              <th>Indicators</th>
              <Th
                label="⚠"
                onClick={() => toggleSort("manual")}
                active={sortKey === "manual"}
                dir={sortDir}
                title="소스 자체 차단/부재로 자동 수집이 불완전한 국가. 클릭하면 이 국가들을 위로 정렬합니다."
              />
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <SummaryRow
                key={c.country_code}
                country={c}
                selected={c.country_code === selectedCountry}
                onSelect={() => onSelectCountry(c.country_code)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Th({
  label,
  onClick,
  active,
  dir,
  title,
}: {
  label: string;
  onClick: () => void;
  active: boolean;
  dir: 1 | -1;
  title?: string;
}) {
  return (
    <th className="sortable" onClick={onClick} title={title}>
      {label}
      {active ? (dir === 1 ? " ▲" : " ▼") : ""}
    </th>
  );
}

function SummaryRow({
  country,
  selected,
  onSelect,
}: {
  country: CountrySummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const info = getManualInfo(country.country_code);
  const half = info?.kind === "half_manual";
  return (
    <tr
      className={`summary-row${selected ? " selected" : ""}${info ? " manual" : ""}${half ? " half-manual" : ""}`}
      onClick={onSelect}
    >
      <td className="mono">{country.country_code}</td>
      <td>{country.country_name ?? "—"}</td>
      <td className="num">{country.rows.toLocaleString()}</td>
      <td className="num">{country.periods.toLocaleString()}</td>
      <td className="mono">{country.min_period ?? "—"}</td>
      <td className="mono">{country.max_period ?? "—"}</td>
      <td>
        <span className={`badge freq-${country.frequency_bucket ?? "unknown"}`}>
          {country.frequency_bucket ?? "unknown"}
        </span>
      </td>
      <td className="mono small">{country.indicators || "—"}</td>
      <td>
        {info ? (
          <span
            className={`badge ${half ? "half-manual-badge" : "manual-badge"}`}
            title={info.reason}
          >
            {half ? "◐ 하프" : "⚠ 수동"}
          </span>
        ) : null}
      </td>
    </tr>
  );
}
