import { fetchAllPeriods } from "../lib/db";
import { computeFrequencyCoverage, computeFrequencyTotals } from "../lib/frequencyCoverage";
import { useEffectQuery } from "../lib/useEffectQuery";

export function FrequencyCoverageBar() {
  const { loading, data, error } = useEffectQuery(fetchAllPeriods, []);

  if (loading) return <div className="panel freq-coverage muted">주기별 국가 수 집계 중…</div>;
  if (error) return null;

  const rows = data ?? [];
  const coverage = computeFrequencyCoverage(rows);
  const totals = computeFrequencyTotals(rows);

  return (
    <div
      className="panel freq-coverage"
      title="더 세밀한 주기의 데이터는 더 굵은 주기로 환산되어 카운트됩니다(월별 3개월 모두 있으면 분기 1개, 분기 Q4 또는 월별 12월이 있으면 연간 1개). 반대 방향(연간→분기/월별)으로는 환산되지 않습니다."
    >
      <div className="freq-coverage-item">
        <span className="freq-coverage-count">{coverage.annual}</span>
        <span className="freq-coverage-label">
          Annual <span className="freq-coverage-sub">국가 · {totals.annual.toLocaleString()} 관측치</span>
        </span>
      </div>
      <div className="freq-coverage-item">
        <span className="freq-coverage-count">{coverage.quarterly}</span>
        <span className="freq-coverage-label">
          Quarterly <span className="freq-coverage-sub">국가 · {totals.quarterly.toLocaleString()} 관측치</span>
        </span>
      </div>
      <div className="freq-coverage-item">
        <span className="freq-coverage-count">{coverage.monthly}</span>
        <span className="freq-coverage-label">
          Monthly <span className="freq-coverage-sub">국가 · {totals.monthly.toLocaleString()} 관측치</span>
        </span>
      </div>
    </div>
  );
}
