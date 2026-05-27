from __future__ import annotations

import pandas as pd
import pytest

from src.analysis.portfolio_market_risk import (
    RISK_STATUS_INSUFFICIENT_HISTORY,
    RISK_STATUS_INVALID_SYMBOL,
    RISK_STATUS_MISSING_HISTORY,
    RISK_STATUS_OK,
    PortfolioMarketRiskConfig,
    build_portfolio_market_risk_summary,
    enrich_portfolio_with_market_risk,
)


def price_frame(closes: list[object]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "close": closes,
        }
    )


def test_valid_holding_receives_market_risk_metrics() -> None:
    result = enrich_portfolio_with_market_risk(
        [{"symbol": "AAPL", "quantity": 2}],
        {"AAPL": price_frame([100, 110, 105])},
    )

    row = result.holdings.iloc[0]
    assert row["symbol"] == "AAPL"
    assert row["quantity"] == 2
    assert row["total_return_pct"] == pytest.approx(5.0)
    assert row["annualized_volatility_pct"] is not None
    assert row["max_drawdown_pct"] == pytest.approx(-4.545454545454541)
    assert row["observation_count"] == 3
    assert row["risk_data_status"] == RISK_STATUS_OK


def test_multiple_holdings_are_enriched_correctly() -> None:
    result = enrich_portfolio_with_market_risk(
        pd.DataFrame(
            [
                {"symbol": "AAPL", "name": "Apple"},
                {"symbol": "MSFT", "name": "Microsoft"},
            ]
        ),
        {
            "AAPL": price_frame([100, 120]),
            "MSFT": price_frame([50, 55]),
        },
    )

    assert list(result.holdings["symbol"]) == ["AAPL", "MSFT"]
    assert list(result.holdings["risk_data_status"]) == [RISK_STATUS_OK, RISK_STATUS_OK]
    assert result.holdings.loc[0, "name"] == "Apple"
    assert result.holdings.loc[1, "total_return_pct"] == pytest.approx(10.0)


def test_missing_price_history_sets_status_without_crashing() -> None:
    result = enrich_portfolio_with_market_risk(
        [{"symbol": "AAPL"}],
        {},
    )

    row = result.holdings.iloc[0]
    assert row["risk_data_status"] == RISK_STATUS_MISSING_HISTORY
    assert row["observation_count"] == 0
    assert pd.isna(row["total_return_pct"])


def test_empty_holdings_input_is_safe() -> None:
    result = enrich_portfolio_with_market_risk([], {})

    assert result.error is None
    assert result.holdings.empty
    assert result.summary["position_count"] == 0


def test_missing_symbol_column_is_safe() -> None:
    result = enrich_portfolio_with_market_risk(
        [{"ticker": "AAPL"}],
        {"AAPL": price_frame([100, 110])},
    )

    assert result.error == "missing_symbol_column:symbol"
    assert result.holdings.iloc[0]["ticker"] == "AAPL"
    assert result.summary["position_count"] == 1
    assert result.summary["positions_with_risk_data"] == 0


def test_invalid_and_insufficient_price_history_are_safe() -> None:
    result = enrich_portfolio_with_market_risk(
        [{"symbol": ""}, {"symbol": "AAPL"}, {"symbol": "MSFT"}],
        {
            "AAPL": pd.DataFrame({"date": ["2026-01-01"], "open": [100]}),
            "MSFT": price_frame([100]),
        },
    )

    assert list(result.holdings["risk_data_status"]) == [
        RISK_STATUS_INVALID_SYMBOL,
        RISK_STATUS_INSUFFICIENT_HISTORY,
        RISK_STATUS_INSUFFICIENT_HISTORY,
    ]
    assert list(result.holdings["observation_count"]) == [0, 0, 1]


def test_custom_symbol_column_is_supported() -> None:
    result = enrich_portfolio_with_market_risk(
        [{"ticker": "aapl"}],
        {"AAPL": price_frame([100, 110])},
        PortfolioMarketRiskConfig(symbol_column="ticker"),
    )

    assert result.holdings.iloc[0]["symbol"] == "AAPL"
    assert result.holdings.iloc[0]["risk_data_status"] == RISK_STATUS_OK


def test_summary_counts_positions_with_and_without_risk_data() -> None:
    result = enrich_portfolio_with_market_risk(
        [{"symbol": "AAPL"}, {"symbol": "MSFT"}, {"symbol": "MISSING"}],
        {
            "AAPL": price_frame([100, 110, 105]),
            "MSFT": price_frame([50, 55, 60]),
        },
    )

    assert result.summary["position_count"] == 3
    assert result.summary["positions_with_risk_data"] == 2
    assert result.summary["positions_missing_risk_data"] == 1
    assert result.summary["average_total_return_pct"] == pytest.approx(12.5)


def test_summary_identifies_highest_volatility_and_deepest_drawdown() -> None:
    enriched = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "risk_data_status": RISK_STATUS_OK,
                "total_return_pct": 10.0,
                "annualized_volatility_pct": 20.0,
                "max_drawdown_pct": -5.0,
            },
            {
                "symbol": "MSFT",
                "risk_data_status": RISK_STATUS_OK,
                "total_return_pct": 5.0,
                "annualized_volatility_pct": 30.0,
                "max_drawdown_pct": -12.0,
            },
        ]
    )

    summary = build_portfolio_market_risk_summary(enriched)

    assert summary["highest_volatility_symbol"] == "MSFT"
    assert summary["deepest_drawdown_symbol"] == "MSFT"
    assert summary["worst_max_drawdown_pct"] == -12.0


def test_tests_use_supplied_price_history_without_live_network() -> None:
    result = enrich_portfolio_with_market_risk(
        [{"symbol": "AAPL"}],
        {"AAPL": price_frame([100, 101])},
    )

    assert result.holdings.iloc[0]["risk_data_status"] == RISK_STATUS_OK
