import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchAllPeriods, fetchCountrySummaries } from "../lib/db";
import { useEffectQuery } from "../lib/useEffectQuery";
import { computeCountryFrequencyTags } from "../lib/frequencyCoverage";
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

// Finest-to-coarsest, matching the annual ⊂ quarterly ⊂ monthly ⊂ higher
// ladder — used both for filter-button ordering and for the "Freq" column
// sort (a country's rank = its finest available tag).
const FREQUENCY_ORDER: FrequencyBucket[] = [
  "higher",
  "monthly",
  "quarterly",
  "semi_annual",
  "annual",
  "other",
  "unknown",
];
const FREQUENCY_RANK: Record<FrequencyBucket, number> = Object.fromEntries(
  FREQUENCY_ORDER.map((f, i) => [f, i]),
) as Record<FrequencyBucket, number>;

function finestTag(tags: Set<FrequencyBucket> | undefined): FrequencyBucket {
  if (!tags || tags.size === 0) return "unknown";
  let best: FrequencyBucket = "unknown";
  let bestRank = Infinity;
  for (const tag of tags) {
    const rank = FREQUENCY_RANK[tag];
    if (rank < bestRank) {
      bestRank = rank;
      best = tag;
    }
  }
  return best;
}

type SortKey =
  | "country_code"
  | "rows"
  | "periods"
  | "min_period"
  | "max_period"
  | "frequency_bucket"
  | "manual";

export function DbSummaryTable({ selectedCountry, onSelectCountry }: Props) {
  const { t } = useTranslation();
  const { loading, data, error } = useEffectQuery(fetchCountrySummaries, []);
  const { data: periods } = useEffectQuery(fetchAllPeriods, []);
  // Default to the flag column, flagged countries on top, so the list opens
  // with exactly what needs manual attention front and center.
  const [sortKey, setSortKey] = useState<SortKey>("manual");
  const [sortDir, setSortDir] = useState<1 | -1>(1);
  const [filter, setFilter] = useState("");
  const [selectedFreqs, setSelectedFreqs] = useState<Set<FrequencyBucket>>(
    () => new Set(),
  );

  // Per-country set of every frequency a country's *actual* data supports
  // (annual ⊂ quarterly ⊂ monthly ⊂ higher cascade — see frequencyCoverage.ts),
  // not just its single declared `frequency_bucket`.
  const tagsByCountry = useMemo(() => {
    const declared = new Map((data ?? []).map((c) => [c.country_code, c.frequency_bucket]));
    return computeCountryFrequencyTags(periods ?? [], declared);
  }, [data, periods]);

  const availableFreqs = useMemo(() => {
    const present = new Set<FrequencyBucket>();
    for (const tags of tagsByCountry.values()) {
      for (const tag of tags) present.add(tag);
    }
    return FREQUENCY_ORDER.filter((f) => present.has(f));
  }, [tagsByCountry]);

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
      filtered = filtered.filter((c) => {
        const tags = tagsByCountry.get(c.country_code);
        if (!tags || tags.size === 0) return selectedFreqs.has("unknown");
        for (const tag of tags) {
          if (selectedFreqs.has(tag)) return true;
        }
        return false;
      });
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
      if (sortKey === "frequency_bucket") {
        const av = FREQUENCY_RANK[finestTag(tagsByCountry.get(a.country_code))];
        const bv = FREQUENCY_RANK[finestTag(tagsByCountry.get(b.country_code))];
        if (av !== bv) return (av - bv) * sortDir;
        return a.country_code < b.country_code ? -1 : a.country_code > b.country_code ? 1 : 0;
      }
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    });
  }, [data, filter, selectedFreqs, sortKey, sortDir, tagsByCountry]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 1 ? -1 : 1));
    } else {
      setSortKey(key);
      setSortDir(1);
    }
  }

  if (loading) return <div className="panel">{t("dbSummary.loading")}</div>;
  if (error) {
    return (
      <div className="panel error">
        {t("dbSummary.errorLoading", { message: error.message })}
      </div>
    );
  }

  const manualCount = (data ?? []).filter((c) => needsManualUpdate(c.country_code)).length;
  const halfManualCount = (data ?? []).filter((c) => isHalfManual(c.country_code)).length;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>{t("dbSummary.title")}</h2>
        <span className="muted">
          {t("dbSummary.summary", {
            count: data?.length ?? 0,
            manual: manualCount - halfManualCount,
            half: halfManualCount,
          })}
        </span>
      </div>

      <input
        className="filter-input"
        placeholder={t("dbSummary.filterPlaceholder")}
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
            {t("dbSummary.clear")}
          </button>
        ) : null}
      </div>

      <div className="table-scroll">
        <table className="summary-table">
          <thead>
            <tr>
              <Th label="CC" onClick={() => toggleSort("country_code")} active={sortKey === "country_code"} dir={sortDir} />
              <th>{t("dbSummary.countryColumn")}</th>
              <Th label="Rows" onClick={() => toggleSort("rows")} active={sortKey === "rows"} dir={sortDir} />
              <Th label="Periods" onClick={() => toggleSort("periods")} active={sortKey === "periods"} dir={sortDir} />
              <Th label="Min" onClick={() => toggleSort("min_period")} active={sortKey === "min_period"} dir={sortDir} />
              <Th label="Max" onClick={() => toggleSort("max_period")} active={sortKey === "max_period"} dir={sortDir} />
              <Th label="Freq" onClick={() => toggleSort("frequency_bucket")} active={sortKey === "frequency_bucket"} dir={sortDir} />
              <th>{t("dbSummary.indicatorsColumn")}</th>
              <Th
                label="⚠"
                onClick={() => toggleSort("manual")}
                active={sortKey === "manual"}
                dir={sortDir}
                title={t("dbSummary.warnColumnTitle")}
              />
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <SummaryRow
                key={c.country_code}
                country={c}
                tags={tagsByCountry.get(c.country_code)}
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
  tags,
  selected,
  onSelect,
}: {
  country: CountrySummary;
  tags: Set<FrequencyBucket> | undefined;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  const info = getManualInfo(country.country_code);
  const half = info?.kind === "half_manual";
  const dash = t("dbSummary.dash");
  const sortedTags = FREQUENCY_ORDER.filter((f) => tags?.has(f));
  return (
    <tr
      className={`summary-row${selected ? " selected" : ""}${info ? " manual" : ""}${half ? " half-manual" : ""}`}
      onClick={onSelect}
    >
      <td className="mono">{country.country_code}</td>
      <td>{country.country_name ?? dash}</td>
      <td className="num">{country.rows.toLocaleString()}</td>
      <td className="num">{country.periods.toLocaleString()}</td>
      <td className="mono">{country.min_period ?? dash}</td>
      <td className="mono">{country.max_period ?? dash}</td>
      <td>
        {sortedTags.length > 0 ? (
          <span className="freq-badge-group">
            {sortedTags.map((tag) => (
              <span key={tag} className={`badge freq-${tag}`}>
                {tag}
              </span>
            ))}
          </span>
        ) : (
          <span className="badge freq-unknown">unknown</span>
        )}
      </td>
      <td className="mono small">{country.indicators || dash}</td>
      <td>
        {info ? (
          <span
            className={`badge ${half ? "half-manual-badge" : "manual-badge"}`}
            title={info.reason}
          >
            {half ? t("dbSummary.manualBadgeHalf") : t("dbSummary.manualBadgeFull")}
          </span>
        ) : null}
      </td>
    </tr>
  );
}
