from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

import pandas as pd

DataMode = Literal["SAMPLE", "REAL_WITH_FALLBACK"]

HISTORY_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "value_traded",
    "symbol",
    "market",
    "data_source",
    "provider",
]


@dataclass(frozen=True)
class Quote:
    symbol: str
    market: str
    price: float | None
    change_pct: float | None
    volume: float | None
    value_traded: float | None
    currency: str
    data_source: str
    provider: str
    as_of: datetime | str | None
    error: str | None = None

    def to_dict(self) -> dict[str, float | str | None]:
        payload = asdict(self)
        payload["change_rate"] = self.change_pct
        payload["trading_value"] = self.value_traded
        return payload


class BaseDataProvider(ABC):
    @abstractmethod
    def get_price_history(
        self, symbol: str, market: str = "KR", period: str | int = 180
    ) -> pd.DataFrame:
        """Return standardized OHLCV history."""

    @abstractmethod
    def get_latest_quote(self, symbol: str, market: str = "KR") -> Quote:
        """Return a standardized latest quote snapshot."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return a human-readable provider name."""

    @abstractmethod
    def is_sample_mode(self) -> bool:
        """Return True when the provider is serving generated sample data."""

    def get_quote(
        self, symbol: str, market: str = "KR"
    ) -> dict[str, float | str | None]:
        return self.get_latest_quote(symbol=symbol, market=market).to_dict()


DataProvider = BaseDataProvider


def empty_price_history(
    symbol: str,
    market: str,
    data_source: str,
    provider: str,
    error: str | None = None,
) -> pd.DataFrame:
    df = pd.DataFrame(columns=HISTORY_COLUMNS)
    df.attrs["symbol"] = symbol
    df.attrs["market"] = market.upper()
    df.attrs["data_source"] = data_source
    df.attrs["provider"] = provider
    df.attrs["error"] = error
    return df
