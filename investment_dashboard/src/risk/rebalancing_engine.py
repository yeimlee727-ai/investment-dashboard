from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

PROFILE_TARGETS: dict[str, dict[str, float]] = {
    "균형 성장": {
        "미국 코어 ETF": 35.0,
        "미국 반도체/AI ETF": 20.0,
        "인도 ETF": 15.0,
        "개별 성장주": 5.0,
        "현금": 25.0,
    },
    "공격형 성장": {
        "미국 코어 ETF": 35.0,
        "미국 반도체/AI ETF": 25.0,
        "인도 ETF": 15.0,
        "개별 성장주": 10.0,
        "현금": 15.0,
    },
    "안정 성장": {
        "미국 코어 ETF": 30.0,
        "미국 반도체/AI ETF": 10.0,
        "인도 ETF": 10.0,
        "개별 성장주": 3.0,
        "현금": 47.0,
    },
}

STRESS_SCENARIOS: dict[str, dict[str, float]] = {
    "미국 기술주 조정": {
        "미국 코어 ETF": -15.0,
        "미국 반도체/AI ETF": -30.0,
        "인도 ETF": -10.0,
        "개별 성장주": -35.0,
        "일반 ETF": -12.0,
        "일반 위험자산": -15.0,
    },
    "반도체 급락": {
        "미국 코어 ETF": -10.0,
        "미국 반도체/AI ETF": -35.0,
        "인도 ETF": -8.0,
        "개별 성장주": -25.0,
        "일반 ETF": -10.0,
        "일반 위험자산": -12.0,
    },
    "신흥국/인도 조정": {
        "미국 코어 ETF": -5.0,
        "미국 반도체/AI ETF": -8.0,
        "인도 ETF": -20.0,
        "개별 성장주": -10.0,
        "일반 ETF": -8.0,
        "일반 위험자산": -10.0,
    },
    "개별 성장주 급락": {
        "미국 코어 ETF": -5.0,
        "미국 반도체/AI ETF": -5.0,
        "인도 ETF": -5.0,
        "개별 성장주": -40.0,
        "일반 ETF": -5.0,
        "일반 위험자산": -15.0,
    },
    "원화 강세 / 달러 약세": {
        "미국 코어 ETF": 0.0,
        "미국 반도체/AI ETF": 0.0,
        "인도 ETF": 0.0,
        "개별 성장주": -10.0,
        "일반 ETF": 0.0,
        "일반 위험자산": -5.0,
    },
    "복합 위험 시나리오": {
        "미국 코어 ETF": -15.0,
        "미국 반도체/AI ETF": -30.0,
        "인도 ETF": -15.0,
        "개별 성장주": -40.0,
        "일반 ETF": -15.0,
        "일반 위험자산": -20.0,
    },
}

MAX_SINGLE_POSITION_WEIGHT = 40.0
MAX_INDIVIDUAL_GROWTH_WEIGHT = 10.0
MAX_SEMICONDUCTOR_WEIGHT = 30.0


@dataclass
class RebalancingResult:
    risk_summary: dict[str, Any]
    risk_contribution: pd.DataFrame
    correlation_matrix: pd.DataFrame
    correlation_summary: dict[str, Any]
    stress_results: pd.DataFrame
    target_comparison: pd.DataFrame
    allocation_plan: pd.DataFrame
    comments: list[str]
    returns: pd.DataFrame


