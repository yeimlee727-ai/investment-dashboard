from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.data_providers.base import BaseDataProvider, Quote, empty_price_history
from src.data_providers.external_market_data_provider import ExternalMarketDataProvider
from src.data_providers.market_data_provider import MarketDataProvider


class FailingRealProvider(BaseDataProvider):
    def get_price_history(
        self, symbol: str, market: str = "KR", period: str | int = 180, **kwargs: object
    ) -> pd.DataFrame:
        return empty_price_history(
            symbol=symbol,
            market=market,
            data_source="REAL_ERROR",
            provider=self.get_provider_name(),
            error="network disabled",
        )

    def get_latest_quote(self, symbol: str, market: str = "KR") -> Quote:
        return Quote(
            symbol=symbol,
            market=market,
            price=None,
            change_pct=None,
            volume=None,
            value_traded=None,
            currency="USD",
            data_source="REAL_ERROR",
            provider=self.get_provider_name(),
            as_of=datetime.now().isoformat(timespec="seconds"),
            error="network disabled",
        )

    def get_provider_name(self) -> str:
        return "FailingRealProvider"

    def is_sample_mode(self) -> bool:
        return False


class EmptyRealProvider(FailingRealProvider):
    def get_price_history(
        self, symbol: str, market: str = "KR", period: str | int = 180, **kwargs: object
    ) -> pd.DataFrame:
        return empty_price_history(
            symbol=symbol,
            market=market,
            data_source="REAL_NO_DATA",
            provider=self.get_provider_name(),
            error="empty response",
        )


class SuccessfulRealProvider(FailingRealProvider):
    def get_price_history(
        self, symbol: str, market: str = "US", period: str | int = 180, **kwargs: object
    ) -> pd.DataFrame:
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
                "open": [100.0, 101.0],
                "high": [102.0, 103.0],
                "low": [99.0, 100.0],
                "close": [101.0, 102.0],
                "volume": [1000.0, 1100.0],
                "value_traded": [101000.0, 112200.0],
                "symbol": [symbol, symbol],
                "market": [market, market],
                "data_source": ["YFINANCE", "YFINANCE"],
                "provider": [self.get_provider_name(), self.get_provider_name()],
            }
        )
        df.attrs["data_source"] = "YFINANCE"
        df.attrs["provider"] = self.get_provider_name()
        df.attrs["error"] = None
        return df

    def get_latest_quote(self, symbol: str, market: str = "US") -> Quote:
        return Quote(
            symbol=symbol,
            market=market,
            price=102.0,
            change_pct=1.0,
            volume=1100.0,
            value_traded=112200.0,
            currency="USD",
            data_source="YFINANCE",
            provider=self.get_provider_name(),
            as_of="2026-01-02T00:00:00",
            error=None,
        )

    def get_provider_name(self) -> str:
        return "SuccessfulRealProvider"


def test_real_with_fallback_uses_sample_when_real_history_fails() -> None:
    provider = MarketDataProvider(
        mode="REAL_WITH_FALLBACK", real_provider=FailingRealProvider()
    )

    history = provider.get_price_history("AAPL", "US", period=30)

    assert not history.empty
    assert history["data_source"].unique().tolist() == ["SAMPLE_FALLBACK"]
    assert history.attrs["error"] == "network disabled"
    assert provider.is_fallback_mode() is True


def test_real_with_fallback_quote_records_error_and_sample_price() -> None:
    provider = MarketDataProvider(
        mode="REAL_WITH_FALLBACK", real_provider=FailingRealProvider()
    )

    quote = provider.get_latest_quote("AAPL", "US")

    assert quote.price is not None
    assert quote.data_source == "SAMPLE_FALLBACK"
    assert quote.error == "network disabled"


def test_real_provider_failure_quote_can_return_none_without_fallback() -> None:
    quote = FailingRealProvider().get_latest_quote("AAPL", "US")

    assert quote.price is None
    assert quote.error == "network disabled"


def test_empty_real_history_falls_back_without_breaking_dataframe() -> None:
    provider = MarketDataProvider(
        mode="REAL_WITH_FALLBACK", real_provider=EmptyRealProvider()
    )

    history = provider.get_price_history("AAPL", "US", period=30)

    assert not history.empty
    assert history.attrs["data_source"] == "SAMPLE_FALLBACK"
    assert "provider" in history.columns


def test_successful_real_provider_preserves_provider_and_data_source() -> None:
    provider = MarketDataProvider(
        mode="REAL_WITH_FALLBACK", real_provider=SuccessfulRealProvider()
    )

    history = provider.get_price_history("AAPL", "US", period=30)
    quote = provider.get_latest_quote("AAPL", "US")

    assert history["data_source"].unique().tolist() == ["YFINANCE"]
    assert provider.is_fallback_mode() is False
    assert quote.data_source == "YFINANCE"
    assert quote.provider == "SuccessfulRealProvider"


def test_external_provider_uses_yfinance_ticker_candidates() -> None:
    provider = ExternalMarketDataProvider()

    assert provider._ticker_candidates("AAPL", "US") == ["AAPL"]
    assert provider._ticker_candidates("005930", "KR") == ["005930.KS", "005930.KQ"]
    assert provider._ticker_candidates("091990.KQ", "KR") == ["091990.KQ"]
