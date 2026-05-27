from __future__ import annotations

import math

import pandas as pd

from src.analysis.candidate_scoring import (
    TIER_CAUTION,
    TIER_HIGH_PRIORITY,
    TIER_INSUFFICIENT,
    TIER_STANDARD,
    CandidateScore,
    build_candidate_score_summary,
    calculate_candidate_score,
    clamp_score,
    score_candidate_records,
    score_data_quality_component,
    score_momentum_quality_component,
    score_risk_quality_component,
)


def candidate(
    symbol: str,
    quadrant: str = "undervalued_discovery",
    investment_map_score: object = 50.0,
    financial_metric_growth_pct: object = 20.0,
    market_reaction_pct: object = 0.0,
    total_return_pct: object = 8.0,
    annualized_volatility_pct: object = 15.0,
    max_drawdown_pct: object = -8.0,
    observation_count: object = 60,
    risk_data_status: str = "ok",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "market": "US",
        "quadrant": quadrant,
        "investment_map_score": investment_map_score,
        "financial_metric_growth_pct": financial_metric_growth_pct,
        "market_reaction_pct": market_reaction_pct,
        "total_return_pct": total_return_pct,
        "annualized_volatility_pct": annualized_volatility_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "observation_count": observation_count,
        "risk_data_status": risk_data_status,
    }


def test_undervalued_discovery_scores_higher_than_chase_risk() -> None:
    undervalued = calculate_candidate_score(candidate("UNDER"))
    chase = calculate_candidate_score(
        candidate(
            "CHASE",
            quadrant="chase_risk",
            investment_map_score=80,
            financial_metric_growth_pct=-5,
            market_reaction_pct=50,
        )
    )

    assert undervalued.total_score > chase.total_score
    assert undervalued.candidate_tier in {TIER_HIGH_PRIORITY, TIER_STANDARD}
    assert chase.candidate_tier == TIER_CAUTION


def test_chase_risk_is_penalized_even_with_high_market_reaction() -> None:
    record = candidate(
        "CHASE",
        quadrant="chase_risk",
        financial_metric_growth_pct=-10,
        market_reaction_pct=80,
        total_return_pct=50,
    )

    assert score_momentum_quality_component(record) <= 40
    assert calculate_candidate_score(record).candidate_tier == TIER_CAUTION


def test_high_volatility_lowers_risk_quality_score() -> None:
    low_vol = score_risk_quality_component(
        candidate("LOW", annualized_volatility_pct=15)
    )
    high_vol = score_risk_quality_component(
        candidate("HIGH", annualized_volatility_pct=55)
    )

    assert high_vol < low_vol


def test_deep_drawdown_lowers_risk_quality_score() -> None:
    controlled = score_risk_quality_component(candidate("OK", max_drawdown_pct=-5))
    deep = score_risk_quality_component(candidate("DEEP", max_drawdown_pct=-35))

    assert deep < controlled


def test_missing_risk_data_lowers_data_quality_and_produces_caution() -> None:
    record = candidate(
        "MISS",
        risk_data_status="missing_price_history",
        observation_count=0,
    )
    score = calculate_candidate_score(record)

    assert score_data_quality_component(record) < 40
    assert any("Data quality is limited" in caution for caution in score.cautions)


def test_insufficient_data_quadrant_produces_insufficient_tier() -> None:
    score = calculate_candidate_score(candidate("BAD", quadrant="insufficient_data"))

    assert score.candidate_tier == TIER_INSUFFICIENT
    assert score.total_score < 50


def test_score_candidate_records_sorts_by_total_score_descending() -> None:
    scores = score_candidate_records(
        pd.DataFrame(
            [
                candidate("LOW", quadrant="justified_decline", investment_map_score=0),
                candidate("HIGH", investment_map_score=80),
                candidate("MID", quadrant="justified_rise", investment_map_score=20),
            ]
        )
    )

    assert [score.symbol for score in scores] == ["HIGH", "MID", "LOW"]


def test_build_candidate_score_summary_counts_tiers() -> None:
    scores = [
        CandidateScore(
            "A", None, None, 75, 80, 80, 70, 90, TIER_HIGH_PRIORITY, [], [], "ok"
        ),
        CandidateScore(
            "B", None, None, 60, 60, 60, 60, 90, TIER_STANDARD, [], [], "ok"
        ),
        CandidateScore("C", None, None, 30, 10, 50, 30, 90, TIER_CAUTION, [], [], "ok"),
        CandidateScore(
            "D", None, None, 20, 10, 30, 20, 10, TIER_INSUFFICIENT, [], [], "missing"
        ),
    ]

    summary = build_candidate_score_summary(scores)

    assert summary.total_count == 4
    assert summary.high_priority_review_count == 1
    assert summary.standard_review_count == 1
    assert summary.caution_review_count == 1
    assert summary.insufficient_data_count == 1
    assert summary.top_symbols == ["A", "B", "C", "D"]
    assert summary.caution_symbols == ["C", "D"]


def test_none_nan_inf_values_are_handled_safely() -> None:
    record = candidate(
        "SAFE",
        investment_map_score=math.inf,
        total_return_pct=math.nan,
        annualized_volatility_pct=-math.inf,
        max_drawdown_pct=None,
        observation_count=None,
    )
    score = calculate_candidate_score(record)

    assert clamp_score(math.inf) == 0.0
    assert score.total_score >= 0
    assert score.risk_quality_score == 35.0


def test_empty_input_is_handled_safely() -> None:
    assert score_candidate_records([]) == []
    assert build_candidate_score_summary([]).total_count == 0


def test_no_network_or_yfinance_dependency_is_introduced() -> None:
    import src.analysis.candidate_scoring as module

    assert not hasattr(module, "yfinance")
    assert not hasattr(module, "yf")


def test_no_buy_sell_hold_wording_appears_in_reasons_or_cautions() -> None:
    scores = score_candidate_records(
        [
            candidate("UNDER"),
            candidate("CHASE", quadrant="chase_risk", market_reaction_pct=80),
            candidate("MISS", risk_data_status="missing_price_history"),
        ]
    )
    text = " ".join(
        " ".join(score.reasons + score.cautions).lower() for score in scores
    )

    for forbidden in [
        "buy",
        "sell",
        "hold",
        "strong buy",
        "target price",
        "guaranteed",
    ]:
        assert forbidden not in text
