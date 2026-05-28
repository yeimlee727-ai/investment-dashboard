from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from src.analysis.action_plan_generator import (
    build_action_plan_summary,
    build_candidate_action_plan,
)
from src.analysis.candidate_scoring import (
    build_candidate_score_summary,
    score_candidate_records,
)
from src.analysis.decision_support_package import (
    DecisionSupportPackage,
    build_llm_ready_payload,
    build_decision_support_package,
)
from src.analysis.investment_map import (
    build_investment_map_points,
    build_investment_map_summary,
)
from src.analysis.insight_generator import build_mock_insight_report
from src.analysis.portfolio_fit import (
    analyze_candidate_portfolio_fit,
    build_portfolio_fit_summary,
)
from src.analysis.portfolio_market_risk import enrich_portfolio_with_market_risk
from src.analysis.portfolio_risk_insights import (
    build_portfolio_risk_insight_summary,
    build_position_risk_insights,
)


@dataclass(frozen=True)
class EndToEndDecisionSupportDemoResult:
    portfolio_holdings: list[dict[str, Any]]
    candidate_universe: list[dict[str, Any]]
    enriched_portfolio_risk: list[dict[str, Any]]
    portfolio_risk_insights: list[dict[str, Any]]
    investment_map_points: list[dict[str, Any]]
    investment_map_summary: dict[str, Any]
    candidate_scores: list[dict[str, Any]]
    candidate_score_summary: dict[str, Any]
    portfolio_fit_results: list[dict[str, Any]]
    portfolio_fit_summary: dict[str, Any]
    insight_report: dict[str, Any]
    action_plans: list[dict[str, Any]]
    action_plan_summary: dict[str, Any]
    decision_support_package: DecisionSupportPackage
    markdown: str
    llm_ready_payload: dict[str, Any]
    safety_flags: dict[str, bool]


def build_mock_portfolio_holdings() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "AAPL",
            "name": "Apple",
            "sector": "Technology",
            "country": "US",
            "currency": "USD",
            "theme": "Quality growth",
            "weight_pct": 24.0,
        },
        {
            "symbol": "NVDA",
            "name": "NVIDIA",
            "sector": "Technology",
            "country": "US",
            "currency": "USD",
            "theme": "AI infrastructure",
            "weight_pct": 18.0,
        },
        {
            "symbol": "JNJ",
            "name": "Johnson & Johnson",
            "sector": "Healthcare",
            "country": "US",
            "currency": "USD",
            "theme": "Defensive quality",
            "weight_pct": 16.0,
        },
        {
            "symbol": "005930",
            "name": "Samsung Electronics",
            "sector": "Semiconductors",
            "country": "KR",
            "currency": "KRW",
            "theme": "Cyclical technology",
            "weight_pct": 14.0,
        },
    ]


def build_mock_candidate_universe() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "MSFT",
            "name": "Microsoft",
            "market": "US",
            "sector": "Software",
            "country": "US",
            "currency": "USD",
            "theme": "Quality growth",
            "financial_metric_name": "revenue_growth",
            "financial_metric_growth_pct": 32.0,
            "market_reaction_pct": -4.0,
            "total_return_pct": 14.0,
            "annualized_volatility_pct": 21.0,
            "max_drawdown_pct": -11.0,
            "observation_count": 60,
            "risk_data_status": "ok",
            "market_cap": 3_000_000_000_000,
            "volume": 25_000_000,
        },
        {
            "symbol": "TSLA",
            "name": "Tesla",
            "market": "US",
            "sector": "Technology",
            "country": "US",
            "currency": "USD",
            "theme": "High beta growth",
            "financial_metric_name": "operating_income_growth",
            "financial_metric_growth_pct": -8.0,
            "market_reaction_pct": 42.0,
            "total_return_pct": 28.0,
            "annualized_volatility_pct": 58.0,
            "max_drawdown_pct": -38.0,
            "observation_count": 60,
            "risk_data_status": "ok",
            "market_cap": 800_000_000_000,
            "volume": 75_000_000,
        },
        {
            "symbol": "LLY",
            "name": "Eli Lilly",
            "market": "US",
            "sector": "Healthcare",
            "country": "US",
            "currency": "USD",
            "theme": "Healthcare innovation",
            "financial_metric_name": "eps_growth",
            "financial_metric_growth_pct": 18.0,
            "market_reaction_pct": 21.0,
            "total_return_pct": 19.0,
            "annualized_volatility_pct": 24.0,
            "max_drawdown_pct": -14.0,
            "observation_count": 60,
            "risk_data_status": "ok",
            "market_cap": 700_000_000_000,
            "volume": 4_000_000,
        },
        {
            "symbol": "XYZ",
            "name": "Limited Data Example",
            "market": "US",
            "sector": None,
            "country": "US",
            "currency": "USD",
            "theme": "Incomplete data",
            "financial_metric_name": "revenue_growth",
            "financial_metric_growth_pct": None,
            "market_reaction_pct": None,
            "total_return_pct": None,
            "annualized_volatility_pct": None,
            "max_drawdown_pct": None,
            "observation_count": 0,
            "risk_data_status": "missing_price_history",
            "market_cap": None,
            "volume": None,
        },
    ]


