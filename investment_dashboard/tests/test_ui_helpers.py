from __future__ import annotations

import importlib

import pandas as pd
import plotly.graph_objects as go

from src.ui_helpers import (
    apply_plotly_dark_theme,
    contains_prohibited_decision_wording,
    format_calculation_value,
    format_reliability_label,
    format_avg_profit_loss_ratio,
    format_profit_factor,
    get_allocation_notice,
    get_backtest_warning_messages,
    get_data_mode_status,
    get_fx_status_message,
    get_rebalancing_band_label,
    get_stress_test_notice,
    get_upload_apply_result_message,
    get_upload_read_success_message,
    get_upload_validation_summary_message,
    korean_column_name,
    localize_columns,
    mock_delete_warning_message,
    portfolio_upload_notice_message,
    format_display_dataframe,
    safe_display_value,
    safe_currency_amount,
    security_display_label,
    safe_krw,
    safe_percent,
)


def test_data_mode_status_messages() -> None:
    sample = get_data_mode_status("SAMPLE")
    real = get_data_mode_status("REAL_WITH_FALLBACK")
    fallback = get_data_mode_status("REAL_WITH_FALLBACK", is_fallback=True)

    assert sample[0] == "SAMPLE MODE"
    assert sample[2] == "warning"
    assert real[0] == "REAL DATA MODE"
    assert real[2] == "info"
    assert fallback[0] == "FALLBACK MODE"
    assert fallback[2] == "warning"


def test_backtest_low_trade_warning_message() -> None:
    messages = get_backtest_warning_messages(
        trade_count=3,
        profit_factor=1.5,
        avg_profit_loss_ratio=1.2,
        data_source="SAMPLE",
    )

    assert any("통계적 신뢰도" in message for message in messages)
    assert any("SAMPLE/FALLBACK" in message for message in messages)


def test_profit_factor_no_loss_display() -> None:
    assert format_profit_factor(999.0) == "999+ (손실 거래 없음)"
    assert format_avg_profit_loss_ratio(0.0, 999.0) == "N/A (손실 거래 없음)"


def test_fx_status_messages() -> None:
    assert "1,350.00" in get_fx_status_message(1350.0, "SAMPLE_FX", None)
    assert "제한" in get_fx_status_message(None, "REAL_FX_ERROR", "network")
    assert "오류" in get_fx_status_message(1350.0, "SAMPLE_FX_FALLBACK", "network")


def test_korean_column_label_helpers() -> None:
    localized = localize_columns(
        [{"symbol": "005930", "market_value": 10.5, "market_value_krw": 1000}]
    )

    assert korean_column_name("symbol") == "종목코드"
    assert korean_column_name("position_weight_krw") == "비중(원화 기준)"
    assert korean_column_name("fx_rate") == "적용 환율"
    assert localized == [
        {"종목코드": "005930", "평가금액(현지통화)": 10.5, "평가금액(원화)": 1000}
    ]


def test_mock_delete_warning_message_is_clear() -> None:
    message = mock_delete_warning_message()

    assert "MockBroker" in message
    assert "실제 주문" in message


def test_portfolio_upload_notice_message_is_clear() -> None:
    message = portfolio_upload_notice_message()

    assert "MockBroker 가상 포지션" in message
    assert "실제 주문" in message
    assert "계좌" in message


def test_bulk_upload_confirmation_messages_are_clear() -> None:
    read_message = get_upload_read_success_message("sample.csv", 4)
    validation_message, tone = get_upload_validation_summary_message(4, 0, 2)
    apply_message = get_upload_apply_result_message(
        {
            "added": 1,
            "updated": 2,
            "skipped": 1,
            "failed": 0,
            "excluded_error_count": 1,
            "current_position_count": 4,
        }
    )

    assert "총 4개 행" in read_message
    assert "sample.csv" in read_message
    assert tone == "warning"
    assert "검증 완료" in validation_message
    assert "가상 포지션 일괄 반영 완료" in apply_message
    assert "신규 1건" in apply_message
    assert "오류 1건" in apply_message
    assert "현재 MockBroker 가상 포지션: 4개" in apply_message
    for message in [read_message, validation_message, apply_message]:
        assert "주문 완료" not in message
        assert "체결 완료" not in message


