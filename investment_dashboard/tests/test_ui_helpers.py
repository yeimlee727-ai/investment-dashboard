from __future__ import annotations

import importlib

from src.ui_helpers import (
    format_avg_profit_loss_ratio,
    format_profit_factor,
    get_backtest_warning_messages,
    get_data_mode_status,
    get_fx_status_message,
    korean_column_name,
    localize_columns,
    mock_delete_warning_message,
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
    localized = localize_columns([{"symbol": "005930", "market_value_krw": 1000}])

    assert korean_column_name("symbol") == "종목코드"
    assert localized == [{"종목코드": "005930", "평가금액(원화)": 1000}]


def test_mock_delete_warning_message_is_clear() -> None:
    message = mock_delete_warning_message()

    assert "MockBroker" in message
    assert "실제 주문" in message


def test_app_import_smoke() -> None:
    app = importlib.import_module("app")
    assert hasattr(app, "main")
    assert callable(app.summarize_watchlist)
