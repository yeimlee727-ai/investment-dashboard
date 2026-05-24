from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.broker.base import Broker, OrderRequest, OrderResult
from src.database import get_session
from src.data_providers.market_data_provider import MarketDataProvider
from src.models import RealizedPnlLog, VirtualOrder, VirtualPosition, utc_now
from src.risk.risk_engine import RiskEngine


class MockBroker(Broker):
    """Virtual broker that records simulated fills only."""

    def __init__(
        self,
        risk_engine: RiskEngine | None = None,
        data_provider: MarketDataProvider | None = None,
    ) -> None:
        self.risk_engine = risk_engine or RiskEngine()
        self.data_provider = data_provider or MarketDataProvider()

    def place_order(self, request: OrderRequest) -> OrderResult:
        side = request.side.upper()
        market = request.market.upper()
        with get_session() as session:
            if request.quantity <= 0:
                return self._record_rejected_order(
                    session, request, side, "가상 수량은 0보다 커야 합니다."
                )
            if request.price <= 0:
                return self._record_rejected_order(
                    session, request, side, "가상 가격은 0보다 커야 합니다."
                )
            if market not in {"KR", "US"}:
                return self._record_rejected_order(
                    session, request, side, "시장구분은 KR 또는 US만 지원합니다."
                )
            if side not in {"BUY", "SELL"}:
                return self._record_rejected_order(
                    session, request, side, "지원하지 않는 가상 주문 구분입니다."
                )

            position = session.execute(
                select(VirtualPosition).where(
                    VirtualPosition.symbol == request.symbol,
                    VirtualPosition.market == market,
                    VirtualPosition.is_open.is_(True),
                )
            ).scalar_one_or_none()
            exposure = (position.quantity * position.avg_price) if position else 0.0
            daily_realized_pnl = self._get_daily_realized_pnl(session)
            if side == "SELL" and (
                position is None or position.quantity < request.quantity
            ):
                return self._record_rejected_order(
                    session,
                    request,
                    side,
                    "보유 수량이 부족해 가상 매도를 처리할 수 없습니다.",
                )

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
                return self._record_rejected_order(
                    session, request, side, decision.reason
                )

            order = VirtualOrder(
                symbol=request.symbol,
                market=market,
                side=side,
                quantity=request.quantity,
                price=request.price,
                reason=request.reason,
                status="filled",
            )
            session.add(order)
            session.flush()

            if side == "BUY":
                self._apply_buy(session, request, position, market)
            else:
                self._apply_sell(session, request, position, market)

            return OrderResult(
                order.id,
                request.symbol,
                side,
                request.quantity,
                request.price,
                "filled",
                "가상 주문 처리 완료",
                order.created_at,
            )

    def get_positions(
        self, current_prices: dict[str, float] | None = None
    ) -> list[dict[str, float | int | str | None]]:
        current_prices = current_prices or {}
        with get_session() as session:
            positions = (
                session.execute(
                    select(VirtualPosition).where(VirtualPosition.is_open.is_(True))
                )
                .scalars()
                .all()
            )
            rows: list[dict[str, float | int | str | None]] = []
            for p in positions:
                price_key = f"{p.market}:{p.symbol}"
                override_price = current_prices.get(price_key) or current_prices.get(
                    p.symbol
                )
                quote_price, quote_error = (
                    (None, None)
                    if override_price is not None
                    else self._get_quote_price(p.symbol, p.market)
                )
                current_price = (
                    override_price if override_price is not None else quote_price
                )
                cost_basis = p.quantity * p.avg_price
                market_value = (
                    p.quantity * current_price if current_price is not None else None
                )
                unrealized_pnl = (
                    (current_price - p.avg_price) * p.quantity
                    if current_price is not None
                    else None
                )
                unrealized_return = (
                    (current_price / p.avg_price - 1) * 100
                    if current_price is not None and p.avg_price
                    else None
                )
                total_pnl = (
                    p.realized_pnl + unrealized_pnl
                    if unrealized_pnl is not None
                    else p.realized_pnl
                )
                total_pnl_pct = (
                    total_pnl / cost_basis * 100
                    if current_price is not None and cost_basis
                    else None
                )
                rows.append(
                    {
                        "market": p.market,
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "avg_price": round(p.avg_price, 2),
                        "current_price": (
                            round(current_price, 2)
                            if current_price is not None
                            else None
                        ),
                        "quote_error": quote_error,
                        "market_value": (
                            round(market_value, 2) if market_value is not None else None
                        ),
                        "cost_basis": round(cost_basis, 2),
                        "unrealized_pnl": (
                            round(unrealized_pnl, 2)
                            if unrealized_pnl is not None
                            else None
                        ),
                        "unrealized_pnl_pct": (
                            round(unrealized_return, 2)
                            if unrealized_return is not None
                            else None
                        ),
                        "unrealized_return": (
                            round(unrealized_return, 2)
                            if unrealized_return is not None
                            else None
                        ),
                        "realized_pnl": round(p.realized_pnl, 2),
                        "total_pnl": round(total_pnl, 2),
                        "total_pnl_pct": (
                            round(total_pnl_pct, 2)
                            if total_pnl_pct is not None
                            else None
                        ),
                        "position_weight": None,
                        "updated_at": p.updated_at,
                    }
                )
            total_market_value = sum(
                float(row["market_value"])
                for row in rows
                if row.get("market_value") is not None
            )
            for row in rows:
                market_value = row.get("market_value")
                row["position_weight"] = (
                    round(float(market_value) / total_market_value * 100, 2)
                    if market_value is not None and total_market_value
                    else None
                )
            return rows

    def get_portfolio_summary(
        self, current_prices: dict[str, float] | None = None
    ) -> dict[str, float | int | str | None]:
        positions = self.get_positions(current_prices=current_prices)
        valued_positions = [
            position
            for position in positions
            if position.get("market_value") is not None
            and position.get("unrealized_pnl") is not None
        ]
        total_market_value = sum(float(p["market_value"]) for p in valued_positions)
        total_cost_basis = sum(float(p["cost_basis"]) for p in positions)
        total_unrealized_pnl = sum(float(p["unrealized_pnl"]) for p in valued_positions)
        total_realized_pnl = sum(float(p["realized_pnl"]) for p in positions)
        total_pnl = total_unrealized_pnl + total_realized_pnl
        max_loss = min(
            valued_positions,
            key=lambda item: float(item.get("total_pnl") or 0),
            default=None,
        )
        max_profit = max(
            valued_positions,
            key=lambda item: float(item.get("total_pnl") or 0),
            default=None,
        )
        return {
            "total_market_value": round(total_market_value, 2),
            "total_cost_basis": round(total_cost_basis, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "total_unrealized_pnl_pct": (
                round(total_unrealized_pnl / total_cost_basis * 100, 2)
                if total_cost_basis
                else 0.0
            ),
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "position_count": len(positions),
            "cash_balance": None,
            "top1_weight": max(
                [
                    float(p["position_weight"])
                    for p in positions
                    if p["position_weight"]
                ],
                default=0.0,
            ),
            "max_loss_symbol": (
                f"{max_loss['market']}:{max_loss['symbol']}" if max_loss else ""
            ),
            "max_profit_symbol": (
                f"{max_profit['market']}:{max_profit['symbol']}" if max_profit else ""
            ),
            "quote_error_count": sum(1 for p in positions if p.get("quote_error")),
        }

    def get_order_logs(self) -> list[dict[str, float | int | str | datetime | None]]:
        with get_session() as session:
            orders = (
                session.execute(
                    select(VirtualOrder).order_by(VirtualOrder.created_at.desc())
                )
                .scalars()
                .all()
            )
            realized_logs = session.execute(select(RealizedPnlLog)).scalars().all()
            rows: list[dict[str, float | int | str | datetime | None]] = []
            for order in orders:
                realized_pnl = self._match_order_realized_pnl(order, realized_logs)
                rows.append(
                    {
                        "created_at": order.created_at,
                        "market": order.market,
                        "symbol": order.symbol,
                        "side": order.side,
                        "quantity": order.quantity,
                        "price": order.price,
                        "status": order.status,
                        "reason": order.reason,
                        "realized_pnl": realized_pnl,
                        "error_message": (
                            order.reason if order.status == "rejected" else ""
                        ),
                    }
                )
            return rows

    def get_realized_pnl_logs(
        self,
    ) -> list[dict[str, float | int | str | datetime | None]]:
        with get_session() as session:
            logs = (
                session.execute(
                    select(RealizedPnlLog).order_by(RealizedPnlLog.created_at.desc())
                )
                .scalars()
                .all()
            )
            return [
                {
                    "realized_at": log.created_at,
                    "market": log.market,
                    "symbol": log.symbol,
                    "quantity": log.quantity,
                    "entry_price": log.entry_price,
                    "avg_price": log.entry_price,
                    "exit_price": log.exit_price,
                    "realized_pnl": round(log.realized_pnl, 2),
                    "realized_pnl_pct": (
                        round((log.exit_price / log.entry_price - 1) * 100, 2)
                        if log.entry_price
                        else None
                    ),
                    "holding_days": None,
                    "reason": "가상 매도 실현손익",
                    "exit_reason": "가상 매도",
                }
                for log in logs
            ]

    def _apply_buy(
        self,
        session: Session,
        request: OrderRequest,
        position: VirtualPosition | None,
        market: str,
    ) -> None:
        if position is None:
            session.add(
                VirtualPosition(
                    symbol=request.symbol,
                    market=market,
                    quantity=request.quantity,
                    avg_price=request.price,
                )
            )
            return
        total_cost = (
            position.quantity * position.avg_price + request.quantity * request.price
        )
        position.quantity += request.quantity
        position.avg_price = total_cost / position.quantity
        position.updated_at = utc_now()

    def _apply_sell(
        self,
        session: Session,
        request: OrderRequest,
        position: VirtualPosition | None,
        market: str,
    ) -> None:
        if position is None:
            return
        realized = (request.price - position.avg_price) * request.quantity
        position.realized_pnl += realized
        position.quantity -= request.quantity
        position.is_open = position.quantity > 0
        position.updated_at = utc_now()
        session.add(
            RealizedPnlLog(
                symbol=request.symbol,
                market=market,
                quantity=request.quantity,
                entry_price=position.avg_price,
                exit_price=request.price,
                realized_pnl=realized,
            )
        )

    def _record_rejected_order(
        self, session: Session, request: OrderRequest, side: str, message: str
    ) -> OrderResult:
        order = VirtualOrder(
            symbol=request.symbol,
            market=request.market.upper(),
            side=side,
            quantity=request.quantity,
            price=request.price,
            status="rejected",
            reason=f"{request.reason} | {message}" if request.reason else message,
        )
        session.add(order)
        session.flush()
        return OrderResult(
            order.id,
            request.symbol,
            side,
            request.quantity,
            request.price,
            "rejected",
            message,
            order.created_at,
        )

    def _get_quote_price(
        self, symbol: str, market: str
    ) -> tuple[float | None, str | None]:
        try:
            if hasattr(self.data_provider, "get_latest_quote"):
                quote_obj = self.data_provider.get_latest_quote(
                    symbol=symbol, market=market
                )
                if quote_obj.price is None:
                    return None, quote_obj.error or "현재가 조회 실패"
                return float(quote_obj.price), quote_obj.error
            quote = self.data_provider.get_quote(symbol=symbol, market=market)
            price = quote.get("price")
            if price is None:
                return None, str(quote.get("error") or "현재가 조회 실패")
            return float(price), None
        except Exception as exc:
            return None, f"현재가 조회 실패: {exc}"

    def _get_daily_realized_pnl(self, session: Session) -> float:
        seoul_now = datetime.now(ZoneInfo("Asia/Seoul"))
        seoul_today_start = datetime.combine(
            seoul_now.date(), time.min, tzinfo=ZoneInfo("Asia/Seoul")
        )
        utc_start = seoul_today_start.astimezone(timezone.utc).replace(tzinfo=None)
        logs = (
            session.execute(
                select(RealizedPnlLog).where(RealizedPnlLog.created_at >= utc_start)
            )
            .scalars()
            .all()
        )
        return float(sum(log.realized_pnl for log in logs))

    def get_daily_realized_pnl(self) -> float:
        with get_session() as session:
            return self._get_daily_realized_pnl(session)

    def _match_order_realized_pnl(
        self, order: VirtualOrder, logs: list[RealizedPnlLog]
    ) -> float | None:
        if order.side != "SELL" or order.status != "filled":
            return None
        candidates = [
            log
            for log in logs
            if log.symbol == order.symbol
            and log.market == order.market
            and log.quantity == order.quantity
            and log.exit_price == order.price
        ]
        if not candidates:
            return None
        return round(candidates[-1].realized_pnl, 2)
