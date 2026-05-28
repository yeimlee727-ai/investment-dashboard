import json
import math
import re

from src.analysis import decision_support_package
from src.analysis.action_plan_generator import build_candidate_action_plan
from src.analysis.decision_support_package import (
    DecisionSupportPackageConfig,
    build_decision_support_package,
    build_decision_support_package_summary,
    build_llm_ready_payload,
    render_decision_support_package_markdown,
    sanitize_package_value,
)
from src.analysis.insight_generator import build_mock_insight_report

FORBIDDEN_PATTERNS = [
    r"\bbuy\b",
    r"\bsell\b",
    r"\bhold\b",
    r"\bstrong buy\b",
    r"\btarget price\b",
    r"\bguaranteed return\b",
    r"\bmust profit\b",
    r"\btake profit\b",
    r"\bstop loss\b",
    r"\bentry price\b",
    r"\ballocation percentage\b",
    r"\bexact position size\b",
]


def sample_inputs():
    portfolio_context = {
        "position_count": 3,
        "sector_exposure": {"Technology": 42.0},
        "country_exposure": {"US": 70.0},
        "currency_exposure": {"USD": 70.0},
        "concentration_notes": "Technology exposure requires manual review.",
    }
    risk_insight_summary = {
        "high_volatility_symbols": ["TSLA"],
        "deep_drawdown_symbols": ["NVDA"],
        "weak_return_symbols": [],
        "overall_risk_note": "Portfolio risk review found elevated risk flags.",
    }
    investment_map_summary = {
        "total_count": 2,
        "undervalued_discovery_count": 1,
        "chase_risk_count": 1,
        "top_undervalued_symbols": ["MSFT"],
        "top_chase_risk_symbols": ["TSLA"],
    }
    candidate_score_summary = {
        "total_count": 2,
        "high_priority_review_count": 1,
        "standard_review_count": 1,
        "caution_review_count": 0,
        "insufficient_data_count": 0,
        "top_symbols": ["MSFT", "AAPL"],
        "caution_symbols": ["TSLA"],
        "summary_note": "Candidate scoring produced review records.",
    }
    portfolio_fit_summary = {
        "total_count": 2,
        "strong_fit_review_count": 1,
        "moderate_fit_review_count": 1,
        "weak_fit_review_count": 0,
        "insufficient_data_count": 0,
        "top_fit_symbols": ["MSFT", "AAPL"],
        "concentration_caution_symbols": ["TSLA"],
        "summary_note": "Portfolio fit analysis produced review records.",
    }
    insight_report = build_mock_insight_report(
        portfolio_context=portfolio_context,
        risk_insight_summary=risk_insight_summary,
        candidate_score_summary=candidate_score_summary,
        portfolio_fit_summary=portfolio_fit_summary,
        market_regime_context={"regime_label": "manual neutral", "data_status": "mock"},
    )
    action_plan = build_candidate_action_plan(
        candidate_score={
            "symbol": "MSFT",
            "candidate_tier": "high_priority_review",
            "reasons": ["Candidate is marked for manual review."],
            "cautions": ["Data quality should be reviewed."],
            "data_status": "ok",
        },
        portfolio_fit_result={
            "symbol": "MSFT",
            "fit_tier": "strong_fit_review",
            "reasons": ["Portfolio fit review is favorable."],
            "cautions": ["Concentration caution requires manual review."],
            "data_status": "ok",
        },
    )
    action_plan_summary = {
        "total_count": 1,
        "ready_for_manual_review_count": 1,
        "review_with_caution_count": 0,
        "insufficient_data_count": 0,
        "not_suitable_for_review_count": 0,
        "top_review_symbols": ["MSFT"],
        "caution_symbols": [],
        "summary_note": "Generated conditional review plans.",
    }
    return {
        "portfolio_context": portfolio_context,
        "risk_insight_summary": risk_insight_summary,
        "investment_map_summary": investment_map_summary,
        "candidate_score_summary": candidate_score_summary,
        "portfolio_fit_summary": portfolio_fit_summary,
        "insight_report": insight_report,
        "action_plan_summary": action_plan_summary,
        "action_plans": [action_plan],
        "market_regime_context": {
            "regime_label": "manual neutral",
            "risk_level": "normal",
            "data_status": "mock",
        },
    }


def test_build_decision_support_package_handles_full_inputs():
    package = build_decision_support_package(**sample_inputs())

    assert package.package_version == "0.1"
    assert package.data_status == "ok"
    assert package.safety_flags["decision_support_only"] is True
    assert package.action_plans[0]["symbol"] == "MSFT"
    assert "# Decision-Support Package" in package.markdown


