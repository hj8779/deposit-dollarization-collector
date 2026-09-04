import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Effect } from "effect";
import { deleteDepositRow, upsertDepositRow, upsertDepositRows } from "../lib/db";
import { parseEvdsWorkbook } from "../lib/evdsImport";
import { parseLvaWorkbook } from "../lib/lvaImport";
import type { DepositRow, Indicator } from "../lib/types";

interface Props {
  countryCode: string;
  reason: string;
  rows: DepositRow[];
  /** Called after a successful save/delete so the parent can refetch the chart data. */
  onChanged: () => void;
}

interface EditableRow {
  key: string; // stable React key, independent of period/indicator edits
  period: string;
  indicator: Indicator;
  value: string; // kept as text while editing so "12." / "-" don't get clobbered
  saving: boolean;
  error: string | null;
  dirty: boolean;
  persisted: boolean; // true once it exists in the DB (so Delete has something to remove)
}

const INDICATORS: Indicator[] = ["FCD", "TD", "FCD_TD_RATIO"];
const PERIOD_RE = /^\d{4}(-Annual|-Q[1-4]|-\d{2}|-\d{2}-\d{2})$/;

let keyCounter = 0;
const nextKey = () => `new-${++keyCounter}`;

function fromDepositRow(row: DepositRow): EditableRow {
  return {
    key: `${row.period}::${row.indicator}`,
    period: row.period,
    indicator: row.indicator,
    value: String(row.value),
    saving: false,
    error: null,
    dirty: false,
    persisted: true,
  };
}

