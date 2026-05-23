from __future__ import annotations

from src.data_providers.base import HISTORY_COLUMNS
from src.data_providers.sample_provider import SampleDataProvider


def test_sample_history_is_deterministic_and_standardized() -> None:
    provider = SampleDataProvider()

    first = provider.get_price_history("005930", "KR", period=30)
    second = provider.get_price_history("005930", "KR", period=30)

    assert list(first[HISTORY_COLUMNS].columns) == HISTORY_COLUMNS
    assert first["close"].tolist() == second["close"].tolist()
    assert first["data_source"].unique().tolist() == ["SAMPLE"]
    assert first["provider"].unique().tolist() == ["SampleDataProvider"]
    assert first.attrs["error"] is None


def test_sample_quote_has_standard_fields_and_legacy_aliases() -> None:
    provider = SampleDataProvider()

    quote = provider.get_quote("NVDA", "US")

    assert quote["symbol"] == "NVDA"
    assert quote["market"] == "US"
    assert quote["price"] is not None
    assert quote["currency"] == "USD"
    assert quote["data_source"] == "SAMPLE"
    assert quote["change_rate"] == quote["change_pct"]
    assert quote["trading_value"] == quote["value_traded"]
