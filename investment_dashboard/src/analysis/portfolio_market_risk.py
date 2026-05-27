from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd

from src.analysis.risk_metrics import build_risk_metric_result

RISK_STATUS_OK = "ok"
RISK_STATUS_MISSING_HISTORY = "missing_price_history"
RISK_STATUS_INSUFFICIENT_HISTORY = "insufficient_price_history"
RISK_STATUS_INVALID_SYMBOL = "invalid_symbol"

RISK_COLUMNS = [
    "total_return_pct",
    "annualized_volatility_pct",
    "max_drawdown_pct",
    "observation_count",
    "risk_data_status",
]


@dataclass(frozen=True)
class PortfolioMarketRiskConfig:
    symbol_column: str = "symbol"
    minimum_observations: int = 2


@dataclass(frozen=True)
class PortfolioRiskEnrichmentResult:
    holdings: pd.DataFrame
    summary: dict[str, Any]
    error: str | None = None


def enrich_portfolio_with_market_risk(
    holdings: pd.DataFrame | list[dict[str, Any]],
    price_history_by_symbol: dict[str, pd.DataFrame] | None,
    config: PortfolioMarketRiskConfig | None = None,
) -> PortfolioRiskEnrichmentResult:
    config = config or PortfolioMarketRiskConfig()
    frame = _holdings_frame(holdings)
    if frame.empty:
        enriched = _empty_enriched_frame(frame)
        return PortfolioRiskEnrichmentResult(
            enriched, build_portfolio_market_risk_summary(enriched)
        )
    if config.symbol_column not in frame.columns:
        enriched = _empty_enriched_frame(frame)
        return PortfolioRiskEnrichmentResult(
            enriched,
            build_portfolio_market_risk_summary(enriched),
            error=f"missing_symbol_column:{config.symbol_column}",
        )

    histories = {
        str(symbol).upper(): history
        for symbol, history in (price_history_by_symbol or {}).items()
    }
    rows = []
    for _, holding in frame.iterrows():
        row = holding.to_dict()
        symbol = _normalize_symbol(row.get(config.symbol_column))
        if not symbol:
            rows.append(_with_metrics(row, "", None, RISK_STATUS_INVALID_SYMBOL))
            continue

        history = histories.get(symbol)
        if history is None or history.empty:
            rows.append(_with_metrics(row, symbol, None, RISK_STATUS_MISSING_HISTORY))
            continue

        metrics = build_risk_metric_result(history, symbol)
        status = (
            RISK_STATUS_OK
            if metrics.observation_count >= config.minimum_observations
            and metrics.total_return_pct is not None
            else RISK_STATUS_INSUFFICIENT_HISTORY
        )
        rows.append(_with_metrics(row, symbol, metrics, status))

    enriched = pd.DataFrame(rows)
    return PortfolioRiskEnrichmentResult(
        enriched,
        build_portfolio_market_risk_summary(enriched),
    )


def build_portfolio_market_risk_summary(enriched: pd.DataFrame) -> dict[str, Any]:
    if enriched is None or enriched.empty:
        return {
            "position_count": 0,
            "positions_with_risk_data": 0,
            "positions_missing_risk_data": 0,
            "average_total_return_pct": None,
            "average_annualized_volatility_pct": None,
            "worst_max_drawdown_pct": None,
            "highest_volatility_symbol": None,
            "deepest_drawdown_symbol": None,
        }

    ok_frame = enriched[enriched.get("risk_data_status") == RISK_STATUS_OK].copy()
    return {
        "position_count": len(enriched),
        "positions_with_risk_data": len(ok_frame),
        "positions_missing_risk_data": len(enriched) - len(ok_frame),
        "average_total_return_pct": _mean_or_none(ok_frame, "total_return_pct"),
        "average_annualized_volatility_pct": _mean_or_none(
            ok_frame, "annualized_volatility_pct"
        ),
        "worst_max_drawdown_pct": _min_or_none(ok_frame, "max_drawdown_pct"),
        "highest_volatility_symbol": _symbol_for_extreme(
            ok_frame, "annualized_volatility_pct", highest=True
        ),
        "deepest_drawdown_symbol": _symbol_for_extreme(
            ok_frame, "max_drawdown_pct", highest=False
        ),
    }


def _holdings_frame(holdings: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    if holdings is None:
        return pd.DataFrame()
    if isinstance(holdings, pd.DataFrame):
        return holdings.copy()
    return pd.DataFrame(holdings)


def _empty_enriched_frame(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    for column in RISK_COLUMNS:
        if column not in enriched.columns:
            enriched[column] = pd.Series(dtype="object")
    return enriched


def _normalize_symbol(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    return text


def _with_metrics(
    row: dict[str, Any], symbol: str, metrics: Any, status: str
) -> dict[str, Any]:
    row["symbol"] = symbol
    row["total_return_pct"] = getattr(metrics, "total_return_pct", None)
    row["annualized_volatility_pct"] = getattr(
        metrics, "annualized_volatility_pct", None
    )
    row["max_drawdown_pct"] = getattr(metrics, "max_drawdown_pct", None)
    row["observation_count"] = getattr(metrics, "observation_count", 0)
    row["risk_data_status"] = status
    return row


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype="float64")
    values = pd.to_numeric(frame[column], errors="coerce")
    values = values.replace([math.inf, -math.inf], pd.NA).dropna()
    return values.astype("float64")


def _mean_or_none(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric_series(frame, column)
    return _safe_float(values.mean()) if not values.empty else None


def _min_or_none(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric_series(frame, column)
    return _safe_float(values.min()) if not values.empty else None


def _symbol_for_extreme(frame: pd.DataFrame, column: str, highest: bool) -> str | None:
    values = _numeric_series(frame, column)
    if values.empty or "symbol" not in frame.columns:
        return None
    index = values.idxmax() if highest else values.idxmin()
    return str(frame.loc[index, "symbol"])


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number
