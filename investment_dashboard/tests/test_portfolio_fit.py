from __future__ import annotations

import math

from src.analysis.portfolio_fit import (
    FIT_INSUFFICIENT,
    FIT_MODERATE,
    FIT_STRONG,
    PortfolioFitResult,
    analyze_candidate_portfolio_fit,
    build_portfolio_fit_summary,
    calculate_candidate_exposure_impact,
    calculate_exposure_by_field,
    calculate_portfolio_fit,
    normalize_weight_pct,
    score_diversification_fit,
    score_fit_data_quality,
)


def holdings() -> list[dict[str, object]]:
    return [
        {
            "symbol": "AAPL",
            "sector": "Technology",
            "country": "US",
            "currency": "USD",
            "theme": "AI",
            "weight_pct": 42.0,
        },
        {
            "symbol": "MSFT",
            "sector": "Technology",
            "country": "US",
            "currency": "USD",
            "theme": "Cloud",
            "weight_pct": 18.0,
        },
    ]


def candidate(symbol: str = "TSM", **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "sector": "Semiconductors",
        "country": "Taiwan",
        "currency": "TWD",
        "theme": "AI",
        "candidate_tier": "standard_review",
        "total_score": 72.0,
        "opportunity_score": 75.0,
        "risk_quality_score": 70.0,
        "momentum_quality_score": 65.0,
        "data_quality_score": 90.0,
        "annualized_volatility_pct": 25.0,
        "max_drawdown_pct": -15.0,
        "data_status": "ok",
    }
    record.update(overrides)
    return record


def test_underrepresented_sector_receives_stronger_diversification_score() -> None:
    underrepresented = score_diversification_fit(holdings(), candidate("TSM"))
    concentrated = score_diversification_fit(
        holdings(), candidate("NVDA", sector="Technology", country="US", currency="USD")
    )

    assert underrepresented > concentrated


def test_concentrated_sector_receives_concentration_caution() -> None:
    result = calculate_portfolio_fit(
        holdings(), candidate("NVDA", sector="Technology", country="US", currency="USD")
    )

    assert result.exposure_impacts["sector"]["status"] == "elevated"
    assert any("concentrated exposure" in caution for caution in result.cautions)


def test_missing_candidate_metadata_lowers_data_quality_score() -> None:
    complete = score_fit_data_quality(holdings(), candidate("TSM"))
    incomplete = score_fit_data_quality(
        holdings(), candidate("UNK", sector=None, country=None, currency=None)
    )

    assert incomplete < complete


def test_missing_portfolio_weight_pct_is_handled_safely() -> None:
    exposure = calculate_exposure_by_field(
        [{"symbol": "AAPL", "sector": "Technology"}], "sector"
    )

    assert exposure == {"Technology": 0.0}
    assert normalize_weight_pct(math.inf) == 0.0
    assert normalize_weight_pct(-5) == 0.0


def test_empty_holdings_are_handled_safely() -> None:
    result = calculate_portfolio_fit([], candidate("TSM"))

    assert isinstance(result, PortfolioFitResult)
    assert result.fit_score > 0
    assert result.data_quality_score < 100


def test_empty_candidates_are_handled_safely() -> None:
    assert analyze_candidate_portfolio_fit(holdings(), []) == []


def test_analyze_candidate_portfolio_fit_sorts_by_fit_score_descending() -> None:
    results = analyze_candidate_portfolio_fit(
        holdings(),
        [
            candidate(
                "LOW", sector="Technology", country="US", currency="USD", total_score=40
            ),
            candidate("HIGH", total_score=90),
        ],
    )

    assert [result.symbol for result in results] == ["HIGH", "LOW"]


def test_build_portfolio_fit_summary_counts_fit_tiers() -> None:
    results = [
        PortfolioFitResult("A", None, 75, FIT_STRONG, 80, 80, 80, 80, {}, [], [], "ok"),
        PortfolioFitResult(
            "B", None, 55, FIT_MODERATE, 60, 60, 60, 60, {}, [], [], "ok"
        ),
        PortfolioFitResult(
            "C", None, 30, "weak_fit_review", 30, 30, 30, 60, {}, [], [], "ok"
        ),
        PortfolioFitResult(
            "D", None, 30, FIT_INSUFFICIENT, 30, 30, 30, 30, {}, [], [], "missing"
        ),
    ]

    summary = build_portfolio_fit_summary(results)

    assert summary.total_count == 4
    assert summary.strong_fit_review_count == 1
    assert summary.moderate_fit_review_count == 1
    assert summary.weak_fit_review_count == 1
    assert summary.insufficient_data_count == 1
    assert summary.top_fit_symbols == ["A", "B", "C", "D"]


def test_concentration_caution_symbols_are_identified() -> None:
    result = calculate_portfolio_fit(
        holdings(), candidate("NVDA", sector="Technology", country="US", currency="USD")
    )
    summary = build_portfolio_fit_summary([result])

    assert summary.concentration_caution_symbols == ["NVDA"]


def test_none_nan_inf_values_are_handled_safely() -> None:
    result = calculate_portfolio_fit(
        [{"symbol": "A", "sector": None, "country": math.nan, "weight_pct": math.inf}],
        candidate(
            "SAFE",
            total_score=math.inf,
            annualized_volatility_pct=-math.inf,
            max_drawdown_pct=None,
            sector=None,
            country=None,
            currency=None,
        ),
    )

    assert result.fit_score >= 0
    assert result.data_quality_score < 60


def test_exposure_impact_marks_underrepresented_metadata_positive() -> None:
    impacts = calculate_candidate_exposure_impact(holdings(), candidate("TSM"))

    assert impacts["sector"]["status"] == "positive"
    assert impacts["country"]["status"] == "positive"


def test_no_network_or_yfinance_dependency_is_introduced() -> None:
    import src.analysis.portfolio_fit as module

    assert not hasattr(module, "yfinance")
    assert not hasattr(module, "yf")


def test_no_recommendation_or_allocation_wording_in_messages() -> None:
    result = calculate_portfolio_fit(
        holdings(), candidate("NVDA", sector="Technology", country="US", currency="USD")
    )
    text = " ".join(result.reasons + result.cautions).lower()

    for forbidden in [
        "buy",
        "sell",
        "hold",
        "target price",
        "guaranteed",
        "entry price",
        "stop loss",
        "take profit",
        "allocate",
        "allocation percentage",
    ]:
        assert forbidden not in text
