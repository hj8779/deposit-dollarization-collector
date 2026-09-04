import pandas as pd

from src.storage.supabase_store import _validate_value_range


def _row(country_code, period, indicator, value):
    return {
        "country_code": country_code,
        "year": int(period[:4]),
        "period": period,
        "indicator": indicator,
        "value": value,
    }


def test_negative_fcd_or_td_is_dropped():
    df = pd.DataFrame([
        _row("ARE", "2025-01", "FCD", -21053.0),
        _row("ARE", "2025-01", "TD", 578138.0),
    ])
    out = _validate_value_range(df)
    assert list(out["indicator"]) == ["TD"]


def test_ratio_outside_0_100_is_dropped():
    df = pd.DataFrame([
        _row("ARE", "2021-03", "FCD_TD_RATIO", -129.5981),
        _row("ARE", "2021-03", "FCD_TD_RATIO", 150.0),
        _row("ARE", "2021-03", "FCD_TD_RATIO", 42.5),
    ])
    out = _validate_value_range(df)
    assert list(out["value"]) == [42.5]


def test_valid_rows_pass_through_unchanged():
    df = pd.DataFrame([
        _row("KEN", "2026-05", "FCD", 1397034.0),
        _row("KEN", "2026-05", "TD", 6032347.0),
        _row("KEN", "2026-05", "FCD_TD_RATIO", 23.159),
        _row("KEN", "2026-05", "FCD_TD_RATIO", 0.0),
        _row("KEN", "2026-05", "FCD_TD_RATIO", 100.0),
    ])
    out = _validate_value_range(df)
    assert len(out) == len(df)
