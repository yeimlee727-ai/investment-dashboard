from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import math
from typing import Any

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_MISSING_INPUTS = "missing_inputs"

SECTION_PORTFOLIO_CONTEXT = "portfolio_context"
SECTION_RISK_INSIGHT_SUMMARY = "risk_insight_summary"
SECTION_INVESTMENT_MAP_SUMMARY = "investment_map_summary"
SECTION_CANDIDATE_SCORE_SUMMARY = "candidate_score_summary"
SECTION_PORTFOLIO_FIT_SUMMARY = "portfolio_fit_summary"
SECTION_INSIGHT_REPORT = "insight_report"
SECTION_ACTION_PLAN_SUMMARY = "action_plan_summary"
SECTION_ACTION_PLANS = "action_plans"
SECTION_MARKET_REGIME_CONTEXT = "market_regime_context"


@dataclass(frozen=True)
class DecisionSupportPackageConfig:
    package_version: str = "0.1"
    include_markdown: bool = True
    include_disclaimer: bool = True
    max_symbols_per_section: int = 5


@dataclass(frozen=True)
class DecisionSupportPackage:
    package_version: str
    data_status: str
    portfolio_context: dict[str, Any] | None
    risk_insight_summary: dict[str, Any] | None
    investment_map_summary: dict[str, Any] | None
    candidate_score_summary: dict[str, Any] | None
    portfolio_fit_summary: dict[str, Any] | None
    insight_report: dict[str, Any] | None
    action_plan_summary: dict[str, Any] | None
    action_plans: list[dict[str, Any]]
    market_regime_context: dict[str, Any] | None
    limitations: list[str]
    safety_flags: dict[str, bool]
    markdown: str


@dataclass(frozen=True)
class DecisionSupportPackageSummary:
    data_status: str
    included_sections: list[str]
    missing_sections: list[str]
    candidate_review_count: int
    portfolio_fit_review_count: int
    action_plan_count: int
    caution_symbol_count: int
    summary_note: str


