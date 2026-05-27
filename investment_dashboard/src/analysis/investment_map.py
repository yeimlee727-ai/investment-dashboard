from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd

QUADRANT_UNDERVALUED_DISCOVERY = "undervalued_discovery"
QUADRANT_CHASE_RISK = "chase_risk"
QUADRANT_JUSTIFIED_RISE = "justified_rise"
QUADRANT_JUSTIFIED_DECLINE = "justified_decline"
QUADRANT_INSUFFICIENT_DATA = "insufficient_data"

STATUS_OK = "ok"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_INVALID_FINANCIAL = "invalid_financial_metric"
STATUS_INVALID_MARKET = "invalid_market_reaction"


@dataclass(frozen=True)
class InvestmentMapConfig:
    financial_growth_threshold_pct: float = 0.0
    market_reaction_threshold_pct: float = 0.0
    min_financial_growth_for_opportunity_pct: float = 5.0
    max_market_reaction_for_opportunity_pct: float = 5.0


@dataclass(frozen=True)
class InvestmentMapPoint:
    symbol: str
    name: str | None
    market: str | None
    financial_metric_name: str | None
    financial_metric_growth_pct: float | None
    market_reaction_pct: float | None
    market_cap: float | None
    quadrant: str
    score: float
    data_status: str


@dataclass(frozen=True)
class InvestmentMapSummary:
    total_count: int
    undervalued_discovery_count: int
    chase_risk_count: int
    justified_rise_count: int
    justified_decline_count: int
    insufficient_data_count: int
    top_undervalued_symbols: list[str]
    top_chase_risk_symbols: list[str]


def safe_growth_pct(previous_value: Any, current_value: Any) -> float | None:
    previous = _safe_float(previous_value)
    current = _safe_float(current_value)
    if previous is None or current is None or previous == 0:
        return None
    return _safe_float((current / previous - 1) * 100)


def classify_investment_map_quadrant(
    financial_metric_growth_pct: Any,
    market_reaction_pct: Any,
    config: InvestmentMapConfig | None = None,
) -> str:
    config = config or InvestmentMapConfig()
    financial_growth = _safe_float(financial_metric_growth_pct)
    market_reaction = _safe_float(market_reaction_pct)
    if financial_growth is None or market_reaction is None:
        return QUADRANT_INSUFFICIENT_DATA
    financial_improved = financial_growth >= config.financial_growth_threshold_pct
    market_improved = market_reaction >= config.market_reaction_threshold_pct
    if financial_improved and not market_improved:
        return QUADRANT_UNDERVALUED_DISCOVERY
    if not financial_improved and market_improved:
        return QUADRANT_CHASE_RISK
    if financial_improved and market_improved:
        return QUADRANT_JUSTIFIED_RISE
    return QUADRANT_JUSTIFIED_DECLINE


def calculate_investment_map_score(
    financial_metric_growth_pct: Any,
    market_reaction_pct: Any,
    quadrant: str | None = None,
    config: InvestmentMapConfig | None = None,
) -> float:
    config = config or InvestmentMapConfig()
    financial_growth = _safe_float(financial_metric_growth_pct)
    market_reaction = _safe_float(market_reaction_pct)
    if financial_growth is None or market_reaction is None:
        return 0.0
    quadrant = quadrant or classify_investment_map_quadrant(
        financial_growth, market_reaction, config
    )
    if quadrant == QUADRANT_UNDERVALUED_DISCOVERY:
        return _round_score(
            max(financial_growth - config.min_financial_growth_for_opportunity_pct, 0)
            + max(config.max_market_reaction_for_opportunity_pct - market_reaction, 0)
        )
    if quadrant == QUADRANT_CHASE_RISK:
        return _round_score(
            max(market_reaction - config.market_reaction_threshold_pct, 0)
            + max(config.financial_growth_threshold_pct - financial_growth, 0)
        )
    if quadrant == QUADRANT_JUSTIFIED_RISE:
        return _round_score(min(abs(financial_growth), abs(market_reaction)) * 0.25)
    if quadrant == QUADRANT_JUSTIFIED_DECLINE:
        return _round_score(min(abs(financial_growth), abs(market_reaction)) * 0.25)
    return 0.0


