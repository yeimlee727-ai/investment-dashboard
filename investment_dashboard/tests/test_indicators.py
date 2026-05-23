from __future__ import annotations

import pandas as pd

from src.indicators.technicals import add_technical_indicators, calculate_rsi


def test_rsi_handles_all_rising_all_falling_and_unchanged() -> None:
    rising = calculate_rsi(pd.Series(range(1, 30)), period=14)
    falling = calculate_rsi(pd.Series(range(30, 1, -1)), period=14)
    unchanged = calculate_rsi(pd.Series([10] * 30), period=14)
    assert rising.iloc[-1] == 100
    assert falling.iloc[-1] == 0
    assert unchanged.iloc[-1] == 50


def test_wilder_rsi_option_returns_safe_values() -> None:
    rsi = calculate_rsi(pd.Series(range(1, 40)), period=14, method="wilder")
    assert rsi.iloc[-1] == 100
    assert rsi.between(0, 100).all()


def test_technical_columns_and_short_data_are_safe() -> None:
    df = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=10, freq="B"),
            "open": range(10, 20),
            "high": range(11, 21),
            "low": range(9, 19),
            "close": range(10, 20),
            "volume": [1000] * 10,
        }
    )
    result = add_technical_indicators(df)
    for column in ["ema20", "ema60", "macd", "macd_hist", "atr14", "volume_ma20"]:
        assert column in result.columns
    assert "period_high" in result.columns
    assert not result["atr14"].isna().all()
