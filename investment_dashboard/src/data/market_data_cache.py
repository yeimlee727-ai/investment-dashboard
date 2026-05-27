from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Callable

import pandas as pd

MARKET_DATA_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume"]


@dataclass(frozen=True)
class MarketDataRequest:
    symbol: str
    start_date: str
    end_date: str
    interval: str = "1d"


@dataclass(frozen=True)
class MarketDataCacheConfig:
    cache_dir: Path = Path(".cache/market_data")
    ttl_hours: int = 24


class MarketDataCache:
    def __init__(
        self,
        config: MarketDataCacheConfig | None = None,
        downloader: Callable[[MarketDataRequest], pd.DataFrame] | None = None,
    ) -> None:
        self.config = config or MarketDataCacheConfig()
        self.downloader = downloader or self._download_with_yfinance

    def get_history(self, request: MarketDataRequest) -> pd.DataFrame:
        path = self.cache_path(request)
        if self._is_cache_valid(path):
            return normalize_price_history(pd.read_csv(path), request.symbol)

        frame = normalize_price_history(self.downloader(request), request.symbol)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return frame

    def cache_path(self, request: MarketDataRequest) -> Path:
        symbol = _safe_cache_part(request.symbol.upper())
        start = _safe_cache_part(request.start_date)
        end = _safe_cache_part(request.end_date)
        interval = _safe_cache_part(request.interval)
        return self.config.cache_dir / f"{symbol}_{start}_{end}_{interval}.csv"

    def _is_cache_valid(self, path: Path) -> bool:
        if not path.exists():
            return False
        if self.config.ttl_hours < 0:
            return True
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        return datetime.now() - modified <= timedelta(hours=self.config.ttl_hours)

    @staticmethod
    def _download_with_yfinance(request: MarketDataRequest) -> pd.DataFrame:
        import yfinance as yf

        return yf.download(
            request.symbol,
            start=request.start_date,
            end=request.end_date,
            interval=request.interval,
            progress=False,
            auto_adjust=False,
        )


def normalize_price_history(raw: pd.DataFrame | None, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return _empty_price_frame()

    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [_flatten_column(column) for column in frame.columns]

    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()

    columns = {_normalize_column_name(column): column for column in frame.columns}
    normalized = pd.DataFrame()
    normalized["date"] = _date_values(frame, columns)
    normalized["symbol"] = str(symbol).upper()
    for target in ["open", "high", "low", "close", "volume"]:
        source = _find_source_column(columns, target)
        normalized[target] = (
            pd.to_numeric(frame[source], errors="coerce") if source else pd.NA
        )

    normalized = normalized.dropna(subset=["date"])
    if normalized.empty:
        return _empty_price_frame()
    return normalized[MARKET_DATA_COLUMNS].reset_index(drop=True)


def _date_values(frame: pd.DataFrame, columns: dict[str, str]) -> pd.Series:
    source = _find_source_column(columns, "date")
    values = frame[source] if source else frame.index
    return pd.to_datetime(values, errors="coerce").dt.strftime("%Y-%m-%d")


def _find_source_column(columns: dict[str, str], target: str) -> str | None:
    aliases = {
        "date": ["date", "datetime", "timestamp"],
        "open": ["open"],
        "high": ["high"],
        "low": ["low"],
        "close": ["close", "adj close", "adj_close"],
        "volume": ["volume"],
    }
    for alias in aliases[target]:
        if alias in columns:
            return columns[alias]
    for normalized, original in columns.items():
        if normalized.endswith(f"_{target}") or normalized.startswith(f"{target}_"):
            return original
    return None


def _flatten_column(column: object) -> str:
    if not isinstance(column, tuple):
        return str(column)
    parts = [str(part) for part in column if str(part) and str(part) != "nan"]
    return "_".join(parts)


def _normalize_column_name(column: object) -> str:
    text = str(column).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text.replace("adj_close", "adj close")


def _safe_cache_part(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    return safe.strip("._-") or "unknown"


def _empty_price_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=MARKET_DATA_COLUMNS)
