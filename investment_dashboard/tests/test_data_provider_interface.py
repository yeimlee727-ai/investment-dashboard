from __future__ import annotations

from src.data_providers.base import BaseDataProvider, Quote
from src.data_providers.market_data_provider import MarketDataProvider
from src.data_providers.sample_provider import SampleDataProvider


def test_sample_provider_implements_base_interface() -> None:
    provider = SampleDataProvider()

    assert isinstance(provider, BaseDataProvider)
    assert provider.get_provider_name() == "SampleDataProvider"
    assert provider.is_sample_mode() is True

    quote = provider.get_latest_quote("AAPL", "US")

    assert isinstance(quote, Quote)
    assert quote.symbol == "AAPL"
    assert quote.market == "US"
    assert quote.price is not None
    assert quote.data_source == "SAMPLE"


def test_market_data_provider_exposes_mode_and_name() -> None:
    sample = MarketDataProvider(mode="SAMPLE")
    real_with_fallback = MarketDataProvider(mode="REAL_WITH_FALLBACK")

    assert sample.get_provider_name() == "MarketDataProvider(SAMPLE)"
    assert sample.is_sample_mode() is True
    assert real_with_fallback.get_provider_name() == (
        "MarketDataProvider(REAL_WITH_FALLBACK)"
    )
