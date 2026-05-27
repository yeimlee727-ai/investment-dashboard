from __future__ import annotations

import math

import pandas as pd
import pytest

from src.analysis.investment_map import (
    QUADRANT_CHASE_RISK,
    QUADRANT_INSUFFICIENT_DATA,
    QUADRANT_JUSTIFIED_DECLINE,
    QUADRANT_JUSTIFIED_RISE,
    QUADRANT_UNDERVALUED_DISCOVERY,
    STATUS_INSUFFICIENT_DATA,
    STATUS_INVALID_FINANCIAL,
    InvestmentMapPoint,
    build_investment_map_points,
    build_investment_map_summary,
    calculate_investment_map_score,
    classify_investment_map_quadrant,
    safe_growth_pct,
)


def record(
    symbol: str,
    financial_metric_growth_pct: object,
    market_reaction_pct: object,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "market": "US",
        "financial_metric_name": "revenue_growth",
        "financial_metric_growth_pct": financial_metric_growth_pct,
        "market_reaction_pct": market_reaction_pct,
        "market_cap": 1_000_000,
    }


def test_positive_financial_growth_low_market_reaction_is_undervalued_discovery() -> (
    None
):
    assert (
        classify_investment_map_quadrant(12.0, -3.0) == QUADRANT_UNDERVALUED_DISCOVERY
    )


def test_weak_financial_growth_positive_market_reaction_is_chase_risk() -> None:
    assert classify_investment_map_quadrant(-2.0, 20.0) == QUADRANT_CHASE_RISK


def test_positive_financial_growth_positive_market_reaction_is_justified_rise() -> None:
    assert classify_investment_map_quadrant(8.0, 9.0) == QUADRANT_JUSTIFIED_RISE


def test_negative_financial_growth_negative_market_reaction_is_justified_decline() -> (
    None
):
    assert classify_investment_map_quadrant(-8.0, -9.0) == QUADRANT_JUSTIFIED_DECLINE


def test_missing_or_invalid_data_is_insufficient_data() -> None:
    assert classify_investment_map_quadrant(None, 10.0) == QUADRANT_INSUFFICIENT_DATA
    assert (
        classify_investment_map_quadrant(math.inf, 10.0) == QUADRANT_INSUFFICIENT_DATA
    )


def test_safe_growth_pct_calculates_growth_correctly() -> None:
    assert safe_growth_pct(100, 125) == pytest.approx(25.0)


def test_safe_growth_pct_handles_previous_zero_safely() -> None:
    assert safe_growth_pct(0, 125) is None


def test_none_nan_inf_values_are_handled_safely() -> None:
    for value in [None, math.nan, math.inf, -math.inf, "invalid"]:
        assert safe_growth_pct(value, 125) is None
        assert safe_growth_pct(100, value) is None


def test_build_investment_map_points_returns_deterministic_records() -> None:
    points = build_investment_map_points(
        [
            record("aapl", 12.0, -3.0),
            record("msft", -2.0, 20.0),
        ]
    )

    assert points == [
        InvestmentMapPoint(
            symbol="AAPL",
            name="aapl Corp",
            market="US",
            financial_metric_name="revenue_growth",
            financial_metric_growth_pct=12.0,
            market_reaction_pct=-3.0,
            market_cap=1_000_000.0,
            quadrant=QUADRANT_UNDERVALUED_DISCOVERY,
            score=15.0,
            data_status="ok",
        ),
        InvestmentMapPoint(
            symbol="MSFT",
            name="msft Corp",
            market="US",
            financial_metric_name="revenue_growth",
            financial_metric_growth_pct=-2.0,
            market_reaction_pct=20.0,
            market_cap=1_000_000.0,
            quadrant=QUADRANT_CHASE_RISK,
            score=22.0,
            data_status="ok",
        ),
    ]


def test_points_can_calculate_growth_from_previous_and_current_values() -> None:
    points = build_investment_map_points(
        [
            {
                "symbol": "NVDA",
                "previous_financial_metric": 100,
                "current_financial_metric": 130,
                "previous_market_value": 200,
                "current_market_value": 210,
            }
        ]
    )

    point = points[0]
    assert point.financial_metric_growth_pct == pytest.approx(30.0)
    assert point.market_reaction_pct == pytest.approx(5.0)
    assert point.quadrant == QUADRANT_JUSTIFIED_RISE


def test_missing_symbol_and_metric_columns_do_not_crash() -> None:
    points = build_investment_map_points(pd.DataFrame([{"name": "No Symbol"}]))

    assert points[0].symbol == ""
    assert points[0].quadrant == QUADRANT_INSUFFICIENT_DATA
    assert points[0].data_status == STATUS_INSUFFICIENT_DATA


def test_invalid_financial_or_market_metric_status_is_reported() -> None:
    points = build_investment_map_points(
        [
            {
                "symbol": "A",
                "financial_metric_growth_pct": None,
                "market_reaction_pct": 1,
            },
            {
                "symbol": "B",
                "financial_metric_growth_pct": 1,
                "market_reaction_pct": None,
            },
        ]
    )

    assert points[0].data_status == STATUS_INVALID_FINANCIAL
    assert points[1].data_status == "invalid_market_reaction"


def test_build_investment_map_summary_counts_each_quadrant() -> None:
    points = build_investment_map_points(
        [
            record("UNDER", 12.0, -3.0),
            record("CHASE", -2.0, 20.0),
            record("RISE", 8.0, 9.0),
            record("DECLINE", -8.0, -9.0),
            record("MISSING", None, None),
        ]
    )

    summary = build_investment_map_summary(points)

    assert summary.total_count == 5
    assert summary.undervalued_discovery_count == 1
    assert summary.chase_risk_count == 1
    assert summary.justified_rise_count == 1
    assert summary.justified_decline_count == 1
    assert summary.insufficient_data_count == 1


def test_top_symbols_are_sorted_by_score() -> None:
    points = build_investment_map_points(
        [
            record("UNDER_LOW", 8.0, -1.0),
            record("UNDER_HIGH", 30.0, -10.0),
            record("CHASE_LOW", -1.0, 1.0),
            record("CHASE_HIGH", -20.0, 50.0),
        ]
    )

    summary = build_investment_map_summary(points)

    assert summary.top_undervalued_symbols == ["UNDER_HIGH", "UNDER_LOW"]
    assert summary.top_chase_risk_symbols == ["CHASE_HIGH", "CHASE_LOW"]


def test_score_is_zero_for_missing_data_and_not_a_recommendation() -> None:
    assert calculate_investment_map_score(None, None) == 0.0


def test_no_network_or_yfinance_dependency_is_introduced() -> None:
    import src.analysis.investment_map as module

    assert not hasattr(module, "yfinance")
    assert not hasattr(module, "yf")
