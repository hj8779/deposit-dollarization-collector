import * as XLSX from "xlsx";
import type { DepositRow } from "./types";

/**
 * Parses an EVDS (evds2.tcmb.gov.tr) export for Turkey's deposit series.
 *
 * The user builds the export by picking these series in EVDS's formula
 * builder (Deposits category, "Level" unit for each):
 *   1. Saving Deposits, 1.1/1.2 Sight/Time
 *   2. Commercial Corporations' Deposits, 2.1/2.2
 *   3. Other Corporations' Deposits, 3.1/3.2 (+ 3.2.i of which: Funds)
 *   4. Official Deposits
 *   5. Certificates of Deposits
 *   6. Foreign Exchange Deposit Accounts, 6.1/6.2 Sight/Time
 *   7. Precious Stones Deposit Accounts (FX), 7.1/7.2
 *   8. Interbank Deposits
 *   9. TOTAL
 *
 * We only need two of those columns:
 *   FCD = "6. FOREIGN EXCHANGE DEPOSIT ACCOUNTS" (the aggregate line, not
 *         its 6.1/6.2 sub-rows — item 7's precious-stones accounts are a
 *         different asset class and deliberately excluded)
 *   TD  = "9. TOTAL"
 *
 * EVDS's own sheet layout: a header row with series names/codes, one row per
 * date below it, and a metadata block at the bottom (series code → full
 * description) appended after the data ends. We match columns by keyword
 * against the header text; if EVDS exported bare codes instead of names, we
 * fall back to scanning the trailing metadata block for the same keywords
 * and map its series code back to the matching column header.
 */

export interface EvdsImportResult {
  rows: DepositRow[];
  warnings: string[];
  fcdColumnHeader: string;
  tdColumnHeader: string;
  periodCount: number;
}

const FCD_KEYWORDS = ["foreign exchange deposit"]; // matches "6.FOREIGN EXCHANGE DEPOSIT ACCOUNTS - Level"
const FCD_EXCLUDE = ["precious", "sight", "time", "6.1", "6.2"]; // avoid sub-rows / item 7
const TD_KEYWORDS = ["total"]; // matches "9.TOTAL - Level"
const TD_EXCLUDE = ["interbank"];

function normalize(s: unknown): string {
  return String(s ?? "").trim().toLowerCase();
}

/** Series codes appear as "TP_KM_F19" in the header row but "TP.KM.F19" in the
 * trailing metadata block — strip all non-alphanumerics so both forms compare equal. */
function normalizeCode(s: unknown): string {
  return normalize(s).replace(/[^a-z0-9]/g, "");
}

interface ParsedDate {
  year: number;
  /** "YYYY-MM" if the source cell had no day component, else "YYYY-MM-DD". */
  period: string;
}

function parseDateCell(v: unknown): ParsedDate | null {
  if (v instanceof Date && !Number.isNaN(v.getTime())) {
    const y = v.getUTCFullYear();
    const m = String(v.getUTCMonth() + 1).padStart(2, "0");
    const day = String(v.getUTCDate()).padStart(2, "0");
    return { year: y, period: `${y}-${m}-${day}` };
  }
  if (typeof v === "number") {
    // Excel serial date
    const d = XLSX.SSF.parse_date_code(v);
    if (!d) return null;
    const m = String(d.m).padStart(2, "0");
    const day = String(d.d).padStart(2, "0");
    return { year: d.y, period: `${d.y}-${m}-${day}` };
  }
  if (typeof v === "string") {
    const s = v.trim();
    // dd.mm.yyyy
    const m1 = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
    if (m1) {
      const y = +m1[3];
      return { year: y, period: `${y}-${m1[2].padStart(2, "0")}-${m1[1].padStart(2, "0")}` };
    }
    // yyyy-mm-dd
    const m2 = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (m2) {
      const y = +m2[1];
      return { year: y, period: `${y}-${m2[2].padStart(2, "0")}-${m2[3].padStart(2, "0")}` };
    }
    // yyyy-mm (EVDS monthly export — no day component)
    const m3 = s.match(/^(\d{4})-(\d{1,2})$/);
    if (m3) {
      const y = +m3[1];
      return { year: y, period: `${y}-${m3[2].padStart(2, "0")}` };
    }
  }
  return null;
}

function findColumn(
  headerRow: unknown[],
  keywords: string[],
  exclude: string[],
): number | null {
  for (let c = 0; c < headerRow.length; c++) {
    const h = normalize(headerRow[c]);
    if (!h) continue;
    if (exclude.some((x) => h.includes(x))) continue;
    if (keywords.some((k) => h.includes(k))) return c;
  }
  return null;
}

