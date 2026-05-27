from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

READY_MANUAL_REVIEW = "ready_for_manual_review"
REVIEW_WITH_CAUTION = "review_with_caution"
INSUFFICIENT_DATA = "insufficient_data"
NOT_SUITABLE_REVIEW = "not_suitable_for_review"

DATA_STATUS_OK = "ok"
DATA_STATUS_PARTIAL = "partial"
DATA_STATUS_MISSING = "missing_inputs"

SHORT_TERM = "short_term"
MID_TERM = "mid_term"
LONG_TERM = "long_term"


@dataclass(frozen=True)
class ActionPlanConfig:
    max_reasons: int = 5
    max_cautions: int = 5
    include_disclaimer: bool = True
    require_manual_review_note: bool = True


@dataclass(frozen=True)
class ActionPlanHorizon:
    horizon: str
    timeframe: str
    focus: str
    checkpoints: list[str]
    caution_notes: list[str]


@dataclass(frozen=True)
class ActionPlan:
    symbol: str
    name: str | None
    readiness: str
    horizons: list[ActionPlanHorizon]
    key_reasons: list[str]
    key_cautions: list[str]
    manual_review_checklist: list[str]
    invalidation_conditions: list[str]
    disclaimer: str | None
    data_status: str
    markdown: str


@dataclass(frozen=True)
class ActionPlanSummary:
    total_count: int
    ready_for_manual_review_count: int
    review_with_caution_count: int
    insufficient_data_count: int
    not_suitable_for_review_count: int
    top_review_symbols: list[str]
    caution_symbols: list[str]
    summary_note: str


def sanitize_plan_text(value: Any) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "Not available"
    text = str(value).strip()
    if not text or text.lower() in {"nan", "inf", "-inf", "none", "<na>"}:
        return "Not available"
    return text


def classify_action_plan_readiness(
    candidate_score: dict[str, Any] | None,
    portfolio_fit_result: dict[str, Any] | None,
    risk_insights: list[dict[str, Any]] | dict[str, Any] | None = None,
    market_regime_context: dict[str, Any] | None = None,
    config: ActionPlanConfig | None = None,
) -> str:
    config = config or ActionPlanConfig()
    del config
    candidate = candidate_score or {}
    fit = portfolio_fit_result or {}
    if not candidate or not fit:
        return INSUFFICIENT_DATA

    candidate_tier = sanitize_plan_text(candidate.get("candidate_tier"))
    fit_tier = sanitize_plan_text(fit.get("fit_tier"))
    candidate_status = sanitize_plan_text(candidate.get("data_status"))
    fit_status = sanitize_plan_text(fit.get("data_status"))
    risk_flags = _risk_flags(risk_insights)
    regime_risk = sanitize_plan_text((market_regime_context or {}).get("risk_level"))

    if candidate_tier == "insufficient_data" or fit_tier == "insufficient_data":
        return INSUFFICIENT_DATA
    if candidate_tier == "caution_review" or fit_tier == "weak_fit_review":
        return NOT_SUITABLE_REVIEW
    if candidate_status != DATA_STATUS_OK or fit_status != DATA_STATUS_OK:
        return REVIEW_WITH_CAUTION
    if risk_flags or regime_risk.lower() in {"high", "elevated"}:
        return REVIEW_WITH_CAUTION
    if candidate_tier in {"high_priority_review", "standard_review"} and fit_tier in {
        "strong_fit_review",
        "moderate_fit_review",
    }:
        return READY_MANUAL_REVIEW
    return REVIEW_WITH_CAUTION


def build_short_term_review_plan(
    candidate_score: dict[str, Any] | None,
    portfolio_fit_result: dict[str, Any] | None,
    risk_insights: list[dict[str, Any]] | dict[str, Any] | None = None,
    market_regime_context: dict[str, Any] | None = None,
    config: ActionPlanConfig | None = None,
) -> ActionPlanHorizon:
    config = config or ActionPlanConfig()
    del config
    risk_flags = _risk_flags(risk_insights)
    regime_label = sanitize_plan_text((market_regime_context or {}).get("regime_label"))
    checkpoints = [
        "Validate symbol, source data, and recent price history before any manual decision.",
        "Review recent volatility and drawdown behavior for short-window risk conditions.",
        "Check recent company events, disclosures, and market news manually.",
        f"Confirm market regime context before acting on this review framework: {regime_label}.",
        "Pause when the review is driven by urgency rather than evidence.",
    ]
    cautions = [
        "Short-term review should prioritize data quality and risk checkpoints.",
        _risk_caution_text(risk_flags),
    ]
    return ActionPlanHorizon(
        horizon=SHORT_TERM,
        timeframe="1 week to 1 month",
        focus="Data validation, volatility review, event check, and regime confirmation.",
        checkpoints=checkpoints,
        caution_notes=_dedupe_safe(cautions),
    )


