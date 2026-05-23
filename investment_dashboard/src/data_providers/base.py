from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    @abstractmethod
    def get_price_history(
        self, symbol: str, market: str = "KR", days: int = 180
    ) -> pd.DataFrame:
        """Return OHLCV history with date, open, high, low, close, volume columns."""

    @abstractmethod
    def get_quote(self, symbol: str, market: str = "KR") -> dict[str, float | str]:
        """Return a latest quote snapshot."""