def build_mock_price_history_by_symbol() -> dict[str, pd.DataFrame]:
    return {
        "AAPL": _price_history("2026-01-01", [100, 101, 103, 102, 106, 109, 111, 114]),
        "NVDA": _price_history("2026-01-01", [100, 120, 95, 130, 90, 140, 116, 150]),
        "JNJ": _price_history("2026-01-01", [100, 99, 101, 102, 101, 103, 104, 105]),
        "005930": _price_history("2026-01-01", [100, 96, 94, 98, 93, 97, 95, 99]),
    }


def build_mock_market_regime_context() -> dict[str, Any]:
    return {
        "regime_label": "manual neutral regime",
        "risk_level": "normal",
        "macro_notes": "Deterministic mock context for local review only.",
        "data_status": "mock",
    }


def build_mock_decision_support_inputs() -> dict[str, Any]:
    portfolio_context = {
        "position_count": 3,
        "sector_exposure": {"Technology": 42.0, "Healthcare": 18.0, "Cash": 8.0},
        "country_exposure": {"US": 68.0, "KR": 32.0},
        "currency_exposure": {"USD": 68.0, "KRW": 32.0},
        "concentration_notes": "Technology exposure requires manual review.",
    }
    risk_insight_summary = {
        "high_volatility_symbols": ["TSLA"],
        "deep_drawdown_symbols": ["NVDA"],
        "weak_return_symbols": [],
        "overall_risk_note": "Risk review found two positions requiring additional risk checkpoints.",
    }
    investment_map_summary = {
        "total_count": 3,
        "undervalued_discovery_count": 1,
        "chase_risk_count": 1,
        "justified_rise_count": 1,
        "justified_decline_count": 0,
        "insufficient_data_count": 0,
        "top_undervalued_symbols": ["MSFT"],
        "top_chase_risk_symbols": ["TSLA"],
    }
    candidate_score_summary = {
        "total_count": 3,
        "high_priority_review_count": 1,
        "standard_review_count": 1,
        "caution_review_count": 1,
        "insufficient_data_count": 0,
        "top_symbols": ["MSFT", "AAPL", "TSLA"],
        "caution_symbols": ["TSLA"],
        "summary_note": "Candidate scoring identified review candidates and one caution record.",
    }
    portfolio_fit_summary = {
        "total_count": 3,
        "strong_fit_review_count": 1,
        "moderate_fit_review_count": 1,
        "weak_fit_review_count": 1,
        "insufficient_data_count": 0,
        "top_fit_symbols": ["MSFT", "AAPL"],
        "concentration_caution_symbols": ["TSLA"],
        "summary_note": "Portfolio fit review found one concentration caution.",
    }
    market_regime_context = {
        "regime_label": "manual neutral regime",
        "risk_level": "normal",
        "macro_notes": "Manual mock context for local review only.",
        "data_status": "mock",
    }
    insight_report = build_mock_insight_report(
        portfolio_context=portfolio_context,
        risk_insight_summary=risk_insight_summary,
        candidate_score_summary=candidate_score_summary,
        portfolio_fit_summary=portfolio_fit_summary,
        market_regime_context=market_regime_context,
    )
    action_plans = [
        build_candidate_action_plan(
            candidate_score={
                "symbol": "MSFT",
                "name": "Microsoft",
                "candidate_tier": "high_priority_review",
                "reasons": ["Candidate is marked for additional manual review."],
                "cautions": ["Data quality should be reviewed before any decision."],
                "data_status": "ok",
            },
            portfolio_fit_result={
                "symbol": "MSFT",
                "name": "Microsoft",
                "fit_tier": "strong_fit_review",
                "reasons": ["Portfolio fit review is favorable for manual review."],
                "cautions": ["Portfolio context should be reviewed manually."],
                "data_status": "ok",
            },
            market_regime_context=market_regime_context,
        ),
        build_candidate_action_plan(
            candidate_score={
                "symbol": "TSLA",
                "name": "Tesla",
                "candidate_tier": "caution_review",
                "reasons": ["Candidate remains useful for risk-focused review."],
                "cautions": ["Risk checkpoint requires elevated manual attention."],
                "data_status": "ok",
            },
            portfolio_fit_result={
                "symbol": "TSLA",
                "name": "Tesla",
                "fit_tier": "weak_fit_review",
                "reasons": ["Portfolio fit review is classified for caution review."],
                "cautions": ["Concentration caution requires manual validation."],
                "data_status": "ok",
            },
            risk_insights=[
                {
                    "symbol": "TSLA",
                    "insight_type": "high_volatility",
                    "severity": "high",
                    "message": "This position shows elevated annualized volatility.",
                    "data_status": "ok",
                }
            ],
            market_regime_context=market_regime_context,
        ),
    ]
    return {
        "portfolio_context": portfolio_context,
        "risk_insight_summary": risk_insight_summary,
        "investment_map_summary": investment_map_summary,
        "candidate_score_summary": candidate_score_summary,
        "portfolio_fit_summary": portfolio_fit_summary,
        "insight_report": insight_report,
        "action_plan_summary": build_action_plan_summary(action_plans),
        "action_plans": action_plans,
        "market_regime_context": market_regime_context,
    }


