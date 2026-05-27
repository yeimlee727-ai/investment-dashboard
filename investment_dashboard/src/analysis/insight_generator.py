from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_MISSING_INPUTS = "missing_inputs"


@dataclass(frozen=True)
class InsightGeneratorConfig:
    include_disclaimer: bool = True
    max_symbols_per_section: int = 5
    missing_data_note: str = "Some analysis inputs are missing or incomplete."
    report_title: str = "Portfolio Decision-Support Insight Report"


@dataclass(frozen=True)
class InsightSection:
    title: str
    status: str
    bullet_points: list[str]
    note: str | None = None


@dataclass(frozen=True)
class InsightReport:
    title: str
    sections: list[InsightSection]
    data_status: str
    generated_by: str
    markdown: str


def sanitize_text_value(value: Any) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "Not available"
    text = str(value).strip()
    if not text or text.lower() in {"nan", "inf", "-inf", "none", "<na>"}:
        return "Not available"
    return text


def format_symbol_list(symbols: Any, max_items: int = 5) -> str:
    values = []
    if symbols is None:
        return "None identified"
    if isinstance(symbols, str):
        raw_values = [symbols]
    else:
        try:
            raw_values = list(symbols)
        except TypeError:
            raw_values = [symbols]
    for symbol in raw_values:
        text = sanitize_text_value(symbol)
        if text != "Not available" and text not in values:
            values.append(text.upper())
    if not values:
        return "None identified"
    return ", ".join(values[:max_items])


def build_portfolio_context_section(
    portfolio_context: dict[str, Any] | None,
    config: InsightGeneratorConfig | None = None,
) -> InsightSection:
    config = config or InsightGeneratorConfig()
    context = portfolio_context or {}
    if not context:
        return InsightSection(
            title="Portfolio Context",
            status=STATUS_MISSING_INPUTS,
            bullet_points=[config.missing_data_note],
            note="Portfolio context was not supplied.",
        )
    bullets = [
        f"Position count: {sanitize_text_value(context.get('position_count'))}.",
        f"Sector exposure: {sanitize_text_value(context.get('sector_exposure'))}.",
        f"Country exposure: {sanitize_text_value(context.get('country_exposure'))}.",
        f"Currency exposure: {sanitize_text_value(context.get('currency_exposure'))}.",
        f"Concentration note: {sanitize_text_value(context.get('concentration_notes'))}.",
    ]
    return InsightSection("Portfolio Context", STATUS_OK, bullets)


def build_risk_insight_section(
    risk_insight_summary: dict[str, Any] | None,
    config: InsightGeneratorConfig | None = None,
) -> InsightSection:
    config = config or InsightGeneratorConfig()
    summary = risk_insight_summary or {}
    if not summary:
        return InsightSection(
            "Risk Review",
            STATUS_MISSING_INPUTS,
            [config.missing_data_note],
            "Risk insight summary was not supplied.",
        )
    bullets = [
        "Elevated volatility symbols: "
        f"{format_symbol_list(summary.get('high_volatility_symbols'), config.max_symbols_per_section)}.",
        "Deep drawdown symbols: "
        f"{format_symbol_list(summary.get('deep_drawdown_symbols'), config.max_symbols_per_section)}.",
        "Weak return symbols: "
        f"{format_symbol_list(summary.get('weak_return_symbols'), config.max_symbols_per_section)}.",
        f"Risk note: {sanitize_text_value(summary.get('overall_risk_note'))}.",
    ]
    return InsightSection("Risk Review", STATUS_OK, bullets)


def build_candidate_review_section(
    candidate_score_summary: dict[str, Any] | None,
    config: InsightGeneratorConfig | None = None,
) -> InsightSection:
    config = config or InsightGeneratorConfig()
    summary = candidate_score_summary or {}
    if not summary:
        return InsightSection(
            "Candidate Review",
            STATUS_MISSING_INPUTS,
            [config.missing_data_note],
            "Candidate score summary was not supplied.",
        )
    bullets = [
        "Higher-ranked review candidates: "
        f"{format_symbol_list(summary.get('top_symbols'), config.max_symbols_per_section)}.",
        "Candidate caution symbols: "
        f"{format_symbol_list(summary.get('caution_symbols'), config.max_symbols_per_section)}.",
        f"Candidate review note: {sanitize_text_value(summary.get('summary_note'))}.",
        "Candidates are listed for additional manual review only.",
    ]
    return InsightSection("Candidate Review", STATUS_OK, bullets)


