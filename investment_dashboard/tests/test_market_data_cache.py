from __future__ import annotations

import pandas as pd

from src.data.market_data_cache import (
    MARKET_DATA_COLUMNS,
    MarketDataCache,
    MarketDataCacheConfig,
    MarketDataRequest,
    normalize_price_history,
)


def sample_raw_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-02", "2026-01-03"]),
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000, 1100],
        }
    )


def test_cache_miss_triggers_mocked_download(tmp_path) -> None:
    calls = []
    request = MarketDataRequest("AAPL", "2026-01-01", "2026-01-10")

    def downloader(download_request: MarketDataRequest) -> pd.DataFrame:
        calls.append(download_request)
        return sample_raw_history()

    cache = MarketDataCache(
        MarketDataCacheConfig(cache_dir=tmp_path),
        downloader=downloader,
    )

    frame = cache.get_history(request)

    assert calls == [request]
    assert list(frame.columns) == MARKET_DATA_COLUMNS
    assert cache.cache_path(request).exists()


def test_cache_hit_reads_local_file_without_download(tmp_path) -> None:
    request = MarketDataRequest("AAPL", "2026-01-01", "2026-01-10")
    cache = MarketDataCache(MarketDataCacheConfig(cache_dir=tmp_path))
    path = cache.cache_path(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalize_price_history(sample_raw_history(), "AAPL").to_csv(path, index=False)

    def downloader(_: MarketDataRequest) -> pd.DataFrame:
        raise AssertionError("download should not be called on cache hit")

    cache = MarketDataCache(
        MarketDataCacheConfig(cache_dir=tmp_path),
        downloader=downloader,
    )

    frame = cache.get_history(request)

    assert len(frame) == 2
    assert frame.iloc[0]["symbol"] == "AAPL"


def test_yfinance_style_raw_columns_are_normalized() -> None:
    raw = sample_raw_history().set_index("Date")

    frame = normalize_price_history(raw, "msft")

    assert list(frame.columns) == MARKET_DATA_COLUMNS
    assert frame.iloc[0].to_dict() == {
        "date": "2026-01-02",
        "symbol": "MSFT",
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 1000,
    }


def test_empty_download_returns_safe_empty_frame(tmp_path) -> None:
    request = MarketDataRequest("AAPL", "2026-01-01", "2026-01-10")
    cache = MarketDataCache(
        MarketDataCacheConfig(cache_dir=tmp_path),
        downloader=lambda _: pd.DataFrame(),
    )

    frame = cache.get_history(request)

    assert frame.empty
    assert list(frame.columns) == MARKET_DATA_COLUMNS


def test_cache_filename_is_deterministic_and_safe(tmp_path) -> None:
    request = MarketDataRequest("BRK.B", "2026-01-01", "2026-01-10", "1d")
    cache = MarketDataCache(MarketDataCacheConfig(cache_dir=tmp_path))

    first = cache.cache_path(request)
    second = cache.cache_path(request)

    assert first == second
    assert first.name == "BRK.B_2026-01-01_2026-01-10_1d.csv"
