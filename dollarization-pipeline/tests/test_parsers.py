from pathlib import Path

from src.parsers import abw

FIXTURES = Path(__file__).parent / "fixtures"


def test_abw_fcd_td_june_2026():
    content = (FIXTURES / "abw_2026-06.pdf").read_bytes()
    df = abw.parse(content, "ABW")

    row = df[(df["period"] == "2026-06") & (df["indicator"] == "FCD")]
    assert not row.empty
    assert row["value"].iloc[0] == 863.7

    row = df[(df["period"] == "2026-06") & (df["indicator"] == "TD")]
    assert not row.empty
    assert row["value"].iloc[0] == 7308.9


def test_abw_ratio_is_consistent():
    content = (FIXTURES / "abw_2026-06.pdf").read_bytes()
    df = abw.parse(content, "ABW")

    fcd = df[(df["period"] == "2026-06") & (df["indicator"] == "FCD")]["value"].iloc[0]
    td = df[(df["period"] == "2026-06") & (df["indicator"] == "TD")]["value"].iloc[0]
    ratio = df[(df["period"] == "2026-06") & (df["indicator"] == "FCD_TD_RATIO")]["value"].iloc[0]

    assert ratio == round(fcd / td * 100, 2)


def test_abw_ocr_fallback_on_corrupted_pdf():
    """2010년 12월 PDF는 pdfplumber.extract_text()로 읽으면 글자 단위로 뒤집힌 텍스트가
    나오는 손상본. 표준 OCR 폴백(src.collectors.base.find_page_text_via_ocr)을 거쳐
    실제 값(FCD=148.8, TD=2,979.5)을 복구하는지 검증한다. 시스템에 tesseract-ocr 필요."""
    content = (FIXTURES / "abw_2010-12_ocr.pdf").read_bytes()
    df = abw.parse(content, "ABW")

    row = df[(df["period"] == "2010-12") & (df["indicator"] == "FCD")]
    assert not row.empty
    assert row["value"].iloc[0] == 148.8

    row = df[(df["period"] == "2010-12") & (df["indicator"] == "TD")]
    assert not row.empty
    assert row["value"].iloc[0] == 2979.5
