import json
import math
import re

import pandas as pd

from src.analysis import decision_support_demo
from src.analysis.decision_support_demo import (
    build_csv_input_decision_support_payload,
    render_csv_input_decision_support_markdown,
    run_csv_input_decision_support_pipeline,
)
from src.analysis.decision_support_inputs import (
    build_csv_input_decision_support_context,
    normalize_candidate_universe_input,
    normalize_portfolio_holdings_input,
    validate_candidate_universe_input,
    validate_portfolio_holdings_input,
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


def test_valid_portfolio_csv_like_frame_normalizes_correctly() -> None:
    frame = pd.DataFrame(
        {
            " Symbol ": [" msft ", "msft", "aapl"],
            "Weight %": [12.5, 15.0, -3.0],
            "Sector": [" Software ", "Software", " Technology "],
        }
    )

    normalized = normalize_portfolio_holdings_input(frame)
    validation = validate_portfolio_holdings_input(frame)

    assert list(normalized["symbol"]) == ["MSFT", "AAPL"]
    assert normalized.loc[0, "sector"] == "Software"
    assert normalized.loc[1, "weight_pct"] == 0.0
    assert validation.is_valid is True
    assert "Duplicate symbols detected; keeping first record." in validation.warnings
    assert "Negative weight_pct values were clamped to 0." in validation.warnings


def test_valid_candidate_csv_like_frame_normalizes_correctly() -> None:
    frame = pd.DataFrame(
        {
            "Symbol": [" msft "],
            "Financial Metric Growth Pct": ["20"],
            "Market Reaction Pct": ["-2.5"],
            "Risk Data Status": [None],
        }
    )

    normalized = normalize_candidate_universe_input(frame)
    validation = validate_candidate_universe_input(frame)

    assert normalized.loc[0, "symbol"] == "MSFT"
    assert normalized.loc[0, "financial_metric_growth_pct"] == 20.0
    assert normalized.loc[0, "market_reaction_pct"] == -2.5
    assert normalized.loc[0, "risk_data_status"] == "missing_price_history"
    assert validation.is_valid is True


def test_missing_required_columns_return_validation_errors() -> None:
    portfolio_validation = validate_portfolio_holdings_input(
        pd.DataFrame({"symbol": ["AAPL"]})
    )
    candidate_validation = validate_candidate_universe_input(
        pd.DataFrame({"name": ["Example"]})
    )

    assert portfolio_validation.is_valid is False
    assert (
        "Required portfolio column missing: weight_pct." in portfolio_validation.errors
    )
    assert candidate_validation.is_valid is False
    assert "Required candidate column missing: symbol." in candidate_validation.errors


def test_optional_fields_are_safely_filled_and_symbols_are_uppercased() -> None:
    portfolio = normalize_portfolio_holdings_input(
        pd.DataFrame({"symbol": [" brk.b "], "weight_pct": [4]})
    )
    candidate = normalize_candidate_universe_input(pd.DataFrame({"symbol": [" tsla "]}))

    assert portfolio.loc[0, "symbol"] == "BRK.B"
    assert portfolio.loc[0, "name"] == "Unknown"
    assert candidate.loc[0, "symbol"] == "TSLA"
    assert candidate.loc[0, "sector"] == "Unknown"


def test_none_nan_inf_values_are_handled_safely() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAPL", None, "MSFT"],
            "weight_pct": [math.nan, math.inf, "-inf"],
            "annualized_volatility_pct": [math.nan, math.inf, -math.inf],
        }
    )

    normalized = normalize_portfolio_holdings_input(frame)

    assert normalized["weight_pct"].tolist() == [0.0, 0.0, 0.0]
    assert normalized["annualized_volatility_pct"].isna().all()


def test_build_csv_input_context_handles_optional_candidate_data() -> None:
    context = build_csv_input_decision_support_context(
        pd.DataFrame({"symbol": ["AAPL"], "weight_pct": [20]})
    )

    assert context["validation_status"] == "partial"
    assert context["portfolio_validation"].is_valid is True
    assert context["candidate_validation"].is_valid is True
    assert context["candidate_universe"].empty


def test_csv_input_pipeline_returns_complete_result_for_valid_inputs() -> None:
    result = run_csv_input_decision_support_pipeline(
        _portfolio_frame(),
        _candidate_frame(),
    )

    assert result.input_mode == "uploaded_csv"
    assert result.validation_status in {"ok", "partial"}
    assert isinstance(result.decision_support_package, DecisionSupportPackage)
    assert result.decision_support_package.data_status in {"ok", "partial"}
    assert result.candidate_scores
    assert result.portfolio_fit_results
    assert result.action_plans
    assert result.markdown


