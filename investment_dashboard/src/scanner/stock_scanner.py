from __future__ import annotations

import pandas as pd

from src.indicators.technicals import add_technical_indicators


class StockScanner:
    def scan(self, price_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
        rows: list[dict[str, float | str | bool]] = []
        returns_60d: dict[str, float] = {}

        enriched_frames = {
            symbol: add_technical_indicators(df)
            for symbol, df in price_frames.items()
            if not df.empty
        }
        for symbol, df in enriched_frames.items():
            returns_60d[symbol] = float(df.iloc[-1]["return_60d"])

        if returns_60d:
            rank = pd.Series(returns_60d).rank(pct=True) * 100
        else:
            rank = pd.Series(dtype=float)

        for symbol, df in enriched_frames.items():
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            high_reference_name = "52w_high" if "52w_high" in df.columns else "period_high"
            volume_ratio = latest["volume"] / latest["volume_ma20"] if latest["volume_ma20"] else 0
            ema_breakout = prev["close"] <= prev["ema20"] and latest["close"] > latest["ema20"]
            rows.append(
                {
                    "symbol": symbol,
                    "close": float(latest["close"]),
                    "change_rate": float((latest["close"] / prev["close"] - 1) * 100) if prev["close"] else 0.0,
                    "volume": float(latest["volume"]),
                    "trading_value": float(latest.get("trading_value", latest["close"] * latest["volume"])),
                    "volume_ratio": float(volume_ratio),
                    "rsi14": float(latest["rsi14"]),
                    "ema20": float(latest["ema20"]),
                    "ema60": float(latest["ema60"]),
                    "macd": float(latest["macd"]),
                    "macd_hist": float(latest["macd_hist"]),
                    "return_20d": float(latest["return_20d"]),
                    "return_60d": float(latest["return_60d"]),
                    "high_reference_name": high_reference_name,
                    "reference_high": float(latest["reference_high"]),
                    "ema_breakout": bool(ema_breakout),
                    "near_high_rate": float(latest["near_high_rate"]),
                    "rs_score": float(rank.get(symbol, 50.0)),
                    "volume_surge": bool(volume_ratio >= 2.0),
                    "rsi_overbought": bool(latest["rsi14"] >= 70),
                    "rsi_oversold": bool(latest["rsi14"] <= 30),
                    "near_high": bool(latest["near_high_rate"] >= 95),
                }
            )
        if not rows:
            return pd.DataFrame(
                columns=[
                    "symbol",
                    "close",
                    "change_rate",
                    "volume",
                    "trading_value",
                    "volume_ratio",
                    "rsi14",
                    "ema20",
                    "ema60",
                    "macd",
                    "macd_hist",
                    "return_20d",
                    "return_60d",
                    "high_reference_name",
                    "reference_high",
                    "ema_breakout",
                    "near_high_rate",
                    "rs_score",
                    "volume_surge",
                    "rsi_overbought",
                    "rsi_oversold",
                    "near_high",
                ]
            )
        return pd.DataFrame(rows).sort_values(["rs_score", "volume_ratio"], ascending=False)