def sanitize_package_value(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        return sanitize_package_value(asdict(value))
    if isinstance(value, dict):
        return {
            str(key): sanitize_package_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_package_value(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (int, bool)):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "inf", "-inf", "none", "<na>"}:
        return None
    return text


def build_decision_support_package(
    portfolio_context: dict[str, Any] | None = None,
    risk_insight_summary: dict[str, Any] | None = None,
    investment_map_summary: dict[str, Any] | None = None,
    candidate_score_summary: dict[str, Any] | None = None,
    portfolio_fit_summary: dict[str, Any] | None = None,
    insight_report: dict[str, Any] | Any | None = None,
    action_plan_summary: dict[str, Any] | Any | None = None,
    action_plans: list[dict[str, Any]] | list[Any] | None = None,
    market_regime_context: dict[str, Any] | None = None,
    config: DecisionSupportPackageConfig | None = None,
) -> DecisionSupportPackage:
    config = config or DecisionSupportPackageConfig()
    package = DecisionSupportPackage(
        package_version=config.package_version,
        data_status=STATUS_MISSING_INPUTS,
        portfolio_context=_optional_dict(portfolio_context),
        risk_insight_summary=_optional_dict(risk_insight_summary),
        investment_map_summary=_optional_dict(investment_map_summary),
        candidate_score_summary=_optional_dict(candidate_score_summary),
        portfolio_fit_summary=_optional_dict(portfolio_fit_summary),
        insight_report=_optional_dict(insight_report),
        action_plan_summary=_optional_dict(action_plan_summary),
        action_plans=_optional_list(action_plans),
        market_regime_context=_optional_dict(market_regime_context),
        limitations=_limitations(config),
        safety_flags=_safety_flags(),
        markdown="",
    )
    data_status = _package_data_status(package)
    package = DecisionSupportPackage(
        package_version=package.package_version,
        data_status=data_status,
        portfolio_context=package.portfolio_context,
        risk_insight_summary=package.risk_insight_summary,
        investment_map_summary=package.investment_map_summary,
        candidate_score_summary=package.candidate_score_summary,
        portfolio_fit_summary=package.portfolio_fit_summary,
        insight_report=package.insight_report,
        action_plan_summary=package.action_plan_summary,
        action_plans=package.action_plans,
        market_regime_context=package.market_regime_context,
        limitations=package.limitations,
        safety_flags=package.safety_flags,
        markdown="",
    )
    markdown = (
        render_decision_support_package_markdown(package)
        if config.include_markdown
        else ""
    )
    return DecisionSupportPackage(
        package_version=package.package_version,
        data_status=package.data_status,
        portfolio_context=package.portfolio_context,
        risk_insight_summary=package.risk_insight_summary,
        investment_map_summary=package.investment_map_summary,
        candidate_score_summary=package.candidate_score_summary,
        portfolio_fit_summary=package.portfolio_fit_summary,
        insight_report=package.insight_report,
        action_plan_summary=package.action_plan_summary,
        action_plans=package.action_plans,
        market_regime_context=package.market_regime_context,
        limitations=package.limitations,
        safety_flags=package.safety_flags,
        markdown=markdown,
    )


def build_decision_support_package_summary(
    package: DecisionSupportPackage,
) -> DecisionSupportPackageSummary:
    included_sections, missing_sections = _section_presence(package)
    candidate_review_count = _safe_int(
        _get(package.candidate_score_summary, "total_count")
    )
    portfolio_fit_review_count = _safe_int(
        _get(package.portfolio_fit_summary, "total_count")
    )
    action_plan_count = len(package.action_plans)
    caution_symbols = _combined_caution_symbols(package)
    return DecisionSupportPackageSummary(
        data_status=package.data_status,
        included_sections=included_sections,
        missing_sections=missing_sections,
        candidate_review_count=candidate_review_count,
        portfolio_fit_review_count=portfolio_fit_review_count,
        action_plan_count=action_plan_count,
        caution_symbol_count=len(caution_symbols),
        summary_note=_summary_note(package, included_sections, missing_sections),
    )


def render_decision_support_package_markdown(
    package: DecisionSupportPackage,
) -> str:
    summary = build_decision_support_package_summary(package)
    lines = [
        "# Decision-Support Package",
        "",
        f"Package version: {_text(package.package_version)}",
        f"Data status: {_text(package.data_status)}",
        "",
        "## Portfolio Context Summary",
        f"- Position count: {_text(_get(package.portfolio_context, 'position_count'))}.",
        f"- Concentration note: {_text(_get(package.portfolio_context, 'concentration_notes'))}.",
        "",
        "## Risk Review Summary",
        f"- Elevated volatility symbols: {_symbol_list(_get(package.risk_insight_summary, 'high_volatility_symbols'))}.",
        f"- Deep drawdown symbols: {_symbol_list(_get(package.risk_insight_summary, 'deep_drawdown_symbols'))}.",
        f"- Risk note: {_text(_get(package.risk_insight_summary, 'overall_risk_note'))}.",
        "",
        "## Candidate Review Summary",
        f"- Candidate review count: {summary.candidate_review_count}.",
        f"- Top review candidates: {_symbol_list(_get(package.candidate_score_summary, 'top_symbols'))}.",
        f"- Candidate cautions: {_symbol_list(_get(package.candidate_score_summary, 'caution_symbols'))}.",
        "",
        "## Portfolio Fit Summary",
        f"- Portfolio fit review count: {summary.portfolio_fit_review_count}.",
        f"- Top fit review symbols: {_symbol_list(_get(package.portfolio_fit_summary, 'top_fit_symbols'))}.",
        f"- Concentration cautions: {_symbol_list(_get(package.portfolio_fit_summary, 'concentration_caution_symbols'))}.",
        "",
        "## Action Plan Summary",
        f"- Conditional review plan count: {summary.action_plan_count}.",
        f"- Ready for manual review: {_text(_get(package.action_plan_summary, 'ready_for_manual_review_count'))}.",
        f"- Caution symbols: {_symbol_list(_get(package.action_plan_summary, 'caution_symbols'))}.",
        "",
        "## Limitations / Disclaimer",
    ]
    lines.extend(f"- {_text(limitation)}" for limitation in package.limitations)
    lines.extend(
        [
            "- This package is decision-support only and is not financial advice.",
            "- This package does not execute orders or access brokerage accounts.",
            "- Data quality review and manual validation are required before any investment decision.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_llm_ready_payload(package: DecisionSupportPackage) -> dict[str, Any]:
    payload = {
        "package_version": package.package_version,
        "data_status": package.data_status,
        "portfolio_context": package.portfolio_context,
        "risk_insight_summary": package.risk_insight_summary,
        "investment_map_summary": package.investment_map_summary,
        "candidate_score_summary": package.candidate_score_summary,
        "portfolio_fit_summary": package.portfolio_fit_summary,
        "insight_report": package.insight_report,
        "action_plan_summary": package.action_plan_summary,
        "action_plans": package.action_plans,
        "market_regime_context": package.market_regime_context,
        "limitations": package.limitations,
        "safety_metadata": {
            "decision_support_only": True,
            "no_real_trading": True,
            "no_brokerage_api": True,
            "no_account_lookup": True,
            "no_order_execution": True,
            "no_external_api_call": True,
        },
    }
    return sanitize_package_value(payload)


def _optional_dict(value: Any) -> dict[str, Any] | None:
    sanitized = sanitize_package_value(value)
    if isinstance(sanitized, dict) and sanitized:
        return sanitized
    return None


def _optional_list(value: Any) -> list[dict[str, Any]]:
    sanitized = sanitize_package_value(value)
    if not isinstance(sanitized, list):
        return []
    return [item for item in sanitized if isinstance(item, dict)]


def _limitations(config: DecisionSupportPackageConfig) -> list[str]:
    if not config.include_disclaimer:
        return ["Package limitations were configured externally."]
    return [
        "Inputs may be incomplete, stale, mocked, or manually supplied.",
        "Package contents organize prior analysis outputs without creating trading signals.",
        "Future report or payload use should preserve decision-support constraints.",
    ]


def _safety_flags() -> dict[str, bool]:
    return {
        "decision_support_only": True,
        "no_real_trading": True,
        "no_brokerage_api": True,
        "no_account_lookup": True,
        "no_order_execution": True,
    }


def _package_data_status(package: DecisionSupportPackage) -> str:
    included_sections, missing_sections = _section_presence(package)
    if not included_sections:
        return STATUS_MISSING_INPUTS
    if missing_sections:
        return STATUS_PARTIAL
    return STATUS_OK


def _section_presence(
    package: DecisionSupportPackage,
) -> tuple[list[str], list[str]]:
    values = {
        SECTION_PORTFOLIO_CONTEXT: package.portfolio_context,
        SECTION_RISK_INSIGHT_SUMMARY: package.risk_insight_summary,
        SECTION_INVESTMENT_MAP_SUMMARY: package.investment_map_summary,
        SECTION_CANDIDATE_SCORE_SUMMARY: package.candidate_score_summary,
        SECTION_PORTFOLIO_FIT_SUMMARY: package.portfolio_fit_summary,
        SECTION_INSIGHT_REPORT: package.insight_report,
        SECTION_ACTION_PLAN_SUMMARY: package.action_plan_summary,
        SECTION_ACTION_PLANS: package.action_plans,
        SECTION_MARKET_REGIME_CONTEXT: package.market_regime_context,
    }
    included = [section for section, value in values.items() if _has_value(value)]
    missing = [section for section, value in values.items() if not _has_value(value)]
    return included, missing


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _combined_caution_symbols(package: DecisionSupportPackage) -> list[str]:
    symbols: list[str] = []
    for value in [
        _get(package.candidate_score_summary, "caution_symbols"),
        _get(package.portfolio_fit_summary, "concentration_caution_symbols"),
        _get(package.action_plan_summary, "caution_symbols"),
    ]:
        for symbol in _as_list(value):
            text = _text(symbol)
            if text != "Not available" and text not in symbols:
                symbols.append(text)
    return symbols


def _summary_note(
    package: DecisionSupportPackage,
    included_sections: list[str],
    missing_sections: list[str],
) -> str:
    del package
    if not included_sections:
        return "No decision-support package inputs were supplied."
    return (
        f"Decision-support package includes {len(included_sections)} sections "
        f"and is missing {len(missing_sections)} optional or required sections."
    )


def _get(value: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if not isinstance(value, dict):
        return default
    return value.get(key, default)


def _safe_int(value: Any) -> int:
    try:
        number = int(float(value))
    except (OverflowError, TypeError, ValueError):
        return 0
    return max(number, 0)


def _symbol_list(value: Any, max_items: int = 5) -> str:
    symbols = []
    for item in _as_list(value):
        text = _text(item)
        if text != "Not available" and text not in symbols:
            symbols.append(text.upper())
    if not symbols:
        return "None identified"
    return ", ".join(symbols[:max_items])


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _text(value: Any) -> str:
    sanitized = sanitize_package_value(value)
    if sanitized is None:
        return "Not available"
    if isinstance(sanitized, (dict, list)):
        return str(sanitized)
    return str(sanitized)
