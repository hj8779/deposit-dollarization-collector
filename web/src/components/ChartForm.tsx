import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Effect } from "effect";
import { fetchDepositRows } from "../lib/db";
import { useEffectQuery } from "../lib/useEffectQuery";
import { toChartPoints, availableIndicators } from "../lib/chartData";
import {
  getManualInfo,
  isHalfManual,
  needsManualUpdate,
} from "../lib/manualUpdateCountries";
import { DepositChart } from "./DepositChart";
import { SourceInfo } from "./SourceInfo";
import { ManualEntryTable } from "./ManualEntryTable";
import type { CountrySummary, DepositRow, Indicator } from "../lib/types";

interface Props {
  countries: CountrySummary[];
  selectedCountry: string | null;
  onSelectCountry: (countryCode: string) => void;
}

const ALL_INDICATORS: Indicator[] = ["FCD", "TD", "FCD_TD_RATIO"];

export function ChartForm({ countries, selectedCountry, onSelectCountry }: Props) {
  const { t } = useTranslation();
  const [checkedIndicators, setCheckedIndicators] = useState<Set<Indicator>>(
    new Set(ALL_INDICATORS),
  );
  // Bumped after a manual-entry save/delete to force fetchDepositRows to re-run
  // (selectedCountry alone wouldn't change, so it wouldn't normally refetch).
  const [refetchTick, setRefetchTick] = useState(0);

  const country = selectedCountry
    ? (countries.find((c) => c.country_code === selectedCountry) ?? null)
    : null;

  const { loading, data, error } = useEffectQuery(
    selectedCountry ? fetchDepositRows(selectedCountry) : Effect.succeed<DepositRow[]>([]),
    [selectedCountry, refetchTick],
  );

  const indicatorsInData = useMemo(() => (data ? availableIndicators(data) : []), [data]);
  const points = useMemo(() => (data ? toChartPoints(data) : []), [data]);

  // Reset the indicator checkboxes to "everything this country has" whenever the
  // country changes, instead of carrying over a stale selection.
  useEffect(() => {
    if (indicatorsInData.length > 0) setCheckedIndicators(new Set(indicatorsInData));
  }, [selectedCountry, indicatorsInData.length]);

  const visibleIndicators = ALL_INDICATORS.filter(
    (i) => checkedIndicators.has(i) && indicatorsInData.includes(i),
  );

  function toggleIndicator(indicator: Indicator) {
    setCheckedIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(indicator)) next.delete(indicator);
      else next.add(indicator);
      return next;
    });
  }

  const manual = selectedCountry ? needsManualUpdate(selectedCountry) : false;
  const manualInfo = selectedCountry ? getManualInfo(selectedCountry) : null;
  const halfManual = selectedCountry ? isHalfManual(selectedCountry) : false;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>{t("chartForm.title")}</h2>
        {country?.frequency_bucket && (
          <span className="muted">{t("chartForm.frequencyLabel", { freq: country.frequency_bucket })}</span>
        )}
      </div>

      <div className="chart-controls">
        <label className="field">
          <span>{t("chartForm.countryLabel")}</span>
          <select
            value={selectedCountry ?? ""}
            onChange={(e) => onSelectCountry(e.target.value)}
          >
            <option value="" disabled>
              {t("chartForm.countrySelectPlaceholder")}
            </option>
            {countries.map((c) => (
              <option key={c.country_code} value={c.country_code}>
                {c.country_code} — {c.country_name ?? c.country_code}
              </option>
            ))}
          </select>
        </label>

        <div className="field">
          <span>{t("chartForm.indicatorLabel")}</span>
          <div className="indicator-toggles">
            {ALL_INDICATORS.map((indicator) => (
              <label key={indicator} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={checkedIndicators.has(indicator)}
                  disabled={!indicatorsInData.includes(indicator)}
                  onChange={() => toggleIndicator(indicator)}
                />
                {indicator}
              </label>
            ))}
          </div>
        </div>
      </div>

      {selectedCountry && manualInfo && (
        <div className={halfManual ? "manual-notice half-manual-notice" : "manual-notice"}>
          {halfManual ? t("chartForm.manualBadgeHalf") : t("chartForm.manualBadgeFull")} {selectedCountry}: {manualInfo.reason}
          {manualInfo.sourceUrl && (
            <>
              {" "}
              <a href={manualInfo.sourceUrl} target="_blank" rel="noreferrer">
                {t("chartForm.openSource")}
              </a>
            </>
          )}
        </div>
      )}

      {!selectedCountry && <div className="chart-empty">{t("chartForm.selectCountryEmpty")}</div>}
      {selectedCountry && loading && <div className="chart-empty">{t("chartForm.loading")}</div>}
      {selectedCountry && error && (
        <div className="panel error">{t("chartForm.errorLoading", { message: error.message })}</div>
      )}
      {selectedCountry && !loading && !error && (
        <DepositChart points={points} visibleIndicators={visibleIndicators} />
      )}

      {country && <SourceInfo country={country} />}

      {selectedCountry && manual && !loading && !error && (
        <ManualEntryTable
          countryCode={selectedCountry}
          reason={manualInfo?.reason ?? ""}
          rows={data ?? []}
          onChanged={() => setRefetchTick((t) => t + 1)}
        />
      )}
    </div>
  );
}