def build_investment_map_points(
    input_data: pd.DataFrame | list[dict[str, Any]],
    config: InvestmentMapConfig | None = None,
) -> list[InvestmentMapPoint]:
    config = config or InvestmentMapConfig()
    frame = _input_frame(input_data)
    if frame.empty:
        return []
    points = []
    for _, row in frame.iterrows():
        points.append(_point_from_row(row, config))
    return points


def build_investment_map_summary(
    points: list[InvestmentMapPoint] | pd.DataFrame,
) -> InvestmentMapSummary:
    point_list = _point_list(points)
    undervalued = _points_for(point_list, QUADRANT_UNDERVALUED_DISCOVERY)
    chase = _points_for(point_list, QUADRANT_CHASE_RISK)
    return InvestmentMapSummary(
        total_count=len(point_list),
        undervalued_discovery_count=len(undervalued),
        chase_risk_count=len(chase),
        justified_rise_count=len(_points_for(point_list, QUADRANT_JUSTIFIED_RISE)),
        justified_decline_count=len(
            _points_for(point_list, QUADRANT_JUSTIFIED_DECLINE)
        ),
        insufficient_data_count=len(
            _points_for(point_list, QUADRANT_INSUFFICIENT_DATA)
        ),
        top_undervalued_symbols=_top_symbols(undervalued),
        top_chase_risk_symbols=_top_symbols(chase),
    )


def _point_from_row(
    row: pd.Series,
    config: InvestmentMapConfig,
) -> InvestmentMapPoint:
    financial_growth = _growth_from_row(
        row,
        "financial_metric_growth_pct",
        "previous_financial_metric",
        "current_financial_metric",
    )
    market_reaction = _growth_from_row(
        row,
        "market_reaction_pct",
        "previous_market_value",
        "current_market_value",
    )
    quadrant = classify_investment_map_quadrant(
        financial_growth, market_reaction, config
    )
    status = _data_status(financial_growth, market_reaction)
    return InvestmentMapPoint(
        symbol=_symbol(row.get("symbol")),
        name=_optional_text(row.get("name")),
        market=_optional_text(row.get("market")),
        financial_metric_name=_optional_text(row.get("financial_metric_name")),
        financial_metric_growth_pct=financial_growth,
        market_reaction_pct=market_reaction,
        market_cap=_safe_float(row.get("market_cap")),
        quadrant=quadrant,
        score=calculate_investment_map_score(
            financial_growth, market_reaction, quadrant, config
        ),
        data_status=status,
    )


def _growth_from_row(
    row: pd.Series,
    growth_column: str,
    previous_column: str,
    current_column: str,
) -> float | None:
    growth = _safe_float(row.get(growth_column))
    if growth is not None:
        return growth
    return safe_growth_pct(row.get(previous_column), row.get(current_column))


def _data_status(financial_growth: float | None, market_reaction: float | None) -> str:
    if financial_growth is None and market_reaction is None:
        return STATUS_INSUFFICIENT_DATA
    if financial_growth is None:
        return STATUS_INVALID_FINANCIAL
    if market_reaction is None:
        return STATUS_INVALID_MARKET
    return STATUS_OK


def _input_frame(input_data: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    if input_data is None:
        return pd.DataFrame()
    if isinstance(input_data, pd.DataFrame):
        return input_data.copy()
    return pd.DataFrame(input_data)


def _point_list(
    points: list[InvestmentMapPoint] | pd.DataFrame,
) -> list[InvestmentMapPoint]:
    if isinstance(points, pd.DataFrame):
        return build_investment_map_points(points)
    return list(points or [])


def _points_for(
    points: list[InvestmentMapPoint], quadrant: str
) -> list[InvestmentMapPoint]:
    return [point for point in points if point.quadrant == quadrant]


def _top_symbols(points: list[InvestmentMapPoint], limit: int = 5) -> list[str]:
    ordered = sorted(points, key=lambda point: (-point.score, point.symbol))
    return [point.symbol for point in ordered[:limit]]


def _symbol(value: Any) -> str:
    text = _optional_text(value)
    return text.upper() if text else ""


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in {"", "nan", "none", "<na>"} else text


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _round_score(value: float) -> float:
    number = _safe_float(value)
    return round(number, 4) if number is not None else 0.0