export function ManualEntryTable({ countryCode, reason, rows, onChanged }: Props) {
  const { t } = useTranslation();
  const [editable, setEditable] = useState<EditableRow[]>(() => rows.map(fromDepositRow));
  const [importState, setImportState] = useState<
    { status: "idle" } | { status: "busy" } | { status: "error"; message: string } | { status: "done"; summary: string }
  >({ status: "idle" });
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleImportFile(file: File) {
    setImportState({ status: "busy" });
    try {
      let rowsToUpsert: DepositRow[];
      let summary: string;
      if (countryCode === "TUR") {
        const result = await parseEvdsWorkbook(file, countryCode);
        rowsToUpsert = result.rows;
        summary = t("manualEntry.importSummaryEvds", {
          count: result.periodCount,
          fcd: result.fcdColumnHeader,
          td: result.tdColumnHeader,
        });
      } else if (countryCode === "LVA") {
        const result = await parseLvaWorkbook(file, countryCode);
        rowsToUpsert = result.rows;
        summary = t("manualEntry.importSummaryLva", { count: result.periodCount });
      } else {
        throw new Error(t("manualEntry.noParserError", { code: countryCode }));
      }

      const upsertResult = await Effect.runPromise(Effect.either(upsertDepositRows(rowsToUpsert)));
      if (upsertResult._tag === "Left") {
        setImportState({ status: "error", message: upsertResult.left.message });
        return;
      }
      setImportState({ status: "done", summary });
      onChanged();
    } catch (e) {
      setImportState({ status: "error", message: e instanceof Error ? e.message : String(e) });
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  // Re-sync from fresh server data whenever the parent refetches (e.g. after a
  // save elsewhere), but only for rows the user isn't actively mid-edit on.
  useEffect(() => {
    setEditable((prev) => {
      const dirtyByKey = new Map(prev.filter((r) => r.dirty).map((r) => [r.key, r]));
      const fresh = rows.map(fromDepositRow);
      const freshKeys = new Set(fresh.map((r) => r.key));
      const stillDirtyNew = prev.filter((r) => r.dirty && !r.persisted && !freshKeys.has(r.key));
      return [...fresh.map((r) => dirtyByKey.get(r.key) ?? r), ...stillDirtyNew];
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  function addRow() {
    setEditable((prev) => [
      ...prev,
      {
        key: nextKey(),
        period: "",
        indicator: "FCD",
        value: "",
        saving: false,
        error: null,
        dirty: true,
        persisted: false,
      },
    ]);
  }

  function update(key: string, patch: Partial<EditableRow>) {
    setEditable((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch, dirty: true } : r)));
  }

  async function save(row: EditableRow) {
    if (!PERIOD_RE.test(row.period)) {
      update(row.key, { error: t("manualEntry.periodInvalid") });
      return;
    }
    const value = Number(row.value);
    if (!Number.isFinite(value)) {
      update(row.key, { error: t("manualEntry.notANumber") });
      return;
    }

    update(row.key, { saving: true, error: null });
    const year = Number(row.period.slice(0, 4));
    const depositRow: DepositRow = {
      country_code: countryCode,
      year,
      period: row.period,
      indicator: row.indicator,
      value,
      updated_at: new Date().toISOString(),
    };

    const result = await Effect.runPromise(Effect.either(upsertDepositRow(depositRow)));
    if (result._tag === "Left") {
      update(row.key, { saving: false, error: result.left.message });
      return;
    }
    setEditable((prev) =>
      prev.map((r) => (r.key === row.key ? { ...r, saving: false, dirty: false, persisted: true } : r)),
    );
    onChanged();
  }

  async function remove(row: EditableRow) {
    if (!row.persisted) {
      setEditable((prev) => prev.filter((r) => r.key !== row.key));
      return;
    }
    update(row.key, { saving: true, error: null });
    const result = await Effect.runPromise(
      Effect.either(deleteDepositRow({ country_code: countryCode, period: row.period, indicator: row.indicator })),
    );
    if (result._tag === "Left") {
      update(row.key, { saving: false, error: result.left.message });
      return;
    }
    setEditable((prev) => prev.filter((r) => r.key !== row.key));
    onChanged();
  }

  return (
    <div className="manual-entry">
      <div className="panel-header">
        <h3>{t("manualEntry.title", { code: countryCode })}</h3>
        <span className="muted">{reason}</span>
      </div>

      {(countryCode === "TUR" || countryCode === "LVA") && (
        <div className="evds-import">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls"
            disabled={importState.status === "busy"}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleImportFile(file);
            }}
          />
          <span className="muted">
            {countryCode === "TUR" ? t("manualEntry.evdsHint") : t("manualEntry.lvaHint")}
          </span>
          {importState.status === "busy" && <span className="muted"> {t("manualEntry.busy")}</span>}
          {importState.status === "error" && <span className="manual-row-error"> {importState.message}</span>}
          {importState.status === "done" && (
            <span className="muted"> {t("manualEntry.importDone", { summary: importState.summary })}</span>
          )}
        </div>
      )}

      <table className="manual-table">
        <thead>
          <tr>
            <th>{t("manualEntry.periodHeader")}</th>
            <th>{t("manualEntry.indicatorHeader")}</th>
            <th>{t("manualEntry.valueHeader")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {editable.map((row) => (
            <tr key={row.key}>
              <td>
                <input
                  className="mono"
                  placeholder="2024-01"
                  value={row.period}
                  onChange={(e) => update(row.key, { period: e.target.value.trim() })}
                />
              </td>
              <td>
                <select
                  value={row.indicator}
                  onChange={(e) => update(row.key, { indicator: e.target.value as Indicator })}
                >
                  {INDICATORS.map((i) => (
                    <option key={i} value={i}>
                      {i}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  className="mono num-input"
                  placeholder="0.00"
                  value={row.value}
                  onChange={(e) => update(row.key, { value: e.target.value })}
                />
              </td>
              <td className="manual-row-actions">
                <button
                  type="button"
                  className="btn-small"
                  disabled={row.saving || !row.dirty}
                  onClick={() => save(row)}
                >
                  {row.saving ? t("manualEntry.saving") : t("manualEntry.save")}
                </button>
                <button type="button" className="btn-small btn-danger" disabled={row.saving} onClick={() => remove(row)}>
                  {t("manualEntry.delete")}
                </button>
                {row.error && <span className="manual-row-error">{row.error}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <button type="button" className="btn-small" onClick={addRow}>
        {t("manualEntry.addRow")}
      </button>
    </div>
  );
}
