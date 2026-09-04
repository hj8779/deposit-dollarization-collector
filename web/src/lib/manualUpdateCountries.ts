/**
 * Countries whose parser cannot fully auto-update because the *source itself*
 * blocks, requires a browser export, or lacks a machine-readable series.
 * These need a human to check in periodically rather than trusting the
 * scheduled collector run alone.
 *
 * Kind:
 * - `blocked`     — source inaccessible / bot wall / no data (manual entry)
 * - `half_manual` — human exports a file (or checks latest) then collector/UI
 *                   can ingest; partial automation may still exist
 * - `no_source`   — no usable official series
 *
 * Keep in sync with `dollarization-pipeline/src/parsers/*.py` docstrings and
 * with Supabase RLS policies listed in web/README.md (manual write whitelist).
 */

import i18n from "../i18n";

export type ManualKind = "blocked" | "half_manual" | "no_source";

export interface ManualUpdateInfo {
  /** Short reason shown in the ⚠ badge tooltip and chart notice */
  reason: string;
  kind: ManualKind;
  /** Optional source URL for half-manual export instructions */
  sourceUrl?: string;
}

interface ManualUpdateEntry {
  kind: ManualKind;
  sourceUrl?: string;
}

/** Reason text lives in src/i18n/locales/{ko,en}.json under "manualReasons.<code>". */
const MANUAL_UPDATE_COUNTRIES: Record<string, ManualUpdateEntry> = {
  COD: {
    kind: "half_manual",
    sourceUrl: "https://www.bcc.cd/statistiques/secteur-monetaire/depots",
  },
  LBN: {
    kind: "blocked",
  },
  MDG: {
    kind: "no_source",
  },
  BTN: {
    kind: "half_manual",
    sourceUrl: "https://www.rma.org.bt/publication/31/",
  },
  MDA: {
    kind: "half_manual",
    sourceUrl:
      "https://www.bnm.md/bdi/pages/reports/dpmc/DPMC11.xhtml?id=0&lang=en",
  },
  IRQ: {
    kind: "half_manual",
    sourceUrl: "https://cbi.iq/news/view/94",
  },
  RWA: {
    kind: "half_manual",
    sourceUrl: "https://www.bnr.rw/anreports",
  },
  TUR: {
    kind: "half_manual",
    sourceUrl: "https://evds2.tcmb.gov.tr/",
  },
  AGO: {
    kind: "half_manual",
    sourceUrl: "https://www.bna.ao/#/pt/publicacoes-e-media/relatorios/boletins/boletins-estatisticos",
  },
  LVA: {
    kind: "half_manual",
    sourceUrl: "https://statdb.bank.lv/lb/Data.aspx?id=243&lang=en",
  },
};

/** @deprecated string map kept for any external callers; prefer getManualInfo */
export function needsManualUpdate(countryCode: string): boolean {
  return countryCode in MANUAL_UPDATE_COUNTRIES;
}

export function getManualInfo(countryCode: string): ManualUpdateInfo | null {
  const entry = MANUAL_UPDATE_COUNTRIES[countryCode];
  if (!entry) return null;
  return {
    kind: entry.kind,
    sourceUrl: entry.sourceUrl,
    reason: i18n.t(`manualReasons.${countryCode}`),
  };
}

export function isHalfManual(countryCode: string): boolean {
  return MANUAL_UPDATE_COUNTRIES[countryCode]?.kind === "half_manual";
}

export function manualReason(countryCode: string): string {
  return getManualInfo(countryCode)?.reason ?? "";
}

/** ISO3 codes for Supabase RLS WITH CHECK lists */
export function manualCountryCodes(): string[] {
  return Object.keys(MANUAL_UPDATE_COUNTRIES).sort();
}
