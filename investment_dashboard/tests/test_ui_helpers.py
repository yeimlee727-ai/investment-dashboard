from __future__ import annotations

import importlib

from src.ui_helpers import (
    format_avg_profit_loss_ratio,
    format_profit_factor,
    get_backtest_warning_messages,
    get_data_mode_status,
    get_fx_status_message,
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


def test_app_import_smoke() -> None:
    app = importlib.import_module("app")
    assert hasattr(app, "main")
    assert callable(app.summarize_watchlist)
