import json
import re

from src.analysis import decision_support_demo
from src.analysis.decision_support_demo import (
    build_end_to_end_demo_payload,
    build_mock_decision_support_inputs,
    build_mock_decision_support_package,
    render_mock_decision_support_markdown,
    render_end_to_end_demo_markdown,
    run_end_to_end_decision_support_demo,
)
from src.analysis.decision_support_package import DecisionSupportPackage

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


def test_build_mock_decision_support_package_returns_valid_package() -> None:
    package = build_mock_decision_support_package()

    assert isinstance(package, DecisionSupportPackage)
    assert package.package_version == "0.1"
    assert package.data_status == "ok"
    assert package.candidate_score_summary is not None
    assert package.portfolio_fit_summary is not None
    assert package.action_plans


def test_demo_package_includes_required_safety_flags() -> None:
    package = build_mock_decision_support_package()

    for flag in [
        "decision_support_only",
        "no_real_trading",
        "no_brokerage_api",
        "no_account_lookup",
        "no_order_execution",
    ]:
        assert package.safety_flags[flag] is True


def test_demo_markdown_is_deterministic_and_contains_key_headings() -> None:
    first = render_mock_decision_support_markdown()
    second = render_mock_decision_support_markdown()

    assert first == second
    assert "# Decision-Support Package" in first
    assert "## Portfolio Context Summary" in first
    assert "## Risk Review Summary" in first
    assert "## Candidate Review Summary" in first
    assert "## Portfolio Fit Summary" in first
    assert "## Action Plan Summary" in first


def test_demo_workflow_does_not_expose_external_api_dependencies() -> None:
    inputs = build_mock_decision_support_inputs()

    assert inputs["market_regime_context"]["data_status"] == "mock"
    assert not hasattr(decision_support_demo, "yfinance")
    assert not hasattr(decision_support_demo, "yf")
    assert not hasattr(decision_support_demo, "openai")
    assert not hasattr(decision_support_demo, "OpenAI")
    assert not hasattr(decision_support_demo, "mcp")


def test_demo_text_avoids_forbidden_recommendation_wording() -> None:
    package = build_mock_decision_support_package()
    text = "\n".join(
        [
            package.markdown,
            str(package.portfolio_context),
            str(package.risk_insight_summary),
            str(package.candidate_score_summary),
            str(package.portfolio_fit_summary),
        ]
    ).lower()

    for pattern in FORBIDDEN_PATTERNS:
        assert not re.search(pattern, text)


def test_demo_inputs_are_safe_local_mock_records() -> None:
    inputs = build_mock_decision_support_inputs()

    assert inputs["portfolio_context"]["position_count"] == 3
    assert inputs["investment_map_summary"]["total_count"] == 3
    assert inputs["candidate_score_summary"]["total_count"] == 3
    assert inputs["portfolio_fit_summary"]["total_count"] == 3


def test_end_to_end_demo_returns_complete_result() -> None:
    result = run_end_to_end_decision_support_demo()

    assert result.portfolio_holdings
    assert result.candidate_universe
    assert result.enriched_portfolio_risk
    assert result.portfolio_risk_insights
    assert result.investment_map_summary["total_count"] == 4
    assert result.candidate_score_summary["total_count"] == 4
    assert result.portfolio_fit_summary["total_count"] == 4
    assert result.action_plan_summary["total_count"] == 4
    assert result.decision_support_package.data_status in {"ok", "partial"}


def test_end_to_end_demo_outputs_markdown_and_json_payload() -> None:
    result = run_end_to_end_decision_support_demo()
    payload = build_end_to_end_demo_payload()

    assert result.markdown
    assert render_end_to_end_demo_markdown() == result.markdown
    json.dumps(result.llm_ready_payload, sort_keys=True)
    json.dumps(payload, sort_keys=True)
    assert "markdown" in payload
    assert "safety_flags" in payload


def test_end_to_end_demo_safety_flags_are_true() -> None:
    result = run_end_to_end_decision_support_demo()

    for flag in [
        "decision_support_only",
        "no_real_trading",
        "no_brokerage_api",
        "no_account_lookup",
        "no_order_execution",
    ]:
        assert result.safety_flags[flag] is True
        assert result.llm_ready_payload["safety_flags"][flag] is True


def test_end_to_end_demo_produces_sorted_candidate_scores_and_fit_results() -> None:
    result = run_end_to_end_decision_support_demo()
    candidate_scores = result.candidate_scores
    fit_results = result.portfolio_fit_results

    assert candidate_scores
    assert fit_results
    assert result.action_plans
    assert candidate_scores == sorted(
        candidate_scores, key=lambda row: (-row["total_score"], row["symbol"])
    )
    assert fit_results == sorted(
        fit_results, key=lambda row: (-row["fit_score"], row["symbol"])
    )


def test_end_to_end_demo_contains_varied_candidate_outcomes() -> None:
    result = run_end_to_end_decision_support_demo()
    tiers = {row["candidate_tier"] for row in result.candidate_scores}
    quadrants = {row["quadrant"] for row in result.investment_map_points}

    assert "high_priority_review" in tiers
    assert "caution_review" in tiers
    assert "insufficient_data" in tiers
    assert "chase_risk" in quadrants
    assert result.portfolio_fit_summary["concentration_caution_symbols"]


def test_end_to_end_demo_does_not_import_network_openai_mcp_or_broker() -> None:
    assert not hasattr(decision_support_demo, "yfinance")
    assert not hasattr(decision_support_demo, "yf")
    assert not hasattr(decision_support_demo, "openai")
    assert not hasattr(decision_support_demo, "OpenAI")
    assert not hasattr(decision_support_demo, "mcp")
    assert not hasattr(decision_support_demo, "MockBroker")
    assert not hasattr(decision_support_demo, "TossBrokerPlaceholder")


def test_end_to_end_demo_markdown_avoids_forbidden_wording() -> None:
    text = render_end_to_end_demo_markdown().lower()

    for pattern in FORBIDDEN_PATTERNS:
        assert not re.search(pattern, text)


def test_end_to_end_demo_payload_avoids_forbidden_trade_command_wording() -> None:
    payload_text = json.dumps(build_end_to_end_demo_payload(), sort_keys=True).lower()

    assert "api_key" not in payload_text
    assert "hidden_prompt" not in payload_text
    for pattern in FORBIDDEN_PATTERNS:
        assert not re.search(pattern, payload_text)
