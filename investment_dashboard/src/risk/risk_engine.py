from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RiskConfig:
    max_order_amount: float = 1_000_000
    max_symbol_exposure: float = 3_000_000
    daily_loss_limit: float = 500_000
    prevent_duplicate_entry: bool = True
    emergency_stop: bool = False


@dataclass
class RiskDecision:
    allowed: bool
    reason: str


class RiskEngine:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def validate_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        current_symbol_exposure: float = 0.0,
        current_daily_pnl: float = 0.0,
        has_open_position: bool = False,
    ) -> RiskDecision:
        if self.config.emergency_stop:
            return RiskDecision(False, "비상정지 플래그가 켜져 있습니다.")
        if quantity <= 0 or price <= 0:
            return RiskDecision(False, "수량과 가격은 0보다 커야 합니다.")
        order_amount = quantity * price
        if order_amount > self.config.max_order_amount:
            return RiskDecision(False, f"1회 주문 한도 초과: {order_amount:,.0f}")
        if side.upper() == "BUY":
            if current_symbol_exposure + order_amount > self.config.max_symbol_exposure:
                return RiskDecision(False, "종목당 투자 한도를 초과합니다.")
            if self.config.prevent_duplicate_entry and has_open_position:
                return RiskDecision(False, "동일 종목 중복 진입이 차단되었습니다.")
        if current_daily_pnl <= -abs(self.config.daily_loss_limit):
            return RiskDecision(False, "일 손실 한도에 도달했습니다.")
        return RiskDecision(True, "허용")

    def daily_loss_usage_pct(self, current_daily_pnl: float) -> float:
        limit = abs(self.config.daily_loss_limit)
        if limit <= 0:
            return 100.0 if current_daily_pnl < 0 else 0.0
        loss = max(0.0, -current_daily_pnl)
        return min(100.0, round(loss / limit * 100, 2))

    def portfolio_risk_metrics(
        self,
        positions: list[dict[str, Any]],
        current_daily_pnl: float = 0.0,
    ) -> dict[str, float | int]:
        valued_positions = [
            position
            for position in positions
            if position.get("market_value") is not None
        ]
        total_market_value = sum(
            float(position["market_value"]) for position in valued_positions
        )
        weights = (
            sorted(
                [
                    float(position["market_value"]) / total_market_value * 100
                    for position in valued_positions
                ],
                reverse=True,
            )
            if total_market_value
            else []
        )
        unrealized_values = [
            float(position["unrealized_pnl"])
            for position in positions
            if position.get("unrealized_pnl") is not None
        ]
        return {
            "top1_weight": round(weights[0], 2) if weights else 0.0,
            "top3_weight": round(sum(weights[:3]), 2) if weights else 0.0,
            "loss_position_count": sum(1 for value in unrealized_values if value < 0),
            "profit_position_count": sum(1 for value in unrealized_values if value > 0),
            "unrealized_loss_total": round(
                sum(value for value in unrealized_values if value < 0), 2
            ),
            "unrealized_profit_total": round(
                sum(value for value in unrealized_values if value > 0), 2
            ),
            "daily_realized_pnl": round(current_daily_pnl, 2),
            "daily_loss_usage_pct": self.daily_loss_usage_pct(current_daily_pnl),
        }