def build_mid_term_review_plan(
    candidate_score: dict[str, Any] | None,
    portfolio_fit_result: dict[str, Any] | None,
    risk_insights: list[dict[str, Any]] | dict[str, Any] | None = None,
    market_regime_context: dict[str, Any] | None = None,
    config: ActionPlanConfig | None = None,
) -> ActionPlanHorizon:
    config = config or ActionPlanConfig()
    del config, risk_insights, market_regime_context
    candidate_tier = sanitize_plan_text((candidate_score or {}).get("candidate_tier"))
    fit_tier = sanitize_plan_text((portfolio_fit_result or {}).get("fit_tier"))
    checkpoints = [
        "Track whether the original thesis remains supported by updated fundamentals.",
        "Review earnings quality, margin trend, and balance sheet risk with fresh source data.",
        "Reassess portfolio concentration and correlation exposure before making any decision.",
        f"Compare candidate review tier and portfolio fit tier over time: {candidate_tier}, {fit_tier}.",
        "Document what evidence would strengthen or weaken the review case.",
    ]
    return ActionPlanHorizon(
        horizon=MID_TERM,
        timeframe="1 to 6 months",
        focus="Thesis monitoring, fundamental validation, concentration review, and risk reassessment.",
        checkpoints=checkpoints,
        caution_notes=[
            "Mid-term review should be updated when fundamentals, risk metrics, or portfolio context materially change."
        ],
    )


def build_long_term_review_plan(
    candidate_score: dict[str, Any] | None,
    portfolio_fit_result: dict[str, Any] | None,
    risk_insights: list[dict[str, Any]] | dict[str, Any] | None = None,
    market_regime_context: dict[str, Any] | None = None,
    config: ActionPlanConfig | None = None,
) -> ActionPlanHorizon:
    config = config or ActionPlanConfig()
    del config, candidate_score, portfolio_fit_result, risk_insights
    regime_status = sanitize_plan_text((market_regime_context or {}).get("data_status"))
    checkpoints = [
        "Review business quality, competitive position, and durability of growth assumptions.",
        "Evaluate whether factor exposure and sector role still complement the broader portfolio.",
        "Test scenario resilience under adverse growth, valuation, currency, and liquidity assumptions.",
        f"Treat regime context as manual or mock input unless independently validated: {regime_status}.",
        "Keep a written thesis validation checklist for future comparison.",
    ]
    return ActionPlanHorizon(
        horizon=LONG_TERM,
        timeframe="6 months to 3 years",
        focus="Business quality, factor exposure, diversification role, and scenario resilience.",
        checkpoints=checkpoints,
        caution_notes=[
            "Long-term review should remain conditional on evidence quality and portfolio role."
        ],
    )


