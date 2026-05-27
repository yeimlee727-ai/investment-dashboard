import math
import re

from src.analysis import action_plan_generator
from src.analysis.action_plan_generator import (
    INSUFFICIENT_DATA,
    NOT_SUITABLE_REVIEW,
    READY_MANUAL_REVIEW,
    REVIEW_WITH_CAUTION,
    ActionPlan,
    ActionPlanHorizon,
    build_action_plan_summary,
    build_candidate_action_plan,
    classify_action_plan_readiness,
    render_action_plan_markdown,
    sanitize_plan_text,
)

FORBIDDEN_PATTERNS = [
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
    "allocation percentage",
    "exact position size",
]


def candidate_record(**overrides):
    record = {
        "symbol": "AAPL",
        "name": "Apple",
        "total_score": 82.0,
        "candidate_tier": "high_priority_review",
        "reasons": [
            "Investment Map classification suggests fundamentals improved while market reaction remains limited."
        ],
        "cautions": [
            "Candidate requires additional manual review before any investment decision."
        ],
        "data_status": "ok",
    }
    record.update(overrides)
    return record


def fit_record(**overrides):
    record = {
        "symbol": "AAPL",
        "fit_score": 76.0,
        "fit_tier": "strong_fit_review",
        "diversification_score": 80.0,
        "concentration_risk_score": 75.0,
        "candidate_quality_score": 82.0,
        "data_quality_score": 90.0,
        "exposure_impacts": {},
        "reasons": [
            "Candidate may improve diversification because one or more exposures are underrepresented in the current portfolio."
        ],
        "cautions": [
            "Candidate quality score is useful context, but portfolio concentration impact requires manual review."
        ],
        "data_status": "ok",
    }
    record.update(overrides)
    return record


def high_risk_insight():
    return {
        "symbol": "AAPL",
        "insight_type": "deep_drawdown",
        "severity": "high",
        "message": "This position has experienced a deep historical drawdown.",
        "data_status": "ok",
    }


def test_build_candidate_action_plan_returns_three_horizons():
    plan = build_candidate_action_plan(candidate_record(), fit_record())

    assert [horizon.horizon for horizon in plan.horizons] == [
        "short_term",
        "mid_term",
        "long_term",
    ]
    assert [horizon.timeframe for horizon in plan.horizons] == [
        "1 week to 1 month",
        "1 to 6 months",
        "6 months to 3 years",
    ]


def test_strong_candidate_and_fit_are_ready_for_manual_review():
    readiness = classify_action_plan_readiness(candidate_record(), fit_record())
    plan = build_candidate_action_plan(candidate_record(), fit_record())

    assert readiness == READY_MANUAL_REVIEW
    assert plan.readiness == READY_MANUAL_REVIEW
    assert plan.data_status == "ok"


def test_high_risk_flags_or_concentration_cautions_create_caution_review():
    plan = build_candidate_action_plan(
        candidate_record(),
        fit_record(
            cautions=["Candidate overlaps with an already concentrated exposure."]
        ),
        risk_insights=[high_risk_insight()],
    )

    assert plan.readiness == REVIEW_WITH_CAUTION
    assert "deep_drawdown" in plan.markdown


def test_caution_tier_can_be_not_suitable_for_review():
    plan = build_candidate_action_plan(
        candidate_record(candidate_tier="caution_review"),
        fit_record(fit_tier="weak_fit_review"),
    )

    assert plan.readiness == NOT_SUITABLE_REVIEW


def test_missing_candidate_or_fit_data_produces_insufficient_data():
    assert (
        build_candidate_action_plan(None, fit_record()).readiness == INSUFFICIENT_DATA
    )
    assert (
        build_candidate_action_plan(candidate_record(), None).readiness
        == INSUFFICIENT_DATA
    )


def test_empty_inputs_do_not_crash():
    plan = build_candidate_action_plan()

    assert plan.readiness == INSUFFICIENT_DATA
    assert plan.symbol == ""
    assert plan.data_status == "missing_inputs"
    assert "Conditional Review Plan" in plan.markdown


def test_none_nan_inf_values_are_handled_safely():
    plan = build_candidate_action_plan(
        candidate_record(
            symbol=None,
            name=math.nan,
            total_score=math.inf,
            reasons=[None, math.nan, math.inf, "-inf"],
        ),
        fit_record(symbol="-inf", fit_score=-math.inf, cautions=[None]),
        risk_insights=math.inf,
        market_regime_context={"regime_label": math.nan, "data_status": math.inf},
    )

    assert sanitize_plan_text(math.nan) == "Not available"
    assert plan.symbol == ""
    assert not re.search(r"\b(?:nan|inf|-inf)\b", plan.markdown.lower())


