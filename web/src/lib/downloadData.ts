import * as XLSX from "xlsx";
import type { ChartPoint } from "./types";

/** Row shape written to CSV/XLSX exports: one row per period, columns for
 * whichever indicators the country actually has (FCD/TD/FCD_TD_RATIO may be
 * undefined for periods that don't have that indicator). */
function toExportRows(points: ChartPoint[]) {
  return points.map((p) => ({
    period: p.period,
    FCD: p.FCD ?? "",
    TD: p.TD ?? "",
    FCD_TD_RATIO: p.FCD_TD_RATIO ?? "",
  }));
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function downloadCsv(points: ChartPoint[], countryCode: string) {
  const sheet = XLSX.utils.json_to_sheet(toExportRows(points));
  const csv = XLSX.utils.sheet_to_csv(sheet);
  triggerDownload(
    new Blob([csv], { type: "text/csv;charset=utf-8;" }),
    `${countryCode}_deposit_dollarization.csv`,
  );
}

export function downloadXlsx(points: ChartPoint[], countryCode: string) {
  const sheet = XLSX.utils.json_to_sheet(toExportRows(points));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, sheet, countryCode);
  const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
  triggerDownload(
    new Blob([buf], { type: "application/octet-stream" }),
    `${countryCode}_deposit_dollarization.xlsx`,
  );
}