def test_build_decision_support_package_handles_missing_partial_inputs_safely():
    package = build_decision_support_package(
        portfolio_context={"position_count": 1},
        risk_insight_summary=None,
    )

    assert package.data_status == "partial"
    assert package.risk_insight_summary is None
    assert package.action_plans == []
    assert "Not available" in package.markdown


def test_summary_identifies_included_and_missing_sections():
    package = build_decision_support_package(
        portfolio_context={"position_count": 1},
        candidate_score_summary={"total_count": 2, "caution_symbols": ["TSLA"]},
        action_plans=[{"symbol": "MSFT"}],
    )
    summary = build_decision_support_package_summary(package)

    assert "portfolio_context" in summary.included_sections
    assert "candidate_score_summary" in summary.included_sections
    assert "risk_insight_summary" in summary.missing_sections
    assert summary.candidate_review_count == 2
    assert summary.action_plan_count == 1
    assert summary.caution_symbol_count == 1


def test_render_markdown_includes_expected_section_headings():
    package = build_decision_support_package(**sample_inputs())
    markdown = render_decision_support_package_markdown(package)

    assert "## Portfolio Context Summary" in markdown
    assert "## Risk Review Summary" in markdown
    assert "## Candidate Review Summary" in markdown
    assert "## Portfolio Fit Summary" in markdown
    assert "## Action Plan Summary" in markdown
    assert "## Limitations / Disclaimer" in markdown


def test_llm_ready_payload_is_json_serializable():
    package = build_decision_support_package(**sample_inputs())
    payload = build_llm_ready_payload(package)

    dumped = json.dumps(payload, sort_keys=True)

    assert "safety_metadata" in payload
    assert "hidden_prompt" not in dumped
    assert "api_key" not in dumped.lower()


def test_safety_flags_are_included_and_true():
    package = build_decision_support_package(**sample_inputs())
    payload = build_llm_ready_payload(package)

    for key in [
        "decision_support_only",
        "no_real_trading",
        "no_brokerage_api",
        "no_account_lookup",
        "no_order_execution",
    ]:
        assert package.safety_flags[key] is True
        assert payload["safety_metadata"][key] is True


def test_none_nan_inf_values_are_handled_safely():
    package = build_decision_support_package(
        portfolio_context={
            "position_count": math.nan,
            "concentration_notes": math.inf,
            "sector_exposure": {"Tech": -math.inf},
        },
        candidate_score_summary={"total_count": math.inf, "top_symbols": [None]},
        action_plans=[{"symbol": math.nan, "markdown": "-inf"}],
    )
    payload = build_llm_ready_payload(package)
    dumped = json.dumps(payload)

    assert sanitize_package_value(math.nan) is None
    assert not re.search(r"\b(?:nan|inf|-inf)\b", dumped.lower())
    assert not re.search(r"\b(?:nan|inf|-inf)\b", package.markdown.lower())


def test_no_network_yfinance_or_openai_dependency_is_introduced():
    assert not hasattr(decision_support_package, "yfinance")
    assert not hasattr(decision_support_package, "yf")
    assert not hasattr(decision_support_package, "openai")
    assert not hasattr(decision_support_package, "OpenAI")


def test_generated_markdown_avoids_forbidden_recommendation_wording():
    package = build_decision_support_package(**sample_inputs())
    markdown = package.markdown.lower()

    for pattern in FORBIDDEN_PATTERNS:
        assert not re.search(pattern, markdown)


def test_generated_markdown_excludes_price_and_position_size_instructions():
    package = build_decision_support_package(**sample_inputs())
    markdown = package.markdown.lower()

    for phrase in [
        "allocation percentage",
        "target price",
        "entry price",
        "stop loss",
        "take profit",
        "exact position size",
    ]:
        assert phrase not in markdown


def test_no_real_trading_account_or_broker_functionality_is_introduced():
    package = build_decision_support_package(**sample_inputs())
    payload = build_llm_ready_payload(package)
    module_names = dir(decision_support_package)

    assert payload["safety_metadata"]["no_real_trading"] is True
    assert payload["safety_metadata"]["no_account_lookup"] is True
    assert payload["safety_metadata"]["no_brokerage_api"] is True
    assert "place_order" not in module_names
    assert "lookup_account" not in module_names
    assert "Broker" not in module_names


def test_config_can_disable_markdown_and_disclaimer_limitations():
    package = build_decision_support_package(
        **sample_inputs(),
        config=DecisionSupportPackageConfig(
            include_markdown=False,
            include_disclaimer=False,
        ),
    )

    assert package.markdown == ""
    assert package.limitations == ["Package limitations were configured externally."]
