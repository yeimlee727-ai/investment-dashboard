from __future__ import annotations

import pandas as pd

from src.dart.dart_client import aggregate_disclosure_risk


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


class ScoringEngine:
    weights = {
        "price_momentum": 0.22,
        "volume_momentum": 0.16,
        "relative_strength": 0.22,
        "technical_trend": 0.18,
        "event_score": 0.12,
        "risk_control": 0.10,
    }

    def score_row(
        self, row: pd.Series | dict[str, float | bool | str], event_bonus: float = 0.0
    ) -> dict[str, float | str]:
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
        disclosure_type = str(row.get("disclosure_type", "") or "")
        risk_tag = str(row.get("risk_tag", "") or "")
        risk_score = float(row.get("risk_score", 38) or 38)
        aggregate_risk_score = float(
            row.get("aggregate_risk_score", risk_score) or risk_score
        )
        aggregate_risk_tag = str(row.get("aggregate_risk_tag", risk_tag) or risk_tag)

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
        event_score = self._event_score(
            disclosure_type, risk_tag, risk_score, event_bonus
        )
        risk_penalty = 0.0
        if rsi >= 78:
            risk_penalty += 12
        if rsi <= 25:
            risk_penalty += 8
        risk_penalty += self._disclosure_risk_penalty(
            aggregate_risk_tag, aggregate_risk_score
        )
        risk_control = clamp(100 - risk_penalty)

        total = (
            price_momentum * self.weights["price_momentum"]
            + volume_momentum * self.weights["volume_momentum"]
            + relative_strength * self.weights["relative_strength"]
            + technical_trend * self.weights["technical_trend"]
            + event_score * self.weights["event_score"]
            + risk_control * self.weights["risk_control"]
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

    def score_dataframe(
        self, df: pd.DataFrame, disclosures: pd.DataFrame | None = None
    ) -> pd.DataFrame:
        if df.empty:
            return df
        scored = df.copy()
        if disclosures is not None and not disclosures.empty:
            scored = self._attach_disclosure_context(scored, disclosures)
        score_rows = [self.score_row(row) for _, row in scored.iterrows()]
        return pd.concat(
            [scored.reset_index(drop=True), pd.DataFrame(score_rows)], axis=1
        )

    def _attach_disclosure_context(
        self, df: pd.DataFrame, disclosures: pd.DataFrame
    ) -> pd.DataFrame:
        if "stock_code" not in disclosures.columns:
            return df
        severity = {"critical": 5, "risk": 4, "caution": 3, "neutral": 2, "positive": 1}
        context = disclosures.copy()
        context["severity"] = context.get("risk_tag", "neutral").map(severity).fillna(2)
        context = context.sort_values(
            ["stock_code", "severity"], ascending=[True, False]
        ).drop_duplicates("stock_code")
        aggregate = aggregate_disclosure_risk(disclosures)
        mapping = context.set_index("stock_code")[
            ["disclosure_type", "risk_tag", "risk_score"]
        ].to_dict("index")
        aggregate_mapping = aggregate.set_index("stock_code").to_dict("index")
        enriched = df.copy()
        enriched["disclosure_type"] = enriched["symbol"].map(
            lambda symbol: mapping.get(symbol, {}).get("disclosure_type", "")
        )
        enriched["risk_tag"] = enriched["symbol"].map(
            lambda symbol: mapping.get(symbol, {}).get("risk_tag", "")
        )
        enriched["risk_score"] = enriched["symbol"].map(
            lambda symbol: mapping.get(symbol, {}).get("risk_score", 38)
        )
        enriched["aggregate_risk_tag"] = enriched["symbol"].map(
            lambda symbol: aggregate_mapping.get(symbol, {}).get(
                "aggregate_risk_tag", "neutral"
            )
        )
        enriched["aggregate_risk_score"] = enriched["symbol"].map(
            lambda symbol: aggregate_mapping.get(symbol, {}).get(
                "aggregate_risk_score", 38
            )
        )
        return enriched

    def _event_score(
        self,
        disclosure_type: str,
        risk_tag: str,
        risk_score: float,
        event_bonus: float,
    ) -> float:
        base_by_tag = {
            "positive": 72,
            "neutral": 50,
            "caution": 38,
            "risk": 24,
            "critical": 8,
        }
        type_adjustment = {
            "공급계약": 8,
            "자기주식취득": 8,
            "현금배당": 8,
            "무상증자": 6,
            "신규시설투자": 2,
            "실적공시": 0,
            "유상증자": -8,
            "전환사채": -8,
            "신주인수권부사채": -8,
            "교환사채": -8,
            "최대주주변경": -10,
            "소송": -18,
            "감사의견": -25,
            "횡령배임": -35,
            "거래위험": -35,
            "기타": 0,
        }
        return clamp(
            base_by_tag.get(risk_tag, 50)
            + type_adjustment.get(disclosure_type, 0)
            - max(0, risk_score - 70) * 0.2
            + event_bonus
        )

    def _disclosure_risk_penalty(
        self, aggregate_risk_tag: str, aggregate_risk_score: float
    ) -> float:
        base_penalty = {
            "positive": 0,
            "neutral": 0,
            "caution": 10,
            "risk": 24,
            "critical": 48,
        }.get(aggregate_risk_tag, 0)
        score_penalty = max(0.0, aggregate_risk_score - 45) * 0.25
        return min(60.0, base_penalty + score_penalty)

    def make_comment_prompt(
        self,
        row: pd.Series | dict[str, float | bool | str],
        rs_score: float,
        volume_ratio: float,
    ) -> str:
        symbol = str(row.get("symbol", "이 종목"))
        rsi = float(row.get("rsi14", 50) or 50)
        near_high = float(row.get("near_high_rate", 0) or 0)
        return (
            f"{symbol} 분석 코멘트를 한국어로 작성하세요. "
            f"거래량은 20일 평균 대비 {volume_ratio:.1f}배, RS 점수는 {rs_score:.1f}점, "
            f"RSI는 {rsi:.1f}, 52주 신고가 근접률은 {near_high:.1f}%입니다. "
            "가격 모멘텀, 거래량 모멘텀, 추세, 리스크를 균형 있게 설명하세요."
        )