def test_csv_input_pipeline_works_when_candidates_are_missing() -> None:
    result = run_csv_input_decision_support_pipeline(_portfolio_frame(), None)

    assert result.validation_status == "partial"
    assert result.decision_support_package.data_status in {"partial", "ok"}
    assert result.candidate_scores == []
    assert result.action_plans == []
    assert (
        "Candidate CSV data is empty or was not provided." in result.validation_warnings
    )


def test_csv_input_pipeline_marks_missing_risk_data_conservatively() -> None:
    result = run_csv_input_decision_support_pipeline(
        pd.DataFrame({"symbol": ["AAPL"], "weight_pct": [10]}),
        _candidate_frame(),
    )

    assert result.enriched_portfolio_risk[0]["risk_data_status"] == (
        "missing_price_history"
    )
    assert result.portfolio_risk_insights


def test_csv_input_markdown_is_deterministic_and_payload_is_json_serializable() -> None:
    first = render_csv_input_decision_support_markdown(
        _portfolio_frame(), _candidate_frame()
    )
    second = render_csv_input_decision_support_markdown(
        _portfolio_frame(), _candidate_frame()
    )
    payload = build_csv_input_decision_support_payload(
        _portfolio_frame(), _candidate_frame()
    )

    assert first == second
    assert "# Decision-Support Package" in first
    json.dumps(payload, sort_keys=True)
    assert payload["input_mode"] == "uploaded_csv"
    assert "validation_status" in payload


def test_csv_input_pipeline_safety_flags_are_present_and_true() -> None:
    result = run_csv_input_decision_support_pipeline(
        _portfolio_frame(), _candidate_frame()
    )

    for flag in [
        "decision_support_only",
        "no_real_trading",
        "no_brokerage_api",
        "no_account_lookup",
        "no_order_execution",
        "no_llm_api_call",
        "no_mcp_integration",
    ]:
        assert result.safety_flags[flag] is True
        assert result.llm_ready_payload["safety_flags"][flag] is True


def test_csv_input_pipeline_does_not_expose_external_or_broker_dependencies() -> None:
    assert not hasattr(decision_support_demo, "yfinance")
    assert not hasattr(decision_support_demo, "yf")
    assert not hasattr(decision_support_demo, "openai")
    assert not hasattr(decision_support_demo, "OpenAI")
    assert not hasattr(decision_support_demo, "mcp")
    assert not hasattr(decision_support_demo, "MockBroker")
    assert not hasattr(decision_support_demo, "TossBrokerPlaceholder")


def test_csv_input_outputs_avoid_forbidden_recommendation_wording() -> None:
    result = run_csv_input_decision_support_pipeline(
        _portfolio_frame(), _candidate_frame()
    )
    text = result.markdown.lower()
    payload_text = json.dumps(result.llm_ready_payload, sort_keys=True).lower()

    for pattern in FORBIDDEN_PATTERNS:
        assert not re.search(pattern, text)
        assert not re.search(pattern, payload_text)


def _portfolio_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "name": "Apple",
                "sector": "Technology",
                "country": "US",
                "currency": "USD",
                "theme": "Quality growth",
                "weight_pct": 24.0,
                "total_return_pct": 12.0,
                "annualized_volatility_pct": 22.0,
                "max_drawdown_pct": -11.0,
                "risk_data_status": "ok",
            },
            {
                "symbol": "JNJ",
                "name": "Johnson & Johnson",
                "sector": "Healthcare",
                "country": "US",
                "currency": "USD",
                "theme": "Defensive quality",
                "weight_pct": 16.0,
                "total_return_pct": 4.0,
                "annualized_volatility_pct": 18.0,
                "max_drawdown_pct": -8.0,
                "risk_data_status": "ok",
            },
        ]
    )


def _candidate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "MSFT",
                "name": "Microsoft",
                "sector": "Software",
                "country": "US",
                "currency": "USD",
                "theme": "Quality growth",
                "financial_metric_name": "revenue_growth",
                "financial_metric_growth_pct": 30.0,
                "market_reaction_pct": -3.0,
                "total_return_pct": 10.0,
                "annualized_volatility_pct": 20.0,
                "max_drawdown_pct": -10.0,
                "observation_count": 45,
                "risk_data_status": "ok",
            },
            {
                "symbol": "TSLA",
                "name": "Tesla",
                "sector": "Technology",
                "country": "US",
                "currency": "USD",
                "theme": "High beta growth",
                "financial_metric_name": "operating_income_growth",
                "financial_metric_growth_pct": -8.0,
                "market_reaction_pct": 40.0,
                "total_return_pct": 22.0,
                "annualized_volatility_pct": 58.0,
                "max_drawdown_pct": -36.0,
                "observation_count": 45,
                "risk_data_status": "ok",
            },
        ]
    )