class RebalancingEngine:
    """Risk and rebalancing support for virtual positions only."""

    def analyze(
        self,
        positions: list[dict[str, Any]],
        data_provider: Any,
        profile: str = "균형 성장",
        target_weights: dict[str, float] | None = None,
        tolerance_pct: float = 5.0,
        additional_investment_krw: float = 3_000_000,
        decision_frame: pd.DataFrame | None = None,
        period: str | int = "3y",
    ) -> RebalancingResult:
        normalized = self._normalize_positions(positions)
        histories = self._load_histories(normalized, data_provider, period)
        returns = self._returns_frame(histories)
        decision_context = self._decision_context(decision_frame)
        targets = self._target_weights(profile, target_weights)
        risk = self._risk_contribution(normalized, returns, histories)
        corr, corr_summary = self._correlation(returns)
        stress = self._stress_tests(normalized)
        target = self._target_comparison(normalized, targets, tolerance_pct)
        allocation = self._allocation_plan(
            normalized,
            targets,
            risk,
            decision_context,
            additional_investment_krw,
        )
        summary = self._risk_summary(normalized, risk, corr_summary, stress, target)
        comments = self._comments(summary, target, allocation)
        return RebalancingResult(
            risk_summary=summary,
            risk_contribution=self._clean_frame(risk),
            correlation_matrix=self._clean_frame(corr),
            correlation_summary=corr_summary,
            stress_results=self._clean_frame(stress),
            target_comparison=self._clean_frame(target),
            allocation_plan=self._clean_frame(allocation),
            comments=comments,
            returns=self._clean_frame(returns),
        )

    def _normalize_positions(
        self, positions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        rows = []
        total_value = sum(
            self._score_float(position.get("market_value_krw"))
            for position in positions
            if self._finite_float(position.get("market_value_krw")) is not None
        )
        for position in positions:
            symbol = str(position.get("symbol", "")).upper()
            market = str(position.get("market", "KR")).upper()
            if not symbol:
                continue
            value = self._finite_float(position.get("market_value_krw"))
            weight = self._finite_float(position.get("position_weight_krw"))
            if weight is None and value is not None and total_value > 0:
                weight = value / total_value * 100
            if value is None or value <= 0:
                weight = None
            row = dict(position)
            row["symbol"] = symbol
            row["market"] = market
            row["name"] = str(position.get("name") or symbol)
            row["market_value_krw"] = value
            row["position_weight_krw"] = weight
            row["asset_class"] = self.classify_asset(row)
            rows.append(row)
        return rows

    def classify_asset(self, position: dict[str, Any]) -> str:
        symbol = str(position.get("symbol", "")).upper()
        market = str(position.get("market", "KR")).upper()
        text = " ".join(
            str(position.get(key, "")) for key in ["symbol", "name", "sector", "memo"]
        ).upper()
        if symbol == "390390" or any(
            keyword in text for keyword in ["반도체", "SEMICONDUCTOR", "SEMI", "AI"]
        ):
            return "미국 반도체/AI ETF"
        if symbol == "360750" or any(
            keyword in text for keyword in ["S&P500", "S&P 500", "SP500", "SNP500"]
        ):
            return "미국 코어 ETF"
        if symbol == "453870" or any(
            keyword in text for keyword in ["인도", "INDIA", "NIFTY"]
        ):
            return "인도 ETF"
        if market == "US" and not self._is_etf(position):
            return "개별 성장주"
        if self._is_etf(position):
            return "일반 ETF"
        return "일반 위험자산"

    def _load_histories(
        self,
        positions: list[dict[str, Any]],
        data_provider: Any,
        period: str | int,
    ) -> dict[str, pd.DataFrame]:
        histories = {}
        for position in positions:
            key = self._position_key(position)
            try:
                history = data_provider.get_price_history(
                    str(position["symbol"]),
                    str(position["market"]),
                    period=period,
                )
            except TypeError:
                try:
                    history = data_provider.get_price_history(
                        str(position["symbol"]),
                        str(position["market"]),
                        756,
                    )
                except Exception as exc:
                    history = pd.DataFrame()
                    history.attrs["error"] = str(exc)
                    history.attrs["data_source"] = "ERROR"
            except Exception as exc:
                history = pd.DataFrame()
                history.attrs["error"] = str(exc)
                history.attrs["data_source"] = "ERROR"
            histories[key] = history
        return histories

    def _returns_frame(self, histories: dict[str, pd.DataFrame]) -> pd.DataFrame:
        series = {}
        for key, history in histories.items():
            returns = self._daily_returns(history)
            if not returns.empty:
                series[key] = returns.tail(252)
        if not series:
            return pd.DataFrame()
        frame = (
            pd.DataFrame(series).replace([np.inf, -np.inf], np.nan).dropna(how="all")
        )
        return frame.dropna(axis=1, how="all")

    def _daily_returns(self, history: pd.DataFrame) -> pd.Series:
        if (
            history.empty
            or "close" not in history.columns
            or "date" not in history.columns
        ):
            return pd.Series(dtype=float)
        view = history.sort_values("date").copy()
        view.index = pd.to_datetime(view["date"])
        close = pd.to_numeric(view["close"], errors="coerce")
        returns = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        if returns.empty:
            return pd.Series(dtype=float)
        return returns

    def _risk_contribution(
        self,
        positions: list[dict[str, Any]],
        returns: pd.DataFrame,
        histories: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        columns = [
            "symbol",
            "market",
            "name",
            "asset_class",
            "position_weight_krw",
            "individual_volatility",
            "risk_contribution",
            "risk_weight_gap",
            "risk_evaluation",
            "data_source",
            "reliability",
            "reliability_reason",
        ]
        if not positions:
            return pd.DataFrame(columns=columns)
        rows = []
        valid_keys = [
            self._position_key(position)
            for position in positions
            if self._position_key(position) in returns.columns
            and self._finite_float(position.get("position_weight_krw")) is not None
            and self._finite_float(position.get("market_value_krw")) is not None
            and self._score_float(position.get("market_value_krw")) > 0
        ]
        weights = self._weights_for_keys(positions, valid_keys)
        contribution_map: dict[str, float | None] = {key: None for key in valid_keys}
        if len(valid_keys) == 1:
            contribution_map[valid_keys[0]] = 100.0
        elif len(valid_keys) >= 2 and weights is not None:
            cov = returns[valid_keys].dropna().cov().to_numpy() * 252
            if cov.size and np.isfinite(cov).all():
                variance = float(weights.T @ cov @ weights)
                if variance > 0:
                    marginal = cov @ weights
                    raw = weights * marginal / variance * 100
                    positive = np.maximum(raw, 0)
                    total = float(positive.sum())
                    if total > 0:
                        normalized = positive / total * 100
                        contribution_map.update(
                            {
                                key: self._round_optional(float(value))
                                for key, value in zip(
                                    valid_keys, normalized, strict=False
                                )
                            }
                        )
        for position in positions:
            key = self._position_key(position)
            history = histories.get(key, pd.DataFrame())
            returns_series = (
                returns[key].dropna() if key in returns else pd.Series(dtype=float)
            )
            volatility = self._annualized_volatility(returns_series)
            weight = self._finite_float(position.get("position_weight_krw"))
            contribution = contribution_map.get(key)
            gap = (
                contribution - weight
                if contribution is not None and weight is not None
                else None
            )
            reliability, reason = self._reliability(history, returns_series)
            rows.append(
                self._clean_row(
                    {
                        "symbol": position["symbol"],
                        "market": position["market"],
                        "name": position["name"],
                        "asset_class": position["asset_class"],
                        "position_weight_krw": self._round_optional(weight),
                        "individual_volatility": self._round_optional(volatility),
                        "risk_contribution": self._round_optional(contribution),
                        "risk_weight_gap": self._round_optional(gap),
                        "risk_evaluation": self._risk_evaluation(gap, len(valid_keys)),
                        "data_source": str(
                            history.attrs.get("data_source") or "UNKNOWN"
                        ),
                        "reliability": reliability,
                        "reliability_reason": reason,
                    }
                )
            )
        return pd.DataFrame(rows, columns=columns)

    def _correlation(
        self, returns: pd.DataFrame
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        if returns.shape[1] < 2:
            return pd.DataFrame(), {
                "average_correlation": None,
                "highest_pair": "",
                "highest_correlation": None,
                "lowest_pair": "",
                "lowest_correlation": None,
                "diversification_comment": "상관관계 계산에는 최소 2개 종목의 수익률 데이터가 필요합니다.",
            }
        corr = returns.corr().replace([np.inf, -np.inf], np.nan)
        clean = corr.where(pd.notna(corr), None)
        pairs = []
        columns = list(corr.columns)
        for i, left in enumerate(columns):
            for right in columns[i + 1 :]:
                value = self._finite_float(corr.loc[left, right])
                if value is not None:
                    pairs.append((left, right, value))
        if not pairs:
            return clean, {
                "average_correlation": None,
                "highest_pair": "",
                "highest_correlation": None,
                "lowest_pair": "",
                "lowest_correlation": None,
                "diversification_comment": "상관계수 대부분이 계산 불가라 해석이 제한됩니다.",
            }
        average = sum(value for _, _, value in pairs) / len(pairs)
        highest = max(pairs, key=lambda item: item[2])
        lowest = min(pairs, key=lambda item: item[2])
        return clean.round(3), {
            "average_correlation": round(average, 3),
            "highest_pair": f"{highest[0]} / {highest[1]}",
            "highest_correlation": round(highest[2], 3),
            "lowest_pair": f"{lowest[0]} / {lowest[1]}",
            "lowest_correlation": round(lowest[2], 3),
            "diversification_comment": self._diversification_comment(average),
        }

    def _stress_tests(self, positions: list[dict[str, Any]]) -> pd.DataFrame:
        columns = [
            "scenario",
            "stress_loss_krw",
            "stress_loss_pct",
            "largest_loss_symbol",
            "comment",
        ]
        total_value = self._total_value(positions)
        if total_value <= 0:
            return pd.DataFrame(columns=columns)
        rows = []
        for scenario, shocks in STRESS_SCENARIOS.items():
            losses = []
            for position in positions:
                value = self._finite_float(position.get("market_value_krw"))
                if value is None:
                    continue
                shock = shocks.get(
                    str(position["asset_class"]), shocks["일반 위험자산"]
                )
                if (
                    scenario == "원화 강세 / 달러 약세"
                    and position.get("market") == "US"
                ):
                    shock = -10.0
                loss = value * shock / 100
                losses.append((str(position["symbol"]), loss))
            total_loss = sum(loss for _, loss in losses)
            largest = min(losses, key=lambda item: item[1])[0] if losses else ""
            rows.append(
                self._clean_row(
                    {
                        "scenario": scenario,
                        "stress_loss_krw": round(total_loss, 2),
                        "stress_loss_pct": round(total_loss / total_value * 100, 2),
                        "largest_loss_symbol": largest,
                        "comment": (
                            "가정 시나리오 기준 추정 손실입니다. 실제 미래 손실 예측이 아닙니다."
                        ),
                    }
                )
            )
        return pd.DataFrame(rows, columns=columns)

    def _target_comparison(
        self,
        positions: list[dict[str, Any]],
        targets: dict[str, float],
        tolerance_pct: float,
    ) -> pd.DataFrame:
        tolerance = self._safe_tolerance(tolerance_pct)
        target_total = sum(self._score_float(value) for value in targets.values())
        target_total_status = (
            "목표 비중 합계가 100%입니다."
            if abs(target_total - 100) <= 0.01
            else "목표 비중 합계가 100%가 아니므로 검토 기준이 왜곡될 수 있습니다."
        )
        total_value = self._total_value(positions)
        current = {category: 0.0 for category in targets}
        for position in positions:
            category = str(position["asset_class"])
            current.setdefault(category, 0.0)
            current[category] += self._score_float(position.get("market_value_krw"))
        current_pct = {
            category: (value / total_value * 100 if total_value > 0 else 0.0)
            for category, value in current.items()
        }
        current_pct["현금"] = max(0.0, 100 - sum(current_pct.values()))
        rows = []
        categories = list(dict.fromkeys([*targets.keys(), *current_pct.keys()]))
        for category in categories:
            now = current_pct.get(category, 0.0)
            target = targets.get(category, 0.0)
            gap = now - target
            exceeded = abs(gap) > tolerance
            rows.append(
                {
                    "asset_class": category,
                    "current_weight": round(now, 2),
                    "target_weight": round(target, 2),
                    "weight_gap": round(gap, 2),
                    "tolerance_pct": round(tolerance, 2),
                    "is_outside_band": exceeded,
                    "rebalance_opinion": self._rebalance_opinion(gap, tolerance),
                    "target_total_weight": round(target_total, 2),
                    "target_total_status": target_total_status,
                }
            )
        return pd.DataFrame(rows)

    def _allocation_plan(
        self,
        positions: list[dict[str, Any]],
        targets: dict[str, float],
        risk: pd.DataFrame,
        decision_context: dict[str, dict[str, Any]],
        additional_investment_krw: float,
    ) -> pd.DataFrame:
        columns = [
            "symbol",
            "market",
            "name",
            "asset_class",
            "current_weight",
            "target_weight",
            "shortage_weight",
            "candidate_amount",
            "adjusted_amount",
            "allocation_reason",
            "limit_reason",
        ]
        investment = max(0.0, self._score_float(additional_investment_krw))
        if investment <= 0 or not positions:
            return pd.DataFrame(columns=columns)
        total_value = self._total_value(positions)
        if total_value <= 0:
            return pd.DataFrame(columns=columns)
        risk_context = (
            risk.set_index("symbol").to_dict("index") if not risk.empty else {}
        )
        raw_rows = []
        for position in positions:
            category = str(position["asset_class"])
            current = self._score_float(position.get("position_weight_krw"))
            target = targets.get(category, 0.0)
            shortage = max(0.0, target - current)
            decision = decision_context.get(str(position["symbol"]), {})
            add_score = self._score_float(decision.get("additional_buy_score"), 50.0)
            sell_score = self._score_float(decision.get("sell_review_score"), 0.0)
            reliability = str(
                decision.get("reliability")
                or risk_context.get(str(position["symbol"]), {}).get("reliability")
                or "UNKNOWN"
            )
            risk_contribution = self._finite_float(
                risk_context.get(str(position["symbol"]), {}).get("risk_contribution")
            )
            limit_reasons = self._allocation_limits(
                position,
                current,
                reliability,
                risk_contribution,
                add_score,
                sell_score,
            )
            eligible = shortage > 0 and not limit_reasons
            raw_weight = shortage * max(add_score, 1) / 100 if eligible else 0.0
            raw_rows.append(
                {
                    "position": position,
                    "current": current,
                    "target": target,
                    "shortage": shortage,
                    "raw_weight": raw_weight,
                    "limit_reasons": limit_reasons,
                }
            )
        total_raw = sum(row["raw_weight"] for row in raw_rows)
        rows = []
        allocated = 0.0
        for row in raw_rows:
            position = row["position"]
            candidate = (
                investment * row["raw_weight"] / total_raw if total_raw > 0 else 0.0
            )
            adjusted, cap_reasons = self._apply_allocation_caps(
                position,
                candidate,
                total_value,
                investment,
            )
            for reason in cap_reasons:
                if reason not in row["limit_reasons"]:
                    row["limit_reasons"].append(reason)
            if adjusted == 0 and candidate > 0 and not row["limit_reasons"]:
                row["limit_reasons"].append("배분 제한")
            allocated += adjusted
            rows.append(
                {
                    "symbol": position["symbol"],
                    "market": position["market"],
                    "name": position["name"],
                    "asset_class": position["asset_class"],
                    "current_weight": round(row["current"], 2),
                    "target_weight": round(row["target"], 2),
                    "shortage_weight": round(row["shortage"], 2),
                    "candidate_amount": round(candidate, 0),
                    "adjusted_amount": round(adjusted, 0),
                    "allocation_reason": (
                        "목표 비중 대비 부족 구간의 추가매수 검토 배분안"
                        if adjusted > 0
                        else "배분 보류"
                    ),
                    "limit_reason": ", ".join(row["limit_reasons"]),
                }
            )
        cash_left = max(0.0, investment - allocated)
        if cash_left > 0:
            rows.append(
                {
                    "symbol": "CASH",
                    "market": "KR",
                    "name": "대기 현금",
                    "asset_class": "현금",
                    "current_weight": None,
                    "target_weight": targets.get("현금", 0.0),
                    "shortage_weight": None,
                    "candidate_amount": round(cash_left, 0),
                    "adjusted_amount": round(cash_left, 0),
                    "allocation_reason": "목표 비중, 신뢰도, 위험 기여도 제한 후 남는 대기 현금",
                    "limit_reason": "",
                }
            )
        return pd.DataFrame([self._clean_row(row) for row in rows], columns=columns)

    def _risk_summary(
        self,
        positions: list[dict[str, Any]],
        risk: pd.DataFrame,
        corr_summary: dict[str, Any],
        stress: pd.DataFrame,
        target: pd.DataFrame,
    ) -> dict[str, Any]:
        top_risk = ""
        if not risk.empty and "risk_contribution" in risk:
            numeric = pd.to_numeric(risk["risk_contribution"], errors="coerce")
            if numeric.notna().any():
                top_risk = str(risk.loc[numeric.idxmax(), "symbol"])
        worst_loss_pct = None
        if not stress.empty:
            losses = pd.to_numeric(stress["stress_loss_pct"], errors="coerce")
            if losses.notna().any():
                worst_loss_pct = float(losses.min())
        return {
            "position_count": len(positions),
            "total_market_value_krw": round(self._total_value(positions), 2),
            "top_risk_symbol": top_risk,
            "average_correlation": corr_summary.get("average_correlation"),
            "worst_stress_loss_pct": (
                round(worst_loss_pct, 2) if worst_loss_pct is not None else None
            ),
            "overweight_count": (
                int(target["is_outside_band"].sum()) if not target.empty else 0
            ),
            "data_reliability": self._summary_reliability(risk),
        }

    def _comments(
        self,
        summary: dict[str, Any],
        target: pd.DataFrame,
        allocation: pd.DataFrame,
    ) -> list[str]:
        comments = ["모든 결과는 MockBroker 가상 포지션 기반 의사결정 보조 정보입니다."]
        if summary.get("top_risk_symbol"):
            comments.append(
                f"{summary['top_risk_symbol']}은 위험 기여도가 상대적으로 높아 비중 조절 검토 대상입니다."
            )
        if summary.get("overweight_count", 0):
            comments.append(
                "목표 비중 허용 범위를 벗어난 자산군이 있어 리밸런싱 검토가 필요합니다."
            )
        if not allocation.empty:
            allocated = pd.to_numeric(
                allocation["adjusted_amount"], errors="coerce"
            ).sum()
            if allocated > 0:
                comments.append(
                    "추가 투자금 배분안은 목표 비중 부족분과 위험 제한을 함께 반영했습니다."
                )
        if not target.empty and "현금" in set(target["asset_class"]):
            comments.append(
                "현금 비중은 추가 투자금 집행 전 대기 자금으로 별도 점검하세요."
            )
        return comments

    def _target_weights(
        self, profile: str, custom: dict[str, float] | None
    ) -> dict[str, float]:
        targets = dict(PROFILE_TARGETS.get(profile, PROFILE_TARGETS["균형 성장"]))
        if custom:
            targets.update(
                {
                    key: max(0.0, self._score_float(value))
                    for key, value in custom.items()
                }
            )
        return targets

    def _decision_context(
        self, frame: pd.DataFrame | None
    ) -> dict[str, dict[str, Any]]:
        if frame is None or frame.empty or "symbol" not in frame.columns:
            return {}
        return frame.set_index("symbol").to_dict("index")

    def _weights_for_keys(
        self, positions: list[dict[str, Any]], keys: list[str]
    ) -> np.ndarray | None:
        raw = []
        by_key = {self._position_key(position): position for position in positions}
        for key in keys:
            weight = self._finite_float(by_key[key].get("position_weight_krw"))
            if weight is None:
                return None
            raw.append(weight)
        total = sum(raw)
        if total <= 0:
            return None
        return np.array(raw, dtype=float) / total

    def _allocation_limits(
        self,
        position: dict[str, Any],
        current_weight: float,
        reliability: str,
        risk_contribution: float | None,
        add_score: float,
        sell_score: float,
    ) -> list[str]:
        reasons = []
        if reliability in {"LOW", "UNKNOWN"}:
            reasons.append("데이터 신뢰도 낮음")
        if risk_contribution is not None and risk_contribution - current_weight >= 12:
            reasons.append("위험 기여도 높음")
        if risk_contribution is None:
            reasons.append("위험 기여도 계산 불가")
        if add_score < 45:
            reasons.append("추가매수 점수 낮음")
        if sell_score >= 70:
            reasons.append("매도 검토 신호 높음")
        if str(position.get("asset_class")) == "개별 성장주" and current_weight >= 10:
            reasons.append("개별 성장주 상한 근접")
        if (
            str(position.get("asset_class")) == "미국 반도체/AI ETF"
            and current_weight >= 30
        ):
            reasons.append("반도체/AI 상한 근접")
        if bool(position.get("fx_error")):
            reasons.append("환율 오류")
        return reasons

    def _apply_allocation_caps(
        self,
        position: dict[str, Any],
        candidate: float,
        total_value: float,
        additional_investment: float,
    ) -> tuple[float, list[str]]:
        if candidate <= 0:
            return 0.0, []
        current_value = self._finite_float(position.get("market_value_krw"))
        if current_value is None or current_value < 0:
            return 0.0, ["평가금액 계산 불가"]
        post_total = total_value + additional_investment
        if post_total <= 0:
            return 0.0, ["포트폴리오 평가금액 계산 불가"]

        caps = [(MAX_SINGLE_POSITION_WEIGHT, "단일 종목 상한 점검")]
        asset_class = str(position.get("asset_class"))
        if asset_class == "개별 성장주":
            caps.append((MAX_INDIVIDUAL_GROWTH_WEIGHT, "개별 성장주 상한 점검"))
        if asset_class == "미국 반도체/AI ETF":
            caps.append((MAX_SEMICONDUCTOR_WEIGHT, "반도체/AI 상한 점검"))

        adjusted = candidate
        reasons = []
        for cap_weight, reason in caps:
            capacity = max(0.0, post_total * cap_weight / 100 - current_value)
            if adjusted > capacity:
                adjusted = capacity
                reasons.append(reason)
        return max(0.0, adjusted), reasons

    def _reliability(
        self, history: pd.DataFrame, returns: pd.Series
    ) -> tuple[str, str]:
        source = str(history.attrs.get("data_source") or "").upper()
        if history.empty or returns.empty:
            return "UNKNOWN", "가격 수익률 데이터가 부족합니다."
        if "SAMPLE" in source or "FALLBACK" in source:
            return "LOW", "SAMPLE/FALLBACK 데이터라 실제 시장과 다를 수 있습니다."
        if len(returns) < 120:
            return "MEDIUM", "외부 데이터이나 상관관계/위험 계산 기간이 짧습니다."
        return "HIGH", "외부 데이터 기반으로 위험 지표 계산 기간을 확보했습니다."

    def _risk_evaluation(self, gap: float | None, valid_count: int) -> str:
        if gap is None:
            return "데이터 부족"
        if valid_count <= 1:
            return "단일 종목이라 분산 효과 제한"
        if gap >= 10:
            return "비중 대비 위험 기여도 높음"
        if gap <= -10:
            return "비중 대비 위험 기여도 낮음"
        return "비중과 위험 기여도 유사"

    def _diversification_comment(self, average: float) -> str:
        if average >= 0.75:
            return "종목 간 상관관계가 높아 실제 분산 효과가 제한적입니다."
        if average <= 0.35:
            return "일부 자산은 낮은 상관관계를 보여 분산 효과가 있습니다."
        return "상관관계가 중간 수준이라 분산 효과를 추가 점검할 수 있습니다."

    def _rebalance_opinion(self, gap: float, tolerance: float) -> str:
        if gap > tolerance:
            return "목표 비중 대비 초과 구간입니다. 비중 조절 검토 대상입니다."
        if gap < -tolerance:
            return "목표 비중 대비 부족 구간입니다. 추가 배분 검토 대상입니다."
        return "허용 범위 안에 있어 유지 가능 구간입니다."

    def _summary_reliability(self, risk: pd.DataFrame) -> str:
        if risk.empty or "reliability" not in risk:
            return "UNKNOWN"
        values = set(risk["reliability"].astype(str))
        if "UNKNOWN" in values:
            return "UNKNOWN"
        if "LOW" in values:
            return "LOW"
        if "MEDIUM" in values:
            return "MEDIUM"
        return "HIGH"

    def _total_value(self, positions: list[dict[str, Any]]) -> float:
        return sum(
            self._score_float(position.get("market_value_krw"))
            for position in positions
            if self._finite_float(position.get("market_value_krw")) is not None
        )

    def _annualized_volatility(self, returns: pd.Series) -> float | None:
        if len(returns.dropna()) < 2:
            return None
        return self._finite_float(returns.std() * np.sqrt(252) * 100)

    def _position_key(self, position: dict[str, Any]) -> str:
        return f"{position.get('market', 'KR')}:{position.get('symbol', '')}"

    def _is_etf(self, position: dict[str, Any]) -> bool:
        text = f"{position.get('symbol', '')} {position.get('name', '')}".upper()
        return any(
            keyword in text
            for keyword in ["ETF", "TIGER", "KODEX", "ACE", "SOL", "RISE"]
        )

    def _finite_float(self, value: Any) -> float | None:
        try:
            result = float(value)
            if np.isnan(result) or np.isinf(result):
                return None
            return result
        except (TypeError, ValueError):
            return None

    def _score_float(self, value: Any, default: float = 0.0) -> float:
        result = self._finite_float(value)
        return default if result is None else result

    def _safe_tolerance(self, value: float) -> float:
        tolerance = self._score_float(value)
        return min(100.0, max(0.0, tolerance))

    def _round_optional(self, value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

    def _clean_row(self, row: dict[str, Any]) -> dict[str, Any]:
        cleaned = {}
        for key, value in row.items():
            if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
                cleaned[key] = None
            else:
                cleaned[key] = value
        return cleaned

    def _clean_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        cleaned = frame.replace([np.inf, -np.inf], np.nan).astype(object)
        return cleaned.where(pd.notna(cleaned), None)
