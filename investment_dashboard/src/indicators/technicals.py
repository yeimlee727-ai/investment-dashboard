from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_rsi(
    close: pd.Series, period: int = 14, method: str = "simple"
) -> pd.Series:
    delta = close.diff()
    gain_raw = delta.clip(lower=0)
    loss_raw = -delta.clip(upper=0)
    if method == "wilder":
        gain = gain_raw.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        loss = loss_raw.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    else:
        gain = gain_raw.rolling(period).mean()
        loss = loss_raw.rolling(period).mean()

    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rising_without_loss = (loss == 0) & (gain > 0)
    unchanged = (loss == 0) & (gain == 0)
    rsi = rsi.mask(rising_without_loss, 100)
    rsi = rsi.mask(unchanged, 50)
    return rsi.fillna(50)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(period).mean().fillna(true_range.expanding().mean())


def add_technical_indicators(
    df: pd.DataFrame, rsi_method: str = "wilder"
) -> pd.DataFrame:
    required = {"date", "open", "high", "low", "close", "volume"}
    if missing := required - set(df.columns):
        raise ValueError(f"필수 가격 컬럼 누락: {', '.join(sorted(missing))}")

    result = df.copy().sort_values("date").reset_index(drop=True)
    result["ema20"] = result["close"].ewm(span=20, adjust=False).mean()
    result["ema60"] = result["close"].ewm(span=60, adjust=False).mean()
    result["rsi14"] = calculate_rsi(result["close"], 14, method=rsi_method)
    ema12 = result["close"].ewm(span=12, adjust=False).mean()
    ema26 = result["close"].ewm(span=26, adjust=False).mean()
    result["macd"] = ema12 - ema26
    result["macd_signal"] = result["macd"].ewm(span=9, adjust=False).mean()
    result["macd_hist"] = result["macd"] - result["macd_signal"]
    result["atr14"] = calculate_atr(result, 14)
    result["volume_ma5"] = result["volume"].rolling(5).mean()
    result["volume_ma20"] = result["volume"].rolling(20).mean()
    high_window = 252 if len(result) >= 252 else max(20, len(result))
    high_column = "52w_high" if len(result) >= 252 else "period_high"
    result[high_column] = (
        result["high"].rolling(high_window, min_periods=min(20, high_window)).max()
    )
    result["reference_high"] = result[high_column]
    result["near_high_rate"] = (
        result["close"] / result["reference_high"].replace(0, np.nan) * 100
    ).fillna(0)
    result["return_20d"] = result["close"].pct_change(20).fillna(0) * 100
    result["return_60d"] = result["close"].pct_change(60).fillna(0) * 100
    return result


def latest_snapshot(df: pd.DataFrame) -> dict[str, float]:
    enriched = add_technical_indicators(df)
    latest = enriched.iloc[-1]
    previous = enriched.iloc[-2] if len(enriched) > 1 else latest
    return {
        "close": float(latest["close"]),
        "change_rate": (
            float((latest["close"] / previous["close"] - 1) * 100)
            if previous["close"]
            else 0.0
        ),
        "volume": float(latest["volume"]),
        "trading_value": float(
            latest.get("trading_value", latest["close"] * latest["volume"])
        ),
        "rsi14": float(latest["rsi14"]),
        "ema20": float(latest["ema20"]),
        "ema60": float(latest["ema60"]),
        "macd": float(latest["macd"]),
        "atr14": float(latest["atr14"]),
        "volume_ma5": (
            float(latest["volume_ma5"]) if not np.isnan(latest["volume_ma5"]) else 0.0
        ),
        "volume_ma20": (
            float(latest["volume_ma20"]) if not np.isnan(latest["volume_ma20"]) else 0.0
        ),
        "near_high_rate": float(latest["near_high_rate"]),
        "reference_high": float(latest["reference_high"]),
        "return_20d": float(latest["return_20d"]),
        "return_60d": float(latest["return_60d"]),
    }
