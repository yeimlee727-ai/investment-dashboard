from __future__ import annotations

import pandas as pd

from src.data_providers.base import DataProvider
from src.data_providers.sample_provider import SampleDataProvider


class MarketDataProvider(DataProvider):
    """Facade for swappable KR/US market data sources.

    This MVP delegates to sample data. Replace the internals with a real vendor
    adapter later without changing scanner, scoring, or UI code.
    """

    def __init__(self, fallback_provider: DataProvider | None = None) -> None:
        self.fallback_provider = fallback_provider or SampleDataProvider()

    @property
    def is_sample_mode(self) -> bool:
        return isinstance(self.fallback_provider, SampleDataProvider)

    def get_price_history(self, symbol: str, market: str = "KR", days: int = 180) -> pd.DataFrame:
        try:
            return self.fallback_provider.get_price_history(symbol=symbol, market=market, days=days)
        except Exception as exc:
            raise RuntimeError(f"가격 데이터 조회 실패: {symbol}") from exc

    def get_quote(self, symbol: str, market: str = "KR") -> dict[str, float | str]:
        try:
            return self.fallback_provider.get_quote(symbol=symbol, market=market)
        except Exception as exc:
            raise RuntimeError(f"현재가 조회 실패: {symbol}") from exc
