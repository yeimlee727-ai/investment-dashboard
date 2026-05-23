from __future__ import annotations

import pandas as pd


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


class ScoringEngine:
    def score_row(self, row: pd.Series | dict[str, float | bool | str], event_bonus: float = 0.0) -> dict[str, float | str]:
        close = float(row.get("close", 0) or 0)
        ema20 = float(row.get("ema20", close) or close)
        ema60 = float(row.get("ema60", close) or close)
        change_rate = float(row.get("change_rate", 0) or 0)
        volume_ratio = float(row.get("volume_ratio", 1) or 1)
        rs_score = float(row.get("rs_score", 50) or 50)
        rsi = float(row.get("rsi14", 50) or 50)
        near_high_rate = float(row.get("near_high_rate", 0) or 0)
        macd_hist = float(row.get("macd_hist", 0) or 0)
        return_20d = float(row.get("return_20d", 0) or 0)

        price_momentum = clamp(50 + change_rate * 4 + max(0, near_high_rate - 90) * 2)
        volume_momentum = clamp(volume_ratio * 25)
        relative_strength = clamp(rs_score)
        technical_trend = clamp(
            50
            + (15 if close > ema20 else -15)
            + (15 if ema20 > ema60 else -15)
            + (8 if macd_hist > 0 else -8)
            + clamp(return_20d, -20, 20) * 0.6
        )
        event_score = clamp(50 + event_bonus)
        risk_penalty = 0.0
        if rsi >= 78:
            risk_penalty += 12
        if rsi <= 25:
            risk_penalty += 8

        total = (
            price_momentum * 0.22
            + volume_momentum * 0.18
            + relative_strength * 0.22
            + technical_trend * 0.18
            + event_score * 0.12
            - risk_penalty
        )
        return {
            "score": round(clamp(total), 1),
            "price_momentum": round(price_momentum, 1),
            "volume_momentum": round(volume_momentum, 1),
            "relative_strength": round(relative_strength, 1),
            "technical_trend": round(technical_trend, 1),
            "event_score": round(event_score, 1),
            "risk_penalty": round(risk_penalty, 1),
            "comment_prompt": self.make_comment_prompt(row, rs_score, volume_ratio),
        }

    def score_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        scored = df.copy()
        score_rows = [self.score_row(row) for _, row in scored.iterrows()]
        return pd.concat([scored.reset_index(drop=True), pd.DataFrame(score_rows)], axis=1)

    def make_comment_prompt(self, row: pd.Series | dict[str, float | bool | str], rs_score: float, volume_ratio: float) -> str:
        symbol = str(row.get("symbol", "이 종목"))
        rsi = float(row.get("rsi14", 50) or 50)
        near_high = float(row.get("near_high_rate", 0) or 0)
        return (
            f"{symbol} 분석 코멘트를 한국어로 작성하세요. "
            f"거래량은 20일 평균 대비 {volume_ratio:.1f}배, RS 점수는 {rs_score:.1f}점, "
            f"RSI는 {rsi:.1f}, 52주 신고가 근접률은 {near_high:.1f}%입니다. "
            "가격 모멘텀, 거래량 모멘텀, 추세, 리스크를 균형 있게 설명하세요."
        )
