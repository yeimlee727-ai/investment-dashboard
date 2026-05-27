from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd

STATUS_OK = "ok"
STATUS_MISSING_PRICE_HISTORY = "missing_price_history"
STATUS_INSUFFICIENT_PRICE_HISTORY = "insufficient_price_history"


@dataclass(frozen=True)
class PortfolioRiskInsightConfig:
    high_volatility_pct: float = 45.0
    medium_volatility_pct: float = 25.0
    deep_drawdown_pct: float = -30.0
    medium_drawdown_pct: float = -15.0
    weak_return_pct: float = -10.0
    strong_return_pct: float = 10.0


@dataclass(frozen=True)
class PortfolioRiskInsight:
    symbol: str
    insight_type: str
    severity: str
    message: str
    supporting_metrics: dict[str, float | int | str | None]
    data_status: str


@dataclass(frozen=True)
class PortfolioRiskInsightSummary:
    position_count: int
    high_severity_count: int
    caution_count: int
    watch_count: int
    missing_data_count: int
    high_volatility_symbols: list[str]
    deep_drawdown_symbols: list[str]
    weak_return_symbols: list[str]
    top_risk_symbols: list[str]
    overall_risk_note: str


def classify_volatility_level(
    annualized_volatility_pct: Any,
    config: PortfolioRiskInsightConfig | None = None,
) -> str:
    config = config or PortfolioRiskInsightConfig()
    value = _safe_float(annualized_volatility_pct)
    if value is None:
        return "unknown"
    if value >= config.high_volatility_pct:
        return "high"
    if value >= config.medium_volatility_pct:
        return "medium"
    return "low"


def classify_drawdown_level(
    max_drawdown_pct: Any,
    config: PortfolioRiskInsightConfig | None = None,
) -> str:
    config = config or PortfolioRiskInsightConfig()
    value = _safe_float(max_drawdown_pct)
    if value is None:
        return "unknown"
    if value <= config.deep_drawdown_pct:
        return "deep"
    if value <= config.medium_drawdown_pct:
        return "medium"
    return "controlled"


def classify_total_return_level(
    total_return_pct: Any,
    config: PortfolioRiskInsightConfig | None = None,
) -> str:
    config = config or PortfolioRiskInsightConfig()
    value = _safe_float(total_return_pct)
    if value is None:
        return "unknown"
    if value <= config.weak_return_pct:
        return "weak"
    if value >= config.strong_return_pct:
        return "strong"
    return "neutral"


def build_position_risk_insights(
    enriched: pd.DataFrame | list[dict[str, Any]],
    config: PortfolioRiskInsightConfig | None = None,
) -> list[PortfolioRiskInsight]:
    config = config or PortfolioRiskInsightConfig()
    frame = _input_frame(enriched)
    if frame.empty or "symbol" not in frame.columns:
        return []

    insights = []
    for _, row in frame.iterrows():
        symbol = _symbol(row.get("symbol"))
        if not symbol:
            continue
        insights.extend(_insights_for_row(symbol, row, config))
    return insights


def build_portfolio_risk_insight_summary(
    enriched: pd.DataFrame | list[dict[str, Any]],
    config: PortfolioRiskInsightConfig | None = None,
) -> PortfolioRiskInsightSummary:
    frame = _input_frame(enriched)
    insights = build_position_risk_insights(frame, config)
    high_volatility_symbols = _symbols_for(insights, "high_volatility")
    deep_drawdown_symbols = _symbols_for(insights, "deep_drawdown")
    weak_return_symbols = _symbols_for(insights, "weak_return")
    elevated_symbols = _unique(
        high_volatility_symbols + deep_drawdown_symbols + weak_return_symbols
    )
    missing_count = sum(
        1 for insight in insights if insight.insight_type == "missing_risk_data"
    )
    note = _overall_note(len(elevated_symbols), missing_count)
    return PortfolioRiskInsightSummary(
        position_count=len(frame) if "symbol" in frame.columns else 0,
        high_severity_count=sum(
            1 for insight in insights if insight.severity == "high"
        ),
        caution_count=sum(1 for insight in insights if insight.severity == "caution"),
        watch_count=sum(1 for insight in insights if insight.severity == "watch"),
        missing_data_count=missing_count,
        high_volatility_symbols=high_volatility_symbols,
        deep_drawdown_symbols=deep_drawdown_symbols,
        weak_return_symbols=weak_return_symbols,
        top_risk_symbols=elevated_symbols,
        overall_risk_note=note,
    )