def build_candidate_action_plan(
    candidate_score: dict[str, Any] | None = None,
    portfolio_fit_result: dict[str, Any] | None = None,
    risk_insights: list[dict[str, Any]] | dict[str, Any] | None = None,
    market_regime_context: dict[str, Any] | None = None,
    config: ActionPlanConfig | None = None,
) -> ActionPlan:
    config = config or ActionPlanConfig()
    candidate = candidate_score or {}
    fit = portfolio_fit_result or {}
    readiness = classify_action_plan_readiness(
        candidate, fit, risk_insights, market_regime_context, config
    )
    horizons = [
        build_short_term_review_plan(
            candidate, fit, risk_insights, market_regime_context, config
        ),
        build_mid_term_review_plan(
            candidate, fit, risk_insights, market_regime_context, config
        ),
        build_long_term_review_plan(
            candidate, fit, risk_insights, market_regime_context, config
        ),
    ]
    key_reasons = _collect_limited_messages(
        [candidate.get("reasons"), fit.get("reasons")],
        config.max_reasons,
        "Review case requires manual validation with complete source data.",
    )
    key_cautions = _collect_limited_messages(
        [candidate.get("cautions"), fit.get("cautions"), _risk_messages(risk_insights)],
        config.max_cautions,
        "Data quality and risk conditions should be checked before any manual decision.",
    )
    checklist = _manual_review_checklist(config)
    invalidation_conditions = _invalidation_conditions(risk_insights)
    disclaimer = _disclaimer_text() if config.include_disclaimer else None
    plan = ActionPlan(
        symbol=_symbol(candidate.get("symbol") or fit.get("symbol")),
        name=_optional_text(candidate.get("name") or fit.get("name")),
        readiness=readiness,
        horizons=horizons,
        key_reasons=key_reasons,
        key_cautions=key_cautions,
        manual_review_checklist=checklist,
        invalidation_conditions=invalidation_conditions,
        disclaimer=disclaimer,
        data_status=_plan_data_status(candidate, fit, readiness),
        markdown="",
    )
    markdown = render_action_plan_markdown(plan)
    return ActionPlan(
        symbol=plan.symbol,
        name=plan.name,
        readiness=plan.readiness,
        horizons=plan.horizons,
        key_reasons=plan.key_reasons,
        key_cautions=plan.key_cautions,
        manual_review_checklist=plan.manual_review_checklist,
        invalidation_conditions=plan.invalidation_conditions,
        disclaimer=plan.disclaimer,
        data_status=plan.data_status,
        markdown=markdown,
    )


def build_action_plan_summary(
    action_plans: list[ActionPlan],
) -> ActionPlanSummary:
    plans = list(action_plans or [])
    ready = [plan for plan in plans if plan.readiness == READY_MANUAL_REVIEW]
    caution = [plan for plan in plans if plan.readiness == REVIEW_WITH_CAUTION]
    insufficient = [plan for plan in plans if plan.readiness == INSUFFICIENT_DATA]
    not_suitable = [plan for plan in plans if plan.readiness == NOT_SUITABLE_REVIEW]
    return ActionPlanSummary(
        total_count=len(plans),
        ready_for_manual_review_count=len(ready),
        review_with_caution_count=len(caution),
        insufficient_data_count=len(insufficient),
        not_suitable_for_review_count=len(not_suitable),
        top_review_symbols=[plan.symbol for plan in ready[:5]],
        caution_symbols=[plan.symbol for plan in (caution + not_suitable)[:5]],
        summary_note=_summary_note(plans, caution, insufficient, not_suitable),
    )


def render_action_plan_markdown(action_plan: ActionPlan) -> str:
    lines = [
        f"# Conditional Review Plan: {sanitize_plan_text(action_plan.symbol)}",
        "",
        f"Readiness: {sanitize_plan_text(action_plan.readiness)}",
        f"Data status: {sanitize_plan_text(action_plan.data_status)}",
    ]
    if action_plan.name:
        lines.append(f"Name: {sanitize_plan_text(action_plan.name)}")
    lines.extend(["", "## Key Reasons"])
    lines.extend(
        f"- {sanitize_plan_text(reason)}" for reason in action_plan.key_reasons
    )
    lines.extend(["", "## Key Cautions"])
    lines.extend(
        f"- {sanitize_plan_text(caution)}" for caution in action_plan.key_cautions
    )
    for horizon in action_plan.horizons:
        lines.extend(
            [
                "",
                f"## {horizon.horizon.replace('_', ' ').title()} Review Plan",
                f"Timeframe: {horizon.timeframe}",
                f"Focus: {sanitize_plan_text(horizon.focus)}",
                "Checkpoints:",
            ]
        )
        lines.extend(
            f"- {sanitize_plan_text(checkpoint)}" for checkpoint in horizon.checkpoints
        )
        lines.append("Caution notes:")
        lines.extend(f"- {sanitize_plan_text(note)}" for note in horizon.caution_notes)
    lines.extend(["", "## Manual Review Checklist"])
    lines.extend(
        f"- {sanitize_plan_text(item)}" for item in action_plan.manual_review_checklist
    )
    lines.extend(["", "## Invalidation Conditions"])
    lines.extend(
        f"- {sanitize_plan_text(item)}" for item in action_plan.invalidation_conditions
    )
    if action_plan.disclaimer:
        lines.extend(["", "## Disclaimer", sanitize_plan_text(action_plan.disclaimer)])
    return "\n".join(lines).strip() + "\n"


