from __future__ import annotations

from io import BytesIO
import zipfile
import xml.etree.ElementTree as ET

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


class SampleStrategyResult:
    def __init__(self, scenarios: pd.DataFrame) -> None:
        self.positions = pd.DataFrame()
        self.scenarios = scenarios
        self.portfolio_summary = {}


def read_worksheet_xml(payload: bytes, sheet_name: str) -> str:
    workbook_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(BytesIO(payload)) as workbook:
        workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
        sheet = workbook_root.find(f".//{{{workbook_ns}}}sheet[@name='{sheet_name}']")
        assert sheet is not None
        relationship_id = sheet.attrib[f"{{{rel_ns}}}id"]
        rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        for relationship in rels_root.findall(f"{{{package_rel_ns}}}Relationship"):
            if relationship.attrib["Id"] == relationship_id:
                target = relationship.attrib["Target"]
                return workbook.read(f"xl/{target}").decode("utf-8")
    raise AssertionError(f"Worksheet not found: {sheet_name}")


def test_empty_report_data_is_safe() -> None:
    report = build_portfolio_report_data([], data_mode="SAMPLE", provider_name="TEST")

    assert report.positions.empty
    sheets = build_report_sheets(report)
    assert "Positions" in sheets
    assert sheets["Positions"].iloc[0]["안내"] == "가상 포지션 데이터가 없습니다."
    assert "Scenarios" in sheets
    assert sheets["Scenarios"].iloc[0]["안내"] == "시나리오 전망 데이터 없음"


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
            "Scenarios",
            "Risk_Rebalancing",
            "Stress_Test",
            "Allocation",
            "Limitations",
        ]:
            assert sheet_name in workbook_xml


def test_scenarios_sheet_contains_scenario_data() -> None:
    report = build_portfolio_report_data(
        sample_positions(),
        strategy_result=SampleStrategyResult(
            pd.DataFrame(
                [
                    {
                        "scenario": "Base",
                        "expected_return_pct": 3.2,
                        "comment": "점검용 시나리오",
                    }
                ]
            )
        ),
        data_mode="SAMPLE",
        provider_name="TEST",
    )

    sheets = build_report_sheets(report)
    payload = build_excel_report(report)
    scenarios_xml = read_worksheet_xml(payload, "Scenarios")

    assert "Scenarios" in sheets
    assert "Base" in scenarios_xml
    assert "점검용 시나리오" in scenarios_xml


def test_empty_scenarios_sheet_contains_notice_message() -> None:
    report = build_portfolio_report_data(
        sample_positions(), data_mode="SAMPLE", provider_name="TEST"
    )

    payload = build_excel_report(report)
    scenarios_xml = read_worksheet_xml(payload, "Scenarios")

    assert "시나리오 전망 데이터 없음" in scenarios_xml


def test_scenarios_sheet_sanitizes_nan_inf_none_values() -> None:
    report = build_portfolio_report_data(
        sample_positions(),
        strategy_result=SampleStrategyResult(
            pd.DataFrame(
                {
                    "scenario": ["Base", None, "nan"],
                    "expected_return_pct": [float("nan"), float("inf"), "-inf"],
                }
            )
        ),
        data_mode="SAMPLE",
        provider_name="TEST",
    )

    scenarios_xml = read_worksheet_xml(build_excel_report(report), "Scenarios")
    lower_xml = scenarios_xml.lower()

    assert "계산 불가" in scenarios_xml
    assert ">nan<" not in lower_xml
    assert ">inf<" not in lower_xml
    assert ">-inf<" not in lower_xml
    assert ">none<" not in lower_xml


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