def _insights_for_row(
    symbol: str,
    row: pd.Series,
    config: PortfolioRiskInsightConfig,
) -> list[PortfolioRiskInsight]:
    data_status = str(row.get("risk_data_status", "unknown"))
    metrics = _supporting_metrics(row)
    if data_status in {STATUS_MISSING_PRICE_HISTORY, "missing_risk_data", "unknown"}:
        return [
            PortfolioRiskInsight(
                symbol=symbol,
                insight_type="missing_risk_data",
                severity="watch",
                message=(
                    "Risk data is missing, so this position should be reviewed separately."
                ),
                supporting_metrics=metrics,
                data_status=data_status,
            )
        ]
    if data_status == STATUS_INSUFFICIENT_PRICE_HISTORY:
        return [
            PortfolioRiskInsight(
                symbol=symbol,
                insight_type="insufficient_risk_data",
                severity="watch",
                message=(
                    "Risk data is insufficient, so this position should be reviewed separately."
                ),
                supporting_metrics=metrics,
                data_status=data_status,
            )
        ]

    insights = []
    volatility_level = classify_volatility_level(
        row.get("annualized_volatility_pct"), config
    )
    drawdown_level = classify_drawdown_level(row.get("max_drawdown_pct"), config)
    return_level = classify_total_return_level(row.get("total_return_pct"), config)
    if volatility_level == "high":
        insights.append(
            PortfolioRiskInsight(
                symbol=symbol,
                insight_type="high_volatility",
                severity="caution",
                message="This position shows elevated annualized volatility.",
                supporting_metrics=metrics,
                data_status=data_status,
            )
        )
    if drawdown_level == "deep":
        insights.append(
            PortfolioRiskInsight(
                symbol=symbol,
                insight_type="deep_drawdown",
                severity="high",
                message="This position has experienced a deep historical drawdown.",
                supporting_metrics=metrics,
                data_status=data_status,
            )
        )
    if return_level == "weak":
        insights.append(
            PortfolioRiskInsight(
                symbol=symbol,
                insight_type="weak_return",
                severity="watch",
                message="This position shows weak historical total return in the provided period.",
                supporting_metrics=metrics,
                data_status=data_status,
            )
        )
    if insights:
        return insights
    return [
        PortfolioRiskInsight(
            symbol=symbol,
            insight_type="balanced_risk_profile",
            severity="info",
            message=(
                "This position does not show elevated volatility or deep drawdown "
                "based on the provided data."
            ),
            supporting_metrics=metrics,
            data_status=data_status,
        )
    ]


def _supporting_metrics(row: pd.Series) -> dict[str, float | int | str | None]:
    return {
        "total_return_pct": _safe_float(row.get("total_return_pct")),
        "annualized_volatility_pct": _safe_float(row.get("annualized_volatility_pct")),
        "max_drawdown_pct": _safe_float(row.get("max_drawdown_pct")),
        "observation_count": _safe_int(row.get("observation_count")),
    }


def _input_frame(value: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return pd.DataFrame(value)


def _symbol(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    return "" if text.lower() in {"", "nan", "none", "<na>"} else text


def _symbols_for(insights: list[PortfolioRiskInsight], insight_type: str) -> list[str]:
    return _unique(
        insight.symbol for insight in insights if insight.insight_type == insight_type
    )


def _unique(values: Any) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _overall_note(elevated_count: int, missing_count: int) -> str:
    if elevated_count:
        return (
            "Portfolio risk review found "
            f"{elevated_count} positions with elevated volatility or deep drawdown."
        )
    if missing_count:
        return (
            "Portfolio risk review is limited because "
            f"{missing_count} positions are missing market-risk data."
        )
    return "No elevated position-level market-risk flags were found from the provided data."


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _safe_int(value: Any) -> int | None:
    number = _safe_float(value)
    return int(number) if number is not None else None