export async function parseEvdsWorkbook(
  file: File,
  countryCode: string,
): Promise<EvdsImportResult> {
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf, { type: "array", cellDates: true });
  const sheet = wb.Sheets[wb.SheetNames[0]];
  const grid: unknown[][] = XLSX.utils.sheet_to_json(sheet, { header: 1, raw: true });

  if (grid.length < 2) {
    throw new Error("빈 시트이거나 헤더/데이터 행이 없습니다");
  }

  // Header is the first row that contains a plausible date in some other
  // row right below it — EVDS sometimes has 1-2 title rows above the real
  // header, so scan for the row whose *next* row's first cell parses as a date.
  let headerIdx = 0;
  for (let r = 0; r < Math.min(grid.length - 1, 5); r++) {
    if (parseDateCell(grid[r + 1]?.[0])) {
      headerIdx = r;
      break;
    }
  }
  const headerRow = grid[headerIdx] ?? [];

  let fcdCol = findColumn(headerRow, FCD_KEYWORDS, FCD_EXCLUDE);
  let tdCol = findColumn(headerRow, TD_KEYWORDS, TD_EXCLUDE);

  const warnings: string[] = [];

  // Fallback: header cells are bare series codes (e.g. "TP_KM_F19"), not
  // names — scan the trailing metadata block ("Series Descriptions": series
  // code -> description, one row per series, code punctuated as "TP.KM.F19").
  // Below that, EVDS repeats the same codes again in a "Notes" block (one row
  // per metadata *field* per series — "Datasource", "Application Change
  // Link", etc., e.g. ["TP.KM.F01","Datasource","BANKS"]) — first-wins so
  // those don't clobber the real description with a field name/value.
  if (fcdCol === null || tdCol === null) {
    const codeToDesc = new Map<string, string>();
    for (let r = headerIdx + 1; r < grid.length; r++) {
      const row = grid[r];
      if (!row || row.length < 2) continue;
      const code = normalizeCode(row[0]);
      const desc = normalize(row[1]);
      if (code && desc && !codeToDesc.has(code) && !parseDateCell(row[0])) codeToDesc.set(code, desc);
    }
    const headerCodes = headerRow.map((h) => normalizeCode(h));
    if (fcdCol === null) {
      for (const [code, desc] of codeToDesc) {
        if (FCD_KEYWORDS.some((k) => desc.includes(k)) && !FCD_EXCLUDE.some((x) => desc.includes(x))) {
          const idx = headerCodes.indexOf(code);
          if (idx >= 0) {
            fcdCol = idx;
            break;
          }
        }
      }
    }
    if (tdCol === null) {
      for (const [code, desc] of codeToDesc) {
        if (TD_KEYWORDS.some((k) => desc.includes(k)) && !TD_EXCLUDE.some((x) => desc.includes(x))) {
          const idx = headerCodes.indexOf(code);
          if (idx >= 0) {
            tdCol = idx;
            break;
          }
        }
      }
    }
  }

  if (fcdCol === null) {
    throw new Error(
      "'FOREIGN EXCHANGE DEPOSIT ACCOUNTS' 열을 찾지 못했습니다. 헤더 이름을 확인해주세요.",
    );
  }
  if (tdCol === null) {
    throw new Error("'TOTAL' 열을 찾지 못했습니다. 헤더 이름을 확인해주세요.");
  }

  const now = new Date().toISOString();
  const rows: DepositRow[] = [];
  let periodCount = 0;

  for (let r = headerIdx + 1; r < grid.length; r++) {
    const row = grid[r];
    if (!row) continue;
    const parsed = parseDateCell(row[0]);
    if (!parsed) continue; // trailing metadata block, blank rows, etc.

    const fcdRaw = row[fcdCol];
    const tdRaw = row[tdCol];
    const fcd = typeof fcdRaw === "number" ? fcdRaw : Number(fcdRaw);
    const td = typeof tdRaw === "number" ? tdRaw : Number(tdRaw);
    if (!Number.isFinite(fcd) || !Number.isFinite(td) || td <= 0) continue;

    const { period, year } = parsed;
    const ratio = Math.round((fcd / td) * 10000) / 100;

    rows.push(
      { country_code: countryCode, year, period, indicator: "FCD", value: fcd, updated_at: now },
      { country_code: countryCode, year, period, indicator: "TD", value: td, updated_at: now },
      { country_code: countryCode, year, period, indicator: "FCD_TD_RATIO", value: ratio, updated_at: now },
    );
    periodCount++;
  }

  if (rows.length === 0) {
    throw new Error("파싱 가능한 날짜/값 행을 찾지 못했습니다");
  }

  return {
    rows,
    warnings,
    fcdColumnHeader: String(headerRow[fcdCol] ?? ""),
    tdColumnHeader: String(headerRow[tdCol] ?? ""),
    periodCount,
  };
}