def test_render_action_plan_markdown_includes_all_horizon_sections():
    plan = build_candidate_action_plan(candidate_record(), fit_record())
    markdown = render_action_plan_markdown(plan)

    assert "## Short Term Review Plan" in markdown
    assert "## Mid Term Review Plan" in markdown
    assert "## Long Term Review Plan" in markdown
    assert "## Manual Review Checklist" in markdown
    assert "## Invalidation Conditions" in markdown


def test_build_action_plan_summary_counts_readiness_categories():
    plans = [
        build_candidate_action_plan(
            candidate_record(symbol="AAA"), fit_record(symbol="AAA")
        ),
        build_candidate_action_plan(
            candidate_record(symbol="BBB"),
            fit_record(symbol="BBB"),
            risk_insights=[high_risk_insight()],
        ),
        build_candidate_action_plan(None, fit_record(symbol="CCC")),
        build_candidate_action_plan(
            candidate_record(symbol="DDD", candidate_tier="caution_review"),
            fit_record(symbol="DDD", fit_tier="weak_fit_review"),
        ),
    ]

    summary = build_action_plan_summary(plans)

    assert summary.total_count == 4
    assert summary.ready_for_manual_review_count == 1
    assert summary.review_with_caution_count == 1
    assert summary.insufficient_data_count == 1
    assert summary.not_suitable_for_review_count == 1
    assert summary.top_review_symbols == ["AAA"]
    assert summary.caution_symbols == ["BBB", "DDD"]


def test_market_regime_context_is_optional_and_has_no_external_dependency():
    plan_without_regime = build_candidate_action_plan(candidate_record(), fit_record())
    plan_with_regime = build_candidate_action_plan(
        candidate_record(),
        fit_record(),
        market_regime_context={
            "regime_label": "manual risk review",
            "risk_level": "normal",
            "data_status": "mock",
        },
    )

    assert plan_without_regime.readiness == READY_MANUAL_REVIEW
    assert "manual risk review" in plan_with_regime.markdown
    assert not hasattr(action_plan_generator, "yfinance")
    assert not hasattr(action_plan_generator, "openai")
    assert not hasattr(action_plan_generator, "OpenAI")


def test_generated_text_excludes_forbidden_recommendation_wording():
    plan = build_candidate_action_plan(
        candidate_record(),
        fit_record(),
        risk_insights=[high_risk_insight()],
        market_regime_context={"regime_label": "mock context", "risk_level": "high"},
    )
    text = plan.markdown.lower()

    for forbidden in FORBIDDEN_PATTERNS:
        assert forbidden not in text


def test_generated_text_excludes_price_and_position_size_instructions():
    plan = build_candidate_action_plan(candidate_record(), fit_record())
    text = plan.markdown.lower()

    forbidden_phrases = [
        "allocation percentage",
        "target price",
        "entry price",
        "stop loss",
        "take profit",
        "exact position size",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in text


def test_disclaimer_is_included_by_default():
    plan = build_candidate_action_plan(candidate_record(), fit_record())

    assert plan.disclaimer is not None
    assert "decision-support only" in plan.disclaimer
    assert "does not execute orders" in plan.disclaimer


def test_summary_handles_empty_plan_list():
    summary = build_action_plan_summary([])

    assert summary.total_count == 0
    assert summary.top_review_symbols == []
    assert summary.caution_symbols == []
    assert summary.summary_note == "No conditional review plans were generated."


def test_summary_accepts_constructed_action_plan_records():
    plan = ActionPlan(
        symbol="XYZ",
        name=None,
        readiness=REVIEW_WITH_CAUTION,
        horizons=[
            ActionPlanHorizon(
                horizon="short_term",
                timeframe="1 week to 1 month",
                focus="Risk checkpoint review.",
                checkpoints=["Validate data."],
                caution_notes=["Manual review required."],
            )
        ],
        key_reasons=["Review record."],
        key_cautions=["Risk checkpoint."],
        manual_review_checklist=["Validate source data."],
        invalidation_conditions=["Data quality worsens."],
        disclaimer=None,
        data_status="partial",
        markdown="",
    )

    summary = build_action_plan_summary([plan])

    assert summary.review_with_caution_count == 1
    assert summary.caution_symbols == ["XYZ"]
