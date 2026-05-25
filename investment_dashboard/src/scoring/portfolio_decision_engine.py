from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.dart.dart_client import aggregate_disclosure_risk
from src.indicators.technicals import add_technical_indicators
from src.scoring.scoring_engine import clamp

ANALYSIS_DAYS = 252 * 5
MIN_THREE_YEAR_DAYS = 252 * 3


@dataclass
class PortfolioDecisionResult:
    positions: pd.DataFrame
    portfolio_summary: dict[str, Any]
    scenarios: pd.DataFrame
    rebalance_comments: list[str]
    price_history: pd.DataFrame


class PortfolioDecisionEngine:
    """Portfolio-level decision support built from virtual positions and prices."""

    def analyze(
        self,
        positions: list[dict[str, Any]],
        data_provider: Any,
        disclosures: pd.DataFrame | None = None,
    ) -> PortfolioDecisionResult:
        rows = []
        price_rows = []
        disclosure_context = self._disclosure_context(disclosures)
        for position in positions:
            symbol = str(position.get("symbol", "")).upper()
            market = str(position.get("market", "KR")).upper()
            if not symbol:
                continue
            history = self._get_history(data_provider, symbol, market)
            context = disclosure_context.get(symbol, {})
            rows.append(self.analyze_position(position, history, context))
            price_rows.extend(self._price_history_rows(symbol, market, history))
        frame = pd.DataFrame(rows)
        if not frame.empty:
            frame = frame.replace([np.inf, -np.inf], np.nan).fillna("")
        summary = self._portfolio_summary(frame)
        scenarios = self._scenario_frame(frame)
        comments = self._rebalance_comments(frame, summary)
        return PortfolioDecisionResult(
            frame, summary, scenarios, comments, pd.DataFrame(price_rows)
        )

    def analyze_position(
        self,
        position: dict[str, Any],
        history: pd.DataFrame,
        disclosure_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        disclosure_context = disclosure_context or {}
        symbol = str(position.get("symbol", "")).upper()
        market = str(position.get("market", "KR")).upper()
        name = str(position.get("name") or symbol)
        weight = self._safe_float(position.get("position_weight_krw"))
        total_pnl_pct = self._safe_float(position.get("total_pnl_pct"))
        data_source = str(history.attrs.get("data_source") or "")
        provider = str(history.attrs.get("provider") or "")
        if history.empty or len(history) < 60:
            row = self._empty_position_row(position, name, data_source, provider)
            row["trend_status"] = "데이터 부족"
            return row

        enriched = add_technical_indicators(history).copy()
        enriched["ma120"] = enriched["close"].rolling(120).mean()
        enriched["ma240"] = enriched["close"].rolling(240).mean()
        latest = enriched.iloc[-1]
        close = self._safe_float(latest.get("close"))
        days = int(len(enriched))
        data_years = round(days / 252, 1)
        returns = {
            "return_1m": self._period_return(enriched, 21),
            "return_3m": self._period_return(enriched, 63),
            "return_6m": self._period_return(enriched, 126),
            "return_1y": self._period_return(enriched, 252),
            "return_3y": self._period_return(enriched, MIN_THREE_YEAR_DAYS),
            "cumulative_return": self._period_return(enriched, days - 1),
        }
        volatility = self._annualized_volatility(enriched)
        mdd = self._max_drawdown(enriched)
        high_52w = float(enriched["high"].tail(252).max())
        low_52w = float(enriched["low"].tail(252).min())
        drawdown_from_52w_high = (
            (close / high_52w - 1) * 100 if close and high_52w else 0.0
        )
        rebound_from_52w_low = (close / low_52w - 1) * 100 if close and low_52w else 0.0
        ma_positions = {
            "ma20_position": self._ma_position(close, latest.get("ema20")),
            "ma60_position": self._ma_position(close, latest.get("ema60")),
            "ma120_position": self._ma_position(close, latest.get("ma120")),
            "ma240_position": self._ma_position(close, latest.get("ma240")),
        }
        rsi = self._safe_float(latest.get("rsi14"), 50.0)
        volume_ma20 = self._safe_float(latest.get("volume_ma20"))
        volume = self._safe_float(latest.get("volume"))
        volume_ratio = volume / volume_ma20 if volume_ma20 else 0.0
        trend_status = self.classify_trend(latest, close, drawdown_from_52w_high, days)
        reliability, reliability_reason = self._reliability(days, data_source)
        risk_tag = str(disclosure_context.get("aggregate_risk_tag", "neutral"))
        risk_score = self._safe_float(
            disclosure_context.get("aggregate_risk_score"), 38
        )
        sell_score = self._sell_review_score(
            weight=weight,
            total_pnl_pct=total_pnl_pct,
            rsi=rsi,
            ma_positions=ma_positions,
            drawdown_from_52w_high=drawdown_from_52w_high,
            mdd=mdd,
            volatility=volatility,
            risk_tag=risk_tag,
            risk_score=risk_score,
            reliability=reliability,
            is_etf=self._is_etf(position),
            fx_error=bool(position.get("fx_error")),
        )
        buy_score = self._additional_buy_score(
            weight=weight,
            trend_status=trend_status,
            rsi=rsi,
            volatility=volatility,
            ma_positions=ma_positions,
            return_3m=returns["return_3m"],
            risk_tag=risk_tag,
            reliability=reliability,
            is_etf=self._is_etf(position),
            fx_error=bool(position.get("fx_error")),
        )
        row = {
            "symbol": symbol,
            "market": market,
            "name": name,
            "currency": str(position.get("currency", "")),
            "market_value_krw": round(
                self._safe_float(position.get("market_value_krw")), 2
            ),
            "cost_basis_krw": round(
                self._safe_float(position.get("cost_basis_krw")), 2
            ),
            "total_pnl_krw": round(self._safe_float(position.get("total_pnl_krw")), 2),
            "position_weight_krw": round(weight, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "trend_status": trend_status,
            "data_days": days,
            "data_years": data_years,
            "data_source": data_source,
            "provider": provider,
            "reliability": reliability,
            "reliability_reason": reliability_reason,
            "current_price": round(close, 2),
            "annualized_volatility": round(volatility, 2),
            "mdd": round(mdd, 2),
            "drawdown_from_52w_high": round(drawdown_from_52w_high, 2),
            "rebound_from_52w_low": round(rebound_from_52w_low, 2),
            "rsi": round(rsi, 2),
            "volume_ratio": round(volume_ratio, 2),
            "risk_tag": risk_tag,
            "risk_score": round(risk_score, 1),
            "sell_review_score": round(sell_score, 1),
            "sell_review_opinion": self.sell_review_opinion(sell_score),
            "additional_buy_score": round(buy_score, 1),
            "additional_buy_opinion": self.additional_buy_opinion(buy_score),
            "decision_comment": self._decision_comment(
                symbol, trend_status, buy_score, sell_score, reliability
            ),
        }
        row.update({key: round(value, 2) for key, value in returns.items()})
        row.update({key: round(value, 2) for key, value in ma_positions.items()})
        return self._clean_row(row)

    def classify_trend(
        self, latest: pd.Series, close: float, drawdown_from_52w_high: float, days: int
    ) -> str:
        if days < 120:
            return "데이터 부족"
        ema20 = self._safe_float(latest.get("ema20"))
        ema60 = self._safe_float(latest.get("ema60"))
        ma120 = self._safe_float(latest.get("ma120"))
        ma240 = self._safe_float(latest.get("ma240"))
        if close > ema20 > ema60 > ma120 and (not ma240 or ma120 > ma240):
            return "강한 상승 추세"
        if close > ema60 and ema20 >= ema60:
            return "완만한 상승 추세"
        if close < ma240 and ma240:
            return "하락 추세"
        if close < ma120 and ma120:
            return "조정 구간"
        if close < ema60 or drawdown_from_52w_high <= -20:
            return "조정 구간"
        return "박스권"

    def sell_review_opinion(self, score: float) -> str:
        if score <= 30:
            return "보유 유지 가능 구간"
        if score <= 50:
            return "관망 / 추세 점검"
        if score <= 70:
            return "일부 차익실현 또는 비중 조절 검토"
        if score <= 85:
            return "매도 검토 신호 강함"
        return "리스크 우선 점검 필요"

    def additional_buy_opinion(self, score: float) -> str:
        if score <= 30:
            return "추가매수 부적합 / 관망"
        if score <= 50:
            return "제한적 검토"
        if score <= 70:
            return "조건부 추가매수 후보"
        if score <= 85:
            return "우선 검토 후보"
        return "강한 후보이나 비중 제한 필요"

    def _get_history(
        self, data_provider: Any, symbol: str, market: str
    ) -> pd.DataFrame:
        try:
            return data_provider.get_price_history(symbol, market, period="5y")
        except TypeError:
            return data_provider.get_price_history(symbol, market, 1260)
        except Exception as exc:
            empty = pd.DataFrame()
            empty.attrs["error"] = str(exc)
            empty.attrs["data_source"] = "ERROR"
            return empty

    def _period_return(self, df: pd.DataFrame, days: int) -> float:
        if days <= 0 or len(df) <= days:
            return 0.0
        start = self._safe_float(df.iloc[-days - 1].get("close"))
        end = self._safe_float(df.iloc[-1].get("close"))
        return (end / start - 1) * 100 if start else 0.0

    def _annualized_volatility(self, df: pd.DataFrame) -> float:
        returns = df["close"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        if returns.empty:
            return 0.0
        return float(returns.std() * np.sqrt(252) * 100)

    def _max_drawdown(self, df: pd.DataFrame) -> float:
        close = df["close"].astype(float)
        drawdown = close / close.cummax() - 1
        return float(drawdown.min() * 100)

    def _ma_position(self, close: float, ma_value: Any) -> float:
        ma = self._safe_float(ma_value)
        return (close / ma - 1) * 100 if close and ma else 0.0

    def _sell_review_score(
        self,
        weight: float,
        total_pnl_pct: float,
        rsi: float,
        ma_positions: dict[str, float],
        drawdown_from_52w_high: float,
        mdd: float,
        volatility: float,
        risk_tag: str,
        risk_score: float,
        reliability: str,
        is_etf: bool,
        fx_error: bool,
    ) -> float:
        score = 18.0
        score += max(0.0, weight - 25) * 1.2
        if total_pnl_pct > 30 and rsi >= 70:
            score += 14
        if rsi >= 78:
            score += 12
        for key, penalty in [
            ("ma60_position", 10),
            ("ma120_position", 14),
            ("ma240_position", 16),
        ]:
            if ma_positions.get(key, 0) < 0:
                score += penalty
        if drawdown_from_52w_high <= -25:
            score += 14
        score += min(abs(mdd) * 0.35, 18)
        if volatility >= 45:
            score += 12
        score += {
            "positive": 0,
            "neutral": 0,
            "caution": 8,
            "risk": 18,
            "critical": 35,
        }.get(risk_tag, 0)
        score += max(0.0, risk_score - 70) * 0.25
        if not is_etf:
            score += 5
        if fx_error:
            score += 6
        if reliability in {"LOW", "UNKNOWN"}:
            score += 8
        return clamp(score)

    def _additional_buy_score(
        self,
        weight: float,
        trend_status: str,
        rsi: float,
        volatility: float,
        ma_positions: dict[str, float],
        return_3m: float,
        risk_tag: str,
        reliability: str,
        is_etf: bool,
        fx_error: bool,
    ) -> float:
        score = 45.0
        score += {
            "강한 상승 추세": 24,
            "완만한 상승 추세": 16,
            "박스권": 4,
            "조정 구간": -6,
            "하락 추세": -18,
            "데이터 부족": -20,
        }.get(trend_status, 0)
        if 35 <= rsi <= 65:
            score += 8
        if rsi >= 75:
            score -= 12
        if all(
            ma_positions.get(key, 0) >= -3
            for key in ["ma60_position", "ma120_position"]
        ):
            score += 8
        if -10 <= return_3m <= 12:
            score += 5
        if weight <= 15:
            score += 8
        elif weight >= 30:
            score -= 12
        if volatility <= 28:
            score += 8
        elif volatility >= 45:
            score -= 10
        score += {
            "positive": 4,
            "neutral": 0,
            "caution": -10,
            "risk": -22,
            "critical": -40,
        }.get(risk_tag, 0)
        if is_etf:
            score += 5
        if reliability == "HIGH":
            score += 5
        elif reliability == "LOW":
            score -= 14
        elif reliability == "UNKNOWN":
            score -= 25
        if fx_error:
            score -= 8
        return clamp(score)

    def _reliability(self, days: int, data_source: str) -> tuple[str, str]:
        source = data_source.upper()
        if days < 60:
            return "UNKNOWN", "가격 데이터가 매우 부족합니다."
        if "SAMPLE" in source or "FALLBACK" in source:
            return "LOW", "SAMPLE/FALLBACK 데이터라 실제 시장과 다를 수 있습니다."
        if days < MIN_THREE_YEAR_DAYS:
            return "MEDIUM", "외부 데이터이나 3년 미만입니다."
        return "HIGH", "외부 데이터이며 3년 이상 기간을 확보했습니다."

    def _empty_position_row(
        self, position: dict[str, Any], name: str, data_source: str, provider: str
    ) -> dict[str, Any]:
        symbol = str(position.get("symbol", "")).upper()
        market = str(position.get("market", "KR")).upper()
        return self._clean_row(
            {
                "symbol": symbol,
                "market": market,
                "name": name,
                "currency": str(position.get("currency", "")),
                "market_value_krw": self._safe_float(position.get("market_value_krw")),
                "cost_basis_krw": self._safe_float(position.get("cost_basis_krw")),
                "total_pnl_krw": self._safe_float(position.get("total_pnl_krw")),
                "position_weight_krw": self._safe_float(
                    position.get("position_weight_krw")
                ),
                "total_pnl_pct": self._safe_float(position.get("total_pnl_pct")),
                "trend_status": "데이터 부족",
                "data_days": 0,
                "data_years": 0,
                "data_source": data_source or "UNKNOWN",
                "provider": provider,
                "reliability": "UNKNOWN",
                "reliability_reason": "분석 가능한 가격 데이터가 부족합니다.",
                "sell_review_score": 50.0,
                "sell_review_opinion": "관망 / 추세 점검",
                "additional_buy_score": 20.0,
                "additional_buy_opinion": "추가매수 부적합 / 관망",
                "decision_comment": f"{symbol}은 데이터 부족으로 추세 점검이 필요합니다.",
            }
        )

    def _disclosure_context(
        self, disclosures: pd.DataFrame | None
    ) -> dict[str, dict[str, Any]]:
        if disclosures is None or disclosures.empty or "stock_code" not in disclosures:
            return {}
        aggregate = aggregate_disclosure_risk(disclosures)
        if aggregate.empty:
            return {}
        return aggregate.set_index("stock_code").to_dict("index")

    def _portfolio_summary(self, frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty:
            return {
                "position_count": 0,
                "top1_weight": 0.0,
                "top3_weight": 0.0,
                "kr_weight": 0.0,
                "us_weight": 0.0,
                "etf_weight": 0.0,
                "stock_weight": 0.0,
                "profit_position_count": 0,
                "loss_position_count": 0,
                "max_profit_symbol": "",
                "max_loss_symbol": "",
                "concentration_comment": "분석할 포지션이 없습니다.",
            }
        weights = pd.to_numeric(frame["position_weight_krw"], errors="coerce").fillna(0)
        sorted_weights = weights.sort_values(ascending=False)
        etf_mask = frame.apply(lambda row: self._is_etf(row.to_dict()), axis=1)
        pnl = pd.to_numeric(frame["total_pnl_pct"], errors="coerce").fillna(0)
        market_value = pd.to_numeric(
            frame.get("market_value_krw", pd.Series(dtype=float)), errors="coerce"
        ).fillna(0)
        cost_basis = pd.to_numeric(
            frame.get("cost_basis_krw", pd.Series(dtype=float)), errors="coerce"
        ).fillna(0)
        total_pnl_krw = pd.to_numeric(
            frame.get("total_pnl_krw", pd.Series(dtype=float)), errors="coerce"
        ).fillna(0)
        return {
            "position_count": int(len(frame)),
            "total_market_value_krw": round(float(market_value.sum()), 2),
            "total_cost_basis_krw": round(float(cost_basis.sum()), 2),
            "total_pnl_krw": round(float(total_pnl_krw.sum()), 2),
            "top1_weight": round(
                float(sorted_weights.iloc[0]) if not sorted_weights.empty else 0, 2
            ),
            "top3_weight": round(float(sorted_weights.head(3).sum()), 2),
            "kr_weight": round(float(weights[frame["market"].eq("KR")].sum()), 2),
            "us_weight": round(float(weights[frame["market"].eq("US")].sum()), 2),
            "etf_weight": round(float(weights[etf_mask].sum()), 2),
            "stock_weight": round(float(weights[~etf_mask].sum()), 2),
            "profit_position_count": int((pnl > 0).sum()),
            "loss_position_count": int((pnl < 0).sum()),
            "max_profit_symbol": (
                str(frame.loc[pnl.idxmax(), "symbol"]) if not frame.empty else ""
            ),
            "max_loss_symbol": (
                str(frame.loc[pnl.idxmin(), "symbol"]) if not frame.empty else ""
            ),
            "concentration_comment": self._concentration_comment(
                float(sorted_weights.iloc[0])
            ),
            "reliability": self._portfolio_reliability(frame),
        }

    def _scenario_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["symbol", "upside", "neutral", "downside"])
        rows = []
        for _, row in frame.iterrows():
            rows.append(
                {
                    "symbol": row["symbol"],
                    "market": row["market"],
                    "upside": "60일선 위 가격 유지, 거래량 증가, 상대강도 개선, DART 리스크 없음",
                    "neutral": "박스권 유지, 이동평균선 혼재, 거래량 평균 수준",
                    "downside": "60일선/120일선 이탈, 고점 대비 하락률 확대, 위험 공시 발생",
                }
            )
        return pd.DataFrame(rows)

    def _price_history_rows(
        self, symbol: str, market: str, history: pd.DataFrame
    ) -> list[dict[str, Any]]:
        if history.empty or "close" not in history or "date" not in history:
            return []
        view = history.sort_values("date").tail(MIN_THREE_YEAR_DAYS).copy()
        first_close = self._safe_float(view.iloc[0].get("close"))
        if not first_close:
            return []
        view["normalized_price"] = view["close"] / first_close * 100
        return [
            {
                "date": row["date"],
                "symbol": symbol,
                "market": market,
                "close": round(self._safe_float(row["close"]), 2),
                "normalized_price": round(self._safe_float(row["normalized_price"]), 2),
                "data_source": row.get(
                    "data_source", history.attrs.get("data_source", "")
                ),
            }
            for _, row in view.iterrows()
        ]

    def _rebalance_comments(
        self, frame: pd.DataFrame, summary: dict[str, Any]
    ) -> list[str]:
        if frame.empty:
            return ["보유 가상 포지션이 없어 리밸런싱 코멘트를 생성하지 않았습니다."]
        comments = [str(summary["concentration_comment"])]
        if float(summary.get("us_weight", 0)) >= 70:
            comments.append(
                "달러자산 비중이 높아 환율 변동 영향을 함께 점검해야 합니다."
            )
        if float(summary.get("etf_weight", 0)) >= 70:
            comments.append(
                "ETF 중심 포트폴리오로 개별 종목 리스크는 상대적으로 낮게 분산되어 있습니다."
            )
        high_sell = frame.sort_values("sell_review_score", ascending=False).head(1)
        high_buy = frame.sort_values("additional_buy_score", ascending=False).head(1)
        if not high_sell.empty:
            comments.append(
                f"{high_sell.iloc[0]['symbol']}은 매도 검토 신호가 상대적으로 높아 비중 조절 여부를 점검하세요."
            )
        if not high_buy.empty:
            comments.append(
                f"{high_buy.iloc[0]['symbol']}은 추가매수 우선순위가 상대적으로 높지만 비중 제한을 함께 확인하세요."
            )
        return comments

    def _concentration_comment(self, top1_weight: float) -> str:
        if top1_weight >= 50:
            return "상위 1개 종목 비중이 높아 포트폴리오 집중도 점검이 필요합니다."
        if top1_weight >= 35:
            return "상위 1개 종목 비중이 다소 높아 리밸런싱 검토 여지가 있습니다."
        return "상위 1개 종목 집중도는 과도하지 않은 편입니다."

    def _portfolio_reliability(self, frame: pd.DataFrame) -> str:
        values = set(frame["reliability"].astype(str))
        if "UNKNOWN" in values:
            return "UNKNOWN"
        if "LOW" in values:
            return "LOW"
        if "MEDIUM" in values:
            return "MEDIUM"
        return "HIGH"

    def _decision_comment(
        self,
        symbol: str,
        trend_status: str,
        buy_score: float,
        sell_score: float,
        reliability: str,
    ) -> str:
        return (
            f"{symbol}은 {trend_status} 상태입니다. "
            f"추가매수 점수 {buy_score:.1f}, 매도 검토 점수 {sell_score:.1f}로 "
            f"{reliability} 신뢰도 기준의 의사결정 보조 정보입니다."
        )

    def _is_etf(self, position: dict[str, Any]) -> bool:
        text = f"{position.get('symbol', '')} {position.get('name', '')}".upper()
        return any(
            keyword in text
            for keyword in ["ETF", "TIGER", "KODEX", "ACE", "SOL", "RISE"]
        )

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            result = float(value)
            if np.isnan(result) or np.isinf(result):
                return default
            return result
        except (TypeError, ValueError):
            return default

    def _clean_row(self, row: dict[str, Any]) -> dict[str, Any]:
        cleaned = {}
        for key, value in row.items():
            if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
                cleaned[key] = 0.0
            else:
                cleaned[key] = value
        return cleaned
