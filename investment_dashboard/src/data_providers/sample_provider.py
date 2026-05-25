from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib

import numpy as np
import pandas as pd

from src.data_providers.base import BaseDataProvider, FXRate, Quote


class SampleDataProvider(BaseDataProvider):
    """Deterministic sample data provider for offline MVP usage."""

    US_SAMPLE_BASE_PRICES = {
        "AAPL": 190.0,
        "MSFT": 420.0,
        "NVDA": 120.0,
        "TSLA": 180.0,
        "GRAB": 3.6,
    }

    def get_price_history(
        self, symbol: str, market: str = "KR", period: str | int = 180, **kwargs: object
    ) -> pd.DataFrame:
        days = self._normalize_period(period, kwargs.get("days"))
        market = market.upper()
        seed = self._seed_for(symbol, market)
        rng = np.random.default_rng(seed)
        end = date.today()
        dates = [end - timedelta(days=i) for i in range(days * 2)]
        business_dates = sorted([d for d in dates if d.weekday() < 5])[-days:]
        base_price = self._base_price(symbol, market, seed)
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
        df["change_pct"] = df["close"].pct_change().fillna(0) * 100
        df["value_traded"] = df["close"] * df["volume"]
        df["symbol"] = symbol.upper()
        df["market"] = market
        df["data_source"] = "SAMPLE"
        df["provider"] = self.get_provider_name()
        df["change_rate"] = df["change_pct"]
        df["trading_value"] = df["value_traded"]
        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "change_pct",
            "value_traded",
            "change_rate",
            "trading_value",
        ]
        df[numeric_columns] = df[numeric_columns].round(2)
        df.attrs["data_source"] = "SAMPLE"
        df.attrs["provider"] = self.get_provider_name()
        df.attrs["error"] = None
        return df

    def get_latest_quote(self, symbol: str, market: str = "KR") -> Quote:
        df = self.get_price_history(symbol=symbol, market=market, period=30)
        latest = df.iloc[-1]
        return Quote(
            symbol=symbol.upper(),
            market=market.upper(),
            price=float(latest["close"]),
            change_pct=float(latest["change_pct"]),
            volume=float(latest["volume"]),
            value_traded=float(latest["value_traded"]),
            currency="KRW" if market.upper() == "KR" else "USD",
            data_source="SAMPLE",
            provider=self.get_provider_name(),
            as_of=datetime.now().isoformat(timespec="seconds"),
            error=None,
        )

    def get_provider_name(self) -> str:
        return "SampleDataProvider"

    def is_sample_mode(self) -> bool:
        return True

    def get_fx_rate(self, pair: str = "USD/KRW") -> FXRate:
        if pair.upper() != "USD/KRW":
            return FXRate(
                pair=pair.upper(),
                rate=None,
                data_source="SAMPLE_FX_UNSUPPORTED",
                provider=self.get_provider_name(),
                as_of=datetime.now().isoformat(timespec="seconds"),
                error="샘플 provider는 USD/KRW만 지원합니다.",
            )
        return FXRate(
            pair="USD/KRW",
            rate=1350.0,
            data_source="SAMPLE_FX",
            provider=self.get_provider_name(),
            as_of=datetime.now().isoformat(timespec="seconds"),
            error=None,
        )

    def _seed_for(self, symbol: str, market: str) -> int:
        key = f"{market.upper()}:{symbol.upper()}".encode("utf-8")
        digest = hashlib.sha256(key).hexdigest()
        return int(digest[:16], 16) % (2**32)

    def _base_price(self, symbol: str, market: str, seed: int) -> float:
        if market == "KR":
            return 50_000.0
        symbol = symbol.upper()
        if symbol in self.US_SAMPLE_BASE_PRICES:
            return self.US_SAMPLE_BASE_PRICES[symbol]
        # Keep US sample quotes in USD-scale units instead of KRW-like prices.
        return 15.0 + (seed % 23_500) / 100.0

    def _normalize_period(self, period: str | int, days: object = None) -> int:
        if isinstance(days, int):
            return max(days, 1)
        if isinstance(period, int):
            return max(period, 1)
        period = period.lower().strip()
        if period.endswith("d"):
            return max(int(period[:-1]), 1)
        if period.endswith("mo"):
            return max(int(period[:-2]) * 21, 1)
        if period.endswith("y"):
            return max(int(period[:-1]) * 252, 1)
        return 180
