from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.broker.base import Broker, OrderRequest, OrderResult
from src.database import get_session
from src.data_providers.market_data_provider import MarketDataProvider
from src.models import (
    RealizedPnlLog,
    VirtualOrder,
    VirtualPosition,
    WatchlistItem,
    utc_now,
)
from src.risk.risk_engine import RiskEngine

PortfolioImportRow = dict[str, float | int | str | None]
PortfolioImportResult = dict[str, object]


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
        self,
        current_prices: dict[str, float] | None = None,
        manual_fx_rate: float | None = None,
    ) -> list[dict[str, float | int | str | datetime | None]]:
        current_prices = current_prices or {}
        fx_rate, fx_source, fx_error, fx_as_of = self._get_usd_krw_fx(manual_fx_rate)
        with get_session() as session:
            positions = (
                session.execute(
                    select(VirtualPosition).where(VirtualPosition.is_open.is_(True))
                )
                .scalars()
                .all()
            )
            rows: list[dict[str, float | int | str | datetime | None]] = []
            name_map = self._position_name_map(session)
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
                currency = "KRW" if p.market == "KR" else "USD"
                position_fx_rate = 1.0 if p.market == "KR" else fx_rate
                position_fx_source = "KRW" if p.market == "KR" else fx_source
                position_fx_error = None if p.market == "KR" else fx_error
                market_value_krw = self._to_krw(market_value, position_fx_rate)
                cost_basis_krw = self._to_krw(cost_basis, position_fx_rate)
                unrealized_pnl_krw = self._to_krw(unrealized_pnl, position_fx_rate)
                realized_pnl_krw = self._to_krw(p.realized_pnl, position_fx_rate)
                total_pnl_krw = self._to_krw(total_pnl, position_fx_rate)
                rows.append(
                    {
                        "market": p.market,
                        "symbol": p.symbol,
                        "name": name_map.get((p.market, p.symbol), p.symbol),
                        "currency": currency,
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
                        "fx_rate": (
                            round(position_fx_rate, 4)
                            if position_fx_rate is not None
                            else None
                        ),
                        "market_value_krw": self._round_optional(market_value_krw),
                        "cost_basis_krw": self._round_optional(cost_basis_krw),
                        "unrealized_pnl_krw": self._round_optional(unrealized_pnl_krw),
                        "realized_pnl_krw": self._round_optional(realized_pnl_krw),
                        "total_pnl_krw": self._round_optional(total_pnl_krw),
                        "position_weight_krw": None,
                        "fx_data_source": position_fx_source,
                        "fx_error": position_fx_error,
                        "fx_as_of": fx_as_of if p.market == "US" else None,
                        "updated_at": p.updated_at,
                    }
                )
            total_market_value_krw = sum(
                float(row["market_value_krw"])
                for row in rows
                if row.get("market_value_krw") is not None
            )
            for row in rows:
                market_value_krw = row.get("market_value_krw")
                row["position_weight_krw"] = (
                    round(float(market_value_krw) / total_market_value_krw * 100, 2)
                    if market_value_krw is not None and total_market_value_krw
                    else None
                )
                row["position_weight"] = row["position_weight_krw"]
            return rows

    def get_portfolio_summary(
        self,
        current_prices: dict[str, float] | None = None,
        manual_fx_rate: float | None = None,
    ) -> dict[str, float | int | str | None]:
        positions = self.get_positions(
            current_prices=current_prices, manual_fx_rate=manual_fx_rate
        )
        valued_positions = [
            position
            for position in positions
            if position.get("market_value_krw") is not None
            and position.get("unrealized_pnl_krw") is not None
        ]
        total_market_value = sum(float(p["market_value_krw"]) for p in valued_positions)
        valued_cost_basis = sum(
            float(p["cost_basis_krw"])
            for p in valued_positions
            if p.get("cost_basis_krw") is not None
        )
        total_unrealized_pnl = sum(
            float(p["unrealized_pnl_krw"]) for p in valued_positions
        )
        total_realized_pnl = sum(
            float(p["realized_pnl_krw"])
            for p in positions
            if p.get("realized_pnl_krw") is not None
        )
        total_pnl = total_unrealized_pnl + total_realized_pnl
        max_loss = min(
            valued_positions,
            key=lambda item: float(item.get("total_pnl_krw") or 0),
            default=None,
        )
        max_profit = max(
            valued_positions,
            key=lambda item: float(item.get("total_pnl_krw") or 0),
            default=None,
        )
        fx_rows = [p for p in positions if p.get("market") == "US"]
        fx_errors = [str(p["fx_error"]) for p in fx_rows if p.get("fx_error")]
        if fx_rows:
            fx_rate = next(
                (p.get("fx_rate") for p in fx_rows if p.get("fx_rate")), None
            )
            fx_source = next(
                (p.get("fx_data_source") for p in fx_rows if p.get("fx_data_source")),
                "",
            )
        else:
            fx_rate, fx_source, _, _ = self._get_usd_krw_fx(manual_fx_rate)
        return {
            "total_market_value": round(total_market_value, 2),
            "total_market_value_krw": round(total_market_value, 2),
            "total_cost_basis": round(valued_cost_basis, 2),
            "total_cost_basis_krw": round(valued_cost_basis, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "total_unrealized_pnl_krw": round(total_unrealized_pnl, 2),
            "total_unrealized_pnl_pct": (
                round(total_unrealized_pnl / valued_cost_basis * 100, 2)
                if valued_cost_basis
                else 0.0
            ),
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_realized_pnl_krw": round(total_realized_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_krw": round(total_pnl, 2),
            "position_count": len(positions),
            "cash_balance": None,
            "top1_weight": max(
                [
                    float(p["position_weight_krw"])
                    for p in positions
                    if p.get("position_weight_krw")
                ],
                default=0.0,
            ),
            "top1_weight_krw": max(
                [
                    float(p["position_weight_krw"])
                    for p in positions
                    if p.get("position_weight_krw")
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
            "fx_rate": fx_rate,
            "fx_data_source": fx_source,
            "fx_error_count": len(fx_errors),
            "fx_error": "; ".join(fx_errors),
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

    def delete_position(
        self,
        symbol: str,
        market: str,
        delete_orders: bool = False,
        delete_realized_pnl: bool = False,
    ) -> dict[str, int | str | bool]:
        symbol = symbol.upper().strip()
        market = market.upper().strip()
        if not symbol or market not in {"KR", "US"}:
            return {
                "success": False,
                "message": "삭제 대상 종목코드 또는 시장구분이 올바르지 않습니다.",
                "deleted_positions": 0,
                "deleted_orders": 0,
                "deleted_realized_pnl": 0,
            }
        with get_session() as session:
            position_result = session.execute(
                delete(VirtualPosition).where(
                    VirtualPosition.symbol == symbol,
                    VirtualPosition.market == market,
                )
            )
            deleted_positions = int(position_result.rowcount or 0)
            deleted_orders = 0
            deleted_realized = 0
            if delete_orders:
                order_result = session.execute(
                    delete(VirtualOrder).where(
                        VirtualOrder.symbol == symbol,
                        VirtualOrder.market == market,
                    )
                )
                deleted_orders = int(order_result.rowcount or 0)
            if delete_realized_pnl:
                realized_result = session.execute(
                    delete(RealizedPnlLog).where(
                        RealizedPnlLog.symbol == symbol,
                        RealizedPnlLog.market == market,
                    )
                )
                deleted_realized = int(realized_result.rowcount or 0)
            return {
                "success": deleted_positions > 0,
                "message": (
                    "MockBroker 로컬 포지션 데이터를 삭제했습니다."
                    if deleted_positions
                    else "삭제할 MockBroker 포지션을 찾지 못했습니다."
                ),
                "deleted_positions": deleted_positions,
                "deleted_orders": deleted_orders,
                "deleted_realized_pnl": deleted_realized,
            }

    def import_positions(
        self,
        rows: list[PortfolioImportRow],
        mode: str = "upsert",
    ) -> PortfolioImportResult:
        """Import virtual positions without creating simulated order logs."""

        if mode not in {"upsert", "overwrite_existing", "replace"}:
            return {
                "mode": mode,
                "added": 0,
                "updated": 0,
                "skipped": len(rows),
                "failed": 0,
                "current_position_count": self._count_positions(),
                "applied_at": datetime.now().isoformat(timespec="seconds"),
                "details": [],
                "message": "지원하지 않는 반영 방식입니다.",
            }

        added = updated = skipped = failed = 0
        details: list[dict[str, object]] = []
        with get_session() as session:
            if mode == "replace":
                session.execute(delete(VirtualPosition))

            for row in rows:
                symbol = str(row.get("symbol", "")).upper().strip()
                market = str(row.get("market", "")).upper().strip()
                quantity = self._positive_int(row.get("quantity"))
                avg_price = self._positive_float(row.get("avg_price"))
                if (
                    not symbol
                    or market not in {"KR", "US"}
                    or not quantity
                    or not avg_price
                ):
                    failed += 1
                    details.append(
                        self._import_detail(
                            row=row,
                            result="오류 제외",
                            reason="종목코드, 시장구분, 수량, 평균단가 중 유효하지 않은 값이 있습니다.",
                        )
                    )
                    continue

                position = session.execute(
                    select(VirtualPosition).where(
                        VirtualPosition.symbol == symbol,
                        VirtualPosition.market == market,
                    )
                ).scalar_one_or_none()

                if mode == "overwrite_existing" and position is None:
                    skipped += 1
                    details.append(
                        self._import_detail(
                            row=row,
                            result="건너뜀",
                            reason="기존 동일 market+symbol 가상 포지션이 없습니다.",
                            new_quantity=quantity,
                            new_avg_price=avg_price,
                        )
                    )
                    continue

                if position is None:
                    session.add(
                        VirtualPosition(
                            symbol=symbol,
                            market=market,
                            quantity=quantity,
                            avg_price=avg_price,
                            realized_pnl=0.0,
                            is_open=True,
                        )
                    )
                    added += 1
                    details.append(
                        self._import_detail(
                            row=row,
                            result="신규 추가",
                            reason="MockBroker 가상 포지션 신규 등록",
                            new_quantity=quantity,
                            new_avg_price=avg_price,
                        )
                    )
                    continue

                previous_quantity = position.quantity
                previous_avg_price = position.avg_price
                position.quantity = quantity
                position.avg_price = avg_price
                position.realized_pnl = 0.0
                position.is_open = True
                position.updated_at = utc_now()
                updated += 1
                details.append(
                    self._import_detail(
                        row=row,
                        result="업데이트",
                        reason="기존 MockBroker 가상 포지션을 업로드 값으로 갱신",
                        previous_quantity=previous_quantity,
                        new_quantity=quantity,
                        previous_avg_price=previous_avg_price,
                        new_avg_price=avg_price,
                    )
                )

            session.flush()
            current_position_count = self._count_positions(session)

        return {
            "mode": mode,
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "current_position_count": current_position_count,
            "applied_at": datetime.now().isoformat(timespec="seconds"),
            "details": details,
            "message": "MockBroker 가상 포지션 일괄 반영을 완료했습니다.",
        }

    def _import_detail(
        self,
        row: PortfolioImportRow,
        result: str,
        reason: str,
        previous_quantity: int | None = None,
        new_quantity: int | None = None,
        previous_avg_price: float | None = None,
        new_avg_price: float | None = None,
    ) -> dict[str, object]:
        return {
            "market": str(row.get("market", "")).upper().strip(),
            "symbol": str(row.get("symbol", "")).upper().strip(),
            "name": row.get("name") or "",
            "result": result,
            "previous_quantity": previous_quantity,
            "new_quantity": new_quantity,
            "previous_avg_price": previous_avg_price,
            "new_avg_price": new_avg_price,
            "reason": reason,
        }

    def _count_positions(self, session: Session | None = None) -> int:
        if session is not None:
            return len(
                session.execute(
                    select(VirtualPosition).where(VirtualPosition.is_open.is_(True))
                )
                .scalars()
                .all()
            )
        with get_session() as new_session:
            return self._count_positions(new_session)

    def _position_name_map(self, session: Session) -> dict[tuple[str, str], str]:
        items = session.execute(select(WatchlistItem)).scalars().all()
        return {
            (str(item.market).upper(), str(item.symbol).upper()): item.name
            for item in items
            if item.name
        }

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

    def _get_usd_krw_fx(
        self, manual_fx_rate: float | None = None
    ) -> tuple[float | None, str, str | None, str | datetime | None]:
        if manual_fx_rate is not None and manual_fx_rate > 0:
            return (
                manual_fx_rate,
                "MANUAL",
                None,
                datetime.now().isoformat(timespec="seconds"),
            )
        try:
            if hasattr(self.data_provider, "get_fx_rate"):
                fx = self.data_provider.get_fx_rate("USD/KRW")
                return fx.rate, fx.data_source, fx.error, fx.as_of
            return (
                None,
                "FX_UNAVAILABLE",
                "환율 조회를 지원하지 않는 provider입니다.",
                None,
            )
        except Exception as exc:
            return None, "FX_ERROR", f"환율 조회 실패: {exc}", None

    def _to_krw(self, value: float | None, fx_rate: float | None) -> float | None:
        if value is None or fx_rate is None:
            return None
        return value * fx_rate

    def _positive_int(self, value: object) -> int | None:
        try:
            number = int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    def _positive_float(self, value: object) -> float | None:
        try:
            number = float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    def _round_optional(self, value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

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
