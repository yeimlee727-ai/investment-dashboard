from __future__ import annotations

import pandas as pd

from src.backtest.backtest_engine import BacktestEngine


class SignalBacktestEngine(BacktestEngine):
    def __init__(self, signal_index: int) -> None:
        self.signal_index = signal_index

    def _entry_signal(self, data: pd.DataFrame, i: int, strategy: str) -> bool:
        return i == self.signal_index


def make_frame(length: int = 80, price: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=length, freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "open": [price] * length,
            "high": [price] * length,
            "low": [price] * length,
            "close": [price] * length,
            "volume": [1000.0] * length,
        }
    )


def test_enters_on_next_bar_open_after_signal() -> None:
    df = make_frame()
    df.loc[62, "open"] = 123
    result = SignalBacktestEngine(signal_index=61).run(
        df,
        strategy="custom",
        holding_days=1,
        fee_rate=0,
        slippage_rate=0,
    )
    assert result.trade_count == 1
    assert result.trades.iloc[0]["entry_price"] == 123


def test_does_not_enter_on_last_bar() -> None:
    df = make_frame()
    result = SignalBacktestEngine(signal_index=len(df) - 2).run(
        df,
        strategy="custom",
        fee_rate=0,
        slippage_rate=0,
    )
    assert result.trade_count == 0


def test_position_size_pct_limits_capital_at_risk() -> None:
    df = make_frame()
    df.loc[63, "close"] = 110
    result = SignalBacktestEngine(signal_index=61).run(
        df,
        strategy="custom",
        initial_cash=10_000,
        holding_days=1,
        fee_rate=0,
        slippage_rate=0,
        position_size_pct=0.2,
    )
    assert result.total_return == 2.0


def test_fees_and_slippage_affect_equity_curve() -> None:
    df = make_frame()
    result = SignalBacktestEngine(signal_index=61).run(
        df,
        strategy="custom",
        initial_cash=10_000,
        holding_days=1,
        fee_rate=0.01,
        slippage_rate=0.01,
        position_size_pct=0.2,
    )
    assert result.total_fees > 0
    assert result.total_slippage > 0
    assert result.equity_curve["equity"].min() < 10_000


def test_close_basis_exits_on_close_price() -> None:
    df = make_frame()
    df.loc[63, "close"] = 116
    result = SignalBacktestEngine(signal_index=61).run(
        df,
        strategy="custom",
        holding_days=10,
        fee_rate=0,
        slippage_rate=0,
        stop_take_basis="close",
    )
    assert result.trades.iloc[0]["exit_price"] == 116
    assert result.trades.iloc[0]["exit_reason"] == "익절"


def test_intraday_basis_uses_high_low_and_stop_first() -> None:
    df = make_frame()
    df.loc[63, "low"] = 90
    df.loc[63, "high"] = 120
    df.loc[63, "close"] = 110
    result = SignalBacktestEngine(signal_index=61).run(
        df,
        strategy="custom",
        holding_days=10,
        fee_rate=0,
        slippage_rate=0,
        stop_take_basis="intraday",
    )
    assert result.trades.iloc[0]["exit_price"] == 93
    assert result.trades.iloc[0]["exit_reason"] == "손절"


def test_summary_metrics_are_reasonable() -> None:
    df = make_frame()
    df.loc[63, "close"] = 110
    result = SignalBacktestEngine(signal_index=61).run(
        df, strategy="custom", holding_days=1, fee_rate=0, slippage_rate=0
    )
    assert result.trade_count == 1
    assert result.win_rate == 100
    assert result.mdd <= 0
    assert result.average_holding_days == 1.0
