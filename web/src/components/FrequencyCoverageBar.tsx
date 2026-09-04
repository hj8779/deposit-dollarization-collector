import { useTranslation } from "react-i18next";
import { fetchAllPeriods } from "../lib/db";
import { computeFrequencyCoverage, computeFrequencyTotals } from "../lib/frequencyCoverage";
import { useEffectQuery } from "../lib/useEffectQuery";

export function FrequencyCoverageBar() {
  const { t } = useTranslation();
  const { loading, data, error } = useEffectQuery(fetchAllPeriods, []);

  if (loading) return <div className="panel freq-coverage muted">{t("freqCoverage.loading")}</div>;
  if (error) return null;

  const rows = data ?? [];
  const coverage = computeFrequencyCoverage(rows);
  const totals = computeFrequencyTotals(rows);

  return (
    <div
      className="panel freq-coverage"
      title={t("freqCoverage.tooltip")}
    >
      <div className="freq-coverage-item">
        <span className="freq-coverage-count">{coverage.annual}</span>
        <span className="freq-coverage-label">
          {t("freqCoverage.annual")}{" "}
          <span className="freq-coverage-sub">{t("freqCoverage.sub", { count: totals.annual.toLocaleString() })}</span>
        </span>
      </div>
      <div className="freq-coverage-item">
        <span className="freq-coverage-count">{coverage.quarterly}</span>
        <span className="freq-coverage-label">
          {t("freqCoverage.quarterly")}{" "}
          <span className="freq-coverage-sub">{t("freqCoverage.sub", { count: totals.quarterly.toLocaleString() })}</span>
        </span>
      </div>
      <div className="freq-coverage-item">
        <span className="freq-coverage-count">{coverage.monthly}</span>
        <span className="freq-coverage-label">
          {t("freqCoverage.monthly")}{" "}
          <span className="freq-coverage-sub">{t("freqCoverage.sub", { count: totals.monthly.toLocaleString() })}</span>
        </span>
      </div>
    </div>
  );
}
