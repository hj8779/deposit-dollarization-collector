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

export type ManualKind = "blocked" | "half_manual" | "no_source";

export interface ManualUpdateInfo {
  /** Short reason shown in the ⚠ badge tooltip and chart notice */
  reason: string;
  kind: ManualKind;
  /** Optional source URL for half-manual export instructions */
  sourceUrl?: string;
}

export const MANUAL_UPDATE_COUNTRIES: Record<string, ManualUpdateInfo> = {
  COD: {
    kind: "half_manual",
    reason:
      "BCC 신형 통계 사이트(secteur-monetaire/depots)의 내장 시계열로 2010-12~현재는 자동 수집. 그 이전은 이 위젯에 데이터가 없어 연차보고서 Tableau 4.2를 연도별로 찾아야 함 → 해당 구간은 아래 표에 수동 입력.",
    sourceUrl: "https://www.bcc.cd/statistiques/secteur-monetaire/depots",
  },
  LBN: {
    kind: "blocked",
    reason: "Cloudflare Turnstile 봇 차단",
  },
  MDG: {
    kind: "no_source",
    reason: "BFM 공식 페이지에 기계 판독 가능한 FCD/TD 소스가 없음",
  },
  BTN: {
    kind: "half_manual",
    reason:
      "RMA Financial Sector Performance Review 분기 보고서(2012~2022-Q3)는 자동 수집. 2022-Q3 이후 시리즈 중단 → 최신 분기는 수동 입력.",
    sourceUrl: "https://www.rma.org.bt/publication/31/",
  },
  MDA: {
    kind: "half_manual",
    reason:
      "BNM DPMC11 Monetary Survey는 JSF/PrimeFaces 리포트 설정 후 xlsx 내보내기 필요. 기간 설정 → Export → report.xlsx 를 MDA_REPORT_XLSX 또는 ~/Downloads/report.xlsx 에 두고 수집, 또는 아래 표에 수동 입력.",
    sourceUrl:
      "https://www.bnm.md/bdi/pages/reports/dpmc/DPMC11.xhtml?id=0&lang=en",
  },
  IRQ: {
    kind: "half_manual",
    reason:
      "CBI Key Financial Indicators xlsx로 2003-12(TD)/2004-12(FCD)~현재는 자동 수집. 1991~2003(6월)은 스캔된 'Combined Historical Document' PDF뿐이라 기계 판독 불가 → 해당 구간만 아래 표에 수동 입력.",
    sourceUrl: "https://cbi.iq/news/view/94",
  },
  RWA: {
    kind: "half_manual",
    reason:
      "BNR mstat API + 최근 24개월 URL 프로브로 2018-06~현재는 자동 수집. bnr.rw/anreports에 Annual Report 18건(Table 3 MONETARY AGGREGATES DEVELOPMENTS, Jun-15~)이 더 있다고 확인되지만, 목록 페이지가 Angular SPA라 탭 클릭 후에도 실제 PDF 다운로드 링크가 DOM에 노출되지 않음(별도 API 콜로 추정, 자동화 시도 실패) → 필요 시 해당 페이지에서 연도별로 직접 찾아 아래 표에 수동 입력.",
    sourceUrl: "https://www.bnr.rw/anreports",
  },
  TUR: {
    kind: "half_manual",
    reason:
      "TCMB 'Weekly Money and Banking Statistics' PDF(Wayback Machine 스냅샷 포함)로 부분 자동 수집. 더 정확한 소스는 TCMB EVDS(evds2.tcmb.gov.tr) 시스템이지만 로그인 후 웹 UI에서 시리즈를 선택해 내보내야 해 자동화 불가 → EVDS에서 'Deposits' 카테고리의 1~9번 시리즈(Level 단위)를 선택해 xlsx로 내보낸 뒤 아래 업로드 버튼으로 반영(6.FOREIGN EXCHANGE DEPOSIT ACCOUNTS=FCD, 9.TOTAL=TD 열을 자동 인식).",
    sourceUrl: "https://evds2.tcmb.gov.tr/",
  },
  AGO: {
    kind: "half_manual",
    reason:
      "BNA(Banco Nacional de Angola) 자동 수집은 2012-01~현재만 커버. 그 이전 구간은 BNA 사이트에서 수동으로 찾아 아래 표에 입력: 2010~2012는 Publicações e Média > Relatórios > Boletins > Boletins Estatísticos(https://www.bna.ao/#/pt/publicacoes-e-media/relatorios/boletins/boletins-estatisticos), 2004~2009는 Relatório Anual - Contas(https://www.bna.ao/#/pt/publicacoes-e-media/relatorios/relatorio-anual-contas).",
    sourceUrl: "https://www.bna.ao/#/pt/publicacoes-e-media/relatorios/boletins/boletins-estatisticos",
  },
  LVA: {
    kind: "half_manual",
    reason:
      "미수집(자동화 안 됨). statdb.bank.lv의 '01 MFI balance sheet' 표는 DevExpress ASP.NET PivotGrid(가상 스크롤, API 백엔드 없음)라 스크레이핑이 사실상 불가 → 두 개의 미리 만들어진 표를 xlsx로 내보낸 뒤 아래 업로드 버튼으로 반영: '0104 Balance sheet in breakdown by currency'(2014-12~현재, Euro/Foreign currency 구간의 'DEPOSITS (total)' 행 사용) 또는 그 이전 아카이브 '04 Balance sheet of MFIs (except the Bank of Latvia) (data until December 2014)'(2010-06~2014-11, 'DEPOSITS (total)' 행은 통화 미분리 합계라 그 아래 섹션의 'Foreign currency' 리프 행들을 합산해 FCD 계산) — 둘 다 업로드 시 표 형식을 자동 인식함. 두 표 모두 residency 구분이 없어 FCD/TD가 거주자만이 아닌 전체 예금자 기준임에 유의. 재수출할 때마다 새로 늘어난 기간이 자동으로 채워지므로 반복 업로드로 계속 최신화 가능.",
    sourceUrl: "https://statdb.bank.lv/lb/Data.aspx?id=243&lang=en",
  },
};

/** @deprecated string map kept for any external callers; prefer getManualInfo */
export function needsManualUpdate(countryCode: string): boolean {
  return countryCode in MANUAL_UPDATE_COUNTRIES;
}

export function getManualInfo(countryCode: string): ManualUpdateInfo | null {
  return MANUAL_UPDATE_COUNTRIES[countryCode] ?? null;
}

export function isHalfManual(countryCode: string): boolean {
  return MANUAL_UPDATE_COUNTRIES[countryCode]?.kind === "half_manual";
}

export function manualReason(countryCode: string): string {
  return MANUAL_UPDATE_COUNTRIES[countryCode]?.reason ?? "";
}

/** ISO3 codes for Supabase RLS WITH CHECK lists */
export function manualCountryCodes(): string[] {
  return Object.keys(MANUAL_UPDATE_COUNTRIES).sort();
}