def build_mock_decision_support_package() -> DecisionSupportPackage:
    return build_decision_support_package(**build_mock_decision_support_inputs())


def render_mock_decision_support_markdown() -> str:
    return build_mock_decision_support_package().markdown


def build_mock_decision_support_package_dict() -> dict[str, Any]:
    return asdict(build_mock_decision_support_package())


def run_end_to_end_decision_support_demo() -> EndToEndDecisionSupportDemoResult:
    portfolio_holdings = build_mock_portfolio_holdings()
    candidate_universe = build_mock_candidate_universe()
    price_history_by_symbol = build_mock_price_history_by_symbol()
    market_regime_context = build_mock_market_regime_context()

    enriched_result = enrich_portfolio_with_market_risk(
        portfolio_holdings, price_history_by_symbol
    )
    enriched_portfolio = enriched_result.holdings
    portfolio_risk_insights = build_position_risk_insights(enriched_portfolio)
    risk_insight_summary = build_portfolio_risk_insight_summary(enriched_portfolio)

    investment_map_points = build_investment_map_points(candidate_universe)
    investment_map_summary = build_investment_map_summary(investment_map_points)
    candidate_records = _candidate_records_with_map(
        candidate_universe, investment_map_points
    )
    candidate_scores = score_candidate_records(candidate_records)
    candidate_score_summary = build_candidate_score_summary(candidate_scores)
    fit_records = _candidate_records_with_scores(candidate_records, candidate_scores)
    portfolio_fit_results = analyze_candidate_portfolio_fit(
        portfolio_holdings, fit_records
    )
    portfolio_fit_summary = build_portfolio_fit_summary(portfolio_fit_results)

    portfolio_context = _portfolio_context(portfolio_holdings)
    insight_report = build_mock_insight_report(
        portfolio_context=portfolio_context,
        risk_insight_summary=asdict(risk_insight_summary),
        candidate_score_summary=asdict(candidate_score_summary),
        portfolio_fit_summary=asdict(portfolio_fit_summary),
        market_regime_context=market_regime_context,
    )
    fit_by_symbol = {result.symbol: result for result in portfolio_fit_results}
    action_plans = [
        build_candidate_action_plan(
            candidate_score=asdict(score),
            portfolio_fit_result=asdict(fit_by_symbol.get(score.symbol)),
            risk_insights=[
                asdict(insight)
                for insight in portfolio_risk_insights
                if insight.symbol == score.symbol
            ],
            market_regime_context=market_regime_context,
        )
        for score in candidate_scores
        if fit_by_symbol.get(score.symbol) is not None
    ]
    action_plan_summary = build_action_plan_summary(action_plans)
    package = build_decision_support_package(
        portfolio_context=portfolio_context,
        risk_insight_summary=asdict(risk_insight_summary),
        investment_map_summary=asdict(investment_map_summary),
        candidate_score_summary=asdict(candidate_score_summary),
        portfolio_fit_summary=asdict(portfolio_fit_summary),
        insight_report=insight_report,
        action_plan_summary=action_plan_summary,
        action_plans=action_plans,
        market_regime_context=market_regime_context,
    )
    payload = build_llm_ready_payload(package)
    payload["markdown"] = package.markdown
    payload["safety_flags"] = dict(package.safety_flags)

    return EndToEndDecisionSupportDemoResult(
        portfolio_holdings=portfolio_holdings,
        candidate_universe=candidate_universe,
        enriched_portfolio_risk=enriched_portfolio.to_dict("records"),
        portfolio_risk_insights=[
            asdict(insight) for insight in portfolio_risk_insights
        ],
        investment_map_points=[asdict(point) for point in investment_map_points],
        investment_map_summary=asdict(investment_map_summary),
        candidate_scores=[asdict(score) for score in candidate_scores],
        candidate_score_summary=asdict(candidate_score_summary),
        portfolio_fit_results=[asdict(result) for result in portfolio_fit_results],
        portfolio_fit_summary=asdict(portfolio_fit_summary),
        insight_report=asdict(insight_report),
        action_plans=[asdict(plan) for plan in action_plans],
        action_plan_summary=asdict(action_plan_summary),
        decision_support_package=package,
        markdown=package.markdown,
        llm_ready_payload=payload,
        safety_flags=dict(package.safety_flags),
    )