def _risk_flags(
    risk_insights: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[str]:
    flags = []
    for insight in _as_records(risk_insights):
        severity = sanitize_plan_text(insight.get("severity")).lower()
        insight_type = sanitize_plan_text(insight.get("insight_type")).lower()
        if severity in {"high", "caution"} or insight_type in {
            "high_volatility",
            "deep_drawdown",
            "weak_return",
            "missing_risk_data",
            "insufficient_risk_data",
        }:
            flags.append(insight_type)
    return _dedupe_safe(flags)


def _risk_messages(
    risk_insights: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[str]:
    messages = []
    for insight in _as_records(risk_insights):
        message = sanitize_plan_text(insight.get("message"))
        if message != "Not available":
            messages.append(message)
    return messages


def _risk_caution_text(risk_flags: list[str]) -> str:
    if not risk_flags:
        return "No elevated risk insight flag was supplied for this candidate."
    return "Risk insight flags require manual review: " + ", ".join(risk_flags) + "."


def _collect_limited_messages(
    message_groups: list[Any],
    limit: int,
    fallback: str,
) -> list[str]:
    messages = []
    for group in message_groups:
        for item in _as_list(group):
            text = sanitize_plan_text(item)
            if text != "Not available" and text not in messages:
                messages.append(text)
    if not messages:
        messages.append(fallback)
    return messages[: max(limit, 1)]


def _manual_review_checklist(config: ActionPlanConfig) -> list[str]:
    checklist = [
        "Confirm source data freshness and consistency.",
        "Review candidate score, portfolio fit, and risk insight inputs together.",
        "Validate market regime context manually because it may be mock or incomplete.",
        "Record thesis validation criteria before making any manual decision.",
    ]
    if config.require_manual_review_note:
        checklist.append(
            "Treat this plan as decision-support only and require manual review."
        )
    return checklist


def _invalidation_conditions(
    risk_insights: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[str]:
    conditions = [
        "Source data is incomplete, stale, or inconsistent across inputs.",
        "Risk conditions materially worsen versus the supplied review baseline.",
        "Portfolio concentration concern becomes more severe after updated analysis.",
        "Original thesis is no longer supported by fundamentals or scenario review.",
    ]
    if _risk_flags(risk_insights):
        conditions.append(
            "Elevated risk insight flags remain unresolved after manual review."
        )
    return conditions


def _plan_data_status(
    candidate: dict[str, Any],
    fit: dict[str, Any],
    readiness: str,
) -> str:
    if readiness == INSUFFICIENT_DATA:
        return DATA_STATUS_MISSING
    statuses = {
        sanitize_plan_text(candidate.get("data_status")),
        sanitize_plan_text(fit.get("data_status")),
    }
    if statuses == {DATA_STATUS_OK}:
        return DATA_STATUS_OK
    return DATA_STATUS_PARTIAL


def _summary_note(
    plans: list[ActionPlan],
    caution: list[ActionPlan],
    insufficient: list[ActionPlan],
    not_suitable: list[ActionPlan],
) -> str:
    if not plans:
        return "No conditional review plans were generated."
    caution_total = len(caution) + len(insufficient) + len(not_suitable)
    return (
        f"Generated {len(plans)} conditional review plans, "
        f"including {caution_total} plans requiring caution or additional data review."
    )


def _as_records(
    value: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    try:
        return [item for item in value if isinstance(item, dict)]
    except TypeError:
        return []


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _dedupe_safe(values: list[str]) -> list[str]:
    result = []
    for value in values:
        text = sanitize_plan_text(value)
        if text != "Not available" and text not in result:
            result.append(text)
    return result


def _symbol(value: Any) -> str:
    text = _optional_text(value)
    return text.upper() if text else ""


def _optional_text(value: Any) -> str | None:
    text = sanitize_plan_text(value)
    return None if text == "Not available" else text


def _disclaimer_text() -> str:
    return (
        "This conditional review plan is decision-support only, is not financial advice, "
        "does not assure any return, and does not execute orders or access brokerage accounts."
    )