def build_portfolio_fit_section(
    portfolio_fit_summary: dict[str, Any] | None,
    config: InsightGeneratorConfig | None = None,
) -> InsightSection:
    config = config or InsightGeneratorConfig()
    summary = portfolio_fit_summary or {}
    if not summary:
        return InsightSection(
            "Portfolio Fit Review",
            STATUS_MISSING_INPUTS,
            [config.missing_data_note],
            "Portfolio fit summary was not supplied.",
        )
    bullets = [
        "Top portfolio fit review symbols: "
        f"{format_symbol_list(summary.get('top_fit_symbols'), config.max_symbols_per_section)}.",
        "Concentration caution symbols: "
        f"{format_symbol_list(summary.get('concentration_caution_symbols'), config.max_symbols_per_section)}.",
        f"Portfolio fit note: {sanitize_text_value(summary.get('summary_note'))}.",
        "Fit review does not specify any position size.",
    ]
    return InsightSection("Portfolio Fit Review", STATUS_OK, bullets)


def build_market_regime_section(
    market_regime_context: dict[str, Any] | None,
    config: InsightGeneratorConfig | None = None,
) -> InsightSection:
    config = config or InsightGeneratorConfig()
    regime = market_regime_context or {}
    if not regime:
        return InsightSection(
            "Market Regime Context",
            STATUS_PARTIAL,
            [
                "Market regime data is manually supplied or mocked in this version.",
                config.missing_data_note,
            ],
            "Market regime context was omitted.",
        )
    bullets = [
        f"Regime label: {sanitize_text_value(regime.get('regime_label'))}.",
        f"Macro notes: {sanitize_text_value(regime.get('macro_notes'))}.",
        f"Data status: {sanitize_text_value(regime.get('data_status'))}.",
        "This context should be manually validated before any investment decision.",
    ]
    return InsightSection("Market Regime Context", STATUS_OK, bullets)


def build_disclaimer_section(
    config: InsightGeneratorConfig | None = None,
) -> InsightSection:
    return InsightSection(
        "Limitations / Disclaimer",
        STATUS_OK,
        [
            "This report is decision-support only and is not financial advice.",
            "No return is assured by this report.",
            "This report does not execute orders or access brokerage accounts.",
            "Data quality and risk conditions should be manually reviewed before any investment decision.",
        ],
    )


def build_mock_insight_report(
    portfolio_context: dict[str, Any] | None = None,
    risk_insight_summary: dict[str, Any] | None = None,
    candidate_score_summary: dict[str, Any] | None = None,
    portfolio_fit_summary: dict[str, Any] | None = None,
    market_regime_context: dict[str, Any] | None = None,
    config: InsightGeneratorConfig | None = None,
) -> InsightReport:
    config = config or InsightGeneratorConfig()
    sections = [
        build_portfolio_context_section(portfolio_context, config),
        build_risk_insight_section(risk_insight_summary, config),
        build_candidate_review_section(candidate_score_summary, config),
        build_portfolio_fit_section(portfolio_fit_summary, config),
        build_market_regime_section(market_regime_context, config),
    ]
    if config.include_disclaimer:
        sections.append(build_disclaimer_section(config))
    data_status = _report_data_status(sections)
    report = InsightReport(
        title=config.report_title,
        sections=sections,
        data_status=data_status,
        generated_by="mock_insight_generator",
        markdown="",
    )
    markdown = render_insight_report_markdown(report)
    return InsightReport(
        title=report.title,
        sections=report.sections,
        data_status=report.data_status,
        generated_by=report.generated_by,
        markdown=markdown,
    )


def render_insight_report_markdown(report: InsightReport) -> str:
    lines = [f"# {sanitize_text_value(report.title)}", ""]
    lines.append(f"Data status: {sanitize_text_value(report.data_status)}")
    lines.append(f"Generated by: {sanitize_text_value(report.generated_by)}")
    for section in report.sections:
        lines.extend(["", f"## {section.title}", f"Status: {section.status}"])
        for bullet in section.bullet_points:
            lines.append(f"- {sanitize_text_value(bullet)}")
        if section.note:
            lines.append(f"Note: {sanitize_text_value(section.note)}")
    return "\n".join(lines).strip() + "\n"


def _report_data_status(sections: list[InsightSection]) -> str:
    if not sections:
        return STATUS_MISSING_INPUTS
    statuses = {section.status for section in sections}
    if STATUS_MISSING_INPUTS in statuses:
        return STATUS_MISSING_INPUTS
    if STATUS_PARTIAL in statuses:
        return STATUS_PARTIAL
    return STATUS_OK