def render_end_to_end_demo_markdown() -> str:
    return run_end_to_end_decision_support_demo().markdown


def build_end_to_end_demo_payload() -> dict[str, Any]:
    return run_end_to_end_decision_support_demo().llm_ready_payload


def _price_history(start: str, close_values: list[float]) -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=len(close_values), freq="D")
    return pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "close": close_values,
        }
    )


def _candidate_records_with_map(
    candidates: list[dict[str, Any]], investment_map_points: Any
) -> list[dict[str, Any]]:
    point_by_symbol = {point.symbol: point for point in investment_map_points}
    records = []
    for candidate in candidates:
        row = dict(candidate)
        point = point_by_symbol.get(str(candidate.get("symbol", "")).upper())
        if point is not None:
            row["quadrant"] = point.quadrant
            row["investment_map_score"] = point.score
            row["data_status"] = point.data_status
        records.append(row)
    return records


def _candidate_records_with_scores(
    candidate_records: list[dict[str, Any]], candidate_scores: Any
) -> list[dict[str, Any]]:
    score_by_symbol = {score.symbol: score for score in candidate_scores}
    records = []
    for candidate in candidate_records:
        row = dict(candidate)
        score = score_by_symbol.get(str(candidate.get("symbol", "")).upper())
        if score is not None:
            row.update(
                {
                    "total_score": score.total_score,
                    "candidate_tier": score.candidate_tier,
                    "opportunity_score": score.opportunity_score,
                    "risk_quality_score": score.risk_quality_score,
                    "momentum_quality_score": score.momentum_quality_score,
                    "data_quality_score": score.data_quality_score,
                    "data_status": score.data_status,
                }
            )
        records.append(row)
    return records


def _portfolio_context(holdings: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(holdings)
    return {
        "position_count": len(holdings),
        "sector_exposure": _exposure(frame, "sector"),
        "country_exposure": _exposure(frame, "country"),
        "currency_exposure": _exposure(frame, "currency"),
        "concentration_notes": "Technology exposure and USD exposure require manual review.",
    }


def _exposure(frame: pd.DataFrame, column: str) -> dict[str, float]:
    if frame.empty or column not in frame or "weight_pct" not in frame:
        return {}
    grouped = frame.groupby(column, dropna=False)["weight_pct"].sum()
    return {str(key): round(float(value), 4) for key, value in grouped.items()}
