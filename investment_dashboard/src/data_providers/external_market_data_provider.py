from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.data_providers.base import BaseDataProvider, Quote, empty_price_history


class ExternalMarketDataProvider(BaseDataProvider):
    """Read-only external quote provider.

    US equities use their ticker directly. KR equities try yfinance's common
    KRX suffixes (.KS, then .KQ). This remains read-only market-data access.
    """

    def __init__(self) -> None:
        self._yf = self._load_yfinance()

    def get_price_history(
        self, symbol: str, market: str = "KR", period: str | int = 180, **kwargs: object
    ) -> pd.DataFrame:
        market = market.upper()
        if self._yf is None:
            return empty_price_history(
                symbol=symbol,
                market=market,
                data_source="REAL_UNAVAILABLE",
                provider=self.get_provider_name(),
                error="yfinance가 설치되어 있지 않습니다.",
            )

        try:
            yf_period = self._to_yfinance_period(period, kwargs.get("days"))
            raw = pd.DataFrame()
            used_ticker = ""
            errors: list[str] = []
            for ticker_symbol in self._ticker_candidates(symbol, market):
                try:
                    ticker = self._yf.Ticker(ticker_symbol)
                    raw = ticker.history(period=yf_period, auto_adjust=False)
                    if not raw.empty:
                        used_ticker = ticker_symbol
                        break
                    errors.append(f"{ticker_symbol}: empty")
                except Exception as exc:
                    errors.append(f"{ticker_symbol}: {exc}")
            if raw.empty:
                return empty_price_history(
                    symbol=symbol,
                    market=market,
                    data_source="REAL_NO_DATA",
                    provider=self.get_provider_name(),
                    error=(
                        "외부 provider가 빈 가격 데이터를 반환했습니다."
                        if not errors
                        else "; ".join(errors)
                    ),
                )
            df = raw.reset_index()
            df = df.rename(
                columns={
                    "Date": "date",
                    "Datetime": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            df = df[["date", "open", "high", "low", "close", "volume"]].copy()
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
            df["value_traded"] = df["close"] * df["volume"]
            df["symbol"] = symbol.upper()
            df["market"] = market
            df["data_source"] = "YFINANCE"
            df["provider"] = self.get_provider_name()
            df["provider_symbol"] = used_ticker
            df["change_pct"] = df["close"].pct_change().fillna(0) * 100
            df["change_rate"] = df["change_pct"]
            df["trading_value"] = df["value_traded"]
            df.attrs["data_source"] = "YFINANCE"
            df.attrs["provider"] = self.get_provider_name()
            df.attrs["error"] = None
            return df
        except Exception as exc:
            return empty_price_history(
                symbol=symbol,
                market=market,
                data_source="REAL_ERROR",
                provider=self.get_provider_name(),
                error=str(exc),
            )

    def get_latest_quote(self, symbol: str, market: str = "KR") -> Quote:
        market = market.upper()
        history = self.get_price_history(symbol=symbol, market=market, period="5d")
        if history.empty:
            return self._failed_quote(
                symbol,
                market,
                str(history.attrs.get("error") or "외부 provider 현재가 조회 실패"),
            )
        latest = history.iloc[-1]
        return Quote(
            symbol=symbol.upper(),
            market=market,
            price=float(latest["close"]),
            change_pct=float(latest["change_pct"]),
            volume=float(latest["volume"]),
            value_traded=float(latest["value_traded"]),
            currency="KRW" if market == "KR" else "USD",
            data_source=str(latest["data_source"]),
            provider=self.get_provider_name(),
            as_of=datetime.now().isoformat(timespec="seconds"),
            error=None,
        )

    def get_provider_name(self) -> str:
        return "ExternalMarketDataProvider"

    def is_sample_mode(self) -> bool:
        return False

    def _failed_quote(self, symbol: str, market: str, error: str) -> Quote:
        return Quote(
            symbol=symbol.upper(),
            market=market.upper(),
            price=None,
            change_pct=None,
            volume=None,
            value_traded=None,
            currency="KRW" if market.upper() == "KR" else "USD",
            data_source="REAL_ERROR",
            provider=self.get_provider_name(),
            as_of=datetime.now().isoformat(timespec="seconds"),
            error=error,
        )

    def _load_yfinance(self) -> object | None:
        try:
            import yfinance as yf

            return yf
        except Exception:
            return None

    def _to_yfinance_period(self, period: str | int, days: object = None) -> str:
        if isinstance(days, int):
            return f"{max(days, 1)}d"
        if isinstance(period, int):
            return f"{max(period, 1)}d"
        return period

    def _ticker_candidates(self, symbol: str, market: str) -> list[str]:
        symbol = symbol.upper().strip()
        market = market.upper().strip()
        if market == "US":
            return [symbol]
        if market == "KR":
            if symbol.endswith((".KS", ".KQ")):
                return [symbol]
            return [f"{symbol}.KS", f"{symbol}.KQ"]
        return [symbol]


RealMarketDataProvider = ExternalMarketDataProvider
