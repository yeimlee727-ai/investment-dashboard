from __future__ import annotations

import math

import pandas as pd

from src.analysis.portfolio_risk_insights import (
    PortfolioRiskInsight,
    PortfolioRiskInsightSummary,
    build_portfolio_risk_insight_summary,
    build_position_risk_insights,
    classify_drawdown_level,
    classify_total_return_level,
    classify_volatility_level,
)


def enriched_row(
    symbol: str = "AAPL",
    total_return_pct: object = 5.0,
    annualized_volatility_pct: object = 12.0,
    max_drawdown_pct: object = -5.0,
    risk_data_status: str = "ok",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "total_return_pct": total_return_pct,
        "annualized_volatility_pct": annualized_volatility_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "observation_count": 30,
        "risk_data_status": risk_data_status,
    }


def insight_types(insights: list[PortfolioRiskInsight]) -> list[str]:
    return [insight.insight_type for insight in insights]


def test_high_annualized_volatility_produces_high_volatility_insight() -> None:
    insights = build_position_risk_insights(
        [enriched_row(annualized_volatility_pct=45.0)]
    )

    assert "high_volatility" in insight_types(insights)
    assert insights[0].severity == "caution"
    assert "elevated annualized volatility" in insights[0].message


def test_deep_max_drawdown_produces_deep_drawdown_insight() -> None:
    insights = build_position_risk_insights([enriched_row(max_drawdown_pct=-30.0)])

    assert "deep_drawdown" in insight_types(insights)
    assert insights[0].severity == "high"
    assert "deep historical drawdown" in insights[0].message


def test_weak_total_return_produces_weak_return_insight() -> None:
    insights = build_position_risk_insights([enriched_row(total_return_pct=-10.0)])

    assert "weak_return" in insight_types(insights)
    assert insights[0].severity == "watch"


def test_missing_price_history_produces_missing_risk_data_insight() -> None:
    insights = build_position_risk_insights(
        [enriched_row(risk_data_status="missing_price_history")]
    )

    assert insight_types(insights) == ["missing_risk_data"]
    assert insights[0].data_status == "missing_price_history"


def test_insufficient_risk_data_produces_insufficient_insight() -> None:
    insights = build_position_risk_insights(
        [enriched_row(risk_data_status="insufficient_price_history")]
    )

    assert insight_types(insights) == ["insufficient_risk_data"]
    assert insights[0].severity == "watch"


def test_normal_low_risk_row_produces_balanced_risk_profile() -> None:
    insights = build_position_risk_insights([enriched_row()])

    assert insight_types(insights) == ["balanced_risk_profile"]
    assert insights[0].severity == "info"


def test_empty_dataframe_is_handled_safely() -> None:
    insights = build_position_risk_insights(pd.DataFrame())
    summary = build_portfolio_risk_insight_summary(pd.DataFrame())

    assert insights == []
    assert isinstance(summary, PortfolioRiskInsightSummary)
    assert summary.position_count == 0


def test_missing_metric_columns_are_handled_safely() -> None:
    insights = build_position_risk_insights(pd.DataFrame([{"symbol": "AAPL"}]))

    assert insight_types(insights) == ["missing_risk_data"]
    assert insights[0].supporting_metrics["total_return_pct"] is None


def test_none_nan_inf_values_are_handled_safely() -> None:
    insights = build_position_risk_insights(
        [
            enriched_row(
                total_return_pct=None,
                annualized_volatility_pct=math.inf,
                max_drawdown_pct=float("nan"),
            )
        ]
    )

    assert insight_types(insights) == ["balanced_risk_profile"]
    assert insights[0].supporting_metrics["annualized_volatility_pct"] is None
    assert classify_volatility_level(math.inf) == "unknown"
    assert classify_drawdown_level(float("nan")) == "unknown"
    assert classify_total_return_level(None) == "unknown"


def test_portfolio_summary_counts_severity_levels() -> None:
    summary = build_portfolio_risk_insight_summary(
        [
            enriched_row("HIGHVOL", annualized_volatility_pct=60.0),
            enriched_row("DEEP", max_drawdown_pct=-35.0),
            enriched_row("WEAK", total_return_pct=-20.0),
            enriched_row("MISS", risk_data_status="missing_price_history"),
        ]
    )

    assert summary.position_count == 4
    assert summary.high_severity_count == 1
    assert summary.caution_count == 1
    assert summary.watch_count == 2
    assert summary.missing_data_count == 1


def test_summary_identifies_flagged_symbols() -> None:
    summary = build_portfolio_risk_insight_summary(
        [
            enriched_row("HIGHVOL", annualized_volatility_pct=60.0),
            enriched_row("DEEP", max_drawdown_pct=-35.0),
            enriched_row("WEAK", total_return_pct=-20.0),
        ]
    )

    assert summary.high_volatility_symbols == ["HIGHVOL"]
    assert summary.deep_drawdown_symbols == ["DEEP"]
    assert summary.weak_return_symbols == ["WEAK"]
    assert summary.top_risk_symbols == ["HIGHVOL", "DEEP", "WEAK"]
    assert "Portfolio risk review found 3 positions" in summary.overall_risk_note


def test_no_network_or_yfinance_dependency_is_introduced() -> None:
    import src.analysis.portfolio_risk_insights as module

    assert not hasattr(module, "yfinance")
    assert not hasattr(module, "yf")


def test_messages_do_not_include_recommendation_language() -> None:
    insights = build_position_risk_insights(
        [
            enriched_row(annualized_volatility_pct=60.0),
            enriched_row(max_drawdown_pct=-35.0),
            enriched_row(total_return_pct=-20.0),
            enriched_row(risk_data_status="missing_price_history"),
        ]
    )
    text = " ".join(insight.message.lower() for insight in insights)

    for forbidden in ["buy", "sell", "hold", "guaranteed", "target price"]:
        assert forbidden not in text
