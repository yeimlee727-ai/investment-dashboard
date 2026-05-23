from __future__ import annotations

from datetime import date, timedelta
import hashlib

import numpy as np
import pandas as pd

from src.data_providers.base import DataProvider


class SampleDataProvider(DataProvider):
    """Deterministic sample data provider for offline MVP usage."""

    def get_price_history(self, symbol: str, market: str = "KR", days: int = 180) -> pd.DataFrame:
        seed = self._seed_for(symbol, market)
        rng = np.random.default_rng(seed)
        end = date.today()
        dates = [end - timedelta(days=i) for i in range(days * 2)]
        business_dates = sorted([d for d in dates if d.weekday() < 5])[-days:]
        base_price = 50_000 if market.upper() == "KR" else 150
        drift = rng.normal(0.0008, 0.018, len(business_dates))
        close = base_price * np.cumprod(1 + drift)
        open_ = close * (1 + rng.normal(0, 0.006, len(close)))
        high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.025, len(close)))
        low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.025, len(close)))
        volume = rng.integers(100_000, 4_000_000, len(close)).astype(float)
        if len(volume) > 10:
            volume[-1] *= rng.uniform(1.5, 3.5)
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(business_dates),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
        df["change_rate"] = df["close"].pct_change().fillna(0) * 100
        df["trading_value"] = df["close"] * df["volume"]
        numeric_columns = ["open", "high", "low", "close", "volume", "change_rate", "trading_value"]
        df[numeric_columns] = df[numeric_columns].round(2)
        return df

    def get_quote(self, symbol: str, market: str = "KR") -> dict[str, float | str]:
        df = self.get_price_history(symbol=symbol, market=market, days=30)
        latest = df.iloc[-1]
        return {
            "symbol": symbol,
            "market": market,
            "price": float(latest["close"]),
            "change_rate": float(latest["change_rate"]),
            "volume": float(latest["volume"]),
            "trading_value": float(latest["trading_value"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "close": float(latest["close"]),
        }

    def _seed_for(self, symbol: str, market: str) -> int:
        key = f"{market.upper()}:{symbol.upper()}".encode("utf-8")
        digest = hashlib.sha256(key).hexdigest()
        return int(digest[:16], 16) % (2**32)
