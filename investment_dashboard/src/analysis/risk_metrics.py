from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RiskMetricResult:
    symbol: str
    observation_count: int
    start_date: str | None
    end_date: str | None
    total_return_pct: float | None
    annualized_volatility_pct: float | None
    max_drawdown_pct: float | None


def calculate_daily_returns(frame: pd.DataFrame) -> pd.Series:
    prices = _clean_close_prices(frame)
    if len(prices) < 2:
        return pd.Series(dtype="float64")
    returns = prices.pct_change()
    returns = returns.replace([math.inf, -math.inf], pd.NA).dropna()
    return returns.astype("float64")


def calculate_total_return_pct(frame: pd.DataFrame) -> float | None:
    prices = _clean_close_prices(frame)
    if len(prices) < 2:
        return None
    start = prices.iloc[0]
    end = prices.iloc[-1]
    if start == 0:
        return None
    return _safe_float((end / start - 1) * 100)


def calculate_annualized_volatility_pct(frame: pd.DataFrame) -> float | None:
    returns = calculate_daily_returns(frame)
    if len(returns) < 2:
        return None
    volatility = returns.std(ddof=1) * math.sqrt(252) * 100
    return _safe_float(volatility)


def calculate_max_drawdown_pct(frame: pd.DataFrame) -> float | None:
    prices = _clean_close_prices(frame)
    if prices.empty:
        return None
    rolling_peak = prices.cummax()
    drawdowns = prices / rolling_peak - 1
    drawdowns = drawdowns.replace([math.inf, -math.inf], pd.NA).dropna()
    if drawdowns.empty:
        return None
    return _safe_float(drawdowns.min() * 100)


def build_risk_metric_result(frame: pd.DataFrame, symbol: str) -> RiskMetricResult:
    prices = _clean_close_prices(frame)
    dates = (
        _clean_dates(frame).reindex(prices.index) if not prices.empty else pd.Series()
    )
    return RiskMetricResult(
        symbol=str(symbol).upper(),
        observation_count=len(prices),
        start_date=_date_at(dates, 0),
        end_date=_date_at(dates, -1),
        total_return_pct=calculate_total_return_pct(frame),
        annualized_volatility_pct=calculate_annualized_volatility_pct(frame),
        max_drawdown_pct=calculate_max_drawdown_pct(frame),
    )


def _clean_close_prices(frame: pd.DataFrame) -> pd.Series:
    if frame is None or frame.empty or "close" not in frame.columns:
        return pd.Series(dtype="float64")
    prices = pd.to_numeric(frame["close"], errors="coerce")
    prices = prices.replace([math.inf, -math.inf], pd.NA).dropna()
    return prices.astype("float64")


def _clean_dates(frame: pd.DataFrame) -> pd.Series:
    if frame is None or frame.empty or "date" not in frame.columns:
        return pd.Series(dtype="object")
    dates = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return dates.dropna()


def _date_at(dates: pd.Series, position: int) -> str | None:
    if dates.empty:
        return None
    try:
        return str(dates.iloc[position])
    except IndexError:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number
