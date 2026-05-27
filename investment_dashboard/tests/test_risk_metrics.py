from __future__ import annotations

import math

import pandas as pd
import pytest

from src.analysis.risk_metrics import (
    RiskMetricResult,
    build_risk_metric_result,
    calculate_annualized_volatility_pct,
    calculate_daily_returns,
    calculate_max_drawdown_pct,
    calculate_total_return_pct,
)


def price_frame(closes: list[object]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "close": closes,
        }
    )


def test_total_return_is_calculated_correctly() -> None:
    assert calculate_total_return_pct(price_frame([100, 110])) == pytest.approx(10.0)


def test_max_drawdown_is_calculated_correctly() -> None:
    result = calculate_max_drawdown_pct(price_frame([100, 120, 90, 105]))

    assert result == -25.0


def test_annualized_volatility_returns_valid_value_for_normal_data() -> None:
    result = calculate_annualized_volatility_pct(price_frame([100, 101, 99, 104]))

    assert result is not None
    assert result > 0
    assert math.isfinite(result)


def test_empty_dataframe_is_handled_safely() -> None:
    frame = pd.DataFrame()

    assert calculate_daily_returns(frame).empty
    assert calculate_total_return_pct(frame) is None
    assert calculate_annualized_volatility_pct(frame) is None
    assert calculate_max_drawdown_pct(frame) is None


def test_missing_close_column_is_handled_safely() -> None:
    frame = pd.DataFrame({"date": ["2026-01-01"], "open": [100]})

    assert calculate_daily_returns(frame).empty
    assert build_risk_metric_result(frame, "AAPL").observation_count == 0


def test_none_nan_inf_values_are_handled_safely() -> None:
    frame = price_frame([100, None, float("nan"), float("inf"), -float("inf"), 110])

    result = build_risk_metric_result(frame, "AAPL")

    assert result.observation_count == 2
    assert result.total_return_pct == pytest.approx(10.0)
    assert calculate_daily_returns(frame).iloc[0] == pytest.approx(0.1)


def test_starting_price_zero_does_not_divide_by_zero() -> None:
    frame = price_frame([0, 10, 20])

    assert calculate_total_return_pct(frame) is None


def test_risk_metric_result_contains_expected_fields() -> None:
    result = build_risk_metric_result(price_frame([100, 110, 105]), "aapl")

    assert isinstance(result, RiskMetricResult)
    assert result.symbol == "AAPL"
    assert result.observation_count == 3
    assert result.start_date == "2026-01-01"
    assert result.end_date == "2026-01-03"
    assert result.total_return_pct == pytest.approx(5.0)
    assert result.annualized_volatility_pct is not None
    assert result.max_drawdown_pct is not None
