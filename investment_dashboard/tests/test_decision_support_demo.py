import re

from src.analysis import decision_support_demo
from src.analysis.decision_support_demo import (
    build_mock_decision_support_inputs,
    build_mock_decision_support_package,
    render_mock_decision_support_markdown,
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