def test_reliability_label_is_korean() -> None:
    assert format_reliability_label("HIGH") == "높음"
    assert format_reliability_label("LOW") == "낮음"
    assert format_reliability_label(None) == "알 수 없음"


def test_calculation_unavailable_display() -> None:
    assert format_calculation_value(None) == "계산 불가"
    assert format_calculation_value(float("nan")) == "계산 불가"
    assert format_calculation_value(float("inf")) == "계산 불가"


def test_safe_display_formatters() -> None:
    assert safe_display_value(float("nan")) == "-"
    assert safe_krw(1234567.8) == "1,234,568원"
    assert safe_currency_amount(123.3, "USD") == "$123.30"
    assert safe_currency_amount(1234567.8, "KRW") == "1,234,568원"
    assert safe_percent(12.345) == "12.35%"


def test_security_display_label_prefers_name_and_falls_back_to_symbol() -> None:
    assert security_display_label(" 삼성전자 ", "005930") == "삼성전자"
    assert security_display_label("", "005930") == "005930"
    assert security_display_label(None, "GRAB") == "GRAB"
    assert safe_percent(float("inf")) == "-"


def test_format_display_dataframe_separates_currency_and_percent_columns() -> None:
    frame = format_display_dataframe(
        pd.DataFrame(
            [
                {
                    "symbol": "GRAB",
                    "name": "Grab Holdings",
                    "currency": "USD",
                    "market_value": 123.3,
                    "market_value_krw": 166455,
                    "unrealized_pnl": 16.5,
                    "unrealized_pnl_krw": 22275,
                    "unrealized_pnl_pct": 15.45,
                    "total_pnl_pct": 15.45,
                },
                {
                    "symbol": "005930",
                    "name": "삼성전자",
                    "currency": "KRW",
                    "market_value": 1592623,
                    "market_value_krw": 1592623,
                    "unrealized_pnl": 155000,
                    "unrealized_pnl_krw": 155000,
                    "unrealized_pnl_pct": 10.78,
                    "total_pnl_pct": 10.78,
                },
            ]
        )
    )

    assert frame.loc[0, "평가금액(현지통화)"] == "$123.30"
    assert frame.loc[0, "평가금액(원화)"] == "166,455원"
    assert frame.loc[0, "평가손익(현지통화)"] == "$16.50"
    assert frame.loc[0, "평가손익(원화)"] == "22,275원"
    assert frame.loc[0, "평가손익률(%)"] == "15.45%"
    assert frame.loc[0, "총손익률(%)"] == "15.45%"
    assert "원" not in frame.loc[0, "평가손익률(%)"]
    assert frame.loc[1, "평가금액(현지통화)"] == "1,592,623원"


def test_plotly_dark_theme_helper_keeps_figure_valid() -> None:
    fig = apply_plotly_dark_theme(go.Figure())

    assert fig.layout.template is not None
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"


def test_prohibited_investment_wording_detector() -> None:
    assert contains_prohibited_decision_wording("매수 추천 문구")
    assert not contains_prohibited_decision_wording("추가매수 후보를 검토합니다.")


def test_rebalancing_status_helpers_are_safe() -> None:
    assert get_rebalancing_band_label(True) == "리밸런싱 검토"
    assert get_rebalancing_band_label(False) == "유지 가능 구간"
    assert "가정 시나리오" in get_stress_test_notice()
    assert not contains_prohibited_decision_wording(get_stress_test_notice())
    assert "의사결정 보조 정보" in get_allocation_notice()
    assert not contains_prohibited_decision_wording(get_allocation_notice())


def test_app_import_smoke() -> None:
    app = importlib.import_module("app")
    assert hasattr(app, "main")
    assert callable(app.summarize_watchlist)
