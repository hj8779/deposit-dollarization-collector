"""El Salvador: BCR 'Panorama de las Sociedades de Depósitos' page.
A split-table layout where the label table (table 0) and the value table
(table 1) align 1:1 by row index.
Row 39 = '3.4.1 Depósitos Transferibles en Moneda Extranjera' (foreign-currency
transferable deposits).
Value table row1 = labels for the most recent 12 months ('Jul'-'Jun', first 6
= prior year / last 6 = current year).

TD (total deposits) = row22 (3.1.2 Depósitos a la Vista, demand deposits) +
row29 (3.2.1 Cuasidinero, time/savings deposits) + row39 (FCD). We verified
the identities empirically: M1(row20)=Currency(row21)+Demand(row22),
M2(row28)=M1+Cuasidinero(row29), DSA(row19)=M2+Valores(row35)+Otros
depósitos(row38=39) (e.g. 2025-07 DSA 22553.7 = M2 21432.2 + Valores 1120.9 +
0.6)."""

from datetime import datetime, timezone

import pandas as pd

from src.collectors.base import INDICATOR, INDICATOR_TD, render_page

FILE_URL = "__RENDER__"

_ROW_LABEL = "moneda extranjera"
_DEMAND_LABEL = "depósitos a la vista"
_QUASI_LABEL = "cuasidinero"
_MONTH_MAP = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("SLV is handled via render() (not a file-download flow)")


def render(target: dict) -> pd.DataFrame:
    url = target["source_url"]
    country_code = target["country_code"]
    now = datetime.now(timezone.utc).isoformat()

    playwright, browser, page = render_page(url)
    try:
        tables = page.locator("table")
        label_rows = tables.nth(0).locator("tr").all_inner_texts()
        value_rows = tables.nth(1).locator("tr").all_inner_texts()

        year_header = value_rows[0].split("\t")  # ['2025', '2026'] (6 columns each)
        month_header = [m.strip().lower() for m in value_rows[1].split("\t")]
        n = len(month_header)
        years = [year_header[0]] * (n // 2) + [year_header[-1]] * (n - n // 2)

        def _row_values(row_label: str) -> list[str] | None:
            idx = next(
                (i for i, label in enumerate(label_rows) if row_label in label.lower()), None
            )
            if idx is None or idx >= len(value_rows):
                return None
            return value_rows[idx].split("\t")

        fcd_values = _row_values(_ROW_LABEL)
        demand_values = _row_values(_DEMAND_LABEL)
        quasi_values = _row_values(_QUASI_LABEL)
        if fcd_values is None:
            return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

        out = []
        for i, (year, month_label) in enumerate(zip(years, month_header)):
            month = _MONTH_MAP.get(month_label)
            if month is None:
                continue
            period = f"{year}-{month:02d}"

            fcd_raw = fcd_values[i].replace(",", "") if i < len(fcd_values) else ""
            if fcd_raw and fcd_raw not in ("-", "n.d."):
                fcd_value = float(fcd_raw)
                out.append({
                    "country_code": country_code,
                    "year": int(year),
                    "period": period,
                    "indicator": INDICATOR,
                    "value": fcd_value,
                    "updated_at": now,
                })

                if demand_values is not None and quasi_values is not None and i < len(demand_values) and i < len(quasi_values):
                    demand_raw = demand_values[i].replace(",", "")
                    quasi_raw = quasi_values[i].replace(",", "")
                    if demand_raw not in ("", "-", "n.d.") and quasi_raw not in ("", "-", "n.d."):
                        out.append({
                            "country_code": country_code,
                            "year": int(year),
                            "period": period,
                            "indicator": INDICATOR_TD,
                            "value": float(demand_raw) + float(quasi_raw) + fcd_value,
                            "updated_at": now,
                        })
        return pd.DataFrame(out)
    finally:
        browser.close()
        playwright.stop()
