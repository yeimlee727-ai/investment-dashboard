from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.analysis.action_plan_generator import (
    build_action_plan_summary,
    build_candidate_action_plan,
)
from src.analysis.decision_support_package import (
    DecisionSupportPackage,
    build_decision_support_package,
)
from src.analysis.insight_generator import build_mock_insight_report


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
