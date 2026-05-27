from __future__ import annotations

import math

from src.analysis.insight_generator import (
    InsightGeneratorConfig,
    build_candidate_review_section,
    build_mock_insight_report,
    build_portfolio_fit_section,
    format_symbol_list,
    render_insight_report_markdown,
    sanitize_text_value,
)

FORBIDDEN_WORDING = [
    "buy",
    "sell",
    "hold",
    "strong buy",
    "target price",
    "guaranteed return",
    "must profit",
    "take profit",
    "stop loss",
    "entry price",
]


def sample_report_inputs() -> dict[str, dict[str, object]]:
    return {
        "portfolio_context": {
            "position_count": 4,
            "sector_exposure": "Technology 42%, Healthcare 12%",
            "country_exposure": "US 70%, Korea 30%",
            "currency_exposure": "USD 70%, KRW 30%",
            "concentration_notes": "Technology exposure is elevated.",
        },
        "risk_insight_summary": {
            "high_volatility_symbols": ["NVDA"],
            "deep_drawdown_symbols": ["TSLA"],
            "weak_return_symbols": ["ABC"],
            "overall_risk_note": "Portfolio risk review found elevated risk flags.",
        },
        "candidate_score_summary": {
            "top_symbols": ["MSFT", "GOOGL"],
            "caution_symbols": ["TSLA"],
            "summary_note": "Candidate scoring produced review records.",
        },
        "portfolio_fit_summary": {
            "top_fit_symbols": ["MSFT"],
            "concentration_caution_symbols": ["NVDA"],
            "summary_note": "Portfolio fit analysis found concentration cautions.",
        },
        "market_regime_context": {
            "regime_label": "neutral",
            "macro_notes": "Manual regime context.",
            "data_status": "mock",
        },
    }


def test_build_mock_insight_report_returns_sections_in_required_order() -> None:
    inputs = sample_report_inputs()
    report = build_mock_insight_report(**inputs)

    assert [section.title for section in report.sections] == [
        "Portfolio Context",
        "Risk Review",
        "Candidate Review",
        "Portfolio Fit Review",
        "Market Regime Context",
        "Limitations / Disclaimer",
    ]


def test_render_markdown_is_deterministic_and_contains_section_titles() -> None:
    inputs = sample_report_inputs()
    report = build_mock_insight_report(**inputs)

    first = render_insight_report_markdown(report)
    second = render_insight_report_markdown(report)

    assert first == second
    for title in [
        "Portfolio Context",
        "Risk Review",
        "Candidate Review",
        "Portfolio Fit Review",
        "Market Regime Context",
        "Limitations / Disclaimer",
    ]:
        assert f"## {title}" in first


def test_empty_inputs_produce_safe_missing_status_report() -> None:
    report = build_mock_insight_report()

    assert report.data_status == "missing_inputs"
    assert "Some analysis inputs are missing or incomplete." in report.markdown


def test_risk_summary_values_appear_in_risk_section() -> None:
    report = build_mock_insight_report(**sample_report_inputs())
    risk_section = report.sections[1]
    text = " ".join(risk_section.bullet_points)

    assert "NVDA" in text
    assert "TSLA" in text
    assert "ABC" in text


def test_candidate_score_values_appear_in_candidate_section() -> None:
    section = build_candidate_review_section(
        sample_report_inputs()["candidate_score_summary"]
    )
    text = " ".join(section.bullet_points)

    assert "MSFT" in text
    assert "GOOGL" in text
    assert "TSLA" in text


def test_portfolio_fit_values_appear_in_fit_section() -> None:
    section = build_portfolio_fit_section(
        sample_report_inputs()["portfolio_fit_summary"]
    )
    text = " ".join(section.bullet_points)

    assert "MSFT" in text
    assert "NVDA" in text


def test_market_regime_context_is_optional() -> None:
    inputs = sample_report_inputs()
    inputs.pop("market_regime_context")

    report = build_mock_insight_report(**inputs)

    assert report.sections[4].title == "Market Regime Context"
    assert report.sections[4].status == "partial"


def test_none_nan_inf_values_are_handled_safely() -> None:
    assert sanitize_text_value(None) == "Not available"
    assert sanitize_text_value(math.nan) == "Not available"
    assert sanitize_text_value(math.inf) == "Not available"
    assert sanitize_text_value(-math.inf) == "Not available"
    assert format_symbol_list([None, math.nan, "aapl"]) == "AAPL"


def test_disclaimer_section_is_included_by_default() -> None:
    report = build_mock_insight_report(**sample_report_inputs())

    assert report.sections[-1].title == "Limitations / Disclaimer"
    assert "decision-support only" in report.markdown
    assert "not financial advice" in report.markdown


def test_no_network_yfinance_or_openai_dependency_is_introduced() -> None:
    import src.analysis.insight_generator as module

    assert not hasattr(module, "yfinance")
    assert not hasattr(module, "yf")
    assert not hasattr(module, "openai")
    assert not hasattr(module, "OpenAI")


def test_generated_report_avoids_forbidden_recommendation_wording() -> None:
    report = build_mock_insight_report(**sample_report_inputs())
    text = report.markdown.lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in text


def test_no_allocation_percentage_recommendation_wording() -> None:
    report = build_mock_insight_report(**sample_report_inputs())
    text = report.markdown.lower()

    assert "allocate" not in text
    assert "allocation percentage" not in text
    assert "position size" in text


def test_custom_config_can_hide_disclaimer() -> None:
    report = build_mock_insight_report(
        **sample_report_inputs(),
        config=InsightGeneratorConfig(include_disclaimer=False),
    )

    assert "Limitations / Disclaimer" not in [
        section.title for section in report.sections
    ]
