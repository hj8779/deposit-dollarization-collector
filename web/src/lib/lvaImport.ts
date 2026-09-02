import * as XLSX from "xlsx";
import type { DepositRow } from "./types";

/**
 * Parses Latvijas Banka statdb.bank.lv exports (statdb.bank.lv/lb/Data.aspx?id=243)
 * for Latvia's deposit series. Two different pre-built tables are supported, auto-
 * detected by structure since they lay out currency breakdown completely differently:
 *
 * A) "0104 Balance sheet in breakdown by currency" (2014-12~present). Column A marks
 *    two stacked blocks top-to-bottom: "Euro (total)" then "Foreign currency (total)"
 *    — we track whichever block we're in as we scan down. Within each block, the row
 *    where "Item" (~column G) equals exactly "DEPOSITS (total)" (not the bare
 *    "DEPOSITS" sub-rows, which are a per-sector breakdown) is the total-deposits row
 *    for that currency. FCD = that row in the FC block; TD = FCD + the same row in
 *    the Euro block.
 *
 * B) "04 Balance sheet of MFIs (except the Bank of Latvia) (data until December 2014)"
 *    — an older archived table (2010-06~2014-11) with a totally different currency
 *    layout: "DEPOSITS (total)" is a single un-split row (already TD directly), and
 *    currency only appears as a per-sector-leaf attribute in a "Currency breakdown"
 *    column below it (one row per sector × Euro/Foreign currency, e.g. "Central
 *    government" + "Euro", then "Central government" + "Foreign currency"). So here
 *    FCD has to be reconstructed by summing every "Foreign currency"-tagged leaf row
 *    between the "DEPOSITS (total)" row and the next top-level item (verified against
 *    the file directly: summed FC leaf rows + summed Euro leaf rows == the "DEPOSITS
 *    (total)" row's own value, exactly).
 *
 * Both variants give every period its own column (unlike the older "0103 breakdown by
 * residency" table, which only fully populates the single currently-selected period —
 * that variant is no longer used here because it could only ever yield one observation
 * per export). Neither variant has a residency dimension, so FCD/TD cover ALL
 * depositors (resident + non-resident), not "residents only".
 */

export interface LvaImportResult {
  rows: DepositRow[];
  periodCount: number;
}

function normalize(s: unknown): string {
  return String(s ?? "").trim().toLowerCase();
}

const EURO_BLOCK_LABEL = "euro (total)";
const FC_BLOCK_LABEL = "foreign currency (total)";
const DEPOSITS_TOTAL_LABEL = "deposits (total)";
const FOREIGN_CURRENCY_LABEL = "foreign currency";
const PERIOD_RE = /^(\d{1,2})\s*\/\s*(\d{4})$/;
const ITEM_COL_A = 6; // 0-indexed column G, format A
const BREAKDOWN_COL_A = 7; // 0-indexed column H, format A

function findPeriodColumns(grid: unknown[][]): { headerRow: number; periodCols: { col: number; period: string }[] } {
  for (let r = 0; r < Math.min(grid.length, 15); r++) {
    const row = grid[r] ?? [];
    const found: { col: number; period: string }[] = [];
    for (let c = 0; c < row.length; c++) {
      const s = String(row[c] ?? "").trim();
      const m = s.match(PERIOD_RE);
      if (m) found.push({ col: c, period: `${m[2]}-${m[1].padStart(2, "0")}` });
    }
    if (found.length >= 2) return { headerRow: r, periodCols: found };
  }
  return { headerRow: -1, periodCols: [] };
}

/** Format A: "0104 breakdown by currency" — stacked Euro/Foreign-currency blocks. */
function findFormatARows(grid: unknown[][], headerRow: number): { eurosRow: number; fcRow: number } {
  let eurosRow = -1;
  let fcRow = -1;
  let currentBlock: "eur" | "fc" | null = null;
  for (let r = headerRow + 1; r < grid.length; r++) {
    const row = grid[r] ?? [];
    const blockLabel = normalize(row[0]);
    if (blockLabel === EURO_BLOCK_LABEL) currentBlock = "eur";
    else if (blockLabel === FC_BLOCK_LABEL) currentBlock = "fc";

    if (
      normalize(row[ITEM_COL_A]) === DEPOSITS_TOTAL_LABEL &&
      (row[BREAKDOWN_COL_A] === undefined || row[BREAKDOWN_COL_A] === null || row[BREAKDOWN_COL_A] === "")
    ) {
      if (currentBlock === "eur" && eurosRow < 0) eurosRow = r;
      else if (currentBlock === "fc" && fcRow < 0) fcRow = r;
    }
    if (eurosRow >= 0 && fcRow >= 0) break;
  }
  return { eurosRow, fcRow };
}

