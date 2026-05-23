from __future__ import annotations

from datetime import datetime
from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.broker.base import Broker, OrderRequest, OrderResult
from src.database import get_session
from src.data_providers.market_data_provider import MarketDataProvider
from src.models import VirtualOrder, VirtualPosition
from src.risk.risk_engine import RiskEngine


class MockBroker(Broker):
    """Virtual broker that records simulated fills only."""

    def __init__(self, risk_engine: RiskEngine | None = None, data_provider: MarketDataProvider | None = None) -> None:
        self.risk_engine = risk_engine or RiskEngine()
        self.data_provider = data_provider or MarketDataProvider()

    def place_order(self, request: OrderRequest) -> OrderResult:
        side = request.side.upper()
        with get_session() as session:
            position = session.execute(
                select(VirtualPosition).where(VirtualPosition.symbol == request.symbol, VirtualPosition.is_open.is_(True))
            ).scalar_one_or_none()
            exposure = (position.quantity * position.avg_price) if position else 0.0
            daily_realized_pnl = self._get_daily_realized_pnl(session)
            decision = self.risk_engine.validate_order(
                symbol=request.symbol,
                side=side,
                quantity=request.quantity,
                price=request.price,
                current_symbol_exposure=exposure,
                current_daily_pnl=daily_realized_pnl,
                has_open_position=position is not None,
            )
            if not decision.allowed:
                return OrderResult(None, request.symbol, side, request.quantity, request.price, "rejected", decision.reason, datetime.utcnow())

            order = VirtualOrder(symbol=request.symbol, side=side, quantity=request.quantity, price=request.price, reason=request.reason)
            session.add(order)
            session.flush()

            if side == "BUY":
                self._apply_buy(session, request, position)
            elif side == "SELL":
                self._apply_sell(session, request, position)
            else:
                return OrderResult(order.id, request.symbol, side, request.quantity, request.price, "rejected", "지원하지 않는 주문 방향입니다.", datetime.utcnow())

            return OrderResult(order.id, request.symbol, side, request.quantity, request.price, "filled", "가상 체결 완료", order.created_at)

    def get_positions(self, current_prices: dict[str, float] | None = None) -> list[dict[str, float | int | str]]:
        current_prices = current_prices or {}
        with get_session() as session:
            positions = session.execute(select(VirtualPosition).where(VirtualPosition.is_open.is_(True))).scalars().all()
            rows: list[dict[str, float | int | str]] = []
            for p in positions:
                current_price = current_prices.get(p.symbol) or self._get_quote_price(p.symbol)
                market_value = p.quantity * current_price
                unrealized_pnl = (current_price - p.avg_price) * p.quantity
                unrealized_return = (current_price / p.avg_price - 1) * 100 if p.avg_price else 0.0
                total_pnl = p.realized_pnl + unrealized_pnl
                rows.append(
                    {
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "avg_price": round(p.avg_price, 2),
                        "current_price": round(current_price, 2),
                        "market_value": round(market_value, 2),
                        "unrealized_pnl": round(unrealized_pnl, 2),
                        "unrealized_return": round(unrealized_return, 2),
                        "realized_pnl": round(p.realized_pnl, 2),
                        "total_pnl": round(total_pnl, 2),
                    }
                )
            return rows

    def _apply_buy(self, session: Session, request: OrderRequest, position: VirtualPosition | None) -> None:
        if position is None:
            session.add(VirtualPosition(symbol=request.symbol, quantity=request.quantity, avg_price=request.price))
            return
        total_cost = position.quantity * position.avg_price + request.quantity * request.price
        position.quantity += request.quantity
        position.avg_price = total_cost / position.quantity
        position.updated_at = datetime.utcnow()

    def _apply_sell(self, session: Session, request: OrderRequest, position: VirtualPosition | None) -> None:
        if position is None or position.quantity < request.quantity:
            raise ValueError("보유 수량이 부족합니다.")
        realized = (request.price - position.avg_price) * request.quantity
        position.realized_pnl += realized
        position.quantity -= request.quantity
        position.is_open = position.quantity > 0
        position.updated_at = datetime.utcnow()

    def _get_quote_price(self, symbol: str) -> float:
        try:
            quote = self.data_provider.get_quote(symbol=symbol, market="KR")
            return float(quote["price"])
        except Exception:
            return 0.0

    def _get_daily_realized_pnl(self, session: Session) -> float:
        today_start = datetime.combine(datetime.utcnow().date(), time.min)
        positions = session.execute(select(VirtualPosition).where(VirtualPosition.updated_at >= today_start)).scalars().all()
        return float(sum(position.realized_pnl for position in positions))
