from __future__ import annotations

import importlib

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
    safe_display_value,
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
        {"종목코드": "005930", "평가금액(원통화)": 10.5, "평가금액(원화)": 1000}
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
    assert safe_percent(12.345) == "12.35%"
    assert safe_percent(float("inf")) == "-"


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