/** Format B: "04 Balance sheet of MFIs" archive — un-split total + per-sector currency leaf rows. */
function findFormatBRows(grid: unknown[][], headerRow: number): { depositsRow: number; fcLeafRows: number[] } {
  let depositsRow = -1;
  let itemCol = -1;
  for (let r = headerRow + 1; r < grid.length; r++) {
    const row = grid[r] ?? [];
    for (let c = 0; c < Math.min(row.length, 10); c++) {
      if (normalize(row[c]) === DEPOSITS_TOTAL_LABEL) {
        depositsRow = r;
        itemCol = c;
        break;
      }
    }
    if (depositsRow >= 0) break;
  }
  if (depositsRow < 0 || itemCol < 0) return { depositsRow: -1, fcLeafRows: [] };

  // The row right after "X (total)" typically repeats the bare name "X" as a
  // continuation header for its own breakdown (not a new item) — skip exactly one
  // such row. The section then ends at the next row where the same "Item" column
  // is non-empty again.
  const bareLabel = normalize((grid[depositsRow] ?? [])[itemCol]).replace(/\s*\(total\)\s*$/, "").trim();
  let sectionEnd = grid.length;
  let skippedContinuation = false;
  for (let r = depositsRow + 1; r < grid.length; r++) {
    const v = (grid[r] ?? [])[itemCol];
    if (v !== undefined && v !== null && v !== "") {
      if (!skippedContinuation && normalize(v) === bareLabel) {
        skippedContinuation = true;
        continue;
      }
      sectionEnd = r;
      break;
    }
  }

  const fcLeafRows: number[] = [];
  for (let r = depositsRow + 1; r < sectionEnd; r++) {
    const row = grid[r] ?? [];
    for (let c = 0; c < row.length; c++) {
      if (normalize(row[c]) === FOREIGN_CURRENCY_LABEL) {
        fcLeafRows.push(r);
        break;
      }
    }
  }
  return { depositsRow, fcLeafRows };
}

export async function parseLvaWorkbook(
  file: File,
  countryCode: string,
): Promise<LvaImportResult> {
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf, { type: "array", cellDates: false });
  const sheet = wb.Sheets[wb.SheetNames[0]];
  const grid: unknown[][] = XLSX.utils.sheet_to_json(sheet, { header: 1, raw: true });

  if (grid.length < 10) {
    throw new Error("빈 시트이거나 행이 너무 적습니다");
  }

  const { headerRow, periodCols } = findPeriodColumns(grid);
  if (headerRow < 0 || periodCols.length === 0) {
    throw new Error("기간 헤더 행('MM / YYYY' 여러 개)을 찾지 못했습니다");
  }

  const now = new Date().toISOString();
  const rows: DepositRow[] = [];
  let periodCount = 0;

  const { eurosRow, fcRow } = findFormatARows(grid, headerRow);
  if (eurosRow >= 0 && fcRow >= 0) {
    for (const { col, period } of periodCols) {
      const eur = Number(grid[eurosRow]?.[col]);
      const fc = Number(grid[fcRow]?.[col]);
      if (!Number.isFinite(eur) || !Number.isFinite(fc)) continue;
      const td = eur + fc;
      if (td <= 0) continue;

      const year = Number(period.slice(0, 4));
      const ratio = Math.round((fc / td) * 10000) / 100;
      rows.push(
        { country_code: countryCode, year, period, indicator: "FCD", value: fc, updated_at: now },
        { country_code: countryCode, year, period, indicator: "TD", value: td, updated_at: now },
        { country_code: countryCode, year, period, indicator: "FCD_TD_RATIO", value: ratio, updated_at: now },
      );
      periodCount += 1;
    }
  } else {
    const { depositsRow, fcLeafRows } = findFormatBRows(grid, headerRow);
    if (depositsRow < 0) {
      throw new Error("'DEPOSITS (total)' 행을 찾지 못했습니다 (지원하지 않는 표 형식일 수 있습니다)");
    }
    for (const { col, period } of periodCols) {
      const td = Number(grid[depositsRow]?.[col]);
      if (!Number.isFinite(td) || td <= 0) continue;
      let fc = 0;
      let hasFc = false;
      for (const r of fcLeafRows) {
        const v = Number(grid[r]?.[col]);
        if (Number.isFinite(v)) {
          fc += v;
          hasFc = true;
        }
      }
      if (!hasFc) continue;

      const year = Number(period.slice(0, 4));
      const ratio = Math.round((fc / td) * 10000) / 100;
      rows.push(
        { country_code: countryCode, year, period, indicator: "FCD", value: Math.round(fc * 100) / 100, updated_at: now },
        { country_code: countryCode, year, period, indicator: "TD", value: td, updated_at: now },
        { country_code: countryCode, year, period, indicator: "FCD_TD_RATIO", value: ratio, updated_at: now },
      );
      periodCount += 1;
    }
  }

  if (periodCount === 0) {
    throw new Error("숫자로 읽을 수 있는 기간이 없습니다");
  }

  return { rows, periodCount };
}
