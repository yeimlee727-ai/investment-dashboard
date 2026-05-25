from __future__ import annotations

import pandas as pd

from src.data_providers.base import BaseDataProvider, DataMode, FXRate, Quote
from src.data_providers.external_market_data_provider import ExternalMarketDataProvider
from src.data_providers.sample_provider import SampleDataProvider


class MarketDataProvider(BaseDataProvider):
    """Facade for SAMPLE and read-only real-data-with-fallback modes."""

    def __init__(
        self,
        mode: DataMode = "SAMPLE",
        sample_provider: BaseDataProvider | None = None,
        real_provider: BaseDataProvider | None = None,
        fallback_provider: BaseDataProvider | None = None,
    ) -> None:
        self.mode: DataMode = (
            mode if mode in {"SAMPLE", "REAL_WITH_FALLBACK"} else "SAMPLE"
        )
        self.sample_provider = (
            sample_provider or fallback_provider or SampleDataProvider()
        )
        self.real_provider = real_provider or ExternalMarketDataProvider()
        self.last_data_source = "SAMPLE"
        self.last_error: str | None = None

    def get_price_history(
        self, symbol: str, market: str = "KR", period: str | int = 180, **kwargs: object
    ) -> pd.DataFrame:
        if self.mode == "SAMPLE":
            return self._sample_history(symbol, market, period, **kwargs)

        real_df = self.real_provider.get_price_history(
            symbol=symbol, market=market, period=period, **kwargs
        )
        if not real_df.empty and not real_df.attrs.get("error"):
            self.last_data_source = str(real_df.attrs.get("data_source") or "REAL")
            self.last_error = None
            return real_df

        fallback_error = str(real_df.attrs.get("error") or "실제 데이터 조회 실패")
        self.last_error = fallback_error
        sample_df = self._sample_history(symbol, market, period, **kwargs)
        sample_df["data_source"] = "SAMPLE_FALLBACK"
        sample_df["provider"] = self.get_provider_name()
        sample_df.attrs["data_source"] = "SAMPLE_FALLBACK"
        sample_df.attrs["provider"] = self.get_provider_name()
        sample_df.attrs["error"] = fallback_error
        self.last_error = fallback_error
        self.last_data_source = "SAMPLE_FALLBACK"
        return sample_df

    def get_latest_quote(self, symbol: str, market: str = "KR") -> Quote:
        if self.mode == "SAMPLE":
            quote = self.sample_provider.get_latest_quote(symbol=symbol, market=market)
            self.last_data_source = quote.data_source
            self.last_error = quote.error
            return quote

        quote = self.real_provider.get_latest_quote(symbol=symbol, market=market)
        if quote.price is not None and quote.error is None:
            self.last_data_source = quote.data_source
            self.last_error = None
            return quote

        self.last_error = quote.error or "실제 현재가 조회 실패"
        fallback = self.sample_provider.get_latest_quote(symbol=symbol, market=market)
        self.last_data_source = "SAMPLE_FALLBACK"
        return Quote(
            symbol=fallback.symbol,
            market=fallback.market,
            price=fallback.price,
            change_pct=fallback.change_pct,
            volume=fallback.volume,
            value_traded=fallback.value_traded,
            currency=fallback.currency,
            data_source="SAMPLE_FALLBACK",
            provider=self.get_provider_name(),
            as_of=fallback.as_of,
            error=self.last_error,
        )

    def get_provider_name(self) -> str:
        if self.mode == "SAMPLE":
            return "MarketDataProvider(SAMPLE)"
        return "MarketDataProvider(REAL_WITH_FALLBACK)"

    def is_sample_mode(self) -> bool:
        return self.mode == "SAMPLE" or self.last_data_source == "SAMPLE_FALLBACK"

    def is_fallback_mode(self) -> bool:
        return self.last_data_source == "SAMPLE_FALLBACK"

    def get_fx_rate(self, pair: str = "USD/KRW") -> FXRate:
        if self.mode == "SAMPLE":
            fx = self.sample_provider.get_fx_rate(pair)
            self.last_data_source = fx.data_source
            self.last_error = fx.error
            return fx

        fx = self.real_provider.get_fx_rate(pair)
        if fx.rate is not None and fx.error is None:
            self.last_data_source = fx.data_source
            self.last_error = None
            return fx

        self.last_error = fx.error or "실제 환율 조회 실패"
        fallback = self.sample_provider.get_fx_rate(pair)
        if fallback.rate is None:
            self.last_data_source = fallback.data_source
            return fallback
        self.last_data_source = "SAMPLE_FX_FALLBACK"
        return FXRate(
            pair=fallback.pair,
            rate=fallback.rate,
            data_source="SAMPLE_FX_FALLBACK",
            provider=self.get_provider_name(),
            as_of=fallback.as_of,
            error=self.last_error,
        )

    def _sample_history(
        self, symbol: str, market: str, period: str | int, **kwargs: object
    ) -> pd.DataFrame:
        sample_df = self.sample_provider.get_price_history(
            symbol=symbol, market=market, period=period, **kwargs
        )
        self.last_data_source = str(sample_df.attrs.get("data_source") or "SAMPLE")
        self.last_error = None
        return sample_df
