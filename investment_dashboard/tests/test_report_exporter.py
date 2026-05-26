from __future__ import annotations

from io import BytesIO
import zipfile

import pandas as pd

from src.reporting.report_exporter import (
    FORBIDDEN_REPORT_WORDS,
    build_excel_report,
    build_html_report,
    build_portfolio_report_data,
    build_report_sheets,
    report_file_name,
    sanitize_report_dataframe,
)


def sample_positions() -> list[dict[str, object]]:
    return [
        {
            "symbol": "360750",
            "name": "TIGER 미국S&P500",
            "market": "KR",
            "quantity": 31,
            "avg_price": 26_275,
            "current_price": 27_000,
            "market_value": 837_000,
            "market_value_krw": 837_000,
            "cost_basis_krw": 814_525,
            "unrealized_pnl_krw": 22_475,
            "total_pnl_pct": 2.76,
            "position_weight_krw": 50.0,
            "fx_rate": 1.0,
            "data_source": "SAMPLE",
            "quote_error": None,
            "updated_at": "2026-05-26T12:00:00",
        }
    ]


def test_empty_report_data_is_safe() -> None:
    report = build_portfolio_report_data([], data_mode="SAMPLE", provider_name="TEST")

    assert report.positions.empty
    sheets = build_report_sheets(report)
    assert "Positions" in sheets
    assert sheets["Positions"].iloc[0]["안내"] == "가상 포지션 데이터가 없습니다."


def test_summary_and_positions_report_data() -> None:
    report = build_portfolio_report_data(
        sample_positions(),
        portfolio_summary={
            "total_market_value_krw": 837_000,
            "total_cost_basis_krw": 814_525,
            "total_unrealized_pnl_krw": 22_475,
            "total_pnl_krw": 22_475,
            "total_pnl_pct": 2.76,
            "position_count": 1,
            "top1_weight_krw": 50.0,
        },
        data_mode="SAMPLE",
        provider_name="TEST",
    )

    assert not report.summary.empty
    assert not report.positions.empty
    assert "종목코드" in report.positions.columns


def test_sanitize_report_dataframe_removes_nan_inf_none_strings() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["A", None, "nan"],
            "value": [float("nan"), float("inf"), "-inf"],
        }
    )

    sanitized = sanitize_report_dataframe(frame)
    text = sanitized.to_string()

    assert "계산 불가" in text
    assert " inf" not in text.lower()
    assert "nan" not in text.lower()


def test_excel_report_contains_required_sheet_names() -> None:
    report = build_portfolio_report_data(
        sample_positions(), data_mode="SAMPLE", provider_name="TEST"
    )

    payload = build_excel_report(report)

    assert payload.startswith(b"PK")
    with zipfile.ZipFile(BytesIO(payload)) as workbook:
        workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
        for sheet_name in [
            "Report_Info",
            "Summary",
            "Positions",
            "Strategy",
            "Risk_Rebalancing",
            "Stress_Test",
            "Allocation",
            "Limitations",
        ]:
            assert sheet_name in workbook_xml


def test_html_report_contains_required_safety_notices() -> None:
    report = build_portfolio_report_data(
        sample_positions(), data_mode="SAMPLE", provider_name="TEST"
    )

    html = build_html_report(report)

    assert "의사결정 보조 정보" in html
    assert "실제 주문 기능 없음" in html
    for word in FORBIDDEN_REPORT_WORDS:
        assert word not in html


def test_report_file_name_uses_timestamp_and_extension() -> None:
    name = report_file_name("xlsx", "2026-05-26T12:34:00")

    assert name == "portfolio_report_20260526_123400.xlsx"
